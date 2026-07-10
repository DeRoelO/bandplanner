from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
from app.models import Venue, UserConfig

VENUES_SEED = [
    # --- LARGE ---
    {"name": "Ziggo Dome", "latitude": 52.3134, "longitude": 4.9367, "category": "large", "url": "https://www.ziggodome.nl", "aliases": "Ziggodome,Ziggo"},
    {"name": "AFAS Live", "latitude": 52.3122, "longitude": 4.9396, "category": "large", "url": "https://www.afaslive.nl", "aliases": "AFAS,Afas Live,Heineken Music Hall,HMH"},
    {"name": "Rotterdam Ahoy", "latitude": 51.8742, "longitude": 4.4844, "category": "large", "url": "https://www.ahoy.nl", "aliases": "Ahoy,Ahoy Rotterdam,Sportpaleis Ahoy"},
    {"name": "GelreDome", "latitude": 51.9634, "longitude": 5.8931, "category": "large", "url": "https://www.gelredome.nl", "aliases": "Gelredome"},
    {"name": "Koninklijk Theater Carré", "latitude": 52.3622, "longitude": 4.9038, "category": "large", "url": "https://carre.nl", "aliases": "Carré,Theater Carré"},
    {"name": "Paleis 12", "latitude": 50.8988, "longitude": 4.3418, "category": "large", "url": "https://www.palais12.com", "aliases": "Palais 12,Palais12,Paleis12"},
    {"name": "Sportpaleis", "latitude": 51.2302, "longitude": 4.4423, "category": "large", "url": "https://www.sportpaleis.be", "aliases": "Sportpaleis Antwerpen"},

    # --- MEDIUM ---
    {"name": "Paradiso", "latitude": 52.3622, "longitude": 4.8837, "category": "medium", "url": "https://www.paradiso.nl", "aliases": "Paradiso Amsterdam,Paradiso Grote Zaal"},
    {"name": "Melkweg", "latitude": 52.3648, "longitude": 4.8814, "category": "medium", "url": "https://www.melkweg.nl", "aliases": "Melkweg Amsterdam,The Max,Oude Zaal"},
    {"name": "TivoliVredenburg", "latitude": 52.0931, "longitude": 5.1118, "category": "medium", "url": "https://www.tivolivredenburg.nl", "aliases": "Tivoli,Vredenburg,Tivoli Vredenburg,Ronda,Pandora,Herz"},
    {"name": "013 Poppodium", "latitude": 51.5583, "longitude": 5.0934, "category": "medium", "url": "https://www.013.nl", "aliases": "013,Poppodium 013,013 Tilburg"},
    {"name": "Effenaar", "latitude": 51.4422, "longitude": 5.4839, "category": "medium", "url": "https://www.effenaar.nl", "aliases": "Effenaar Eindhoven"},
    {"name": "Doornroosje", "latitude": 51.8443, "longitude": 5.8523, "category": "medium", "url": "https://www.doornroosje.nl", "aliases": "Doornroosje Nijmegen"},
    {"name": "Hedon", "latitude": 52.5161, "longitude": 6.0967, "category": "medium", "url": "https://www.hedon-zwolle.nl", "aliases": "Hedon Zwolle"},
    {"name": "Patronaat", "latitude": 52.3828, "longitude": 4.6291, "category": "medium", "url": "https://www.patronaat.nl", "aliases": "Patronaat Haarlem"},
    {"name": "De Oosterpoort", "latitude": 53.2144, "longitude": 6.5772, "category": "medium", "url": "https://www.spotgroningen.nl", "aliases": "Oosterpoort,SPOT Groningen,SPOT Oosterpoort"},
    {"name": "Paard", "latitude": 52.0764, "longitude": 4.3075, "category": "medium", "url": "https://www.paard.nl", "aliases": "Paard van Troje"},
    {"name": "Metropool", "latitude": 52.2656, "longitude": 6.7936, "category": "medium", "url": "https://www.metropool.nl", "aliases": "Metropool Hengelo,Metropool Enschede"},
    {"name": "Mezz", "latitude": 51.5878, "longitude": 4.7811, "category": "medium", "url": "https://www.mezz.nl", "aliases": "Mezz Breda"},
    {"name": "Burgerweeshuis", "latitude": 52.2536, "longitude": 6.1558, "category": "medium", "url": "https://www.burgerweeshuis.nl", "aliases": "Burgerweeshuis Deventer"},
    {"name": "Gigant", "latitude": 52.2158, "longitude": 5.9622, "category": "medium", "url": "https://www.gigant.nl", "aliases": "Gigant Apeldoorn"},
    {"name": "Neushoorn", "latitude": 53.2014, "longitude": 5.7925, "category": "medium", "url": "https://www.neushoorn.nl", "aliases": "Neushoorn Leeuwarden"},
    {"name": "Willem Twee poppodium", "latitude": 51.6967, "longitude": 5.3039, "category": "medium", "url": "https://www.willem-twee.nl", "aliases": "Willem Twee,W2,W2 Poppodium"},
    {"name": "Volt", "latitude": 50.9972, "longitude": 5.8719, "category": "medium", "url": "https://www.poppodiumvolt.nl", "aliases": "Volt Sittard,Poppodium Volt"},
    {"name": "Gebr. de Nobel", "latitude": 52.1625, "longitude": 4.4883, "category": "medium", "url": "https://www.gebrdenobel.nl", "aliases": "Gebroeders de Nobel,Nobel Leiden"},
    {"name": "Bibelot", "latitude": 51.8094, "longitude": 4.6739, "category": "medium", "url": "https://www.bibelot.nl", "aliases": "Bibelot Dordrecht,Energiehuis"},
    {"name": "Grenswerk", "latitude": 51.3708, "longitude": 6.1733, "category": "medium", "url": "https://www.grenswerk.nl", "aliases": "Grenswerk Venlo"},
    {"name": "Nieuwe Nor", "latitude": 50.8878, "longitude": 5.9819, "category": "medium", "url": "https://www.nieuwenor.nl", "aliases": "Nieuwe Nor Heerlen"},

    # --- SMALL ---
    {"name": "EKKO", "latitude": 52.0978, "longitude": 5.1169, "category": "small", "url": "https://www.ekko.nl", "aliases": "EKKO Utrecht"},
    {"name": "VERA", "latitude": 53.2178, "longitude": 6.5686, "category": "small", "url": "https://www.vera-groningen.nl", "aliases": "Vera Groningen,Club VERA"},
    {"name": "Rotown", "latitude": 51.9161, "longitude": 4.4719, "category": "small", "url": "https://www.rotown.nl", "aliases": "Rotown Rotterdam"},
    {"name": "Merelyn", "latitude": 51.8475, "longitude": 5.8647, "category": "small", "url": "https://www.doornroosje.nl", "aliases": "Merleyn,Merleyn Nijmegen"},
    {"name": "ACU", "latitude": 52.0944, "longitude": 5.1206, "category": "small", "url": "https://acu.nl", "aliases": "ACU Utrecht"},
    {"name": "db's", "latitude": 52.1022, "longitude": 5.0886, "category": "small", "url": "https://www.dbsutrecht.nl", "aliases": "db's Utrecht,dBs,dbs"},
    {"name": "Cul de Sac", "latitude": 51.5572, "longitude": 5.0875, "category": "small", "url": "https://www.facebook.com/culdesactilburg/", "aliases": "Cul de Sac Tilburg"},
    {"name": "Altstadt", "latitude": 51.4378, "longitude": 5.4797, "category": "small", "url": "https://www.altstadt.nl", "aliases": "Altstadt Eindhoven"},
    {"name": "Little Devil", "latitude": 51.5606, "longitude": 5.0908, "category": "small", "url": "https://www.littledevil.nl", "aliases": "Little Devil Tilburg"},
    {"name": "Baroeg", "latitude": 51.8792, "longitude": 4.5169, "category": "small", "url": "https://www.baroeg.nl", "aliases": "Baroeg Rotterdam"},
    {"name": "Popcentrale", "latitude": 51.8094, "longitude": 4.6739, "category": "small", "url": "https://www.popcentrale.nl", "aliases": "Popcentrale Dordrecht"},
    {"name": "P60", "latitude": 52.3022, "longitude": 4.8622, "category": "small", "url": "https://www.p60.nl", "aliases": "P60 Amstelveen"},
    {"name": "Duycker", "latitude": 52.3033, "longitude": 4.6869, "category": "small", "url": "https://www.duycker.nl", "aliases": "Duycker Hoofddorp"},
    {"name": "De Helling", "latitude": 52.0733, "longitude": 5.1208, "category": "small", "url": "https://dehelling.nl", "aliases": "De Helling Utrecht"},
    {"name": "De Kroepoekfabriek", "latitude": 51.9086, "longitude": 4.3517, "category": "small", "url": "https://kroepoekfabriek.nl", "aliases": "Kroepoekfabriek,KF"},
    {"name": "So What!", "latitude": 52.0153, "longitude": 4.7083, "category": "small", "url": "https://www.so-what.nl", "aliases": "So What Gouda"},
    {"name": "Manifesto", "latitude": 52.6517, "longitude": 5.0747, "category": "small", "url": "https://www.manifesto-hoorn.nl", "aliases": "Manifesto Hoorn"},
    {"name": "De Flux", "latitude": 52.4464, "longitude": 4.8211, "category": "small", "url": "https://www.podiumdeflux.nl", "aliases": "Flux Zaandam,Podium de Flux"},
    {"name": "Gebouw-T", "latitude": 51.4922, "longitude": 4.2908, "category": "small", "url": "https://www.gebouw-t.nl", "aliases": "Gebouw T,Gebouw-T Bergen op Zoom"}
]

def seed_data(db: Session):
    # Seed default user config if none exists
    if db.query(UserConfig).count() == 0:
        default_config = UserConfig(
            home_latitude=52.0907,  # Utrecht Centraal
            home_longitude=5.1214,
            radius_small=25.0,
            radius_medium=60.0,
            radius_large=250.0
        )
        db.add(default_config)
        print("Default user configuration seeded.")

    # Seed venues only if table is empty
    if db.query(Venue).count() == 0:
        seeded_count = 0
        for v_data in VENUES_SEED:
            venue = Venue(
                name=v_data["name"],
                latitude=v_data["latitude"],
                longitude=v_data["longitude"],
                category=v_data["category"],
                url=v_data["url"],
                aliases=v_data.get("aliases", "")
            )
            db.add(venue)
            seeded_count += 1
            
        if seeded_count > 0:
            db.commit()
            print(f"Seeded {seeded_count} venues successfully.")
    else:
        print("Venues database is already seeded and has records. Seeding skipped.")

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db_session = SessionLocal()
    try:
        seed_data(db_session)
    finally:
        db_session.close()
