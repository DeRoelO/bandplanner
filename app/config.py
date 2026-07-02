import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///bandplanner.db"
    
    # Spotify API
    SPOTIFY_CLIENT_ID: str = Field(default="", validation_alias="SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET: str = Field(default="", validation_alias="SPOTIFY_CLIENT_SECRET")
    SPOTIFY_REDIRECT_URI: str = Field(default="http://localhost:8000/callback", validation_alias="SPOTIFY_REDIRECT_URI")
    
    # Gemini API
    GEMINI_API_KEY: str = Field(default="", validation_alias="GEMINI_API_KEY")
    
    # SMTP Email Notificaties
    SMTP_SERVER: str = Field(default="", validation_alias="SMTP_SERVER")
    SMTP_PORT: int = Field(default=587, validation_alias="SMTP_PORT")
    SMTP_USERNAME: str = Field(default="", validation_alias="SMTP_USERNAME")
    SMTP_PASSWORD: str = Field(default="", validation_alias="SMTP_PASSWORD")
    SMTP_FROM_EMAIL: str = Field(default="", validation_alias="SMTP_FROM_EMAIL")
    SMTP_TO_EMAIL: str = Field(default="", validation_alias="SMTP_TO_EMAIL")
    
    # Default User Config (als er niks in de DB staat)
    DEFAULT_HOME_LATITUDE: float = 52.0907  # Utrecht Centraal
    DEFAULT_HOME_LONGITUDE: float = 5.1214
    
    # Radii in km
    DEFAULT_RADIUS_SMALL: float = 25.0
    DEFAULT_RADIUS_MEDIUM: float = 60.0
    DEFAULT_RADIUS_LARGE: float = 250.0  # Tot bijv. Parijs/België
    
    # Scoring gewichten
    WEIGHT_DISTANCE: float = 0.3
    WEIGHT_ARTIST_TOP: float = 0.4
    WEIGHT_GENRE_MATCH: float = 0.2
    WEIGHT_POPULARITY: float = 0.1

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
