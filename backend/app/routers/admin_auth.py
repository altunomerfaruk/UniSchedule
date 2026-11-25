import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ADMIN_COOKIE, ADMIN_LIFETIME, admin_from_request, get_visitor, require_admin, secure_cookies, set_cookie, token_hash, verify_password
from ..database import get_db
from ..models import AdminAccount, AdminSession, SavedSchedule, StudentPreference, VisitorSession
from ..schemas import PreferenceInput
from ..services.saved_schedules import revalidate_saved_schedules


router = APIRouter(prefix="/api/admin")
CSRF_COOKIE = "unischedule_csrf"
FAILURES: dict[str, list[float]] = {}


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


def limited(key: str) -> bool:
    now = time.time()
    FAILURES[key] = [attempt for attempt in FAILURES.get(key, []) if now - attempt < 600]
    return len(FAILURES[key]) >= 5


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    key = f"{request.client.host if request.client else 'unknown'}:{username}"
    if limited(key):
        raise HTTPException(429, "Too many attempts. Try again in ten minutes.")
    admin = db.scalar(select(AdminAccount).where(AdminAccount.username == username))
    if admin is None or not verify_password(payload.password, admin.password_hash):
        FAILURES.setdefault(key, []).append(time.time())
        raise HTTPException(401, "Invalid username or password.")
    FAILURES.pop(key, None)
    old = admin_from_request(request, db)
    if old is not None:
        db.delete(old[1])
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(AdminSession(admin_id=admin.id, token_hash=token_hash(token), csrf_hash=token_hash(csrf), expires_at=int(time.time()) + ADMIN_LIFETIME))
    db.commit()
    set_cookie(response, ADMIN_COOKIE, token, ADMIN_LIFETIME)
    response.set_cookie(CSRF_COOKIE, csrf, max_age=ADMIN_LIFETIME, httponly=False, secure=secure_cookies(), samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"username": admin.username}


@router.get("/me")
def me(admin: AdminAccount = Depends(require_admin)):
    return {"username": admin.username}


@router.post("/logout")
def logout(request: Request, response: Response, admin: AdminAccount = Depends(require_admin), db: Session = Depends(get_db)):
    found = admin_from_request(request, db)
    if found is not None:
        db.delete(found[1])
        db.commit()
    response.delete_cookie(ADMIN_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Signed out."}


@router.get("/legacy")
def legacy_status(admin: AdminAccount = Depends(require_admin), db: Session = Depends(get_db)):
    return {"saved_schedules": len(db.scalars(select(SavedSchedule.id).where(SavedSchedule.visitor_id.is_(None))).all())}


@router.post("/claim-legacy")
def claim_legacy(admin: AdminAccount = Depends(require_admin), visitor: VisitorSession = Depends(get_visitor), db: Session = Depends(get_db)):
    schedules = db.scalars(select(SavedSchedule).where(SavedSchedule.visitor_id.is_(None))).all()
    if not schedules:
        raise HTTPException(409, "No previous schedules remain to import.")
    previous = db.get(StudentPreference, 1)
    current = db.scalar(select(StudentPreference).where(StudentPreference.visitor_id == visitor.id))
    if previous is not None and current is not None:
        for field in PreferenceInput.model_fields:
            setattr(current, field, getattr(previous, field))
    for schedule in schedules:
        schedule.visitor_id = visitor.id
    revalidate_saved_schedules(db, visitor_id=visitor.id)
    db.commit()
    return {"imported": len(schedules)}
