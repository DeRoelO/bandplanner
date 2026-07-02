import math

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Berekent de afstand tussen twee GPS-coördinaten in kilometers met behulp van de Haversine-formule.
    """
    # Straal van de aarde in km
    R = 6371.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
        
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    
    distance = R * c
    return distance

def geocode_location(query: str) -> tuple[float, float] | None:
    """
    Zoekt coördinaten op via OpenStreetMap Nominatim API.
    """
    import urllib.parse
    import requests
    
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=1"
        headers = {"User-Agent": "BandplannerApp/1.0 (contact: github.com/DeRoelO/bandplanner)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"Fout bij geocoding van '{query}': {e}")
    return None

