import json
from collections import Counter
from itertools import product
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import func, select

from app.models import ClassSession, Course, Section
from app.schemas import PreferenceInput
from app.services.scheduler import generate, metrics, overlaps, valid_extension


DATA_FILE = Path(__file__).resolve().parents[1] / "app" / "data" / "fall_2026.json"


def course(db, code):
    return db.scalar(select(Course).where(Course.code == code))


def preferences(db, codes, **changes):
    return PreferenceInput(selected_course_ids=[course(db, code).id for code in codes], **changes)


def test_pdf_catalog_counts_and_final_page(db):
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    assert len(data["courses"]) == 20
    assert len(data["sessions"]) == 115
    assert len({(row["code"], row["section"]) for row in data["sessions"]}) == 31
    assert Counter(row["source_page"] for row in data["sessions"]) == {1: 78, 2: 36, 3: 1}
    assert db.scalar(select(func.count()).select_from(Course)) == 20
    assert db.scalar(select(func.count()).select_from(Section)) == 31
    assert db.scalar(select(func.count()).select_from(ClassSession)) == 115
    last = [row for row in data["sessions"] if row["source_page"] == 3]
    assert [(row["code"], row["section"], row["day"], row["start_time"], row["end_time"]) for row in last] == [("CEN3120", "1", 2, "17:40", "18:30")]


def test_cen3001_theory_and_labs_stay_with_each_section(db):
    sections = {section.label: section for section in course(db, "CEN3001").sections}
    assert set(sections) == {"1", "2", "3"}
    for section in sections.values():
        assert len(section.sessions) == 5
        assert Counter(session.session_type for session in section.sessions) == {"theory": 3, "practical": 2}
        assert all(session.day == 2 for session in section.sessions)
    assert sorted(session.start_time for session in sections["1"].sessions if session.session_type == "practical") == ["11:40", "12:40"]
    for label in ("2", "3"):
        assert sorted(session.start_time for session in sections[label].sessions if session.session_type == "practical") == ["13:40", "14:40"]


def test_generated_schedules_have_whole_sections_and_no_conflicts(db):
    selected = ["CEN3001", "CEN3003", "CEN3005", "CEN3007", "SEN3001"]
    results, error = generate(db, preferences(db, selected))
    assert error is None
    assert 1 <= len(results) <= 5
    assert [result.score for result in results] == sorted((result.score for result in results), reverse=True)
    for result in results:
        assert {section.course.code for section in result.sections} == set(selected)
        sessions = [session for section in result.sections for session in section.sessions]
        assert len(sessions) == 23
        assert all(not overlaps(left, right) for index, left in enumerate(sessions) for right in sessions[index + 1:])
        assert result.total_ects is None


def test_second_session_and_intra_section_conflicts_are_rejected(db):
    cen = course(db, "CEN3001").sections[0]
    candidate = SimpleNamespace(id=999, label="1", course=SimpleNamespace(code="TEST"), sessions=[
        SimpleNamespace(day=0, start_time="09:40", end_time="10:30", delivery_mode="campus"),
        SimpleNamespace(day=2, start_time="09:40", end_time="10:30", delivery_mode="campus"),
    ])
    assert not valid_extension([cen], candidate, PreferenceInput())
    own_overlap = SimpleNamespace(id=998, sessions=[
        SimpleNamespace(day=1, start_time="09:40", end_time="10:30", delivery_mode="campus"),
        SimpleNamespace(day=1, start_time="10:00", end_time="11:00", delivery_mode="campus"),
    ])
    assert not valid_extension([], own_overlap, PreferenceInput())


def test_saturday_preference_and_real_section_counts(db):
    results, error = generate(db, preferences(db, ["CEN3005"], preferred_free_days=[5], free_days_hard=True))
    assert error is None
    assert {result.sections[0].label for result in results} == {"1", "2"}
    assert all(5 in result.free_days for result in results)
    all_results, error = generate(db, preferences(db, ["CEN3005"]))
    assert error is None
    assert len(all_results) == 4
    assert {result.sections[0].label for result in all_results} == {"1", "2", "3", "4"}


def test_online_sessions_conflict_but_do_not_create_campus_day(db):
    online = course(db, "ENG3020").sections[0]
    assert all(session.delivery_mode == "online" for session in online.sessions)
    assert metrics([online], PreferenceInput()).campus_days == 0
    hulu_friday = next(section for section in course(db, "HLU0107").sections if section.label == "3")
    assert not valid_extension([online], hulu_friday, PreferenceInput())


def test_internship_is_saturday_off_campus_and_one_minute(db):
    internship = course(db, "ENG0010").sections[0]
    assert internship.label == "5"
    assert [(session.day, session.start_time, session.end_time, session.delivery_mode) for session in internship.sessions] == [(5, "08:00", "08:01", "off_campus")]
    result = metrics([internship], PreferenceInput())
    assert result.campus_days == 0
    assert result.earliest_class == "—"
    assert 5 not in result.free_days


def test_credit_limit_stays_inactive_for_unknown_values(db):
    results, error = generate(db, preferences(db, ["CEN3001"], max_ects=1))
    assert error is None
    assert len(results) == 3
    assert all(result.total_ects is None for result in results)


def test_single_section_course_returns_one_real_alternative(db):
    results, error = generate(db, preferences(db, ["CEN3003"]))
    assert error is None
    assert len(results) == 1


def test_no_solution_names_conflicting_courses_and_sections(db):
    results, error = generate(db, preferences(db, ["CEN3001", "EEE3140"]))
    assert not results
    assert "CEN3001 section" in error
    assert "EEE3140 section" in error
    assert "Wednesday" in error


def test_ranked_alternatives_match_exhaustive_search(db):
    codes = ["CEN3001", "CEN3005", "HLU0107"]
    chosen_courses = [course(db, code) for code in codes]
    for max_days, free_days in ((6, []), (3, [5])):
        rules = preferences(db, codes, max_campus_days=max_days, preferred_free_days=free_days, free_days_hard=True)
        ordered = sorted(
            chosen_courses,
            key=lambda item: (sum(valid_extension([], section, rules) for section in item.sections), item.id),
        )
        expected = []
        for selection in product(*(item.sections for item in ordered)):
            if all(valid_extension(list(selection[:index]), section, rules) for index, section in enumerate(selection)):
                score = metrics(list(selection), rules)
                expected.append((-score.score, score.campus_days, score.gap_minutes, tuple(section.id for section in selection)))
        results, error = generate(db, rules)
        actual = [(-result.score, result.campus_days, result.gap_minutes, tuple(section.id for section in result.sections)) for result in results]
        assert expected and error is None
        assert actual == sorted(expected)[:5]
        assert len(set(actual)) == len(actual)
