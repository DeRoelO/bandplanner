import requests
import time
from typing import List

# MusicBrainz vraagt om een duidelijke User-Agent
HEADERS = {
    "User-Agent": "Bandplanner/1.0.0 (https://github.com/DeRoelO/bandplanner)"
}

# Eenvoudige in-memory cache om herhaalde requests binnen dezelfde run te voorkomen
_genres_cache = {}

def get_artist_genres(artist_name: str) -> List[str]:
    """
    Haalt genres/tags op voor een artiest via de gratis, openbare MusicBrainz API.
    Dit dient als fallback aangezien Spotify's Web API geen genres meer levert in Sandbox/Development mode.
    """
    if not artist_name:
        return []
        
    name_key = artist_name.strip().lower()
    if name_key in _genres_cache:
        return _genres_cache[name_key]
        
    try:
        # MusicBrainz API rate-limit is max 1 request per seconde, dus we bouwen een kleine delay in
        time.sleep(0.5)
        
        url = f"https://musicbrainz.org/ws/2/artist/?query=artist:{requests.utils.quote(artist_name)}&fmt=json"
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"[MusicBrainz] API error {response.status_code} voor '{artist_name}'")
            return []
            
        data = response.json()
        artists = data.get("artists", [])
        if not artists:
            return []
            
        # We pakken de eerste/beste match
        best_match = artists[0]
        tags = best_match.get("tags", [])
        
        # Filter tags die wijzen op genres
        genres = []
        for tag in tags:
            name = tag.get("name", "").lower()
            # Optioneel: filter nutteloze tags zoals landnamen als dat nodig is,
            # maar voor matching zijn brede tags prima
            if name and not name.isdigit() and len(name) > 2:
                genres.append(name)
                
        _genres_cache[name_key] = genres
        print(f"[MusicBrainz] Genres opgehaald voor '{artist_name}': {genres}")
        return genres
    except Exception as e:
        print(f"[MusicBrainz] Fout bij ophalen genres voor '{artist_name}': {e}")
        return []
