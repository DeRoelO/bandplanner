import time
from typing import Dict, Any, List
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ArtistPreference
from app.services.config_manager import load_user_config, save_user_config

def get_spotify_oauth(db: Session = None, redirect_uri: str = None) -> SpotifyOAuth:
    """
    Creëert de SpotifyOAuth manager op basis van instellingen uit het config.json volume of .env.
    """
    user_config = load_user_config()
    client_id = user_config.get("spotify_client_id") or settings.SPOTIFY_CLIENT_ID
    client_secret = user_config.get("spotify_client_secret") or settings.SPOTIFY_CLIENT_SECRET
    
    # Gebruik specifieke redirect_uri, of die uit config, of als fallback uit settings
    db_redirect = user_config.get("spotify_redirect_uri") or settings.SPOTIFY_REDIRECT_URI
    if db_redirect == "http://localhost:8080/callback":
        db_redirect = "http://127.0.0.1:8080/callback"
    final_redirect = redirect_uri or db_redirect
    
    if not client_id or not client_secret:
        raise ValueError("Spotify Client ID en Secret zijn niet geconfigureerd.")

    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=final_redirect,
        scope="user-top-read"
    )

def get_spotify_client(access_token: str) -> spotipy.Spotify:
    """
    Creëert een Spotipy client met het gegeven access token.
    """
    return spotipy.Spotify(auth=access_token)

def refresh_spotify_token(db: Session = None, user_config: Any = None) -> str:
    """
    Refresht het Spotify access token als dit is verlopen en slaat het op in config.json.
    Retourneert het geldige access token.
    """
    config = load_user_config()
    refresh_token = config.get("spotify_refresh_token")
    if not refresh_token:
        raise ValueError("Geen Spotify refresh token beschikbaar. Koppel eerst je Spotify account.")
        
    oauth = get_spotify_oauth()
    
    # Controleer of het token is verlopen of bijna is verlopen (binnen 60 seconden)
    now = int(time.time())
    access_token = config.get("spotify_access_token")
    expires_at = config.get("spotify_token_expires_at")
    if access_token and expires_at and (expires_at - now > 60):
        return access_token
        
    # Refresh het token
    token_info = oauth.refresh_access_token(refresh_token)
    
    # Sla de nieuwe tokens op in config.json
    config["spotify_access_token"] = token_info["access_token"]
    config["spotify_refresh_token"] = token_info.get("refresh_token", refresh_token)
    config["spotify_token_expires_at"] = token_info["expires_at"]
    
    save_user_config(config)
    return config["spotify_access_token"]


def sync_spotify_preferences(db: Session) -> int:
    """
    Synchroniseert de top artiesten en genres van de gebruiker met de database.
    """
    config = load_user_config()
    if not config or not config.get("spotify_refresh_token"):
        raise ValueError("Spotify is nog niet geconfigureerd of gekoppeld.")
        
    # Zorg dat we een geldig token hebben
    access_token = refresh_spotify_token()
    sp = get_spotify_client(access_token)
    
    # We halen top-artiesten op uit verschillende periodes voor een compleet beeld
    time_ranges = ["short_term", "medium_term", "long_term"]
    
    # Dictionary om scores op te bouwen: artiest_id -> {naam, popularity, genres, score}
    # Korte termijn artiesten wegen zwaarder dan lange termijn
    artist_data: Dict[str, Dict[str, Any]] = {}
    
    # Gewichten per tijdsperiode
    weights = {
        "short_term": 10.0,   # Meest relevant nu
        "medium_term": 7.0,   # Algemeen favoriet
        "long_term": 4.0      # Historische favoriet
    }
    
    for tr in time_ranges:
        try:
            results = sp.current_user_top_artists(limit=50, time_range=tr)
            items = results.get("items", [])
            for idx, item in enumerate(items):
                artist_id = item["id"]
                name = item["name"]
                popularity = item.get("popularity") or 50
                genres = item.get("genres") or []
                
                # Fallback naar MusicBrainz voor genres in Sandbox/Development mode
                if not genres:
                    from app.services.musicbrainz import get_artist_genres
                    genres = get_artist_genres(name)
                
                # Bereken een positie-gebaseerde score binnen deze lijst
                # Positie 1 krijgt max score, positie 50 krijgt min score
                position_score = (50 - idx) / 50.0  # 0.02 tot 1.0
                period_score = position_score * weights[tr]
                
                if artist_id in artist_data:
                    artist_data[artist_id]["score"] += period_score
                    # Voeg eventueel missende genres toe
                    existing_genres = set(artist_data[artist_id]["genres"])
                    existing_genres.update(genres)
                    artist_data[artist_id]["genres"] = list(existing_genres)
                else:
                    artist_data[artist_id] = {
                        "name": name,
                        "popularity": popularity,
                        "genres": genres,
                        "score": period_score
                    }
        except Exception as e:
            print(f"Fout bij ophalen Spotify top artists voor range {tr}: {e}")
            continue

    if not artist_data:
        return 0

    # Normaliseer scores naar een schaal van 0 tot 10
    max_accumulated_score = max(a["score"] for a in artist_data.values()) if artist_data else 1.0
    for a_id, data in artist_data.items():
        data["normalized_score"] = (data["score"] / max_accumulated_score) * 10.0

    # Schrijf naar de database (update bestaande, voeg nieuwe toe)
    # We verwijderen oude top_artist en genre_match voorkeuren om te vernieuwen
    # Maar handmatige voorkeuren behouden we!
    db.query(ArtistPreference).filter(ArtistPreference.source.in_(["top_artist", "genre_match"])).delete()
    
    # 1. Voeg top artiesten toe
    for artist_id, data in artist_data.items():
        pref = ArtistPreference(
            spotify_id=artist_id,
            name=data["name"],
            source="top_artist",
            genres=data["genres"],
            popularity=data["popularity"],
            user_score=data["normalized_score"]
        )
        db.add(pref)
        
    db.commit()
    return len(artist_data)
