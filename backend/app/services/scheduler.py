from dataclasses import dataclass
from functools import cache

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Course, Section
from ..schemas import PreferenceInput


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
ROOM_LABELS = {
    "NORMAL DERSLİK": "Standard classroom",
    "AMFİ": "Lecture hall",
    "LABORATUVAR - BİLGİSAYAR": "Computer laboratory",
    "ONLINE DERS": "Online class",
    "KURUM DIŞI EĞİTİM": "External training",
}


@dataclass
class Result:
    sections: list[Section]
    score: int
    campus_days: int
    free_days: list[int]
    gap_minutes: int
    earliest_class: str
    latest_class: str
    total_ects: int | None


def minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def overlaps(left, right) -> bool:
    return left.day == right.day and left.start_time < right.end_time and right.start_time < left.end_time


def active_sessions(section: Section):
    return [session for session in section.sessions if getattr(session, "is_active", True)]


def public_session_type(session) -> str:
    if session.delivery_mode == "online":
        return "online"
    if session.delivery_mode == "off_campus":
        return "external_training"
    return "laboratory" if session.session_type == "practical" else "lecture"


def complete_ects(sections: list[Section]) -> int | None:
    credits = [section.course.ects for section in sections]
    return sum(credits) if all(value is not None for value in credits) else None


def metrics(sections: list[Section], preferences: PreferenceInput) -> Result:
    sessions = [session for section in sections for session in active_sessions(section)]
    campus_sessions = [session for session in sessions if session.delivery_mode == "campus"]
    campus_days = {session.day for session in campus_sessions}
    occupied_days = {session.day for session in sessions}
    gaps = 0
    for day in campus_days:
        blocks = sorted((session for session in campus_sessions if session.day == day), key=lambda item: item.start_time)
        for previous, following in zip(blocks, blocks[1:]):
            gaps += max(0, minutes(following.start_time) - minutes(previous.end_time) - 10)
    timed_sessions = [session for session in sessions if session.delivery_mode != "off_campus"]
    earliest = min((session.start_time for session in timed_sessions), default="—")
    latest = max((session.end_time for session in timed_sessions), default="—")
    early_minutes = sum(max(0, 580 - minutes(session.start_time)) for session in timed_sessions)
    occupied_preferred = sum(day in occupied_days for day in preferences.preferred_free_days)
    score = round(100 - len(campus_days) * 4 - early_minutes / 30 - (gaps / 60 * 3 if preferences.minimize_gaps else 0) - occupied_preferred * 10)
    return Result(
        sections=list(sections), score=max(0, min(100, score)), campus_days=len(campus_days),
        free_days=[day for day in range(6) if day not in occupied_days], gap_minutes=gaps,
        earliest_class=earliest, latest_class=latest, total_ects=complete_ects(sections),
    )


def conflict_detail(left: Section, right: Section) -> str | None:
    for first in active_sessions(left):
        for second in active_sessions(right):
            if overlaps(first, second):
                start = max(first.start_time, second.start_time)
                end = min(first.end_time, second.end_time)
                return f"{left.course.code} section {left.label} and {right.course.code} section {right.label} overlap on {DAYS[first.day]} {start}–{end}."
    return None


def valid_extension(chosen: list[Section], candidate: Section, preferences: PreferenceInput) -> bool:
    if candidate.id in preferences.excluded_section_ids:
        return False
    candidate_sessions = active_sessions(candidate)
    if not getattr(candidate, "is_active", True) or not getattr(getattr(candidate, "course", None), "is_active", True) or not candidate_sessions:
        return False
    if any(session.start_time < preferences.earliest_time or session.end_time > preferences.latest_time for session in candidate_sessions):
        return False
    if preferences.free_days_hard and any(session.day in preferences.preferred_free_days for session in candidate_sessions):
        return False
    if any(overlaps(left, right) for index, left in enumerate(candidate_sessions) for right in candidate_sessions[index + 1:]):
        return False
    if any(conflict_detail(section, candidate) for section in chosen):
        return False
    campus_days = {session.day for section in chosen + [candidate] for session in active_sessions(section) if session.delivery_mode == "campus"}
    return len(campus_days) <= preferences.max_campus_days


def generate(db: Session, preferences: PreferenceInput) -> tuple[list[Result], str | None]:
    if not preferences.selected_course_ids:
        return [], "Select at least one course before generating a schedule."
    courses = db.scalars(
        select(Course).where(Course.id.in_(preferences.selected_course_ids), Course.is_active.is_(True))
        .options(selectinload(Course.sections).selectinload(Section.sessions))
    ).all()
    if len(courses) != len(preferences.selected_course_ids):
        return [], "One or more selected courses are not in the Fall 2026 catalogue."
    known_ects = [course.ects for course in courses]
    if preferences.max_ects is not None and all(value is not None for value in known_ects) and sum(known_ects) > preferences.max_ects:
        return [], f"Selected courses total {sum(known_ects)} ECTS, above your {preferences.max_ects} ECTS limit."
    options = []
    for course in courses:
        available = [section for section in course.sections if valid_extension([], section, preferences)]
        if not available:
            return [], f"No eligible section remains for {course.code}. Check excluded sections, time limits, and required free days."
        options.append((course, available))
    options.sort(key=lambda item: (len(item[1]), item[0].id))
    campus_days_by_section = {
        section.id: {session.day for session in active_sessions(section) if session.delivery_mode == "campus"}
        for _, sections in options for section in sections
    }

    # A pair of sections has the same conflict in every search branch.
    @cache
    def cached_conflict(left: Section, right: Section) -> str | None:
        return conflict_detail(left, right)

    best: list[Result] = []
    representative_conflict: str | None = None

    def search(index: int, chosen: list[Section], campus_days: set[int]) -> None:
        nonlocal representative_conflict
        if index == len(options):
            best.append(metrics(chosen, preferences))
            best.sort(key=lambda item: (-item.score, item.campus_days, item.gap_minutes, tuple(section.id for section in item.sections)))
            if len(best) > 5:
                best.pop()
            return
        for section in options[index][1]:
            conflict = next((detail for previous in chosen if (detail := cached_conflict(previous, section))), None)
            if conflict:
                if representative_conflict is None:
                    representative_conflict = conflict
                continue
            next_days = campus_days | campus_days_by_section[section.id]
            if len(next_days) <= preferences.max_campus_days:
                search(index + 1, chosen + [section], next_days)

    search(0, [], set())
    if not best:
        if representative_conflict:
            return [], f"No conflict-free combination satisfies all required rules. For example, {representative_conflict} Review sections or required free days."
        return [], "No combination satisfies the required time window, campus day limit, and free-day rules."
    return best, None


def section_payload(section: Section) -> dict:
    return {
        "id": section.id, "label": section.label, "course_id": section.course_id,
        "course_code": section.course.code, "course_name": section.course.name,
        "offering_department": section.course.offering_department, "ects": section.course.ects,
        "sessions": [{
            "id": session.id, "day": session.day, "start_time": session.start_time, "end_time": session.end_time,
            "room_type": session.room_type, "room_type_label": ROOM_LABELS.get(session.room_type, session.room_type),
            "session_type": public_session_type(session), "delivery_mode": session.delivery_mode,
            "classroom": session.classroom, "instructor": session.instructor,
            "source_marker": session.source_marker,
        } for session in sorted(active_sessions(section), key=lambda item: (item.day, item.start_time))],
    }


def result_payload(result: Result) -> dict:
    return {
        "score": result.score, "total_ects": result.total_ects,
        "campus_days": result.campus_days, "free_days": result.free_days,
        "gap_minutes": result.gap_minutes, "earliest_class": result.earliest_class,
        "latest_class": result.latest_class,
        "sections": [section_payload(section) for section in sorted(result.sections, key=lambda item: item.course.code)],
    }
