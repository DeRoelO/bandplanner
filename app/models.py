import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class UserConfig(Base):
    __tablename__ = "user_config"

    id = Column(Integer, primary_key=True, index=True)
    home_latitude = Column(Float, nullable=False, default=52.0907)
    home_longitude = Column(Float, nullable=False, default=5.1214)
    radius_small = Column(Float, nullable=False, default=25.0)
    radius_medium = Column(Float, nullable=False, default=60.0)
    radius_large = Column(Float, nullable=False, default=250.0)
    
    # Spotify Tokens
    spotify_refresh_token = Column(String, nullable=True)
    spotify_access_token = Column(String, nullable=True)
    spotify_token_expires_at = Column(Integer, nullable=True)

    # API Sleutels & Credentials (instelbaar via GUI)
    gemini_api_key = Column(String, nullable=True)
    spotify_client_id = Column(String, nullable=True)
    spotify_client_secret = Column(String, nullable=True)
    spotify_redirect_uri = Column(String, nullable=True, default="http://localhost:8080/callback")
    
    # SMTP Config (instelbaar via GUI)
    smtp_server = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True, default=587)
    smtp_username = Column(String, nullable=True)
    smtp_password = Column(String, nullable=True)
    smtp_from_email = Column(String, nullable=True)
    smtp_to_email = Column(String, nullable=True)
    
    # IMAP Mailbox Config (automatisch inlezen nieuwsbrieven)
    imap_server = Column(String, nullable=True)
    imap_port = Column(Integer, nullable=True, default=993)
    imap_username = Column(String, nullable=True)
    imap_password = Column(String, nullable=True)
    imap_enabled = Column(Boolean, nullable=False, default=False)



class Venue(Base):
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    category = Column(String, nullable=False)  # 'small', 'medium', 'large'
    url = Column(String, nullable=True)
    aliases = Column(String, nullable=True)  # Comma-separated alternative names for matching

    concerts = relationship("Concert", back_populates="venue")

class ArtistPreference(Base):
    __tablename__ = "artist_preferences"

    spotify_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)  # 'top_artist', 'genre_match', 'manual'
    genres = Column(JSON, nullable=True)  # List of genres
    popularity = Column(Integer, nullable=True)  # Spotify popularity index (0-100)
    top_track_streams = Column(Integer, nullable=True)  # Optioneel
    user_score = Column(Float, nullable=False, default=0.0)  # Berekening gebaseerd op luistergedrag/bron
    last_synced = Column(DateTime, default=datetime.datetime.utcnow)

class Concert(Base):
    __tablename__ = "concerts"

    id = Column(Integer, primary_key=True, index=True)
    artist = Column(String, nullable=False, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=True)
    date = Column(DateTime, nullable=False)
    ticket_sale_start = Column(DateTime, nullable=True)
    price = Column(Float, nullable=True)
    url = Column(String, nullable=True)
    
    calculated_score = Column(Float, default=0.0)
    status = Column(String, default="new")  # 'new', 'ignored', 'interested'
    notified = Column(Boolean, default=False)
    
    source = Column(String, nullable=True)  # 'rss_podiuminfo', 'rss_festivalinfo', 'newsletter_gemini', etc.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    venue = relationship("Venue", back_populates="concerts")
