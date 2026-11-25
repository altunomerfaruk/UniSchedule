import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ClassSession, Course, Department, Section, StudentPreference


DATA_FILE = Path(__file__).resolve().parent / "data" / "fall_2026.json"
DEPARTMENT_NAME = "Software Engineering (English)"
ACTIVE_PERIOD = "2026–2027 Fall"
DEFAULT_CODES = ["CEN3001", "CEN3003", "CEN3005", "CEN3007", "SEN3001"]


def load_catalog() -> dict:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    assert data["period"] == ACTIVE_PERIOD
    assert len(data["courses"]) == 20
    assert len(data["sessions"]) == 115
    assert len({(row["code"], row["section"]) for row in data["sessions"]}) == 31
    return data


def seed_fall_data(db: Session) -> None:
    if db.scalar(select(Department.id).limit(1)) is not None:
        return
    data = load_catalog()
    department = Department(name=DEPARTMENT_NAME)
    db.add(department)
    db.flush()
    courses = {}
    for row in data["courses"]:
        course = Course(
            code=row["code"], name=row["name"], offering_department=row["offering_department"],
            ects=row["ects"], credit=row["credit"], mandatory=row["mandatory"], department=department,
        )
        db.add(course)
        db.flush()
        courses[row["code"]] = course
    sections = {}
    for row in data["sessions"]:
        key = (row["code"], row["section"])
        if key not in sections:
            section = Section(label=row["section"], course=courses[row["code"]])
            db.add(section)
            db.flush()
            sections[key] = section
        db.add(ClassSession(
            section=sections[key], day=row["day"], start_time=row["start_time"],
            end_time=row["end_time"], room_type=row["room_type"],
            session_type=row["session_type"], source_marker=row["source_marker"],
            source_page=row["source_page"],
        ))
    db.add(StudentPreference(id=1, selected_course_ids=[courses[code].id for code in DEFAULT_CODES]))
    db.commit()
