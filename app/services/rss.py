import re
import datetime
from typing import List, Tuple, Optional
import feedparser
from sqlalchemy.orm import Session
from app.models import Concert, Venue, UserConfig
from app.services.distance import geocode_location

CONCERT_FEED_URL = "https://www.festivalinfo.nl/rss/PodiuminfoConcertRSS.xml"
FESTIVAL_FEED_URL = "https://www.festivalinfo.nl/rss/FestivalinfoFestivalRSS.xml"

# Regexes voor het parsen van RSS titels
# Concert: "02/07 : Kevin Morby - Paradiso, Amsterdam"
CONCERT_REGEX = re.compile(r"^(\d{2})/(\d{2})\s*:\s*(.*)$")
# Festival: "02/07 - 05/07 : Rock Werchter - Werchter, Be"
FESTIVAL_REGEX = re.compile(r"^(\d{2})/(\d{2})\s*-\s*(\d{2})/(\d{2})\s*:\s*(.*)$")

def parse_date(day: int, month: int, pub_date_parsed) -> datetime.datetime:
    """
    Berekent de juiste datum inclusief jaar op basis van de publicatiedatum van de RSS feed.
    """
    now = datetime.datetime.now()
    year = now.year
    if pub_date_parsed:
        year = pub_date_parsed.tm_year
        pub_month = pub_date_parsed.tm_mon
    else:
        pub_month = now.month
        
    # Als de concertmaand kleiner is dan de publicatiemaand, is het concert volgend jaar
    if month < pub_month:
        year += 1
        
    return datetime.datetime(year, month, day)

def find_or_create_venue(db: Session, venue_name: str, city_name: str = "") -> Venue:
    """
    Zoekt een zaal op in de database op basis van naam of aliases.
    Als deze niet bestaat, wordt er gezocht via OpenStreetMap Nominatim en een nieuwe zaal aangemaakt.
    """
    clean_name = venue_name.strip()
    clean_city = city_name.strip()
    
    # Zoek in database op exacte naam
    venue = db.query(Venue).filter(Venue.name.ilike(clean_name)).first()
    if venue:
        return venue
        
    # Zoek op aliases
    all_venues = db.query(Venue).all()
    for v in all_venues:
        if v.aliases:
            aliases = [a.strip().lower() for a in v.aliases.split(",") if a.strip()]
            if clean_name.lower() in aliases:
                return v
                
    # Probeer te matchen op bevat (bijv. "Paradiso Amsterdam" matcht met "Paradiso")
    for v in all_venues:
        if v.name.lower() in clean_name.lower() or clean_name.lower() in v.name.lower():
            return v

    # Niet gevonden in DB en we maken geen nieuwe podia meer automatisch aan
    print(f"[Sync] Podium '{clean_name}' niet gevonden in database. Concert wordt overgeslagen.")
    return None

def parse_rss_feeds(db: Session) -> int:
    """
    Haalt de RSS-feeds op en slaat nieuwe concerten op.
    Berekent nog geen scores; dat gebeurt in de scoring engine.
    """
    new_concerts_count = 0
    
    # 1. Parse Concert Agenda
    print("Ophalen Podiuminfo concerten...")
    concert_feed = feedparser.parse(CONCERT_FEED_URL)
    for entry in concert_feed.entries:
        title = entry.title
        pub_date = entry.get("published_parsed", None)
        link = entry.link
        
        match = CONCERT_REGEX.match(title)
        if not match:
            continue
            
        day = int(match.group(1))
        month = int(match.group(2))
        rest = match.group(3)
        
        # Split rest in Artist en Venue
        parts = [p.strip() for p in rest.split(" - ") if p.strip()]
        if len(parts) < 2:
            continue
            
        artist = parts[0]
        venue_city_str = parts[-1]
        
        # Split venue en stad (meestal gesplitst door een komma)
        vc_parts = [v.strip() for v in venue_city_str.split(",") if v.strip()]
        venue_name = vc_parts[0]
        city_name = vc_parts[1] if len(vc_parts) > 1 else ""
        
        concert_date = parse_date(day, month, pub_date)
        
        # Zoek zaal
        venue = find_or_create_venue(db, venue_name, city_name)
        if not venue:
            continue
        
        # Controleer of concert al bestaat (combinatie artiest, zaal en datum)
        # We vergelijken alleen de datum (jaar, maand, dag)
        start_of_day = datetime.datetime(concert_date.year, concert_date.month, concert_date.day)
        end_of_day = start_of_day + datetime.timedelta(days=1)
        
        exists = db.query(Concert).filter(
            Concert.artist.ilike(artist),
            Concert.venue_id == venue.id,
            Concert.date >= start_of_day,
            Concert.date < end_of_day
        ).first()
        
        if not exists:
            concert = Concert(
                artist=artist,
                venue_id=venue.id,
                date=concert_date,
                url=link,
                source="rss_podiuminfo",
                status="new"
            )
            db.add(concert)
            new_concerts_count += 1
            
    # 2. Parse Festival Agenda
    print("Ophalen Festivalinfo festivals...")
    festival_feed = feedparser.parse(FESTIVAL_FEED_URL)
    for entry in festival_feed.entries:
        title = entry.title
        pub_date = entry.get("published_parsed", None)
        link = entry.link
        
        match = FESTIVAL_REGEX.match(title)
        if not match:
            continue
            
        start_day = int(match.group(1))
        start_month = int(match.group(2))
        # We negeren de einddatum voor de startdatum van de boeking
        rest = match.group(5)
        
        # Split rest in Festival Naam en Locatie
        parts = [p.strip() for p in rest.split(" - ") if p.strip()]
        if len(parts) < 2:
            continue
            
        festival_name = parts[0]
        loc_str = parts[-1]
        
        # Locatie splitten (stad, land)
        loc_parts = [l.strip() for l in loc_str.split(",") if l.strip()]
        city_name = loc_parts[0]
        country_name = loc_parts[1] if len(loc_parts) > 1 else ""
        
        concert_date = parse_date(start_day, start_month, pub_date)
        
        # Voor festivals maken we een virtueel podium aan
        venue = find_or_create_venue(db, festival_name, city_name)
        if not venue:
            continue
        
        start_of_day = datetime.datetime(concert_date.year, concert_date.month, concert_date.day)
        end_of_day = start_of_day + datetime.timedelta(days=1)
        
        exists = db.query(Concert).filter(
            Concert.artist.ilike(festival_name),
            Concert.venue_id == venue.id,
            Concert.date >= start_of_day,
            Concert.date < end_of_day
        ).first()
        
        if not exists:
            concert = Concert(
                artist=festival_name, # Festival is zelf de act
                venue_id=venue.id,
                date=concert_date,
                url=link,
                source="rss_festivalinfo",
                status="new"
            )
            db.add(concert)
            new_concerts_count += 1
            
    db.commit()
    print(f"Synchronisatie voltooid. {new_concerts_count} nieuwe concerten toegevoegd.")
    return new_concerts_count
