# Bandplanner 🎸

Bandplanner is een lichtgewicht, zelf-gehoste applicatie die helpt bij het ontdekken en bijhouden van concerten en festivals in de buurt. De app analyseert concertgegevens en vergelijkt deze met jouw persoonlijke Spotify-luistergedrag en ingestelde thuislocatie. Zo mis je nooit meer een optreden van een favoriete of veelbelovende artiest in jouw regio!

## Kenmerken

1. **Afstandsbeoordeling op Maat**:
   - Stel je thuislocatie (coördinaten) in.
   - Definieer per type podium (klein, middel, groot) een maximale zoekstraal (bijv. binnen 25km voor kleine zalen, 60km voor middelgrote en 250km voor grote festivals).
   - Hoe dichterbij het concert is, hoe hoger de score.

2. **Spotify Integratie (OAuth)**:
   - Koppel eenvoudig je Spotify-account.
   - Bandplanner synchroniseert je top-artiesten (korte, middellange en lange termijn) en favoriete genres.
   - Artiesten die in je top-lijst staan of wiens genres matchen met jouw smaak, krijgen een hogere score.

3. **Automatische RSS Feeds**:
   - Synchroniseert automatisch met de agenda's van **Podiuminfo** en **Festivalinfo**.
   - Onbekende podia worden automatisch via OpenStreetMap Nominatim geolocaliseerd en toegevoegd aan je database.

4. **Nieuwsbrief Parser met Gemini AI**:
   - Plak de tekst of HTML van een willekeurige nieuwsbrief (bijv. van een lokaal theater of poppodium) in de app.
   - `gemini-2.5-flash` extraheert automatisch artiesten, data, zalen en ticketprijzen.

5. **Notificaties & Agenda Integratie**:
   - Ontvang e-mailnotificaties (via SMTP) zodra er concerten met een hoge match-score worden gevonden.
   - Dynamische `.ics`-feed om direct te importeren in Google Calendar, Apple Agenda of Outlook. Concerten die je als 'Geïnteresseerd' markeert verschijnen automatisch in je agenda.

---

## Installatie & Setup

### 1. Omgevingsvariabelen configureren

Maak een `.env` bestand aan in de hoofdmap van het project met de volgende variabelen:

```env
# Spotify API credentials (maak een app aan op developer.spotify.com)
# Stel de Redirect URI in op: http://localhost:8000/callback
SPOTIFY_CLIENT_ID=jouw_spotify_client_id
SPOTIFY_CLIENT_SECRET=jouw_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8000/callback

# Gemini API Key (verkrijg via aistudio.google.com)
GEMINI_API_KEY=jouw_gemini_api_key

# SMTP E-mail Notificaties (Optioneel)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=jouw_email@gmail.com
SMTP_PASSWORD=jouw_app_specifiek_wachtwoord
SMTP_FROM_EMAIL=bandplanner@jouwdomein.nl
SMTP_TO_EMAIL=jouw_persoonlijk_email@gmail.com
```

### 2. Draaien met Docker (Aanbevolen)

Je kunt de applicatie eenvoudig bouwen en draaien in een Docker container.

#### Bouwen:
```bash
docker build -t bandplanner .
```

#### Draaien:
Draai de container en koppel een volume voor persistente opslag van de SQLite database (`bandplanner.db`):

```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e DATABASE_URL=sqlite:////app/data/bandplanner.db \
  --env-file .env \
  --name bandplanner \
  bandplanner
```

Ga nu naar `http://localhost:8000` in je browser om de GUI te openen!

---

## Hosting op GitHub & CI/CD

Dit project bevat een GitHub Actions workflow (`.github/workflows/docker-publish.yml`) die automatisch een nieuwe Docker image bouwt en publiceert naar **GitHub Container Registry (GHCR)** bij elke push naar de `main` of `master` branch.

### Stappen om dit op te zetten:
1. Maak een nieuwe repository aan op GitHub: `https://github.com/DeRoelO/bandplanner`.
2. Push deze code naar de repository:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of Bandplanner"
   git remote add origin https://github.com/DeRoelO/bandplanner.git
   git branch -M main
   git push -u origin main
   ```
3. Zodra de push is voltooid, start de GitHub Actions workflow automatisch.
4. Je kunt de Docker container downloaden en draaien met:
   ```bash
   docker pull ghcr.io/deroelo/bandplanner:latest
   ```

---

## Licentie

Dit project is gelicenseerd onder de MIT-licentie.
