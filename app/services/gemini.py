from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from sqlalchemy.orm import Session
from app.config import settings
from app.models import UserConfig

class ExtractedConcert(BaseModel):
    artist: str = Field(description="De naam van de artiest, band of act.")
    date: str = Field(description="De datum van het concert in ISO 8601 formaat (YYYY-MM-DD). Als er ook een tijd bekend is, gebruik dan YYYY-MM-DDTHH:MM:SS.")
    venue: str = Field(description="De naam van de locatie of het poppodium.")
    ticket_sale_start: Optional[str] = Field(None, description="De datum/tijd waarop de kaartverkoop start in ISO 8601 formaat (indien vermeld).")
    price: Optional[float] = Field(None, description="De prijs van een ticket in Euro's (alleen getal, bijv. 29.50) (indien vermeld).")
    url: Optional[str] = Field(None, description="De URL voor tickets of meer info (indien vermeld).")

class ExtractedConcertList(BaseModel):
    concerts: List[ExtractedConcert] = Field(description="Een lijst met alle concerten die in de tekst zijn gevonden.")

def parse_newsletter_with_gemini(db: Session, text_content: str) -> List[ExtractedConcert]:
    """
    Stuurt de tekst van een nieuwsbrief naar Gemini om concerten en ticketinformatie te extraheren.
    """
    user_config = db.query(UserConfig).first()
    api_key = user_config.gemini_api_key if user_config and user_config.gemini_api_key else settings.GEMINI_API_KEY
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY is niet ingesteld in de database of .env.")

    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Analyseer de onderstaande nieuwsbrief of e-mailtekst van een poppodium of festival.
    Extraheer alle concerten, optredens, acts of evenementen die erin genoemd worden.
    
    Probeer zo accuraat mogelijk te zijn met datums (vertaal Nederlandse datums zoals '12 oktober 2026' of 'vrijdag 5 juni' naar het juiste jaartal en ISO formaat. Let op: het huidige jaar is 2026).
    Als het jaartal niet expliciet vermeld wordt, neem dan aan dat het in 2026 of begin 2027 plaatsvindt op basis van de context.
    
    Tekst om te analyseren:
    ---
    {text_content}
    ---
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedConcertList,
            temperature=0.1
        )
    )
    
    try:
        if response.parsed:
            return response.parsed.concerts
        else:
            import json
            data = json.loads(response.text)
            parsed_list = ExtractedConcertList(**data)
            return parsed_list.concerts
    except Exception as e:
        print(f"Fout bij het parsen van Gemini respons: {e}")
        print(f"Ruwe respons: {response.text}")
        return []

