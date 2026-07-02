import asyncio
import datetime
import os
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Form
from fastapi.responses import Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.config import settings
from app.database import get_db, SessionLocal
from app.models import Concert, Venue, UserConfig, ArtistPreference
from app.services.spotify import get_spotify_oauth, sync_spotify_preferences
from app.services.rss import parse_rss_feeds
from app.services.scoring import score_all_new_concerts, score_concert
from app.services.notifications import notify_new_concerts, notify_parser_error
from app.services.gemini import parse_newsletter_with_gemini

# --- Achtergrond Synchronisatie Loop ---
async def background_sync_loop():
    # Wacht even bij het opstarten zodat de server goed draait
    await asyncio.sleep(10)
    while True:
        try:
            print("[Background Task] Start automatische synchronisatie...")
            db = SessionLocal()
            try:
                # 1. Sync RSS feeds
                new_count = parse_rss_feeds(db)
                
                # 2. Sync IMAP email newsletters
                from app.services.email_receiver import fetch_and_parse_emails
                try:
                    new_email_count = fetch_and_parse_emails(db)
                    new_count += new_email_count
                except Exception as email_err:
                    print(f"[Background Task] Fout bij ophalen e-mails: {email_err}")
                
                # 3. Score nieuwe concerten
                high_matches = score_all_new_concerts(db)
                
                # 4. Verstuur e-mails voor nieuwe aanbevelingen
                if high_matches:
                    to_notify = [c for c in high_matches if not c.notified]
                    if to_notify:
                        success = notify_new_concerts(db, to_notify)
                        if success:
                            for c in to_notify:
                                c.notified = True
                            db.commit()
                            print(f"[Background Task] E-mail verstuurd voor {len(to_notify)} concerten.")
            except Exception as e:
                print(f"[Background Task] Fout tijdens sync loop: {e}")
                # Stuur een e-mail notificatie over de fout
                notify_parser_error(db, f"Fout in automatische sync loop:\n{e}")
            finally:
                db.close()
        except asyncio.CancelledError:
            print("[Background Task] Synchronisatie loop geannuleerd.")
            break
        
        # Elke 12 uur synchroniseren
        print("[Background Task] Volgende sync over 12 uur.")
        await asyncio.sleep(12 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Opstarten database & seeden
    db = SessionLocal()
    try:
        from app.database import Base, engine
        from app.seed_venues import seed_data
        Base.metadata.create_all(bind=engine)
        seed_data(db)
        print("Database geïnitialiseerd en podia geseed.")
    except Exception as e:
        print(f"Fout bij database initialisatie: {e}")
    finally:
        db.close()
        
    # Start de achtergrondtaak
    sync_task = asyncio.create_task(background_sync_loop())
    yield
    # Afsluiten
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Bandplanner API",
    description="Backend API voor de Bandplanner applicatie",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configureren
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Schemas ---
class ConfigUpdate(BaseModel):
    home_latitude: float
    home_longitude: float
    radius_small: float
    radius_medium: float
    radius_large: float
    
    # Sleutels (instelbaar via GUI)
    gemini_api_key: Optional[str] = ""
    spotify_client_id: Optional[str] = ""
    spotify_client_secret: Optional[str] = ""
    spotify_redirect_uri: Optional[str] = "http://localhost:8080/callback"
    
    # SMTP (instelbaar via GUI)
    smtp_server: Optional[str] = ""
    smtp_port: Optional[int] = 587
    smtp_username: Optional[str] = ""
    smtp_password: Optional[str] = ""
    smtp_from_email: Optional[str] = ""
    smtp_to_email: Optional[str] = ""
    
    # IMAP (instelbaar via GUI)
    imap_server: Optional[str] = ""
    imap_port: Optional[int] = 993
    imap_username: Optional[str] = ""
    imap_password: Optional[str] = ""
    imap_enabled: Optional[bool] = False

class VenueCreateUpdate(BaseModel):
    name: str
    latitude: float
    longitude: float
    category: str
    url: Optional[str] = None
    aliases: Optional[str] = ""

class ConcertStatusUpdate(BaseModel):
    status: str  # 'new', 'ignored', 'interested'

class EmailParseRequest(BaseModel):
    email_text: str

# --- API Routes ---

# 1. Configuur Routes
@app.get("/api/config")
def get_config(db: Session = Depends(get_db)):
    config = db.query(UserConfig).first()
    if not config:
        config = UserConfig(
            home_latitude=settings.DEFAULT_HOME_LATITUDE,
            home_longitude=settings.DEFAULT_HOME_LONGITUDE,
            radius_small=settings.DEFAULT_RADIUS_SMALL,
            radius_medium=settings.DEFAULT_RADIUS_MEDIUM,
            radius_large=settings.DEFAULT_RADIUS_LARGE
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

@app.post("/api/config")
def update_config(data: ConfigUpdate, db: Session = Depends(get_db)):
    config = db.query(UserConfig).first()
    if not config:
        config = UserConfig()
        db.add(config)
        
    config.home_latitude = data.home_latitude
    config.home_longitude = data.home_longitude
    config.radius_small = data.radius_small
    config.radius_medium = data.radius_medium
    config.radius_large = data.radius_large
    
    # Keys
    config.gemini_api_key = data.gemini_api_key
    config.spotify_client_id = data.spotify_client_id
    config.spotify_client_secret = data.spotify_client_secret
    config.spotify_redirect_uri = data.spotify_redirect_uri
    
    # SMTP
    config.smtp_server = data.smtp_server
    config.smtp_port = data.smtp_port
    config.smtp_username = data.smtp_username
    config.smtp_password = data.smtp_password
    config.smtp_from_email = data.smtp_from_email
    config.smtp_to_email = data.smtp_to_email
    
    # IMAP
    config.imap_server = data.imap_server
    config.imap_port = data.imap_port
    config.imap_username = data.imap_username
    config.imap_password = data.imap_password
    config.imap_enabled = data.imap_enabled
    
    db.commit()
    db.refresh(config)

    
    # Herscore alle concerten met status 'new' omdat de locatie/radii zijn veranderd
    from app.services.scoring import score_all_new_concerts
    score_all_new_concerts(db)
    
    return config

# 2. Spotify Auth & Sync Routes
@app.get("/api/spotify/status")
def get_spotify_status(db: Session = Depends(get_db)):
    config = db.query(UserConfig).first()
    
    client_id = config.spotify_client_id if config and config.spotify_client_id else settings.SPOTIFY_CLIENT_ID
    client_secret = config.spotify_client_secret if config and config.spotify_client_secret else settings.SPOTIFY_CLIENT_SECRET
    connected = config is not None and config.spotify_refresh_token is not None
    
    pref_count = db.query(ArtistPreference).filter(
        ArtistPreference.source == "top_artist"
    ).count()
    
    genre_count = db.query(ArtistPreference).filter(
        ArtistPreference.source == "genre_match"
    ).count()
    
    db_redirect = config.spotify_redirect_uri if config and config.spotify_redirect_uri else settings.SPOTIFY_REDIRECT_URI
    
    return {
        "connected": connected,
        "top_artists_count": pref_count,
        "cached_artists_count": genre_count,
        "redirect_uri": db_redirect,
        "client_id_configured": bool(client_id)
    }

@app.get("/login/spotify")
def login_spotify(db: Session = Depends(get_db)):
    config = db.query(UserConfig).first()
    client_id = config.spotify_client_id if config and config.spotify_client_id else settings.SPOTIFY_CLIENT_ID
    client_secret = config.spotify_client_secret if config and config.spotify_client_secret else settings.SPOTIFY_CLIENT_SECRET
    
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400, 
            detail="Spotify Client ID en Secret zijn niet geconfigureerd in de database of .env."
        )
    oauth = get_spotify_oauth(db)
    auth_url = oauth.get_authorize_url()
    return RedirectResponse(url=auth_url)

@app.get("/callback")
def spotify_callback(code: str, db: Session = Depends(get_db)):
    oauth = get_spotify_oauth(db)
    try:
        token_info = oauth.get_access_token(code, as_dict=True)
        config = db.query(UserConfig).first()
        if not config:
            config = UserConfig()
            db.add(config)
            
        config.spotify_refresh_token = token_info["refresh_token"]
        config.spotify_access_token = token_info["access_token"]
        config.spotify_token_expires_at = token_info["expires_at"]
        db.commit()
        
        # Directe sync van Spotify smaakprofiel
        sync_spotify_preferences(db)
        
        return RedirectResponse(url="/")
    except Exception as e:
        return Response(content=f"Fout bij koppelen met Spotify: {e}", media_type="text/plain")

@app.post("/api/spotify/sync")
def trigger_spotify_sync(db: Session = Depends(get_db)):
    try:
        count = sync_spotify_preferences(db)
        return {"status": "success", "synced_artists": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 3. Podia (Venues) Routes
@app.get("/api/venues")
def get_venues(db: Session = Depends(get_db)):
    return db.query(Venue).order_by(Venue.name).all()

@app.post("/api/venues")
def create_venue(data: VenueCreateUpdate, db: Session = Depends(get_db)):
    exists = db.query(Venue).filter(Venue.name.ilike(data.name)).first()
    if exists:
        raise HTTPException(status_code=400, detail="Podium met deze naam bestaat al.")
        
    venue = Venue(**data.model_dump())
    db.add(venue)
    db.commit()
    db.refresh(venue)
    return venue

@app.put("/api/venues/{venue_id}")
def update_venue(venue_id: int, data: VenueCreateUpdate, db: Session = Depends(get_db)):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Podium niet gevonden.")
        
    venue.name = data.name
    venue.latitude = data.latitude
    venue.longitude = data.longitude
    venue.category = data.category
    venue.url = data.url
    venue.aliases = data.aliases
    
    db.commit()
    db.refresh(venue)
    return venue

@app.delete("/api/venues/{venue_id}")
def delete_venue(venue_id: int, db: Session = Depends(get_db)):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Podium niet gevonden.")
        
    db.delete(venue)
    db.commit()
    return {"status": "success"}

# Helper om concerten inclusief podium-relatie te formatteren voor JSON output
def format_concert(c: Concert):
    return {
        "id": c.id,
        "artist": c.artist,
        "date": c.date.isoformat() if c.date else None,
        "ticket_sale_start": c.ticket_sale_start.isoformat() if c.ticket_sale_start else None,
        "price": c.price,
        "url": c.url,
        "calculated_score": c.calculated_score,
        "status": c.status,
        "source": c.source,
        "venue": {
            "id": c.venue.id,
            "name": c.venue.name,
            "category": c.venue.category,
            "latitude": c.venue.latitude,
            "longitude": c.venue.longitude
        } if c.venue else None
    }

# 4. Concerten Routes
@app.get("/api/concerts")
def get_concerts(status: Optional[str] = None, min_score: Optional[float] = None, db: Session = Depends(get_db)):
    query = db.query(Concert)
    if status:
        query = query.filter(Concert.status == status)
    if min_score is not None:
        query = query.filter(Concert.calculated_score >= min_score)
        
    # Sorteren op score (hoogst eerst) en daarna datum (dichtstbijzijnde eerst)
    concerts = query.order_by(Concert.calculated_score.desc(), Concert.date.asc()).all()
    return [format_concert(c) for c in concerts]

@app.post("/api/concerts/{concert_id}/status")
def update_concert_status(concert_id: int, data: ConcertStatusUpdate, db: Session = Depends(get_db)):
    concert = db.query(Concert).filter(Concert.id == concert_id).first()
    if not concert:
        raise HTTPException(status_code=404, detail="Concert niet gevonden.")
        
    concert.status = data.status
    db.commit()
    db.refresh(concert)
    return format_concert(concert)

@app.post("/api/concerts/sync")
def trigger_feed_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Voer dit uit in een achtergrondtaak om timeout te voorkomen (geocoding kan even duren)
    def sync_job():
        sync_db = SessionLocal()
        try:
            new_count = parse_rss_feeds(sync_db)
            
            # Sync emails
            from app.services.email_receiver import fetch_and_parse_emails
            try:
                new_email_count = fetch_and_parse_emails(sync_db)
                new_count += new_email_count
            except Exception as email_err:
                print(f"Error fetching emails during manual sync: {email_err}")
                
            high_matches = score_all_new_concerts(sync_db)
            if high_matches:
                to_notify = [c for c in high_matches if not c.notified]
                if to_notify:
                    success = notify_new_concerts(sync_db, to_notify)
                    if success:
                        for c in to_notify:
                            c.notified = True
                        sync_db.commit()
        except Exception as e:
            print(f"Error manually triggered sync: {e}")
        finally:
            sync_db.close()
            
    background_tasks.add_task(sync_job)
    return {"status": "sync_triggered"}

@app.post("/api/concerts/parse-email")
def parse_email_newsletter(data: EmailParseRequest, db: Session = Depends(get_db)):
    try:
        extracted = parse_newsletter_with_gemini(db, data.email_text)
        
        user_config = db.query(UserConfig).first()
        if not user_config:
            raise HTTPException(status_code=400, detail="Gebruikersconfiguratie ontbreekt.")
            
        # Haal smaakprofiel op voor scoring
        top_artists = db.query(ArtistPreference).filter(ArtistPreference.source == "top_artist").all()
        top_genres_freq = {}
        for ta in top_artists:
            if ta.genres:
                for genre in ta.genres:
                    top_genres_freq[genre.lower()] = top_genres_freq.get(genre.lower(), 0) + ta.user_score
                    
        added_concerts = []
        
        # Loop door de geëxtraheerde concerten heen
        for item in extracted:
            from app.services.rss import find_or_create_venue
            # Zoek of maak podium
            venue = find_or_create_venue(db, item.venue)
            
            # Datum parsen
            try:
                if "T" in item.date:
                    concert_date = datetime.datetime.fromisoformat(item.date)
                else:
                    concert_date = datetime.datetime.strptime(item.date, "%Y-%m-%d")
            except Exception:
                concert_date = datetime.datetime.now() # Fallback
                
            # Kaartverkooptijdstip parsen
            sale_start = None
            if item.ticket_sale_start:
                try:
                    if "T" in item.ticket_sale_start:
                        sale_start = datetime.datetime.fromisoformat(item.ticket_sale_start)
                    else:
                        sale_start = datetime.datetime.strptime(item.ticket_sale_start, "%Y-%m-%d")
                except Exception:
                    pass

            # Controleer of het al bestaat
            start_of_day = datetime.datetime(concert_date.year, concert_date.month, concert_date.day)
            end_of_day = start_of_day + datetime.timedelta(days=1)
            
            exists = db.query(Concert).filter(
                Concert.artist.ilike(item.artist),
                Concert.venue_id == venue.id,
                Concert.date >= start_of_day,
                Concert.date < end_of_day
            ).first()
            
            if not exists:
                new_concert = Concert(
                    artist=item.artist,
                    venue_id=venue.id,
                    date=concert_date,
                    ticket_sale_start=sale_start,
                    price=item.price,
                    url=item.url,
                    source="newsletter_gemini",
                    status="new"
                )
                db.add(new_concert)
                db.commit()
                db.refresh(new_concert)
                
                # Direct scoren
                score = score_concert(db, new_concert, top_genres_freq, user_config)
                new_concert.calculated_score = score
                db.commit()
                db.refresh(new_concert)
                
                added_concerts.append(new_concert)
                
        return {
            "status": "success",
            "extracted_count": len(extracted),
            "added_count": len(added_concerts),
            "added_concerts": [format_concert(c) for c in added_concerts]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout bij verwerken nieuwsbrief: {e}")


# 5. Dynamic iCalendar Feed (.ics)
from icalendar import Calendar, Event
@app.get("/feed.ics")
def get_ics_feed(db: Session = Depends(get_db)):
    concerts = db.query(Concert).filter(Concert.status == "interested").all()
    
    cal = Calendar()
    cal.add('prodid', '-//Bandplanner Dynamic Calendar Feed//')
    cal.add('version', '2.0')
    
    for c in concerts:
        event = Event()
        venue_name = c.venue.name if c.venue else "Onbekend"
        event.add('summary', f"🎸 {c.artist} - {venue_name}")
        
        # We maken het een dag-evenement
        event.add('dtstart', c.date.date())
        event.add('dtend', c.date.date() + datetime.timedelta(days=1))
        
        description = f"Bandplanner Match Score: {c.calculated_score}/10\n"
        if c.price:
            description += f"Prijs: €{c.price:.2f}\n"
        if c.ticket_sale_start:
            description += f"Kaartverkoop start op: {c.ticket_sale_start.strftime('%d-%m-%Y om %H:%M')}\n"
        if c.url:
            description += f"Tickets & Info: {c.url}\n"
            event.add('url', c.url)
            
        event.add('description', description)
        if c.venue:
            event.add('location', f"{c.venue.name}, {c.venue.aliases or ''}")
            
        # Unieke ID voor de kalender
        event.add('uid', f"concert-{c.id}@bandplanner.local")
        
        cal.add_component(event)
        
    return Response(content=cal.to_ical(), media_type="text/calendar")

# Mount Static Files (voor frontend)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
