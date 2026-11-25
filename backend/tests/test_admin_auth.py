from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import password_hash, secure_cookies, verify_password
from app.database import SessionLocal
from app.main import app
from app.models import AdminAccount, SavedSchedule, SavedScheduleItem, StudentPreference


ADMIN_PASSWORD = "isolated-test-password-only"


def add_test_admin():
    with SessionLocal() as db:
        account = AdminAccount(username="testadmin", password_hash=password_hash(ADMIN_PASSWORD))
        db.add(account)
        db.commit()
        assert account.password_hash != ADMIN_PASSWORD
        assert verify_password(ADMIN_PASSWORD, account.password_hash)


def sign_in(client):
    result = client.post("/api/admin/login", json={"username": "testadmin", "password": ADMIN_PASSWORD})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = client.cookies["unischedule_csrf"]


def test_public_visit_is_anonymous_and_mutations_need_admin(client):
    assert client.get("/api/catalog").status_code == 200
    assert client.get("/api/preferences").status_code == 200
    assert client.post("/api/generate").status_code == 200
    assert client.get("/api/admin/me").status_code == 401
    assert client.get("/api/courses/archived").status_code == 401
    assert client.post("/api/courses", json={"code": "AUTH1001", "name": "Guarded", "offering_department": "Software Engineering"}).status_code == 401
    assert client.post("/api/courses/1/sections", json={"label": "9"}).status_code == 401
    assert client.put("/api/sections/1", json={"label": "9"}).status_code == 401
    assert client.delete("/api/sessions/1").status_code == 401
    assert client.post("/api/admin/register", json={"username": "self", "role": "admin"}).status_code == 404


def test_admin_login_csrf_origin_crud_and_logout(client):
    add_test_admin()
    assert client.post("/api/admin/login", json={"username": "testadmin", "password": "wrong"}).status_code == 401
    sign_in(client)
    assert client.get("/api/admin/me").json() == {"username": "testadmin"}
    assert client.cookies["unischedule_admin"]
    with SessionLocal() as db:
        assert db.scalar(select(AdminAccount)).password_hash != ADMIN_PASSWORD

    payload = {"code": "AUTH1001", "name": "Guarded", "offering_department": "Software Engineering", "ects": None, "credit": None, "mandatory": None}
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/courses", json=payload).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/api/courses", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403
    created = client.post("/api/courses", json=payload)
    assert created.status_code == 201, created.text
    course_id = created.json()["id"]
    assert client.put(f"/api/courses/{course_id}", json={**payload, "name": "Updated"}).status_code == 200
    assert client.delete(f"/api/courses/{course_id}").status_code == 200
    assert client.post(f"/api/courses/{course_id}/restore").status_code == 200
    assert client.post("/api/admin/logout").status_code == 200
    assert client.get("/api/admin/me").status_code == 401
    assert client.post("/api/courses", json=payload).status_code == 401


def test_anonymous_visitors_have_separate_preferences_and_schedules(client):
    first = client.get("/api/preferences").json()
    assert client.cookies["unischedule_visitor"]
    with TestClient(app) as other:
        second = other.get("/api/preferences").json()
        assert second == first
        first["selected_course_ids"] = first["selected_course_ids"][:1]
        assert client.put("/api/preferences", json=first).status_code == 200
        assert other.get("/api/preferences").json() == second
        generated = client.post("/api/generate").json()["alternatives"][0]
        saved = client.post("/api/schedules", json={"name": "Private", "section_ids": [item["id"] for item in generated["sections"]]})
        assert saved.status_code == 201
        assert len(client.get("/api/schedules").json()) == 1
        assert other.get("/api/schedules").json() == []


def test_legacy_schedules_require_explicit_admin_claim(client):
    add_test_admin()
    with SessionLocal() as db:
        schedule = SavedSchedule(name="Previous version", score=90, visitor_id=None, items=[SavedScheduleItem(section_id=1)])
        db.add(schedule)
        db.commit()
        legacy_preference = db.get(StudentPreference, 1)
        legacy_selected = list(legacy_preference.selected_course_ids)
    assert client.get("/api/schedules").json() == []
    sign_in(client)
    assert client.get("/api/admin/legacy").json()["saved_schedules"] == 1
    result = client.post("/api/admin/claim-legacy")
    assert result.status_code == 200, result.text
    assert result.json()["imported"] == 1
    assert len(client.get("/api/schedules").json()) == 1
    assert client.get("/api/preferences").json()["selected_course_ids"] == legacy_selected
    assert client.post("/api/admin/claim-legacy").status_code == 409
    with TestClient(app) as other:
        assert other.get("/api/schedules").json() == []


def test_login_throttle_and_production_cookie_setting(client, monkeypatch):
    for _ in range(5):
        assert client.post("/api/admin/login", json={"username": "unknown-throttle", "password": "wrong"}).status_code == 401
    assert client.post("/api/admin/login", json={"username": "unknown-throttle", "password": "wrong"}).status_code == 429
    monkeypatch.setenv("UNISCHEDULE_ENV", "production")
    assert secure_cookies() is True
