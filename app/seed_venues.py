from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
from app.models import UserConfig

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
        db.commit()
        print("Default user configuration seeded.")
    else:
        print("User configuration already exists. Seeding skipped.")

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db_session = SessionLocal()
    try:
        seed_data(db_session)
    finally:
        db_session.close()
