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
from app.services.config_manager import load_user_config, save_user_config
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
            
            # 1. Sync RSS feeds
            def sync_rss_task():
                db = SessionLocal()
                try:
                    return parse_rss_feeds(db)
                finally:
                    db.close()
            new_count = await asyncio.to_thread(sync_rss_task)
            
            # 2. Sync IMAP email newsletters
            def sync_email_task():
                db = SessionLocal()
                try:
                    from app.services.email_receiver import fetch_and_parse_emails
                    return fetch_and_parse_emails(db)
                except Exception as email_err:
                    print(f"[Background Task] Fout bij ophalen e-mails: {email_err}")
                    return 0
                finally:
                    db.close()
            new_count += await asyncio.to_thread(sync_email_task)
            
            # 2b. Run custom scrapers
            def run_scrapers_task():
                db = SessionLocal()
                try:
                    from app.services.scraper_manager import run_custom_scraper
                    venues_with_scrapers = db.query(Venue).filter(Venue.scraper_url != None, Venue.scraper_enabled == True).all()
                    for venue in venues_with_scrapers:
                        try:
                            # Note: run scrapers sequentially inside this thread to avoid concurrency issues
                            run_custom_scraper(db, venue)
                        except Exception as scraper_err:
                            print(f"[Background Task] Fout bij draaien scraper voor '{venue.name}': {scraper_err}")
                finally:
                    db.close()
            await asyncio.to_thread(run_scrapers_task)
            
            # 3. Score nieuwe concerten
            def score_task():
                db = SessionLocal()
                try:
                    return score_all_new_concerts(db)
                finally:
                    db.close()
            high_matches = await asyncio.to_thread(score_task)
            
            # 4. Verstuur e-mails voor nieuwe aanbevelingen
            if high_matches:
                def notify_task():
                    db = SessionLocal()
                    try:
                        to_notify = [c for c in high_matches if not c.notified]
                        if to_notify:
                            success = notify_new_concerts(db, to_notify)
                            if success:
                                for c in to_notify:
                                    c.notified = True
                                db.commit()
                                print(f"[Background Task] E-mail verstuurd voor {len(to_notify)} concerten.")
                    finally:
                        db.close()
                await asyncio.to_thread(notify_task)
                
            # 5. Enrich unknown artists in the background via Spotify
            def enrich_task():
                db = SessionLocal()
                try:
                    from app.services.spotify import enrich_unknown_artists
                    enrich_unknown_artists(db)
                except Exception as enrich_err:
                    print(f"[Background Task] Fout bij verrijken artiesten: {enrich_err}")
                finally:
                    db.close()
            await asyncio.to_thread(enrich_task)
                
        except asyncio.CancelledError:
            print("[Background Task] Synchronisatie loop geannuleerd.")
            break
        except Exception as e:
            print(f"[Background Task] Fout tijdens sync loop: {e}")
            # Stuur een e-mail notificatie over de fout
            db_err = SessionLocal()
            try:
                notify_parser_error(db_err, f"Fout in automatische sync loop:\n{e}")
            finally:
                db_err.close()
        
        # Elke 12 uur synchroniseren
        print("[Background Task] Volgende sync over 12 uur.")
        await asyncio.sleep(12 * 3600)


def apply_automatic_migrations(db_engine):
    from sqlalchemy import inspect, text
    inspector = inspect(db_engine)
    
    # Check if venues columns need migrating
    if inspector.has_table("venues"):
        venue_cols = [c["name"] for c in inspector.get_columns("venues")]
        try:
            with db_engine.connect() as conn:
                if "scraper_url" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_url VARCHAR"))
                if "scraper_code" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_code VARCHAR"))
                if "scraper_enabled" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_enabled BOOLEAN DEFAULT 1"))
                if "scraper_last_run" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_last_run DATETIME"))
                if "scraper_last_status" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_last_status VARCHAR"))
                if "scraper_error_log" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_error_log VARCHAR"))
                if "scraper_strategy" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_strategy VARCHAR"))
                if "scraper_config" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_config JSON"))
                if "scraper_event_count" not in venue_cols:
                    conn.execute(text("ALTER TABLE venues ADD COLUMN scraper_event_count INTEGER"))
                conn.commit()
        except Exception as err:
            print(f"Fout bij migreren venues tabel: {err}")

    # Als de tabel er nog niet is, doet create_all het werk
    if not inspector.has_table("user_config"):
        return
        
    columns = [c["name"] for c in inspector.get_columns("user_config")]
    
    try:
        with db_engine.connect() as conn:
            # Keys
            if "gemini_api_key" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN gemini_api_key VARCHAR"))
            if "spotify_client_id" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN spotify_client_id VARCHAR"))
            if "spotify_client_secret" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN spotify_client_secret VARCHAR"))
            if "spotify_redirect_uri" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN spotify_redirect_uri VARCHAR"))
                
            # SMTP
            if "smtp_server" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN smtp_server VARCHAR"))
            if "smtp_port" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN smtp_port INTEGER"))
            if "smtp_username" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN smtp_username VARCHAR"))
            if "smtp_password" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN smtp_password VARCHAR"))
            if "smtp_from_email" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN smtp_from_email VARCHAR"))
            if "smtp_to_email" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN smtp_to_email VARCHAR"))
                
            # IMAP
            if "imap_server" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN imap_server VARCHAR"))
            if "imap_port" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN imap_port INTEGER"))
            if "imap_username" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN imap_username VARCHAR"))
            if "imap_password" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN imap_password VARCHAR"))
            if "imap_enabled" not in columns:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN imap_enabled BOOLEAN DEFAULT 0"))
                
            conn.commit()
            
            # Venues Table city migration
            columns_venues = [c["name"] for c in inspector.get_columns("venues")]
            if "city" not in columns_venues:
                conn.execute(text("ALTER TABLE venues ADD COLUMN city VARCHAR"))
                conn.commit()
                
            print("Automatische database schema-migratie voltooid.")
    except Exception as err:
        print(f"Fout bij uitvoeren van automatische database migratie: {err}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Opstarten database & seeden
    db = SessionLocal()
    try:
        from app.database import Base, engine
        from app.seed_venues import seed_data
        
        # Zorg dat config.json bestaat
        load_user_config()
        
        Base.metadata.create_all(bind=engine)
        apply_automatic_migrations(engine)
        seed_data(db)
        print("Database geïnitialiseerd, config.json geladen en podia geseed.")
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
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    category: str
    url: Optional[str] = None
    aliases: Optional[str] = ""
    
    # Scraper config
    scraper_url: Optional[str] = None
    scraper_code: Optional[str] = None
    scraper_enabled: Optional[bool] = True

class ConcertStatusUpdate(BaseModel):
    status: str  # 'new', 'ignored', 'interested'

class EmailParseRequest(BaseModel):
    email_text: str

# --- API Routes ---
# 1. Configuur Routes
@app.get("/api/config")
def get_config():
    return load_user_config()

@app.post("/api/config")
def update_config(data: ConfigUpdate, db: Session = Depends(get_db)):
    config_dict = data.model_dump()
    save_user_config(config_dict)
    
    # Herscore alle concerten met status 'new' omdat de locatie/radii zijn veranderd
    from app.services.scoring import score_all_new_concerts
    score_all_new_concerts(db)
    
    return config_dict

# 2. Spotify Auth & Sync Routes
@app.get("/api/spotify/status")
def get_spotify_status(db: Session = Depends(get_db)):
    config = load_user_config()
    
    client_id = config.get("spotify_client_id") or settings.SPOTIFY_CLIENT_ID
    connected = config.get("spotify_refresh_token") is not None
    
    pref_count = db.query(ArtistPreference).filter(
        ArtistPreference.source == "top_artist"
    ).count()
    
    genre_count = db.query(ArtistPreference).filter(
        ArtistPreference.source == "genre_match"
    ).count()
    
    db_redirect = config.get("spotify_redirect_uri") or settings.SPOTIFY_REDIRECT_URI
    if db_redirect == "http://localhost:8080/callback":
        db_redirect = "http://127.0.0.1:8080/callback"
    
    return {
        "connected": connected,
        "top_artists_count": pref_count,
        "cached_artists_count": genre_count,
        "redirect_uri": db_redirect,
        "client_id_configured": bool(client_id)
    }

@app.get("/login/spotify")
def login_spotify():
    config = load_user_config()
    client_id = config.get("spotify_client_id") or settings.SPOTIFY_CLIENT_ID
    client_secret = config.get("spotify_client_secret") or settings.SPOTIFY_CLIENT_SECRET
    
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400, 
            detail="Spotify Client ID en Secret zijn niet geconfigureerd."
        )
    oauth = get_spotify_oauth()
    auth_url = oauth.get_authorize_url()
    return RedirectResponse(url=auth_url)

@app.get("/callback")
def spotify_callback(code: str, db: Session = Depends(get_db)):
    oauth = get_spotify_oauth()
    try:
        token_info = oauth.get_access_token(code, as_dict=True)
        config = load_user_config()
        
        config["spotify_refresh_token"] = token_info["refresh_token"]
        config["spotify_access_token"] = token_info["access_token"]
        config["spotify_token_expires_at"] = token_info["expires_at"]
        save_user_config(config)
        
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
def create_venue(data: VenueCreateUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    exists = db.query(Venue).filter(Venue.name.ilike(data.name)).first()
    if exists:
        raise HTTPException(status_code=400, detail="Podium met deze naam bestaat al.")
        
    lat = data.latitude
    lon = data.longitude
    
    if (lat is None or lon is None or (lat == 0.0 and lon == 0.0)) and data.city:
        from app.services.distance import geocode_location
        coords = geocode_location(data.city)
        if coords:
            lat, lon = coords
        else:
            raise HTTPException(status_code=400, detail=f"Kon coördinaten voor '{data.city}' niet vinden via OpenStreetMap.")
    elif lat is None or lon is None:
        # Utrecht fallback
        lat = 52.0907
        lon = 5.1214

    venue = Venue(
        name=data.name,
        latitude=lat,
        longitude=lon,
        city=data.city,
        category=data.category,
        url=data.url,
        aliases=data.aliases,
        scraper_url=data.scraper_url,
        scraper_code=data.scraper_code,
        scraper_enabled=data.scraper_enabled if data.scraper_enabled is not None else True
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)
    
    if venue.scraper_url:
        from app.services.scraper_manager import run_custom_scraper
        def initial_run():
            sync_db = SessionLocal()
            try:
                v = sync_db.query(Venue).filter(Venue.id == venue.id).first()
                if v:
                    run_custom_scraper(sync_db, v)
                    from app.services.spotify import enrich_unknown_artists
                    enrich_unknown_artists(sync_db)
            finally:
                sync_db.close()
        background_tasks.add_task(initial_run)
        
    return venue

@app.put("/api/venues/{venue_id}")
def update_venue(venue_id: int, data: VenueCreateUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Podium niet gevonden.")
        
    had_scraper = venue.scraper_url is not None
    
    lat = data.latitude
    lon = data.longitude
    
    if (lat is None or lon is None or (lat == 0.0 and lon == 0.0)) and data.city:
        from app.services.distance import geocode_location
        coords = geocode_location(data.city)
        if coords:
            lat, lon = coords
        else:
            raise HTTPException(status_code=400, detail=f"Kon coördinaten voor '{data.city}' niet vinden via OpenStreetMap.")
            
    venue.name = data.name
    venue.city = data.city
    if lat is not None:
        venue.latitude = lat
    if lon is not None:
        venue.longitude = lon
    venue.category = data.category
    venue.url = data.url
    venue.aliases = data.aliases
    
    # Scraper config
    old_scraper_url = venue.scraper_url
    venue.scraper_url = data.scraper_url
    venue.scraper_code = data.scraper_code
    venue.scraper_enabled = data.scraper_enabled if data.scraper_enabled is not None else True
    # Reset opgeslagen strategie als de URL is veranderd zodat discovery opnieuw draait
    if data.scraper_url != old_scraper_url:
        venue.scraper_strategy = None
        venue.scraper_config = None
        venue.scraper_event_count = None
    
    db.commit()
    db.refresh(venue)
    
    if venue.scraper_url and (not had_scraper or data.scraper_url != venue.scraper_url):
        from app.services.scraper_manager import run_custom_scraper
        def initial_run():
            sync_db = SessionLocal()
            try:
                v = sync_db.query(Venue).filter(Venue.id == venue.id).first()
                if v:
                    run_custom_scraper(sync_db, v)
                    from app.services.spotify import enrich_unknown_artists
                    enrich_unknown_artists(sync_db)
            finally:
                sync_db.close()
        background_tasks.add_task(initial_run)
        
    return venue

@app.post("/api/venues/{venue_id}/run_scraper")
def trigger_venue_scraper_run(venue_id: int, background_tasks: BackgroundTasks, force_heal: bool = False, db: Session = Depends(get_db)):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Podium niet gevonden.")
    if not venue.scraper_url:
        raise HTTPException(status_code=400, detail="Dit podium heeft geen scraper geconfigureerd.")
        
    from app.services.scraper_manager import run_custom_scraper
    def manual_run():
        sync_db = SessionLocal()
        try:
            v = sync_db.query(Venue).filter(Venue.id == venue_id).first()
            if v:
                run_custom_scraper(sync_db, v, force_heal=force_heal)
                from app.services.spotify import enrich_unknown_artists
                enrich_unknown_artists(sync_db)
        finally:
            sync_db.close()
            
    background_tasks.add_task(manual_run)
    return {"status": "sync_triggered"}


@app.post("/api/venues/{venue_id}/discover")
def trigger_discovery(venue_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Voert onboarding-discovery uit voor een podium: zoekt de beste databron en slaat de strategie op."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Podium niet gevonden.")
    if not venue.scraper_url:
        raise HTTPException(status_code=400, detail="Dit podium heeft geen scraper URL geconfigureerd.")

    def discovery_run():
        from app.services import discovery
        sync_db = SessionLocal()
        try:
            v = sync_db.query(Venue).filter(Venue.id == venue_id).first()
            if not v:
                return
            # Reset eerst zodat discovery opnieuw begint
            v.scraper_strategy = None
            v.scraper_config = None
            sync_db.commit()
            # Voer discovery + initiële scrape uit
            from app.services.scraper_manager import run_custom_scraper
            run_custom_scraper(sync_db, v)
            from app.services.spotify import enrich_unknown_artists
            enrich_unknown_artists(sync_db)
        except Exception as err:
            print(f"[Discovery] Fout bij onboarding van '{venue_id}': {err}")
        finally:
            sync_db.close()

    background_tasks.add_task(discovery_run)
    return {"status": "discovery_triggered"}

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
                
            # Run custom scrapers
            from app.services.scraper_manager import run_custom_scraper
            venues_with_scrapers = sync_db.query(Venue).filter(Venue.scraper_url != None, Venue.scraper_enabled == True).all()
            for venue in venues_with_scrapers:
                try:
                    run_custom_scraper(sync_db, venue)
                except Exception as scraper_err:
                    print(f"Error running scraper for '{venue.name}' during manual sync: {scraper_err}")
                
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
        
        user_config = load_user_config()
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
            if not venue:
                continue
            
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
