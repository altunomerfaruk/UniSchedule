import hashlib
import hmac
import os
import secrets
import time

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AdminAccount, AdminSession, Course, StudentPreference, VisitorSession
from .seed import DEFAULT_CODES


ADMIN_COOKIE = "unischedule_admin"
VISITOR_COOKIE = "unischedule_visitor"
ADMIN_LIFETIME = 12 * 60 * 60
VISITOR_LIFETIME = 30 * 24 * 60 * 60


def secure_cookies() -> bool:
    return os.getenv("UNISCHEDULE_ENV") == "production" or os.getenv("UNISCHEDULE_COOKIE_SECURE") == "1"


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=5, dklen=64)
    return f"scrypt$16384$8$5${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, cost, block, parallel, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt" or (int(cost), int(block), int(parallel)) != (16384, 8, 5):
            return False
        calculated = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=16384, r=8, p=5, dklen=64)
        return hmac.compare_digest(calculated, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def set_cookie(response: Response, name: str, value: str, lifetime: int) -> None:
    response.set_cookie(name, value, max_age=lifetime, httponly=True, secure=secure_cookies(), samesite="lax", path="/")


def admin_from_request(request: Request, db: Session) -> tuple[AdminAccount, AdminSession] | None:
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        return None
    session = db.scalar(select(AdminSession).where(AdminSession.token_hash == token_hash(token)))
    if session is None or session.expires_at <= int(time.time()):
        return None
    return session.admin, session


def require_admin(request: Request, db: Session = Depends(get_db)) -> AdminAccount:
    found = admin_from_request(request, db)
    if found is None:
        raise HTTPException(status_code=401, detail="Admin sign-in required.")
    admin, session = found
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not hmac.compare_digest(token_hash(csrf), session.csrf_hash):
            raise HTTPException(status_code=403, detail="Invalid CSRF token.")
    return admin


def get_visitor(request: Request, response: Response, db: Session = Depends(get_db)) -> VisitorSession:
    token = request.cookies.get(VISITOR_COOKIE)
    if token:
        visitor = db.scalar(select(VisitorSession).where(VisitorSession.token_hash == token_hash(token)))
        if visitor is not None and visitor.expires_at > int(time.time()):
            return visitor
    token = secrets.token_urlsafe(32)
    visitor = VisitorSession(token_hash=token_hash(token), expires_at=int(time.time()) + VISITOR_LIFETIME)
    db.add(visitor)
    db.flush()
    default_ids = db.scalars(select(Course.id).where(Course.code.in_(DEFAULT_CODES), Course.is_active.is_(True))).all()
    db.add(StudentPreference(visitor_id=visitor.id, selected_course_ids=default_ids))
    db.commit()
    set_cookie(response, VISITOR_COOKIE, token, VISITOR_LIFETIME)
    return visitor
