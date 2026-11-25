from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import AdminAccount, ClassSession, Course, Department, Section, StudentPreference
from ..schemas import CourseInput, SectionInput, SessionInput
from ..services.scheduler import active_sessions, overlaps, section_payload, public_session_type
from ..services.saved_schedules import revalidate_saved_schedules


router = APIRouter(prefix="/api")
ROOM_FOR_TYPE = {
    "lecture": "NORMAL DERSLİK",
    "laboratory": "LABORATUVAR - BİLGİSAYAR",
    "online": "ONLINE DERS",
    "external_training": "KURUM DIŞI EĞİTİM",
}


def field_error(field: str, message: str, status_code: int = 422):
    raise HTTPException(status_code, {"field": field, "message": message})


def course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None or not course.is_active:
        raise HTTPException(404, "Course not found.")
    return course


def section_or_404(db: Session, section_id: int) -> Section:
    section = db.get(Section, section_id)
    if section is None or not section.is_active or not section.course.is_active:
        raise HTTPException(404, "Section not found.")
    return section


def session_or_404(db: Session, session_id: int) -> ClassSession:
    session = db.get(ClassSession, session_id)
    if session is None or not session.is_active or not session.section.is_active or not session.section.course.is_active:
        raise HTTPException(404, "Session not found.")
    return session


def course_payload(course: Course) -> dict:
    sections = sorted((section for section in course.sections if section.is_active), key=lambda item: item.label)
    return {
        "id": course.id, "code": course.code, "name": course.name,
        "offering_department": course.offering_department,
        "ects": course.ects, "credit": course.credit, "mandatory": course.mandatory,
        "weekly_sessions": len(active_sessions(sections[0])) if sections else 0,
        "sections": [section_payload(section) for section in sections],
    }


def section_ids_for(course: Course) -> list[int]:
    return [section.id for section in course.sections]


def check_course_code(db: Session, code: str, current_id: int | None = None) -> None:
    duplicate = db.scalar(select(Course).where(func.lower(Course.code) == code.lower()))
    if duplicate is not None and duplicate.id != current_id:
        message = "This code belongs to an archived course. Restore it from Archived Courses." if not duplicate.is_active else "A course with this code already exists."
        field_error("code", message, 409)


def check_section_label(course: Course, label: str, current_id: int | None = None) -> None:
    if any(section.is_active and section.label.casefold() == label.casefold() and section.id != current_id for section in course.sections):
        field_error("label", "This section number already exists for the course.", 409)


def check_session_overlap(section: Section, day: int, start: str, end: str, current_id: int | None = None) -> None:
    proposed = type("ProposedSession", (), {"day": day, "start_time": start, "end_time": end})()
    for existing in active_sessions(section):
        if existing.id != current_id and overlaps(proposed, existing):
            field_error("start_time", f"Overlaps an existing session on this section ({existing.start_time}–{existing.end_time}).", 409)


@router.get("/courses")
def list_courses(db: Session = Depends(get_db)):
    courses = db.scalars(select(Course).where(Course.is_active.is_(True)).order_by(Course.code)).all()
    return [course_payload(course) for course in courses]


@router.get("/courses/archived")
def list_archived_courses(db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    courses = db.scalars(select(Course).where(Course.is_active.is_(False)).order_by(Course.code)).all()
    return [course_payload(course) for course in courses]


@router.get("/courses/{course_id}")
def get_course(course_id: int, db: Session = Depends(get_db)):
    return course_payload(course_or_404(db, course_id))


@router.post("/courses", status_code=201)
def add_course(payload: CourseInput, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    check_course_code(db, payload.code)
    department = db.scalar(select(Department).limit(1))
    course = Course(**payload.model_dump(), department=department)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course_payload(course)


@router.put("/courses/{course_id}")
def update_course(course_id: int, payload: CourseInput, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    course = course_or_404(db, course_id)
    check_course_code(db, payload.code, course.id)
    changed = any(getattr(course, field) != value for field, value in payload.model_dump().items())
    if changed:
        for field, value in payload.model_dump().items():
            setattr(course, field, value)
        affected = revalidate_saved_schedules(db, section_ids_for(course))
        db.commit()
    else:
        affected = 0
    return {**course_payload(course), "affected_schedules": affected}


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    course = course_or_404(db, course_id)
    course.is_active = False
    preferences = db.scalars(select(StudentPreference)).all()
    was_selected = any(course.id in (preference.selected_course_ids or []) for preference in preferences)
    section_ids = set(section_ids_for(course))
    for preference in preferences:
        preference.selected_course_ids = [item for item in (preference.selected_course_ids or []) if item != course.id]
        preference.excluded_section_ids = [item for item in (preference.excluded_section_ids or []) if item not in section_ids]
    affected = revalidate_saved_schedules(db, list(section_ids))
    db.commit()
    return {"message": f"{course.code} was removed from the active catalogue.", "removed_from_selection": was_selected, "affected_schedules": affected}


@router.post("/courses/{course_id}/restore")
def restore_course(course_id: int, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found.")
    if course.is_active:
        raise HTTPException(409, "Course is already active.")
    course.is_active = True
    affected = revalidate_saved_schedules(db, section_ids_for(course))
    db.commit()
    return {**course_payload(course), "affected_schedules": affected}


@router.get("/courses/{course_id}/sections")
def list_sections(course_id: int, db: Session = Depends(get_db)):
    course = course_or_404(db, course_id)
    return [section_payload(section) for section in course.sections if section.is_active]


@router.post("/courses/{course_id}/sections", status_code=201)
def add_section(course_id: int, payload: SectionInput, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    course = course_or_404(db, course_id)
    check_section_label(course, payload.label)
    section = Section(label=payload.label, course=course)
    db.add(section)
    db.commit()
    db.refresh(section)
    return section_payload(section)


@router.get("/sections/{section_id}")
def get_section(section_id: int, db: Session = Depends(get_db)):
    return section_payload(section_or_404(db, section_id))


@router.put("/sections/{section_id}")
def update_section(section_id: int, payload: SectionInput, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    section = section_or_404(db, section_id)
    check_section_label(section.course, payload.label, section.id)
    affected = 0
    if section.label != payload.label:
        section.label = payload.label
        affected = revalidate_saved_schedules(db, [section.id])
        db.commit()
    return {**section_payload(section), "affected_schedules": affected}


@router.delete("/sections/{section_id}")
def delete_section(section_id: int, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    section = section_or_404(db, section_id)
    section.is_active = False
    for preference in db.scalars(select(StudentPreference)).all():
        preference.excluded_section_ids = [item for item in (preference.excluded_section_ids or []) if item != section.id]
    affected = revalidate_saved_schedules(db, [section.id])
    db.commit()
    return {"message": "Section removed from the active catalogue.", "affected_schedules": affected}


@router.get("/sections/{section_id}/sessions")
def list_sessions(section_id: int, db: Session = Depends(get_db)):
    return section_payload(section_or_404(db, section_id))["sessions"]


@router.post("/sections/{section_id}/sessions", status_code=201)
def add_session(section_id: int, payload: SessionInput, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    section = section_or_404(db, section_id)
    check_session_overlap(section, payload.day, payload.start_time, payload.end_time)
    session = ClassSession(
        section=section, day=payload.day, start_time=payload.start_time, end_time=payload.end_time,
        session_type="practical" if payload.session_type == "laboratory" else "external_training" if payload.session_type == "external_training" else "theory",
        room_type=ROOM_FOR_TYPE[payload.session_type], classroom=payload.classroom, instructor=payload.instructor,
        source_marker=None, source_page=0,
    )
    db.add(session)
    affected = revalidate_saved_schedules(db, [section.id])
    db.commit()
    db.refresh(session)
    return {**next(item for item in section_payload(section)["sessions"] if item["id"] == session.id), "affected_schedules": affected}


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = session_or_404(db, session_id)
    return next(item for item in section_payload(session.section)["sessions"] if item["id"] == session.id)


@router.put("/sessions/{session_id}")
def update_session(session_id: int, payload: SessionInput, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    session = session_or_404(db, session_id)
    check_session_overlap(session.section, payload.day, payload.start_time, payload.end_time, session.id)
    changed = any((session.day != payload.day, session.start_time != payload.start_time, session.end_time != payload.end_time, public_session_type(session) != payload.session_type, session.classroom != payload.classroom, session.instructor != payload.instructor))
    affected = 0
    if changed:
        if public_session_type(session) != payload.session_type:
            session.room_type = ROOM_FOR_TYPE[payload.session_type]
        session.session_type = "practical" if payload.session_type == "laboratory" else "external_training" if payload.session_type == "external_training" else "theory"
        session.day, session.start_time, session.end_time = payload.day, payload.start_time, payload.end_time
        session.classroom, session.instructor = payload.classroom, payload.instructor
        session.source_marker, session.source_page = None, 0
        affected = revalidate_saved_schedules(db, [session.section_id])
        db.commit()
    return {**next(item for item in section_payload(session.section)["sessions"] if item["id"] == session.id), "affected_schedules": affected}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), admin: AdminAccount = Depends(require_admin)):
    session = session_or_404(db, session_id)
    session.is_active = False
    affected = revalidate_saved_schedules(db, [session.section_id])
    db.commit()
    return {"message": "Session removed from the active catalogue.", "affected_schedules": affected}
