import hashlib
import secrets
from datetime import datetime, timedelta
from sqlalchemy import select, delete
from app.db.session import SessionLocal
from app.models import AuthSession
from app.core.config import settings

COOKIE = "halaqat_session"
def create_session(user_id, lifetime_hours=None):
    raw = secrets.token_urlsafe(48)
    lifetime_hours = lifetime_hours or settings.session_hours
    with SessionLocal() as db:
        db.execute(delete(AuthSession).where(AuthSession.expires_at < datetime.utcnow()))
        db.add(AuthSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user_id, expires_at=datetime.utcnow() + timedelta(hours=lifetime_hours)))
        db.commit()
    return raw

def get_session(raw):
    if not raw or len(raw) > 200:
        return None
    with SessionLocal() as db:
        return db.scalar(select(AuthSession).where(AuthSession.token_hash == hashlib.sha256(raw.encode()).hexdigest(), AuthSession.expires_at > datetime.utcnow()))

def delete_session(raw):
    if raw:
        with SessionLocal() as db:
            db.execute(delete(AuthSession).where(AuthSession.token_hash == hashlib.sha256(raw.encode()).hexdigest()))
            db.commit()
