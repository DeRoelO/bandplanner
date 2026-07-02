import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Concert, Venue, ArtistPreference
from app.services.config_manager import load_user_config
from app.services.distance import calculate_haversine_distance
from app.services.spotify import get_spotify_client, refresh_spotify_token


def lookup_artist_on_spotify(db: Session, artist_name: str) -> Optional[ArtistPreference]:
    """
    Zoekt een artiest op via Spotify Search en slaat de resultaten op in de database.
    Dit cachet de genres en populariteit van de artiest.
    """
    user_config = load_user_config()
    if not user_config or not user_config.get("spotify_refresh_token"):
        # Spotify niet gekoppeld, we kunnen niet zoeken
        return None
        
    try:
        # Verkrijg geldige client
        access_token = refresh_spotify_token()
        sp = get_spotify_client(access_token)
        
        # Zoek artiest
        query = f"artist:{artist_name}"
        results = sp.search(q=query, type="artist", limit=1)
        items = results.get("artists", {}).get("items", [])
        
        if not items:
            # Probeer algemene zoekopdracht als specifieke artist: query faalt
            results = sp.search(q=artist_name, type="artist", limit=1)
            items = results.get("artists", {}).get("items", [])
            
        if items:
            item = items[0]
            spotify_id = item["id"]
            name = item["name"]
            popularity = item.get("popularity") or 50
            genres = item.get("genres") or []
            
            # Fallback naar MusicBrainz voor genres in Sandbox/Development mode
            if not genres:
                from app.services.musicbrainz import get_artist_genres
                genres = get_artist_genres(name)
            
            # Controleer of deze al bestaat onder een andere ID of naam
            existing = db.query(ArtistPreference).filter(ArtistPreference.spotify_id == spotify_id).first()
            if existing:
                return existing
                
            # Maak een gecachte voorkeur aan met bron 'genre_match'
            # De score is initieel 0.0, deze wordt berekend in de score_concert functie
            pref = ArtistPreference(
                spotify_id=spotify_id,
                name=name,
                source="genre_match",
                genres=genres,
                popularity=popularity,
                user_score=0.0
            )
            db.add(pref)
            db.commit()
            db.refresh(pref)
            return pref
    except Exception as e:
        print(f"Fout bij opzoeken artiest '{artist_name}' op Spotify: {e}")
        
    return None

def calculate_genre_match_score(artist_genres: List[str], top_genres_freq: dict) -> float:
    """
    Berekent een score (0-10) op basis van de match tussen de genres van de artiest en de topgenres van de gebruiker.
    """
    if not artist_genres or not top_genres_freq:
        return 0.0
        
    match_count = 0
    total_weight = 0.0
    
    # We lopen door de genres van de artiest heen
    for genre in artist_genres:
        genre_lower = genre.lower()
        # Als er een exacte match is
        if genre_lower in top_genres_freq:
            match_count += 1
            total_weight += top_genres_freq[genre_lower]
        else:
            # Probeer gedeeltelijke match (bijv. "indie rock" matcht met "rock")
            for top_g, freq in top_genres_freq.items():
                if top_g in genre_lower or genre_lower in top_g:
                    match_count += 0.5
                    total_weight += freq * 0.5
                    break # Voorkom dubbeltelling per artiestgenre
                    
    if match_count == 0:
        return 0.0
        
    # Bereken gemiddelde match score. We normaliseren dit
    # Als een artiest 1 of meer genres heeft die veel voorkomen in de top van de gebruiker, scoort hij hoog.
    max_freq = max(top_genres_freq.values()) if top_genres_freq else 1.0
    normalized_weight = (total_weight / len(artist_genres)) / max_freq
    return min(10.0, normalized_weight * 10.0)

def score_concert(db: Session, concert: Concert, top_genres_freq: dict, user_config: Optional[dict] = None) -> float:
    """
    Berekent de totale match-score voor een concert.
    """
    if not user_config:
        user_config = load_user_config()
        
    # 1. AFSTANDSSCORE (0-10)
    distance_score = 0.0
    if concert.venue:
        home_latitude = user_config.get("home_latitude", 52.0907)
        home_longitude = user_config.get("home_longitude", 5.1214)
        distance = calculate_haversine_distance(
            home_latitude, home_longitude,
            concert.venue.latitude, concert.venue.longitude
        )
        
        # Bepaal max radius op basis van categorie
        category = concert.venue.category
        if category == "small":
            max_radius = user_config.get("radius_small", 25.0)
        elif category == "medium":
            max_radius = user_config.get("radius_medium", 60.0)
        else: # large
            max_radius = user_config.get("radius_large", 250.0)
            
        if distance <= max_radius:
            # Kortere afstand = hogere score
            distance_score = 10.0 * (1.0 - (distance / max_radius))
        else:
            # Te ver weg
            distance_score = 0.0
    else:
        # Geen venue bekend
        distance_score = 0.0

    # 2. SPOTIFY SCORES
    artist_score = 0.0
    genre_score = 0.0
    popularity_score = 0.0
    
    # Zoek artiest in onze database
    pref = db.query(ArtistPreference).filter(ArtistPreference.name.ilike(concert.artist)).first()
    
    # Als we de artiest niet kennen, proberen we hem op te zoeken op Spotify
    if not pref:
        pref = lookup_artist_on_spotify(db, concert.artist)
        
    if pref:
        # Als de artiest uit de 'top_artist' of 'manual' lijst komt, gebruiken we zijn user_score
        if pref.source in ["top_artist", "manual"]:
            artist_score = pref.user_score
            # Voor favoriete artiesten matchen genres automatisch maximaal
            genre_score = 10.0
        else:
            # Gevonden via search (genre_match), bereken genre match score
            artist_score = 0.0
            genre_score = calculate_genre_match_score(pref.genres or [], top_genres_freq)
            
        # Populariteitsscore (0-10)
        popularity_score = (pref.popularity or 0) / 10.0
    else:
        # Niet gevonden op Spotify
        artist_score = 0.0
        genre_score = 0.0
        popularity_score = 0.0

    # Totaalscore berekenen op basis van gewichten
    total_score = (settings.WEIGHT_DISTANCE * distance_score) + \
                  (settings.WEIGHT_ARTIST_TOP * artist_score) + \
                  (settings.WEIGHT_GENRE_MATCH * genre_score) + \
                  (settings.WEIGHT_POPULARITY * popularity_score)
                  
    # Afronden op 1 decimaal
    return round(total_score, 1)

def score_all_new_concerts(db: Session) -> List[Concert]:
    """
    Berekent de score voor alle concerten die nog de status 'new' hebben.
    Retourneert de lijst met concerten die een hoge score hebben behaald (bijv. >= 6.0).
    """
    user_config = load_user_config()
    if not user_config:
        # Geen config, we kunnen niks scoren
        return []
        
    # Haal alle top genres van de gebruiker op om frequentie te bepalen
    top_artists = db.query(ArtistPreference).filter(ArtistPreference.source == "top_artist").all()
    
    top_genres_freq = {}
    for ta in top_artists:
        if ta.genres:
            for genre in ta.genres:
                genre_lower = genre.lower()
                top_genres_freq[genre_lower] = top_genres_freq.get(genre_lower, 0) + ta.user_score

    # Haal alle concerten op met status 'new'
    new_concerts = db.query(Concert).filter(Concert.status == "new").all()
    
    high_match_concerts = []
    
    for c in new_concerts:
        score = score_concert(db, c, top_genres_freq, user_config)
        c.calculated_score = score
        # Zet status naar 'new' (we bewaren de status, maar de score is nu berekend)
        # We kunnen ze direct beoordelen als 'geïnteresseerd' als ze heel hoog scoren, 
        # maar het is beter om de gebruiker dit te laten bepalen in de GUI.
        # Wel filteren we hoge scores voor de e-mail notificatie!
        if score >= 6.5:
            high_match_concerts.append(c)
            
    db.commit()
    return high_match_concerts
