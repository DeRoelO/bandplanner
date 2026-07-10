import imaplib
import email
from email.header import decode_header
import bs4
from sqlalchemy.orm import Session
from app.models import Concert, ArtistPreference
from app.config import settings
from app.services.gemini import parse_newsletter_with_gemini
from app.services.rss import find_or_create_venue
from app.services.scoring import score_concert
from app.services.config_manager import load_user_config
import datetime

def clean_html(html_content: str) -> str:
    """
    Zet HTML content om naar platte tekst en verwijdert overbodige witruimtes en scripts
    zodat het aantal tokens voor Gemini beperkt blijft.
    """
    try:
        soup = bs4.BeautifulSoup(html_content, "html.parser")
        
        # Verwijder scripts en styles
        for script in soup(["script", "style"]):
            script.decompose()
            
        text = soup.get_text(separator=" ")
        
        # Witruimtes opschonen
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)
        return text
    except Exception as e:
        print(f"Fout bij HTML opschonen: {e}")
        return html_content

def fetch_and_parse_emails(db: Session) -> int:
    """
    Verbindt met de geconfigureerde IMAP mailbox, haalt ongelezen e-mails op,
    stuurt ze naar Gemini en voegt gevonden concerten toe aan de database.
    """
    user_config = load_user_config()
    if not user_config:
        return 0
        
    imap_server = user_config.get("imap_server", "")
    imap_port = user_config.get("imap_port", 993)
    imap_username = user_config.get("imap_username", "")
    imap_password = user_config.get("imap_password", "")
    imap_enabled = user_config.get("imap_enabled", False)
    
    if not imap_enabled or not imap_server or not imap_username or not imap_password:
        print("IMAP e-mailontvangst is niet ingeschakeld of niet volledig geconfigureerd.")
        return 0
        
    added_total = 0
    
    try:
        # Verbinden met de IMAP server
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(imap_username, imap_password)
        mail.select("inbox")
        
        # Zoek naar ongelezen e-mails
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            print("Fout bij het zoeken naar ongelezen e-mails.")
            return 0
            
        mail_ids = messages[0].split()
        print(f"[IMAP] {len(mail_ids)} ongelezen e-mails gevonden.")
        
        if not mail_ids:
            mail.close()
            mail.logout()
            return 0
            
        # Smaakprofiel ophalen voor scoring
        top_artists = db.query(ArtistPreference).filter(ArtistPreference.source == "top_artist").all()
        top_genres_freq = {}
        for ta in top_artists:
            if ta.genres:
                for genre in ta.genres:
                    top_genres_freq[genre.lower()] = top_genres_freq.get(genre.lower(), 0) + ta.user_score

        for mail_id in mail_ids:
            try:
                # E-mail ophalen
                status, data = mail.fetch(mail_id, '(RFC822)')
                if status != 'OK':
                    continue
                    
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Onderwerp decoderen
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or "utf-8", errors="ignore")
                    
                print(f"[IMAP] Verwerken e-mail: '{subject}'")
                
                # Inhoud ophalen
                body_content = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        
                        if content_type == "text/plain" and "attachment" not in content_disposition:
                            payload = part.get_payload(decode=True)
                            body_content += payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                        elif content_type == "text/html" and "attachment" not in content_disposition:
                            # HTML heeft voorkeur omdat daar vaak alle links en opmaak in zitten
                            payload = part.get_payload(decode=True)
                            html_text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                            body_content = clean_html(html_text)
                            break # Als we HTML hebben, stoppen we met zoeken
                else:
                    content_type = msg.get_content_type()
                    payload = msg.get_payload(decode=True)
                    decoded_payload = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
                    if content_type == "text/html":
                        body_content = clean_html(decoded_payload)
                    else:
                        body_content = decoded_payload
                        
                if not body_content.strip():
                    print("[IMAP] E-mail body is leeg, overslaan.")
                    continue
                    
                # Voeg onderwerp toe aan de tekst voor extra context
                full_text_to_parse = f"Onderwerp: {subject}\n\nInhoud:\n{body_content}"
                
                # Stuurt naar Gemini
                extracted = parse_newsletter_with_gemini(db, full_text_to_parse)
                
                added_count = 0
                for item in extracted:
                    venue = find_or_create_venue(db, item.venue)
                    if not venue:
                        continue
                    
                    # Datum parsen
                    try:
                        if "T" in item.date:
                            concert_date = datetime.datetime.fromisoformat(item.date)
                        else:
                            concert_date = datetime.datetime.strptime(item.date, "%Y-%m-%d")
                    except Exception:
                        concert_date = datetime.datetime.now()
                        
                    # Kaartverkoop parsen
                    sale_start = None
                    if item.ticket_sale_start:
                        try:
                            if "T" in item.ticket_sale_start:
                                sale_start = datetime.datetime.fromisoformat(item.ticket_sale_start)
                            else:
                                sale_start = datetime.datetime.strptime(item.ticket_sale_start, "%Y-%m-%d")
                        except Exception:
                            pass
                            
                    start_of_day = datetime.datetime(concert_date.year, concert_date.month, concert_date.day)
                    end_of_day = start_of_day + datetime.timedelta(days=1)
                    
                    exists = db.query(Concert).filter(
                        Concert.artist.ilike(item.artist),
                        Concert.venue_id == venue.id,
                        Concert.date >= start_of_day,
                        Concert.date < end_of_day
                    ).first()
                    
                    if not exists:
                        new_concert = Concert(
                            artist=item.artist,
                            venue_id=venue.id,
                            date=concert_date,
                            ticket_sale_start=sale_start,
                            price=item.price,
                            url=item.url or msg.get("List-Unsubscribe") or None, # Gebruik eventuele unsubscribe of e-mail links
                            source=f"email_{subject[:30]}",
                            status="new"
                        )
                        db.add(new_concert)
                        db.commit()
                        db.refresh(new_concert)
                        
                        # Scoren
                        score = score_concert(db, new_concert, top_genres_freq, user_config, allow_spotify_lookup=False)
                        new_concert.calculated_score = score
                        db.commit()
                        
                        added_count += 1
                        added_total += 1
                        
                print(f"[IMAP] Succesvol verwerkt: '{subject}'. Gevonden: {len(extracted)}, toegevoegd: {added_count}")
                
                # Markeer als gelezen
                mail.store(mail_id, '+FLAGS', '\\Seen')
                
            except Exception as mail_err:
                print(f"[IMAP] Fout bij verwerken van specifieke mail {mail_id}: {mail_err}")
                continue
                
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"[IMAP] Fout bij ophalen van e-mails: {e}")
        
    return added_total
