from fastapi.testclient import TestClient
import pytest

from app.auth import password_hash
from app.database import SessionLocal
from app.main import app
from app.models import AdminAccount, SavedSchedule


@pytest.fixture(autouse=True)
def signed_in_admin(client):
    with SessionLocal() as db:
        db.add(AdminAccount(username="testadmin", password_hash=password_hash("test-password-for-admin")))
        db.commit()
    response = client.post("/api/admin/login", json={"username": "testadmin", "password": "test-password-for-admin"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["unischedule_csrf"]


def course_data(code="MAN1001"):
    return {"code": code, "name": "Managed Course", "offering_department": "Software Engineering (English)", "ects": None, "credit": None, "mandatory": None}


def session_data(day=0, start="09:00", end="09:50", session_type="lecture"):
    return {"day": day, "start_time": start, "end_time": end, "session_type": session_type, "classroom": "A-101", "instructor": "Dr. Test"}


def test_course_crud_validation_and_soft_delete(client):
    assert len(client.get("/api/courses").json()) == 20
    assert client.post("/api/courses", json={**course_data(), "code": "  "}).status_code == 422
    assert client.post("/api/courses", json={**course_data(), "name": "  "}).status_code == 422
    assert client.post("/api/courses", json={**course_data(), "ects": -1}).status_code == 422
    assert client.post("/api/courses", json={**course_data(), "credit": -1}).status_code == 422
    created = client.post("/api/courses", json=course_data("man1001"))
    assert created.status_code == 201, created.text
    course_id = created.json()["id"]
    assert created.json()["code"] == "MAN1001"
    assert client.post("/api/courses", json=course_data("Man1001")).status_code == 409
    updated = client.put(f"/api/courses/{course_id}", json={**course_data("MAN1001"), "name": "Updated Course", "ects": 5, "credit": 3, "mandatory": False})
    assert updated.status_code == 200, updated.text
    assert client.get(f"/api/courses/{course_id}").json()["ects"] == 5
    deleted = client.delete(f"/api/courses/{course_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/courses/{course_id}").status_code == 404
    assert len(client.get("/api/courses").json()) == 20


def test_section_and_session_crud_and_validation(client):
    course_id = client.post("/api/courses", json=course_data()).json()["id"]
    section = client.post(f"/api/courses/{course_id}/sections", json={"label": "1"})
    assert section.status_code == 201, section.text
    section_id = section.json()["id"]
    assert client.post(f"/api/courses/{course_id}/sections", json={"label": "1"}).status_code == 409
    assert client.post(f"/api/courses/{course_id}/sections", json={"label": "  "}).status_code == 422
    assert client.put(f"/api/sections/{section_id}", json={"label": "A"}).status_code == 200
    first = client.post(f"/api/sections/{section_id}/sessions", json=session_data())
    assert first.status_code == 201, first.text
    session_id = first.json()["id"]
    assert first.json()["instructor"] == "Dr. Test"
    assert client.post(f"/api/sections/{section_id}/sessions", json=session_data(start="09:30", end="10:20")).status_code == 409
    assert client.post(f"/api/sections/{section_id}/sessions", json=session_data(start="11:00", end="11:00")).status_code == 422
    assert client.post(f"/api/sections/{section_id}/sessions", json=session_data(day=6)).status_code == 422
    second = client.post(f"/api/sections/{section_id}/sessions", json=session_data(day=5, start="10:00", end="10:50", session_type="online"))
    assert second.status_code == 201, second.text
    assert second.json()["delivery_mode"] == "online"
    assert client.get(f"/api/sessions/{session_id}").status_code == 200
    changed = client.put(f"/api/sessions/{session_id}", json=session_data(start="08:00", end="08:50", session_type="laboratory"))
    assert changed.status_code == 200, changed.text
    assert changed.json()["session_type"] == "laboratory"
    assert len(client.get(f"/api/sections/{section_id}/sessions").json()) == 2
    assert client.delete(f"/api/sessions/{session_id}").status_code == 200
    assert client.get(f"/api/sessions/{session_id}").status_code == 404
    assert len(client.get(f"/api/sections/{section_id}/sessions").json()) == 1
    assert client.delete(f"/api/sections/{section_id}").status_code == 200
    assert client.get(f"/api/sections/{section_id}").status_code == 404


def test_saved_snapshot_survives_course_change_and_deletion(client):
    generated = client.post("/api/generate").json()["alternatives"][0]
    saved = client.post("/api/schedules", json={"name": "Historic", "section_ids": [section["id"] for section in generated["sections"]]})
    assert saved.status_code == 201
    original = saved.json()["sections"]
    first = client.get("/api/courses").json()[0]
    changed = client.put(f"/api/courses/{first['id']}", json={**course_data(first["code"]), "name": "Renamed", "offering_department": first["offering_department"]})
    assert changed.status_code == 200
    assert changed.json()["affected_schedules"] == 1
    historic = client.get("/api/schedules").json()[0]
    assert historic["status"] == "valid"
    assert any(section["course_name"] == "Renamed" for section in historic["sections"])
    with SessionLocal() as db:
        assert db.get(SavedSchedule, saved.json()["id"]).snapshot["sections"] == original
    deleted = client.delete(f"/api/courses/{first['id']}")
    assert deleted.json()["removed_from_selection"] is True
    assert deleted.json()["affected_schedules"] == 1
    inactive = client.get("/api/schedules").json()[0]
    assert inactive["status"] == "invalid"
    assert first["code"] in inactive["invalid_reason"]
    assert inactive["sections"] == original
    assert first["id"] not in client.get("/api/preferences").json()["selected_course_ids"]
    archived = client.get("/api/courses/archived").json()
    assert any(course["id"] == first["id"] for course in archived)
    duplicate = client.post("/api/courses", json=course_data(first["code"]))
    assert duplicate.status_code == 409
    assert "Restore" in duplicate.json()["detail"]["message"]
    restored = client.post(f"/api/courses/{first['id']}/restore")
    assert restored.status_code == 200
    assert client.get("/api/schedules").json()[0]["status"] == "valid"
    assert client.get("/api/schedules").json()[0]["sections"] != original


def test_new_course_is_used_for_generation_and_survives_client_restart(client):
    created = client.post("/api/courses", json={**course_data("MAN1002"), "ects": 4}).json()
    section = client.post(f"/api/courses/{created['id']}/sections", json={"label": "2"}).json()
    client.post(f"/api/sections/{section['id']}/sessions", json=session_data(day=5, start="12:00", end="12:50"))
    pref = client.get("/api/preferences").json()
    pref["selected_course_ids"] = [created["id"]]
    assert client.put("/api/preferences", json=pref).status_code == 200
    generated = client.post("/api/generate").json()["alternatives"]
    assert len(generated) == 1
    assert generated[0]["sections"][0]["course_code"] == "MAN1002"
    assert generated[0]["total_ects"] == 4
    with TestClient(app) as restarted:
        assert restarted.get(f"/api/courses/{created['id']}").json()["sections"][0]["sessions"][0]["day"] == 5


def test_section_label_change_keeps_saved_schedule_valid(client):
    generated = client.post("/api/generate").json()["alternatives"][0]
    client.post("/api/schedules", json={"name": "Stable", "section_ids": [section["id"] for section in generated["sections"]]})
    section = generated["sections"][0]
    updated = client.put(f"/api/sections/{section['id']}", json={"label": "77"})
    assert updated.status_code == 200
    saved = client.get("/api/schedules").json()[0]
    assert saved["status"] == "valid"
    assert any(item["label"] == "77" for item in saved["sections"])


def test_session_change_review_and_conflict_revalidation(client):
    courses = [client.post("/api/courses", json=course_data(code)).json() for code in ("MAN2001", "MAN2002")]
    sections = [client.post(f"/api/courses/{course['id']}/sections", json={"label": "1"}).json() for course in courses]
    sessions = [client.post(f"/api/sections/{section['id']}/sessions", json=session_data(start=start, end=end)).json() for section, start, end in zip(sections, ("09:00", "10:00"), ("09:50", "10:50"))]
    pref = client.get("/api/preferences").json()
    pref["selected_course_ids"] = [course["id"] for course in courses]
    assert client.put("/api/preferences", json=pref).status_code == 200
    generated = client.post("/api/generate").json()["alternatives"][0]
    saved = client.post("/api/schedules", json={"name": "Managed", "section_ids": [item["id"] for item in generated["sections"]]}).json()
    snapshot = saved["sections"]

    added = client.post(f"/api/sections/{sections[0]['id']}/sessions", json=session_data(start="11:00", end="11:50"))
    assert added.status_code == 201
    review = client.get("/api/schedules").json()[0]
    assert review["status"] == "needs_review"
    assert review["sections"] == snapshot
    assert client.delete(f"/api/sessions/{added.json()['id']}").status_code == 200
    assert client.get("/api/schedules").json()[0]["status"] == "valid"

    changed = client.put(f"/api/sessions/{sessions[1]['id']}", json=session_data(start="09:20", end="10:10"))
    assert changed.status_code == 200
    invalid = client.get("/api/schedules").json()[0]
    assert invalid["status"] == "invalid"
    assert "MAN2001" in invalid["invalid_reason"] and "MAN2002" in invalid["invalid_reason"]
    assert invalid["sections"] == snapshot
    assert client.put(f"/api/sessions/{sessions[1]['id']}", json=session_data(start="10:00", end="10:50")).status_code == 200
    assert client.get("/api/schedules").json()[0]["status"] == "valid"
    with SessionLocal() as db:
        assert db.get(SavedSchedule, saved["id"]).snapshot["sections"] == snapshot


def test_time_inputs_require_ascii_zero_padded_format(client):
    course = client.post("/api/courses", json=course_data("MAN3001")).json()
    section = client.post(f"/api/courses/{course['id']}/sections", json={"label": "1"}).json()
    for bad in ("+8:40", "08:+0", "8:40", "24:00", "08:60", "０８:４０"):
        assert client.post(f"/api/sections/{section['id']}/sessions", json=session_data(start=bad)).status_code == 422
        pref = client.get("/api/preferences").json()
        pref["earliest_time"] = bad
        assert client.put("/api/preferences", json=pref).status_code == 422
