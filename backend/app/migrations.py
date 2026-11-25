from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, selectinload

from .models import SavedSchedule, SavedScheduleItem, Section, StudentPreference
from .schemas import PreferenceInput
from .services.scheduler import metrics, result_payload


ADDITIVE_COLUMNS = {
    "courses": {"is_active": "BOOLEAN NOT NULL DEFAULT 1"},
    "sections": {"is_active": "BOOLEAN NOT NULL DEFAULT 1"},
    "class_sessions": {
        "classroom": "VARCHAR(64)",
        "instructor": "VARCHAR(120)",
        "is_active": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "saved_schedules": {
        "snapshot": "JSON",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'valid'",
        "invalid_reason": "VARCHAR(240)",
        "visitor_id": "INTEGER REFERENCES visitor_sessions(id)",
    },
    "student_preferences": {"visitor_id": "INTEGER REFERENCES visitor_sessions(id)"},
}


def migrate_schema(engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        for table, columns in ADDITIVE_COLUMNS.items():
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def backfill_saved_snapshots(db: Session) -> None:
    preference = db.get(StudentPreference, 1)
    if preference is None:
        return
    preferences = PreferenceInput.model_validate({key: getattr(preference, key) for key in PreferenceInput.model_fields})
    schedules = db.scalars(
        select(SavedSchedule)
        .where(SavedSchedule.snapshot.is_(None))
        .options(selectinload(SavedSchedule.items).selectinload(SavedScheduleItem.section).selectinload(Section.sessions))
    ).all()
    for schedule in schedules:
        sections = [item.section for item in schedule.items]
        schedule.snapshot = result_payload(metrics(sections, preferences))
        schedule.status = "valid"
    if schedules:
        db.commit()
