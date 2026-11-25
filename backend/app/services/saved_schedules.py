from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import SavedSchedule, SavedScheduleItem, Section, StudentPreference
from ..schemas import PreferenceInput
from .scheduler import DAYS, active_sessions, complete_ects, conflict_detail, metrics, overlaps, result_payload


def current_preference_input(db: Session, visitor_id: int | None) -> PreferenceInput:
    preference = db.scalar(select(StudentPreference).where(StudentPreference.visitor_id == visitor_id)) if visitor_id is not None else db.get(StudentPreference, 1)
    if preference is None:
        return PreferenceInput()
    return PreferenceInput.model_validate({key: getattr(preference, key) for key in PreferenceInput.model_fields})


def session_signature(section_payload: dict) -> tuple:
    return tuple(sorted(
        (session["id"], session["day"], session["start_time"], session["end_time"], session["session_type"], session["delivery_mode"])
        for session in section_payload["sessions"]
    ))


def invalid_reason(sections: list[Section], preferences: PreferenceInput) -> str | None:
    for section in sections:
        if not section.course.is_active:
            return f"{section.course.code} was deleted from the active catalogue."
        if not section.is_active:
            return f"{section.course.code} section {section.label} was deleted from the active catalogue."
        sessions = active_sessions(section)
        if not sessions:
            return f"{section.course.code} section {section.label} has no active sessions."
        if section.id in preferences.excluded_section_ids:
            return f"{section.course.code} section {section.label} is excluded by current preferences."
        for session in sessions:
            if session.start_time < preferences.earliest_time or session.end_time > preferences.latest_time:
                return f"{section.course.code} section {section.label} is outside the current class time window."
            if preferences.free_days_hard and session.day in preferences.preferred_free_days:
                return f"{section.course.code} section {section.label} meets on required free day {DAYS[session.day]}."
        for index, left in enumerate(sessions):
            if any(overlaps(left, right) for right in sessions[index + 1:]):
                return f"{section.course.code} section {section.label} has overlapping sessions."
    for index, left in enumerate(sections):
        for right in sections[index + 1:]:
            if left.course_id == right.course_id:
                return f"The saved schedule has two sections of {left.course.code}."
            detail = conflict_detail(left, right)
            if detail:
                return detail
    campus_days = {session.day for section in sections for session in active_sessions(section) if session.delivery_mode == "campus"}
    if len(campus_days) > preferences.max_campus_days:
        return f"The schedule requires {len(campus_days)} campus days, above the current {preferences.max_campus_days}-day limit."
    ects = complete_ects(sections)
    if ects is not None and preferences.max_ects is not None and ects > preferences.max_ects:
        return f"The schedule has {ects} ECTS, above the current {preferences.max_ects} ECTS limit."
    return None


def revalidate_saved_schedules(db: Session, section_ids: list[int] | None = None, visitor_id: int | None = None) -> int:
    db.flush()
    query = select(SavedSchedule).options(
        selectinload(SavedSchedule.items).selectinload(SavedScheduleItem.section).selectinload(Section.sessions)
    )
    if section_ids is not None:
        if not section_ids:
            return 0
        query = query.join(SavedScheduleItem).where(SavedScheduleItem.section_id.in_(section_ids)).distinct()
    if visitor_id is not None:
        query = query.where(SavedSchedule.visitor_id == visitor_id)
    schedules = db.scalars(query).all()
    for schedule in schedules:
        preferences = current_preference_input(db, schedule.visitor_id)
        sections = [item.section for item in schedule.items]
        problem = invalid_reason(sections, preferences)
        if problem:
            schedule.status = "invalid"
            schedule.invalid_reason = problem
            continue
        current = result_payload(metrics(sections, preferences))
        previous = {section["id"]: session_signature(section) for section in (schedule.snapshot or {}).get("sections", [])}
        changed = any(previous.get(section["id"]) != session_signature(section) for section in current["sections"])
        if changed:
            schedule.status = "needs_review"
            schedule.invalid_reason = "The sessions or delivery mode changed. Review this schedule and generate it again if needed."
        else:
            schedule.status = "valid"
            schedule.invalid_reason = None
    return len(schedules)
