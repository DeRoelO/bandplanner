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

USER_AGENT = "BandplannerBot/2.0 (contact: github.com/DeRoelO/bandplanner)"
TIMEOUT = 15

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

# ─── Helpers ─────────────────────────────────────────────────────────────────

def fetch_html(url: str) -> tuple[str, dict]:
    """Haalt HTML op en retourneert (html, headers)."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text, dict(resp.headers)


def fetch_json(url: str) -> dict | list | None:
    """Haalt JSON op van een URL."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=TIMEOUT)
        if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
            return resp.json()
    except Exception:
        pass
    return None


def parse_date_str(s: str) -> Optional[str]:
    """
    Probeert een datumstring te parsen naar YYYY-MM-DD.
    Ondersteunt ISO-formaten en Nederlandse datums.
    """
    if not s:
        return None
    s = s.strip()

    # ISO / datetime strings
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Nederlandse datum: "12 mei 2026", "12 mei", "za 12 mei 2026"
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


def validate_events(events: list[dict]) -> list[str]:
    """Valideert een lijst met events en retourneert een lijst met foutmeldingen."""
    errors = []
    if not events:
        errors.append("Geen evenementen gevonden")
        return errors

    with_artist = sum(1 for e in events if e.get("artist"))
    with_date = sum(1 for e in events if e.get("date"))
    with_url = sum(1 for e in events if e.get("url"))

    if with_artist / len(events) < 0.7:
        errors.append(f"Minder dan 70% heeft een artiest ({with_artist}/{len(events)})")
    if with_date / len(events) < 0.7:
        errors.append(f"Minder dan 70% heeft een datum ({with_date}/{len(events)})")

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

            # Verwerk @graph arrays
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

                # Artiest ophalen
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

                # Datum ophalen
                raw_date = candidate.get("startDate") or candidate.get("startdate") or candidate.get("date")
                date_str = parse_date_str(str(raw_date)) if raw_date else None

                # URL ophalen
                url = candidate.get("url") or candidate.get("@id")

                # Prijs ophalen
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

                if artist and date_str:
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

    # Probeer standaard endpoint
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
            # Geef voorkeur aan kortere routes (minder specifiek = lijst endpoint)
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

        # Titel / artiest
        artist = None
        title_field = item.get("title")
        if isinstance(title_field, dict):
            artist = title_field.get("rendered", "")
        elif isinstance(title_field, str):
            artist = title_field
        if not artist:
            artist = item.get("name") or item.get("post_title") or ""

        # Datum - probeer common ACF/meta velden
        raw_date = (
            item.get("acf", {}).get("date")
            or item.get("acf", {}).get("event_date")
            or item.get("acf", {}).get("start_date")
            or item.get("meta", {}).get("event_date")
            or item.get("date")
            or item.get("start_date")
        )
        date_str = parse_date_str(str(raw_date)) if raw_date else None

        url = item.get("link") or item.get("url")

        if artist and date_str:
            events.append({
                "artist": artist.strip(),
                "date": date_str,
                "venue": venue_name,
                "price": None,
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
        # Check of dit een lijst van event-achtige objecten is
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

                # Artiest
                artist = (
                    item.get("title") or item.get("name") or item.get("artist")
                    or item.get("performer") or item.get("heading") or ""
                )
                if isinstance(artist, dict):
                    artist = artist.get("rendered") or artist.get("value") or ""

                # Datum
                raw_date = (
                    item.get("startDate") or item.get("start_date") or item.get("startdate")
                    or item.get("date") or item.get("dateStart") or item.get("event_date")
                )
                date_str = parse_date_str(str(raw_date)) if raw_date else None

                url = item.get("url") or item.get("link") or item.get("permalink")

                if artist and date_str:
                    events.append({
                        "artist": str(artist).strip(),
                        "date": date_str,
                        "venue": venue_name,
                        "price": None,
                        "url": url,
                    })
            if events:
                return events

    # Recursief zoeken in dicts en lists
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

    # Via HTML selectors
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

    # Via regex patronen in inline scripts
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

    # Sorteer op score, probeer beste kandidaat eerst
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
