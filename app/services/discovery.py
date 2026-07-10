"""
Discovery Engine voor Bandplanner Scrapers.

Probeert per podium automatisch de beste gegevensbron te vinden via:
1. JSON-LD Event/MusicEvent (schema.org)
2. WordPress REST API
3. Embedded JSON (__NEXT_DATA__, __NUXT__, etc.)
4. HTML BeautifulSoup + Gemini als fallback

De gevonden strategie wordt opgeslagen in de Venue.scraper_strategy en
Venue.scraper_config velden, zodat periodieke runs niet opnieuw hoeven
te discoveren.

Validatie controleert ook op garbage-artiestennamen (UI-labels, navigatietekst)
en triggert automatisch herdicover als de kwaliteit niet klopt.
"""

import json
import re
import traceback
from datetime import datetime, date
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ─── Constanten ──────────────────────────────────────────────────────────────

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 15

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive"
}

EVENT_KEYS = {
    "title", "name", "date", "startdate", "start_date", "startDate",
    "location", "venue", "url", "event", "events", "artist", "performer",
}

MONTHS_NL = {
    "jan": 1, "januari": 1, "feb": 2, "februari": 2, "mrt": 3, "maart": 3,
    "apr": 4, "april": 4, "mei": 5, "jun": 6, "juni": 6,
    "jul": 7, "juli": 7, "aug": 8, "augustus": 8, "sep": 9, "september": 9,
    "okt": 10, "oktober": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Woorden die NOOIT een artiestnaam zijn — UI-labels, navigatie, agenda-termen
GARBAGE_ARTIST_WORDS = {
    # Nederlands
    "wachtlijst", "speeldata", "agenda", "programma", "voorstelling", "uitverkocht",
    "beschikbaar", "tickets", "kopen", "info", "meer info", "lees meer", "details",
    "inloggen", "aanmelden", "registreren", "menu", "zoeken", "filter", "categorie",
    "datum", "locatie", "zaal", "prijs", "gratis", "uitverkoop", "kaartverkoop",
    "home", "terug", "verder", "volgende", "vorige", "sluiten", "open",
    "ja", "nee", "ok", "annuleren", "bevestigen", "opslaan",
    "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag",
    "ma", "di", "wo", "do", "vr", "za", "zo",
    "januari", "februari", "maart", "april", "mei", "juni", "juli",
    "augustus", "september", "oktober", "november", "december",
    # Engels
    "waitlist", "sold out", "buy tickets", "more info", "read more",
    "login", "register", "search", "filter", "category", "location",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "today", "tomorrow", "this week",
    # Peppered / CMS specifiek
    "speeldata en tijden", "wachtrij", "meerdere tijdstippen", "koekbouw",
    "voorverkoop", "persbericht", "aankondiging", "nieuwsbrief",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def fetch_html(url: str) -> tuple[str, dict]:
    """Haalt HTML op en retourneert (html, headers)."""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    # Corrigeer encoding indien requests de verkeerde aanname doet
    if resp.encoding == 'ISO-8859-1':
        resp.encoding = resp.apparent_encoding
    return resp.text, dict(resp.headers)




def fetch_json(url: str) -> dict | list | None:
    """Haalt JSON op van een URL."""
    try:
        json_headers = HEADERS.copy()
        json_headers["Accept"] = "application/json"
        resp = requests.get(url, headers=json_headers, timeout=TIMEOUT)
        if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
            return resp.json()
    except Exception:
        pass
    return None


def parse_date_str(s: str) -> Optional[str]:
    """
    Probeert een datumstring te parsen naar YYYY-MM-DD.
    Ondersteunt ISO-formaten, SQL datetimes en Nederlandse datums.
    """
    if not s:
        return None
    s = s.strip()

    # Als de string al begint met YYYY-MM-DD (zoals 2026-08-29 of 2026-08-29 23:30:00)
    # kunnen we direct de eerste 10 tekens pakken! Dit is extreem robuust.
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]

    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    s_lower = s.lower()
    for month_name, month_num in MONTHS_NL.items():
        if month_name in s_lower:
            numbers = re.findall(r"\d+", s_lower)
            if numbers:
                day = int(numbers[0])
                year = int(numbers[1]) if len(numbers) > 1 else datetime.now().year
                try:
                    return date(year, month_num, day).isoformat()
                except ValueError:
                    pass
    return None


def score_json_candidate(data) -> int:
    """Geeft een score aan een JSON-object op basis van event-achtige velden."""
    score = 0

    def walk(value, depth=0):
        nonlocal score
        if depth > 6:
            return
        if isinstance(value, dict):
            keys = {str(k).lower() for k in value}
            score += len(keys & EVENT_KEYS)
            for child in value.values():
                walk(child, depth + 1)
        elif isinstance(value, list):
            if len(value) >= 3:
                score += 2
            for child in value[:20]:
                walk(child, depth + 1)

    walk(data)
    return score


# ─── Garbage-detectie ─────────────────────────────────────────────────────────

def is_garbage_artist(name: str) -> bool:
    """Geeft True terug als de naam duidelijk geen artiestnaam is."""
    if not name:
        return True
    cleaned = name.strip().lower()
    if len(cleaned) <= 1:
        return True
    # Alleen cijfers
    if re.match(r"^\d+$", cleaned):
        return True
    # Exacte match met blacklist
    if cleaned in GARBAGE_ARTIST_WORDS:
        return True
    # Dag-afkorting + getal ("za 11", "vr 10 jul")
    if re.match(r"^(ma|di|wo|do|vr|za|zo)\s+\d", cleaned):
        return True
    # Puur datum-string ("12 juli 2026")
    if re.match(r"^\d{1,2}\s+[a-z]+\s+\d{2,4}$", cleaned):
        return True
    return False


def filter_garbage_events(events: list[dict]) -> list[dict]:
    """Filtert aantoonbaar foute events eruit (garbage artiesten, geen datum)."""
    return [
        e for e in events
        if not is_garbage_artist(e.get("artist", "")) and e.get("date")
    ]


# ─── Validatie ────────────────────────────────────────────────────────────────

def validate_events(events: list[dict]) -> list[str]:
    """
    Valideert een lijst met events op kwaliteit.
    Geeft een lijst met foutmeldingen terug (leeg = geldig).

    Controleert op:
    - Voldoende artiesten en datums
    - Garbage-artiestennamen (UI-labels, navigatietekst)
    - Toekomstige events
    """
    errors = []
    if not events:
        errors.append("Geen evenementen gevonden")
        return errors

    with_artist = sum(1 for e in events if e.get("artist"))
    with_date = sum(1 for e in events if e.get("date"))

    if with_artist / len(events) < 0.7:
        errors.append(f"Minder dan 70% heeft een artiest ({with_artist}/{len(events)})")
    if with_date / len(events) < 0.7:
        errors.append(f"Minder dan 70% heeft een datum ({with_date}/{len(events)})")

    # Garbage-detectie: hoeveel artiesten zijn duidelijk geen namen?
    garbage = [e for e in events if is_garbage_artist(e.get("artist", ""))]
    if garbage and len(garbage) / len(events) >= 0.3:
        examples = [e.get("artist") for e in garbage[:3]]
        errors.append(
            f"{len(garbage)}/{len(events)} artiestennamen zijn UI-labels of navigatietekst "
            f"(bijv. {examples}). De scraper pakt de verkeerde HTML-elementen."
        )

    # URL-deduplicatie
    urls = [e["url"] for e in events if e.get("url")]
    if urls and len(urls) != len(set(urls)):
        errors.append("Dubbele event-URL's gevonden")

    # Minstens één toekomstig event
    now = datetime.now()
    future = 0
    for e in events:
        d = e.get("date")
        if d:
            try:
                if datetime.strptime(d[:10], "%Y-%m-%d") >= now:
                    future += 1
            except Exception:
                pass
    if future == 0:
        errors.append("Geen toekomstige evenementen gevonden")

    return errors


# ─── Adapter 1: JSON-LD ───────────────────────────────────────────────────────

def extract_jsonld_events(html: str, venue_name: str) -> list[dict]:
    """Extraheert Event/MusicEvent objecten uit JSON-LD script-tags."""
    soup = BeautifulSoup(html, "html.parser")
    events = []

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text(strip=True))
        except (json.JSONDecodeError, TypeError):
            continue

        objects = data if isinstance(data, list) else [data]

        for obj in objects:
            if not isinstance(obj, dict):
                continue

            candidates = []
            graph = obj.get("@graph", [])
            if isinstance(graph, list):
                candidates.extend(graph)
            candidates.append(obj)

            for candidate in candidates:
                event_type = candidate.get("@type", [])
                if isinstance(event_type, str):
                    event_type = [event_type]

                if not ({"Event", "MusicEvent", "TheaterEvent", "SocialEvent"} & set(event_type)):
                    continue

                artist = None
                performer = candidate.get("performer") or candidate.get("artists")
                if isinstance(performer, list) and performer:
                    first = performer[0]
                    artist = first.get("name") if isinstance(first, dict) else str(first)
                elif isinstance(performer, dict):
                    artist = performer.get("name")
                elif isinstance(performer, str):
                    artist = performer
                if not artist:
                    artist = candidate.get("name", "")

                raw_date = candidate.get("startDate") or candidate.get("startdate") or candidate.get("date")
                date_str = parse_date_str(str(raw_date)) if raw_date else None

                url = candidate.get("url") or candidate.get("@id")

                price = None
                offers = candidate.get("offers")
                if isinstance(offers, dict):
                    price_raw = offers.get("price") or offers.get("lowPrice")
                    try:
                        price = float(str(price_raw).replace(",", ".")) if price_raw else None
                    except (ValueError, TypeError):
                        price = None
                elif isinstance(offers, list) and offers:
                    price_raw = offers[0].get("price")
                    try:
                        price = float(str(price_raw).replace(",", ".")) if price_raw else None
                    except (ValueError, TypeError):
                        price = None

                if artist and date_str and not is_garbage_artist(artist):
                    events.append({
                        "artist": artist.strip(),
                        "date": date_str,
                        "venue": venue_name,
                        "price": price,
                        "url": url,
                    })

    return events


# ─── Adapter 2: WordPress REST API ───────────────────────────────────────────

def discover_wordpress_api(html: str, page_url: str) -> list[str]:
    """Zoekt WordPress REST API endpoints in HTML link-tags en headers."""
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for link in soup.select("link[href]"):
        rel = " ".join(link.get("rel", []))
        link_type = link.get("type", "")
        href = link.get("href", "")

        if not href:
            continue
        if "api.w.org" in rel:
            candidates.append(urljoin(page_url, href))
        if link_type == "application/json" and "wp-json" in href:
            candidates.append(urljoin(page_url, href))

    base = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    candidates.append(f"{base}/wp-json/")

    return list(dict.fromkeys(candidates))


EVENT_ROUTE_KEYWORDS = {"event", "events", "agenda", "program", "programme", "show", "shows", "concert", "concerts"}


def find_wordpress_event_endpoint(api_index_url: str) -> Optional[str]:
    """Vindt een event-achtig endpoint in de WordPress REST API index."""
    data = fetch_json(api_index_url)
    if not data or not isinstance(data, dict):
        return None

    routes = data.get("routes", {})
    best = None
    for route_path in routes:
        lower = route_path.lower()
        if any(kw in lower for kw in EVENT_ROUTE_KEYWORDS):
            if best is None or len(route_path) < len(best):
                best = route_path

    if best:
        base = api_index_url.rstrip("/").rsplit("/wp-json", 1)[0]
        return f"{base}/wp-json{best}"

    return None


def extract_wordpress_events(endpoint: str, venue_name: str) -> list[dict]:
    """Haalt events op van een WordPress REST endpoint en normaliseert ze."""
    data = fetch_json(endpoint)
    if not data or not isinstance(data, list):
        return []

    events = []
    for item in data:
        if not isinstance(item, dict):
            continue

        # 1. Titel / artiest
        artist = None
        
        # Check custom object structures first
        prod = item.get("prod")
        if isinstance(prod, dict):
            artist = prod.get("title")
            
        event_obj = item.get("event")
        if not artist and isinstance(event_obj, dict):
            artist = event_obj.get("title") or event_obj.get("name")
            
        if not artist:
            title_field = item.get("title")
            if isinstance(title_field, dict):
                artist = title_field.get("rendered", "")
            elif isinstance(title_field, str):
                artist = title_field
                
        if not artist:
            artist = item.get("name") or item.get("post_title") or ""

        # 2. Datum
        raw_date = None
        if isinstance(event_obj, dict):
            # event.start of event.start_date (Mezz gebruikt bijv. 'start' of 'start_date')
            raw_date = event_obj.get("start") or event_obj.get("start_date") or event_obj.get("date")
            
        acf = item.get("acf")
        if not raw_date and isinstance(acf, dict):
            raw_date = acf.get("date") or acf.get("event_date") or acf.get("start_date") or acf.get("date_time")
            
        meta = item.get("meta")
        if not raw_date and isinstance(meta, dict):
            raw_date = meta.get("event_date")
            
        if not raw_date:
            raw_date = item.get("date") or item.get("start_date")
            
        date_str = parse_date_str(str(raw_date)) if raw_date else None

        # 3. URL
        url = None
        if isinstance(prod, dict):
            url = prod.get("link") or prod.get("url")
        if not url and isinstance(event_obj, dict):
            url = event_obj.get("ticket_url_iframe") or event_obj.get("link") or event_obj.get("url")
        if not url:
            url = item.get("link") or item.get("url")

        # 4. Prijs
        price = None
        if isinstance(acf, dict):
            price_raw = acf.get("price")
            try:
                price = float(price_raw) if price_raw is not None else None
            except (ValueError, TypeError):
                pass

        if artist and date_str and not is_garbage_artist(artist):
            events.append({
                "artist": artist.strip(),
                "date": date_str,
                "venue": venue_name,
                "price": price,
                "url": url,
            })

    return events


# ─── Adapter 3: Embedded JSON ─────────────────────────────────────────────────

EMBEDDED_SELECTORS = [
    "script#__NEXT_DATA__",
    "script#__NUXT_DATA__",
    'script[type="application/json"]',
    "script#initial-state",
    "script#preloaded-state",
]

EMBEDDED_PATTERNS = [
    r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});',
    r'window\.__REDUX_STATE__\s*=\s*(\{.+?\});',
    r'window\.pageData\s*=\s*(\{.+?\});',
    r'window\.__APP_STATE__\s*=\s*(\{.+?\});',
]


def find_event_arrays(data, venue_name: str, depth: int = 0) -> list[dict]:
    """Zoekt recursief naar event-achtige arrays in een JSON-structuur."""
    if depth > 8:
        return []

    events = []

    if isinstance(data, list) and len(data) >= 2:
        sample = data[:5]
        keys_union = set()
        for item in sample:
            if isinstance(item, dict):
                keys_union |= {k.lower() for k in item.keys()}

        has_event_keys = bool(keys_union & EVENT_KEYS)
        has_date = any(k in keys_union for k in {"date", "startdate", "start_date", "startDate"})
        has_name = any(k in keys_union for k in {"title", "name", "artist", "performer"})

        if has_event_keys and has_date and has_name:
            for item in data:
                if not isinstance(item, dict):
                    continue

                artist = (
                    item.get("title") or item.get("name") or item.get("artist")
                    or item.get("performer") or item.get("heading") or ""
                )
                if isinstance(artist, dict):
                    artist = artist.get("rendered") or artist.get("value") or ""

                raw_date = (
                    item.get("startDate") or item.get("start_date") or item.get("startdate")
                    or item.get("date") or item.get("dateStart") or item.get("event_date")
                )
                date_str = parse_date_str(str(raw_date)) if raw_date else None

                url = item.get("url") or item.get("link") or item.get("permalink")

                if artist and date_str and not is_garbage_artist(str(artist)):
                    events.append({
                        "artist": str(artist).strip(),
                        "date": date_str,
                        "venue": venue_name,
                        "price": None,
                        "url": url,
                    })
            if events:
                return events

    if isinstance(data, dict):
        for value in data.values():
            sub = find_event_arrays(value, venue_name, depth + 1)
            if sub:
                events.extend(sub)
    elif isinstance(data, list):
        for item in data:
            sub = find_event_arrays(item, venue_name, depth + 1)
            if sub:
                events.extend(sub)

    return events


def extract_embedded_json_events(html: str, venue_name: str) -> list[dict]:
    """Zoekt en parseert embedded JSON in de HTML-pagina."""
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for selector in EMBEDDED_SELECTORS:
        for script in soup.select(selector):
            text = script.get_text(strip=True)
            if not text:
                continue
            try:
                data = json.loads(text)
                if isinstance(data, (dict, list)):
                    candidates.append((score_json_candidate(data), data))
            except json.JSONDecodeError:
                pass

    for script in soup.find_all("script"):
        text = script.get_text()
        for pattern in EMBEDDED_PATTERNS:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    candidates.append((score_json_candidate(data), data))
                except json.JSONDecodeError:
                    pass

    if not candidates:
        return []

    candidates.sort(key=lambda x: x[0], reverse=True)
    for _, data in candidates[:3]:
        events = find_event_arrays(data, venue_name)
        if events:
            return events

    return []


# ─── Hoofd Discovery Functie ──────────────────────────────────────────────────

def discover_best_strategy(venue_name: str, url: str) -> dict:
    """
    Probeert de beste scraping-strategie te vinden voor een podium.

    Retourneert een dict met:
      - strategy: 'jsonld' | 'wordpress' | 'embedded_json' | 'html_gemini'
      - config: dict met strategie-specifieke config (endpoint etc.)
      - sample_events: eerste paar gevonden events (voor preview)
      - confidence: 0.0 - 1.0
      - errors: lijst met validatiefouten
    """
    print(f"[Discovery] Start discovery voor '{venue_name}' ({url})")

    try:
        html, headers = fetch_html(url)
    except Exception as e:
        return {
            "strategy": "html_gemini",
            "config": {},
            "sample_events": [],
            "confidence": 0.0,
            "errors": [f"Kon pagina niet ophalen: {e}"]
        }

    # ── Strategie 1: JSON-LD ──────────────────────────────────────────────
    try:
        events = extract_jsonld_events(html, venue_name)
        if events:
            errors = validate_events(events)
            if not errors:
                print(f"[Discovery] JSON-LD succesvol: {len(events)} events gevonden")
                return {
                    "strategy": "jsonld",
                    "config": {"url": url},
                    "sample_events": events[:3],
                    "confidence": 0.95,
                    "errors": []
                }
    except Exception as e:
        print(f"[Discovery] JSON-LD fout: {e}")

    # ── Strategie 2: WordPress REST API ──────────────────────────────────
    try:
        api_candidates = discover_wordpress_api(html, url)
        for api_base in api_candidates:
            endpoint = find_wordpress_event_endpoint(api_base)
            if endpoint:
                events = extract_wordpress_events(endpoint, venue_name)
                if events:
                    errors = validate_events(events)
                    if not errors:
                        print(f"[Discovery] WordPress REST succesvol: {len(events)} events via {endpoint}")
                        return {
                            "strategy": "wordpress",
                            "config": {"api_base": api_base, "endpoint": endpoint},
                            "sample_events": events[:3],
                            "confidence": 0.90,
                            "errors": []
                        }
    except Exception as e:
        print(f"[Discovery] WordPress fout: {e}")

    # ── Strategie 3: Embedded JSON ────────────────────────────────────────
    try:
        events = extract_embedded_json_events(html, venue_name)
        if events:
            errors = validate_events(events)
            if not errors:
                print(f"[Discovery] Embedded JSON succesvol: {len(events)} events gevonden")
                return {
                    "strategy": "embedded_json",
                    "config": {"url": url},
                    "sample_events": events[:3],
                    "confidence": 0.80,
                    "errors": []
                }
    except Exception as e:
        print(f"[Discovery] Embedded JSON fout: {e}")


    # ── Fallback: Gemini HTML parser ──────────────────────────────────────
    print(f"[Discovery] Geen gestructureerde bron gevonden. Fallback naar Gemini HTML parser.")
    return {
        "strategy": "html_gemini",
        "config": {"url": url},
        "sample_events": [],
        "confidence": 0.5,
        "errors": ["Geen gestructureerde databron gevonden, Gemini HTML-parser wordt gebruikt"]
    }


def run_strategy(venue_name: str, url: str, strategy: str, config: dict) -> list[dict]:
    """
    Voert een opgeslagen strategie uit zonder opnieuw te discoveren.
    Retourneert een lijst van genormaliseerde event-dicts.
    """
    try:
        html, _ = fetch_html(config.get("url") or url)
    except Exception as e:
        raise Exception(f"Kon pagina niet ophalen: {e}")

    if strategy == "jsonld":
        return extract_jsonld_events(html, venue_name)

    elif strategy == "wordpress":
        endpoint = config.get("endpoint")
        if not endpoint:
            raise Exception("WordPress endpoint niet gevonden in config")
        return extract_wordpress_events(endpoint, venue_name)

    elif strategy == "embedded_json":
        return extract_embedded_json_events(html, venue_name)

    elif strategy == "html_gemini":
        # Retourneer de HTML zodat scraper_manager de Gemini code kan gebruiken
        raise Exception("__HTML__:" + html)

    else:
        raise Exception(f"Onbekende strategie: {strategy}")
