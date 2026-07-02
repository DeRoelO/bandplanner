import json
import os
from typing import Dict, Any

CONFIG_FILE = "/app/data/config.json"

DEFAULT_CONFIG = {
    "home_latitude": 52.0907,
    "home_longitude": 5.1214,
    "radius_small": 25.0,
    "radius_medium": 60.0,
    "radius_large": 250.0,
    
    # Keys
    "gemini_api_key": "",
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "spotify_redirect_uri": "http://127.0.0.1:8080/callback",
    
    # Spotify Tokens (stored inside this file for absolute persistence)
    "spotify_refresh_token": None,
    "spotify_access_token": None,
    "spotify_token_expires_at": None,
    
    # SMTP
    "smtp_server": "",
    "smtp_port": 587,
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from_email": "",
    "smtp_to_email": "",
    
    # IMAP
    "imap_server": "",
    "imap_port": 993,
    "imap_username": "",
    "imap_password": "",
    "imap_enabled": False
}

def load_user_config() -> Dict[str, Any]:
    """Loads the user configuration from the Docker volume, creating it with defaults if it doesn't exist."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    
    if not os.path.exists(CONFIG_FILE):
        save_user_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
        
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # Ensure all default config keys exist in the loaded data
            updated = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
                    updated = True
            
            # Migrate any legacy 'localhost' redirect URI default
            if data.get("spotify_redirect_uri") == "http://localhost:8080/callback":
                data["spotify_redirect_uri"] = "http://127.0.0.1:8080/callback"
                updated = True
                
            if updated:
                save_user_config(data)
            return data
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return DEFAULT_CONFIG

def save_user_config(config_data: Dict[str, Any]) -> None:
    """Saves the configuration dictionary to the persistent config.json file."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config.json: {e}")
