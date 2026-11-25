from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import get_visitor
from ..database import get_db
from ..models import Course, SavedSchedule, SavedScheduleItem, Section, StudentPreference, VisitorSession
from ..schemas import PreferenceInput, SaveScheduleInput
from ..seed import ACTIVE_PERIOD, DEPARTMENT_NAME
from ..services.scheduler import complete_ects, generate, metrics, result_payload, valid_extension
from ..services.saved_schedules import revalidate_saved_schedules
from .management import course_payload


router = APIRouter(prefix="/api")


def current_preferences(db: Session, visitor: VisitorSession) -> StudentPreference:
    return db.scalar(select(StudentPreference).where(StudentPreference.visitor_id == visitor.id))


def preference_payload(preference: StudentPreference) -> dict:
    return PreferenceInput.model_validate({key: getattr(preference, key) for key in PreferenceInput.model_fields}).model_dump()


@router.get("/health")
def health():
    return {"status": "ok", "period": ACTIVE_PERIOD}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)):
    courses = db.scalars(
        select(Course).where(Course.is_active.is_(True))
        .options(selectinload(Course.sections).selectinload(Section.sessions))
        .order_by(Course.code)
    ).all()
    return {
        "source_notice": "The supplied 2026–2027 Fall PDF omits ECTS, credits, instructors, mandatory status, and room numbers. Manually entered values may be shown.",
        "department": DEPARTMENT_NAME,
        "period": ACTIVE_PERIOD,
        "courses": [course_payload(item) for item in courses],
    }


@router.get("/preferences")
def get_preferences(db: Session = Depends(get_db), visitor: VisitorSession = Depends(get_visitor)):
    return preference_payload(current_preferences(db, visitor))


@router.put("/preferences")
def set_preferences(payload: PreferenceInput, db: Session = Depends(get_db), visitor: VisitorSession = Depends(get_visitor)):
    pref = current_preferences(db, visitor)
    for key, value in payload.model_dump().items():
        setattr(pref, key, value)
    revalidate_saved_schedules(db, visitor_id=visitor.id)
    db.commit()
    db.refresh(pref)
    return preference_payload(pref)


@router.post("/generate")
def generate_schedules(db: Session = Depends(get_db), visitor: VisitorSession = Depends(get_visitor)):
    pref = PreferenceInput.model_validate(preference_payload(current_preferences(db, visitor)))
    results, error = generate(db, pref)
    if error:
        raise HTTPException(422, error)
    return {"alternatives": [result_payload(result) for result in results]}


@router.get("/schedules")
def list_schedules(db: Session = Depends(get_db), visitor: VisitorSession = Depends(get_visitor)):
    schedules = db.scalars(
        select(SavedSchedule).where(SavedSchedule.visitor_id == visitor.id)
        .options(selectinload(SavedSchedule.items).selectinload(SavedScheduleItem.section).selectinload(Section.sessions))
        .order_by(SavedSchedule.id.desc())
    ).all()
    pref = PreferenceInput.model_validate(preference_payload(current_preferences(db, visitor)))
    return [
        {"id": schedule.id, "name": schedule.name, "status": schedule.status, "invalid_reason": schedule.invalid_reason,
         **(result_payload(metrics([item.section for item in schedule.items], pref)) if schedule.status == "valid" else schedule.snapshot or result_payload(metrics([item.section for item in schedule.items], pref)))}
        for schedule in schedules
    ]


@router.post("/schedules", status_code=201)
def save_schedule(payload: SaveScheduleInput, db: Session = Depends(get_db), visitor: VisitorSession = Depends(get_visitor)):
    sections = db.scalars(
        select(Section).where(Section.id.in_(payload.section_ids))
        .options(selectinload(Section.sessions), selectinload(Section.course))
    ).all()
    if len(sections) != len(payload.section_ids) or len({section.course_id for section in sections}) != len(sections) or any(not section.is_active or not section.course.is_active for section in sections):
        raise HTTPException(422, "Choose one valid section per course.")
    pref = PreferenceInput.model_validate(preference_payload(current_preferences(db, visitor)))
    if {section.course_id for section in sections} != set(pref.selected_course_ids):
        raise HTTPException(422, "The schedule must cover every selected course.")
    total_ects = complete_ects(sections)
    if total_ects is not None and pref.max_ects is not None and total_ects > pref.max_ects:
        raise HTTPException(422, f"Selected courses total {total_ects} ECTS, above your {pref.max_ects} ECTS limit.")
    chosen = []
    for section in sections:
        if not valid_extension(chosen, section, pref):
            raise HTTPException(422, "The schedule violates a required rule or contains a time conflict.")
        chosen.append(section)
    result = metrics(sections, pref)
    snapshot = result_payload(result)
    schedule = SavedSchedule(visitor_id=visitor.id, name=payload.name.strip(), score=result.score, snapshot=snapshot, status="valid", items=[SavedScheduleItem(section_id=section.id) for section in sections])
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return {"id": schedule.id, "name": schedule.name, "status": "valid", "invalid_reason": None, **snapshot}
