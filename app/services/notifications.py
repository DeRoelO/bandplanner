import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Concert, UserConfig

def send_email_notification(db: Session, subject: str, html_content: str) -> bool:
    """
    Algemene helper om een HTML e-mail te sturen via SMTP.
    Gebruikt SMTP instellingen uit de DB of .env als fallback.
    """
    user_config = db.query(UserConfig).first()
    
    server_addr = user_config.smtp_server if user_config and user_config.smtp_server else settings.SMTP_SERVER
    port = user_config.smtp_port if user_config and user_config.smtp_port else settings.SMTP_PORT
    username = user_config.smtp_username if user_config and user_config.smtp_username else settings.SMTP_USERNAME
    password = user_config.smtp_password if user_config and user_config.smtp_password else settings.SMTP_PASSWORD
    from_email = user_config.smtp_from_email if user_config and user_config.smtp_from_email else settings.SMTP_FROM_EMAIL
    to_email = user_config.smtp_to_email if user_config and user_config.smtp_to_email else settings.SMTP_TO_EMAIL
    
    if not all([server_addr, username, password, to_email]):
        print("SMTP e-mailnotificaties zijn niet volledig geconfigureerd in de database of .env. E-mail overgeslagen.")
        return False
        
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email or username
        msg['To'] = to_email
        
        # Voeg HTML content toe
        msg.attach(MIMEText(html_content, 'html'))
        
        # SMTP connectie maken
        server = smtplib.SMTP(server_addr, port)
        server.ehlo()
        if port == 587:
            server.starttls()
            server.ehlo()
            
        server.login(username, password)
        server.sendmail(msg['From'], [msg['To']], msg.as_string())
        server.close()
        print(f"E-mail succesvol verzonden naar {to_email} met onderwerp: '{subject}'")
        return True
    except Exception as e:
        print(f"Fout bij het verzenden van e-mail via SMTP: {e}")
        return False

def notify_new_concerts(db: Session, concerts: List[Concert]) -> bool:
    """
    Stuurt een overzichtelijke e-mail met nieuw gevonden concert-tips.
    """
    if not concerts:
        return False
        
    subject = f"Bandplanner: {len(concerts)} nieuwe concert-tips gevonden! 🎸"
    
    # Mooie HTML template
    rows = ""
    for c in concerts:
        venue_name = c.venue.name if c.venue else "Onbekend"
        date_str = c.date.strftime("%d-%m-%Y")
        
        # Score kleur bepalen
        score_color = "#3b82f6"  # Blauw
        if c.calculated_score >= 8.0:
            score_color = "#10b981"  # Groen
        elif c.calculated_score >= 5.0:
            score_color = "#f59e0b"  # Oranje
            
        ticket_sale = c.ticket_sale_start.strftime("%d-%m-%Y %H:%M") if c.ticket_sale_start else "Onbekend"
        price_str = f"&euro;{c.price:.2f}" if c.price else "Onbekend"
        link_str = f'<a href="{c.url}" target="_blank" style="color: #3b82f6; text-decoration: none; font-weight: bold;">Tickets & Info</a>' if c.url else "N.v.t."
        
        rows += f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 12px; font-weight: bold; color: #1e293b;">{c.artist}</td>
            <td style="padding: 12px; color: #475569;">{venue_name}</td>
            <td style="padding: 12px; color: #475569;">{date_str}</td>
            <td style="padding: 12px; font-weight: bold; color: {score_color};">{c.calculated_score:.1f}/10</td>
            <td style="padding: 12px; color: #475569;">{price_str}</td>
            <td style="padding: 12px; color: #475569; font-size: 13px;">{ticket_sale}</td>
            <td style="padding: 12px;">{link_str}</td>
        </tr>
        """
        
    html_content = f"""
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 20px; margin: 0;">
        <div style="max-width: 800px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border: 1px solid #e2e8f0; overflow: hidden;">
            <div style="background: linear-gradient(135deg, #1e1b4b 0%, #311042 100%); color: #ffffff; padding: 24px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em;">Bandplanner</h1>
                <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.8;">Jouw gepersonaliseerde concert agenda op basis van Spotify & Locatie</p>
            </div>
            
            <div style="padding: 24px;">
                <p style="color: #334155; font-size: 16px; line-height: 1.5; margin-top: 0;">
                    Beste muziekliefhebber,<br><br>
                    We hebben nieuwe concerten gevonden die aansluiten bij jouw smaak en locatie! Hieronder vind je het overzicht:
                </p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; text-align: left;">
                    <thead>
                        <tr style="background-color: #f1f5f9; border-bottom: 2px solid #e2e8f0;">
                            <th style="padding: 12px; color: #475569; font-weight: 600;">Artiest</th>
                            <th style="padding: 12px; color: #475569; font-weight: 600;">Locatie</th>
                            <th style="padding: 12px; color: #475569; font-weight: 600;">Datum</th>
                            <th style="padding: 12px; color: #475569; font-weight: 600;">Score</th>
                            <th style="padding: 12px; color: #475569; font-weight: 600;">Prijs</th>
                            <th style="padding: 12px; color: #475569; font-weight: 600;">Kaartverkoop</th>
                            <th style="padding: 12px; color: #475569; font-weight: 600;">Actie</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
                
                <p style="color: #64748b; font-size: 12px; line-height: 1.5; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 15px; text-align: center;">
                    Dit is een automatisch gegenereerd bericht van je Bandplanner instance.<br>
                    Bezoek de GUI op je server om je instellingen, Spotify sync of podia aan te passen.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return send_email_notification(db, subject, html_content)

def notify_parser_error(db: Session, error_message: str) -> bool:
    """
    Stuurt een waarschuwingsmail als er een parser of synchronisatie faalt.
    """
    subject = "Bandplanner Systeem Waarschuwing: Gegevensbron Fout ⚠️"
    
    html_content = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; background-color: #fff5f5;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #feb2b2; border-radius: 8px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #c53030; margin-top: 0;">Systeemfout Gedetecteerd</h2>
            <p>Beste beheerder,</p>
            <p>Er is een probleem opgetreden tijdens het ophalen of verwerken van gegevens voor Bandplanner.</p>
            <div style="background-color: #edf2f7; padding: 15px; border-radius: 4px; font-family: monospace; white-space: pre-wrap; font-size: 13px;">
                {error_message}
            </div>
            <p>Controleer de logs van de Docker-container voor meer details.</p>
        </div>
    </body>
    </html>
    """
    
    return send_email_notification(db, subject, html_content)

