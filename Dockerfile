FROM python:3.11-slim

# Omgevingsvariabelen instellen voor Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Werkmap instellen
WORKDIR /app

# Systeemafhankelijkheden installeren
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Kopieer requirements en installeer python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Kopieer applicatiecode
COPY app/ ./app/

# Aanmaken van een niet-root gebruiker voor veiligheid
RUN useradd -u 1000 appuser && \
    chown -R appuser:appuser /app

# Overschakelen naar de niet-root gebruiker
USER appuser

# Expose de poort waarop FastAPI draait
EXPOSE 8000

# Start commando
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
