import re
import urllib.parse
import traceback
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from google import genai
from google.genai import types

from app.config import settings
from app.models import Concert, Venue, ArtistPreference
from app.services.config_manager import load_user_config
from app.services.rss import find_or_create_venue
from app.services.scoring import score_concert
from app.services.discovery import HEADERS
from app.services import discovery

# ─── Gemini helpers ───────────────────────────────────────────────────────────

def clean_html_for_gemini(html_content: str) -> str:
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    # Verwijder absoluut irrelevante tags om tokens te besparen en ruis te verminderen
    for tag in soup(["script", "style", "head", "meta", "footer", "nav", "svg", "noscript", "iframe", "header"]):
        tag.decompose()
        
    # Smart repeat reduction using tag grouping.
    # Dit zorgt ervoor dat extreem lange agenda's (zoals 250+ concerten op één pagina) 
    # worden gereduceerd tot maximaal 5 representatieve elementen per layout-type.
    # Hierdoor past de volledige pagina-structuur gegarandeerd binnen de token-limiet.
    tags_by_class = {}
    for tag in soup.find_all(True):
        classes = tag.get("class")
        if classes:
            class_str = " ".join(sorted(classes))
            tags_by_class.setdefault(class_str, []).append(tag)
            
    for class_str, tags in tags_by_class.items():
        if len(tags) > 8:
            for tag in tags[5:]:
                try:
                    tag.decompose()
                except Exception:
                    pass

    # Neem de eerste 80.000 tekens van de super compacte, representatieve HTML structuur
    return str(soup)[:80000]


def execute_scraper_code(code: str, html: str) -> List[Dict[str, Any]]:
    """Voert gegenereerde Python scraper-code uit in een sandbox."""
    compiled_code = compile(code, "<custom_scraper>", "exec")

    sandbox_globals = {
        "BeautifulSoup": BeautifulSoup,
        "urllib": urllib.parse,
        "re": re,
        "datetime": datetime,
        "print": print,
    }
    exec(compiled_code, sandbox_globals, sandbox_globals)

    if "scrape" not in sandbox_globals:
        raise ValueError("Het script definieert geen 'scrape(html)' functie.")

    results = sandbox_globals["scrape"](html)

    if not isinstance(results, list):
        raise ValueError(f"De 'scrape' functie gaf een {type(results)} in plaats van een list.")

    validated_results = []
    for item in results:
        if not isinstance(item, dict):
            continue
        artist = item.get("artist")
        date_str = item.get("date")
        venue = item.get("venue")

        if not artist or not date_str or not venue:
            continue

        validated_results.append({
            "artist": str(artist).strip(),
            "date": str(date_str).strip(),
            "venue": str(venue).strip(),
            "price": float(item["price"]) if item.get("price") is not None else None,
            "url": str(item["url"]).strip() if item.get("url") else None
        })

    return validated_results


def _get_gemini_client():
    user_config = load_user_config()
    api_key = user_config.get("gemini_api_key") or settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("Gemini API Key ontbreekt in config.json of .env.")
    return genai.Client(api_key=api_key)


def generate_scraper_code(name: str, url: str, html: str) -> str:
    """Vraagt Gemini om een BeautifulSoup scraper te genereren."""
    client = _get_gemini_client()
    cleaned_html = clean_html_for_gemini(html)

    prompt = f"""
    Je bent een expert Python scraper ontwikkelaar. Schrijf een Python functie `scrape(html: str) -> list[dict]` die concerten/programma-items extraheert uit de HTML van de website '{name}' ({url}).
    
    Hier is een representatief deel van de HTML van de pagina:
    ```html
    {cleaned_html}
    ```
    
    Je functie MOET aan de volgende eisen voldoen:
    1. Gebruik `BeautifulSoup` om de HTML te parsen.
    2. Haal alle concerten/optredens op. Elk concert moet een dict zijn met:
       - 'artist': de naam van de artiest/band (verplicht, string).
       - 'date': de datum in 'YYYY-MM-DD' formaat (verplicht, string). Vertaal Nederlandse datums (bijv. '12 mei', 'zaterdag 5 juni') naar YYYY-MM-DD. Aangezien we in 2026 leven, mag je ervan uitgaan dat datums in de toekomst liggen (2026 of begin 2027).
       - 'venue': de naam van het podium/theater (altijd '{name}', verplicht, string).
       - 'price': de ticketprijs als float (bijv. 29.50) of None indien niet vermeld of gratis.
       - 'url': de absolute ticket/info URL (gebruik `urllib.parse.urljoin('{url}', link)` om relatieve links absoluut te maken) of None.
    3. Retourneer een list van deze dicts.
    4. Schrijf robuuste code die fouten in individuele elementen opvangt (met try/except) zodat de hele functie niet faalt als één concert een afwijkende layout heeft.
    
    Geef ALTIJD en UITSLUITEND de rauwe Python code terug. Geen markdown blocks zoals ```python, geen inleiding, geen uitleg. Gewoon direct de code.
    """

    response = client.models.generate_content(
        model='gemini-flash-lite-latest',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1)
    )

    code = response.text.strip()
    if code.startswith("```python"):
        code = code.split("```python")[1].split("```")[0].strip()
    elif code.startswith("```"):
        code = code.split("```")[1].split("```")[0].strip()

    return code


def heal_scraper_code(venue: Venue, html: str, error_msg: str) -> str:
    """Vraagt Gemini om een falend script te repareren."""
    client = _get_gemini_client()
    cleaned_html = clean_html_for_gemini(html)

    prompt = f"""
    Je bent een expert Python scraper ontwikkelaar. Een door jou gegenereerd scraper-script voor '{venue.name}' ({venue.scraper_url}) is gefaald of heeft 0 resultaten opgeleverd.
    
    De foutmelding/reden is:
    ```
    {error_msg}
    ```
    
    Hier is de huidige Python code van het script dat faalt:
    ```python
    {venue.scraper_code}
    ```
    
    Hier is een actueel deel van de HTML van de pagina:
    ```html
    {cleaned_html}
    ```
    
    Pas de BeautifulSoup selector(s) of datum-parsing logica aan zodat het script weer correct werkt.
    Volg dezelfde regels:
    1. Functie moet `scrape(html: str) -> list[dict]` heten.
    2. Velden: 'artist', 'date', 'venue' (moet '{venue.name}' zijn), 'price', 'url'.
    3. Maak links absoluut met `urllib.parse.urljoin('{venue.scraper_url}', link)`
    
    Geef ALTIJD en UITSLUITEND de rauwe Python code terug. Geen markdown blocks zoals ```python, geen inleiding, geen uitleg. Gewoon direct de code.
    """

    response = client.models.generate_content(
        model='gemini-flash-lite-latest',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1)
    )

    code = response.text.strip()
    if code.startswith("```python"):
        code = code.split("```python")[1].split("```")[0].strip()
    elif code.startswith("```"):
        code = code.split("```")[1].split("```")[0].strip()

    return code


# ─── Core scraper run ─────────────────────────────────────────────────────────

STRATEGY_LABELS = {
    "rss": "RSS Feed",
    "jsonld": "JSON-LD",
    "wordpress": "WordPress API",
    "embedded_json": "Embedded JSON",
    "html_gemini": "HTML + Gemini",
}


def _purge_garbage_concerts(db: Session, venue: Venue) -> int:
    """
    Verwijdert automatisch concerten van dit podium waarvan de artiestennaam
    duidelijk een UI-label of navigatietekst is (bijv. 'wachtlijst', 'speeldata').
    Wordt aangeroepen na elke succesvolle scraper-run om stale rommel op te ruimen.
    """
    source_prefix = f"scraper_{venue.name.lower().replace(' ', '_')}"
    concerts = db.query(Concert).filter(
        Concert.venue_id == venue.id,
        Concert.source.like(f"{source_prefix}%")
    ).all()

    removed = 0
    for concert in concerts:
        if discovery.is_garbage_artist(concert.artist):
            print(f"[Scraper Manager] Garbage concert verwijderd: '{concert.artist}' ({venue.name})")
            db.delete(concert)
            removed += 1

    if removed:
        db.commit()
        print(f"[Scraper Manager] {removed} garbage concert(en) verwijderd voor '{venue.name}'")

    return removed


def _save_concerts(db: Session, venue: Venue, events: list[dict]) -> List[Concert]:
    """Slaat een lijst van genormaliseerde event-dicts op als Concert-rijen."""
    user_config = load_user_config()
    top_artists = db.query(ArtistPreference).filter(ArtistPreference.source == "top_artist").all()
    top_genres_freq = {}
    for ta in top_artists:
        if ta.genres:
            for genre in ta.genres:
                top_genres_freq[genre.lower()] = top_genres_freq.get(genre.lower(), 0) + ta.user_score

    import datetime as dt_mod

    added_concerts = []
    for item in events:
        venue_obj = find_or_create_venue(db, item.get("venue") or venue.name)
        if not venue_obj:
            venue_obj = venue

        try:
            date_str = item["date"]
            if "T" in date_str:
                concert_date = datetime.fromisoformat(date_str)
            else:
                concert_date = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            concert_date = datetime.now()

        start_of_day = datetime(concert_date.year, concert_date.month, concert_date.day)
        end_of_day = start_of_day + dt_mod.timedelta(days=1)

        exists = db.query(Concert).filter(
            Concert.artist.ilike(item["artist"]),
            Concert.venue_id == venue_obj.id,
            Concert.date >= start_of_day,
            Concert.date < end_of_day
        ).first()

        if not exists:
            new_concert = Concert(
                artist=item["artist"],
                venue_id=venue_obj.id,
                date=concert_date,
                price=item.get("price"),
                url=item.get("url"),
                source=f"scraper_{venue.name.lower().replace(' ', '_')}",
                status="new"
            )
            db.add(new_concert)
            db.commit()
            db.refresh(new_concert)

            score = score_concert(db, new_concert, top_genres_freq, user_config, allow_spotify_lookup=False)
            new_concert.calculated_score = score
            db.commit()
            db.refresh(new_concert)

            added_concerts.append(new_concert)

    return added_concerts


def run_custom_scraper(db: Session, venue: Venue, force_heal: bool = False) -> List[Concert]:
    """
    Haalt events op voor een podium. Gebruikt de opgeslagen strategie als die beschikbaar is,
    anders voert eerst discovery uit.

    Volgorde:
      1. Opgeslagen strategie uitvoeren (jsonld / wordpress / embedded_json)
      2. Als geen strategie → discovery uitvoeren en opslaan
      3. Bij html_gemini: Gemini BeautifulSoup code gebruiken / genereren
    """
    print(f"[Scraper Manager] Start scraper '{venue.name}' ({venue.scraper_url})...")

    strategy = venue.scraper_strategy
    config = venue.scraper_config or {}

    # ── Stap A: Run opgeslagen niet-Gemini strategie direct ───────────────
    if strategy and strategy != "html_gemini" and not force_heal:
        try:
            events = discovery.run_strategy(venue.name, venue.scraper_url, strategy, config)
            if events:
                events = discovery.filter_garbage_events(events)
                errors = discovery.validate_events(events)
                if not errors:
                    _purge_garbage_concerts(db, venue)
                    added = _save_concerts(db, venue, events)
                    label = STRATEGY_LABELS.get(strategy, strategy)
                    venue.scraper_last_run = datetime.now()
                    venue.scraper_last_status = "success"
                    venue.scraper_error_log = None
                    venue.scraper_event_count = len(events)
                    db.commit()
                    print(f"[Scraper Manager] '{venue.name}' ({label}): {len(events)} events, {len(added)} nieuw.")
                    return added
                else:
                    # Strategie geeft events terug maar validatie faalt → herdicover
                    print(f"[Scraper Manager] Validatie mislukt voor '{venue.name}': {errors}. Herdicover...")
                    strategy = None
            else:
                # 0 events → strategie waarschijnlijk gebroken, reset en herdicover
                print(f"[Scraper Manager] '{venue.name}' strategie {strategy} gaf 0 events. Herdicover...")
                strategy = None
        except Exception as e:
            if "__HTML__:" in str(e):
                # html_gemini sentinel → doorsturen naar Gemini flow hieronder
                strategy = "html_gemini"
            else:
                print(f"[Scraper Manager] Strategie fout voor '{venue.name}': {e}. Herdicover...")
                strategy = None

    # ── Stap B: Discovery (als er nog geen strategie is) ─────────────────
    if not strategy:
        result = discovery.discover_best_strategy(venue.name, venue.scraper_url)
        strategy = result["strategy"]
        config = result["config"]

        # Sla de gevonden strategie op voor volgende runs
        venue.scraper_strategy = strategy
        venue.scraper_config = config
        db.commit()

        label = STRATEGY_LABELS.get(strategy, strategy)
        print(f"[Scraper Manager] Discovery resultaat voor '{venue.name}': {label} "
              f"(confidence {result['confidence']:.0%})")

        if strategy != "html_gemini" and result["sample_events"]:
            # We hebben al events uit discovery, sla ze op
            events = result["sample_events"]
            # Maar haal dan ook de volledige lijst op
            try:
                events = discovery.run_strategy(venue.name, venue.scraper_url, strategy, config)
            except Exception:
                events = result["sample_events"]

            if events:
                events = discovery.filter_garbage_events(events)
                added = _save_concerts(db, venue, events)
                _purge_garbage_concerts(db, venue)
                venue.scraper_last_run = datetime.now()
                venue.scraper_last_status = "success"
                venue.scraper_error_log = None
                venue.scraper_event_count = len(events)
                db.commit()
                print(f"[Scraper Manager] '{venue.name}' ({label}): {len(events)} events, {len(added)} nieuw.")
                return added

    # ── Stap C: html_gemini fallback ──────────────────────────────────────
    try:
        resp = requests.get(venue.scraper_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        if resp.encoding == 'ISO-8859-1':
            resp.encoding = resp.apparent_encoding
        html = resp.text
    except Exception as e:
        error_msg = f"Fout bij ophalen van website: {e}"
        print(f"[Scraper Manager] {error_msg}")
        venue.scraper_last_run = datetime.now()
        venue.scraper_last_status = "failed"
        venue.scraper_error_log = error_msg
        db.commit()
        return []

    if not venue.scraper_code:
        try:
            print(f"[Scraper Manager] Geen code gevonden. Genereren via Gemini...")
            venue.scraper_code = generate_scraper_code(venue.name, venue.scraper_url, html)
            db.commit()
        except Exception as e:
            error_msg = f"Fout bij genereren scraper-code via Gemini: {e}"
            print(f"[Scraper Manager] {error_msg}")
            venue.scraper_last_run = datetime.now()
            venue.scraper_last_status = "failed"
            venue.scraper_error_log = error_msg
            db.commit()
            return []

    # Voer de Gemini-code uit
    events = []
    error_occurred = False
    error_msg = ""

    try:
        events = execute_scraper_code(venue.scraper_code, html)
        if not events:
            raise ValueError("Het script heeft 0 concerten kunnen extraheren.")
    except Exception as e:
        error_occurred = True
        error_msg = f"{e}\n{traceback.format_exc()}"
        print(f"[Scraper Manager] Scraper '{venue.name}' faalde: {e}")

    # Self-Healing bij fouten
    if error_occurred or force_heal:
        try:
            print(f"[Scraper Manager] Auto-reparatie (Self-Healing) activeren voor '{venue.name}'...")
            fixed_code = heal_scraper_code(
                venue, html,
                error_msg if not force_heal else "Handmatige reparatie geforceerd."
            )
            print(f"[Scraper Manager] Nieuwe code ontvangen. Testen...")

            events = execute_scraper_code(fixed_code, html)
            if not events:
                raise ValueError("Gecorrigeerde code retourneerde nog steeds 0 resultaten.")

            venue.scraper_code = fixed_code
            error_occurred = False
            error_msg = ""
            print(f"[Scraper Manager] Scraper '{venue.name}' succesvol gerepareerd door Gemini!")
        except Exception as heal_err:
            error_msg = f"Originele fout:\n{error_msg}\n\nReparatie mislukt:\n{heal_err}"
            print(f"[Scraper Manager] Self-Healing mislukt voor '{venue.name}': {heal_err}")
            venue.scraper_last_run = datetime.now()
            venue.scraper_last_status = "failed"
            venue.scraper_error_log = error_msg
            db.commit()
            return []

    if not events:
        venue.scraper_last_run = datetime.now()
        venue.scraper_last_status = "failed"
        venue.scraper_error_log = "Geen events gevonden"
        db.commit()
        return []

    # Filter garbage artiestennamen vóór opslaan
    events = discovery.filter_garbage_events(events)
    if not events:
        venue.scraper_last_run = datetime.now()
        venue.scraper_last_status = "failed"
        venue.scraper_error_log = "Alle gevonden events hadden garbage-artiestennamen. Herdicover wordt getriggerd."
        venue.scraper_strategy = None  # Reset zodat discovery opnieuw draait
        venue.scraper_config = None
        db.commit()
        print(f"[Scraper Manager] '{venue.name}': alle events waren garbage. Strategie gereset voor herdicover.")
        return []

    # Ruim bestaande garbage-concerten op
    _purge_garbage_concerts(db, venue)

    added = _save_concerts(db, venue, events)

    venue.scraper_last_run = datetime.now()
    venue.scraper_last_status = "success"
    venue.scraper_error_log = None
    venue.scraper_event_count = len(events)
    db.commit()

    print(f"[Scraper Manager] Scraper '{venue.name}' afgerond (Gemini). {len(added)} nieuwe concerten toegevoegd.")
    return added
