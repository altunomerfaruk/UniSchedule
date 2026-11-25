from app.seed import ACTIVE_PERIOD, DEPARTMENT_NAME


def test_catalog_and_swagger(client):
    assert client.get("/api/health").json() == {"status": "ok", "period": ACTIVE_PERIOD}
    catalog = client.get("/api/catalog").json()
    assert catalog["department"] == DEPARTMENT_NAME
    assert catalog["period"] == ACTIVE_PERIOD
    assert len(catalog["courses"]) == 20
    assert sum(len(section["sessions"]) for course in catalog["courses"] for section in course["sections"]) == 115
    assert sum(len(course["sections"]) for course in catalog["courses"]) == 31
    assert all(course["ects"] is None and course["credit"] is None and course["mandatory"] is None for course in catalog["courses"])
    assert client.get("/openapi.json").status_code == 200


def test_preference_generation_and_save(client):
    pref = client.get("/api/preferences").json()
    assert len(pref["selected_course_ids"]) == 5
    response = client.post("/api/generate")
    assert response.status_code == 200, response.text
    alternatives = response.json()["alternatives"]
    assert 1 <= len(alternatives) <= 5
    assert alternatives[0]["total_ects"] is None
    selected = alternatives[0]
    saved = client.post("/api/schedules", json={"name": "PDF schedule", "section_ids": [section["id"] for section in selected["sections"]]})
    assert saved.status_code == 201, saved.text
    assert any(item["name"] == "PDF schedule" for item in client.get("/api/schedules").json())


def test_saturday_hard_free_chooses_tuesday_microprocessors(client):
    catalog = client.get("/api/catalog").json()
    microprocessors = next(item for item in catalog["courses"] if item["code"] == "CEN3005")
    pref = client.get("/api/preferences").json()
    pref["selected_course_ids"] = [microprocessors["id"]]
    pref["preferred_free_days"] = [5]
    pref["free_days_hard"] = True
    assert client.put("/api/preferences", json=pref).status_code == 200
    response = client.post("/api/generate")
    assert response.status_code == 200, response.text
    assert {item["sections"][0]["label"] for item in response.json()["alternatives"]} == {"1", "2"}


def test_invalid_preferences_and_conflict_explanation(client):
    pref = client.get("/api/preferences").json()
    pref["earliest_time"] = "19:00"
    pref["latest_time"] = "08:00"
    assert client.put("/api/preferences", json=pref).status_code == 422
    pref["earliest_time"] = "08:00"
    pref["latest_time"] = "18:30"
    pref["preferred_free_days"] = [6]
    assert client.put("/api/preferences", json=pref).status_code == 422
    pref["preferred_free_days"] = []
    catalog = client.get("/api/catalog").json()
    pref["selected_course_ids"] = [item["id"] for item in catalog["courses"] if item["code"] in ("CEN3001", "EEE3140")]
    assert client.put("/api/preferences", json=pref).status_code == 200
    response = client.post("/api/generate")
    assert response.status_code == 422
    assert "CEN3001 section" in response.json()["detail"]
    assert "EEE3140 section" in response.json()["detail"]


def test_unknown_ects_cannot_be_misrepresented_as_total(client):
    catalog = client.get("/api/catalog").json()
    one = next(item for item in catalog["courses"] if item["code"] == "CEN3001")
    pref = client.get("/api/preferences").json()
    pref["selected_course_ids"] = [one["id"]]
    pref["max_ects"] = 1
    assert client.put("/api/preferences", json=pref).status_code == 200
    generated = client.post("/api/generate")
    assert generated.status_code == 200
    option = generated.json()["alternatives"][0]
    assert option["total_ects"] is None
    saved = client.post("/api/schedules", json={"name": "Unknown ECTS", "section_ids": [option["sections"][0]["id"]]})
    assert saved.status_code == 201
