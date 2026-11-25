from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    courses: Mapped[list["Course"]] = relationship(back_populates="department")


class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(Integer)
    admin: Mapped[AdminAccount] = relationship()


class VisitorSession(Base):
    __tablename__ = "visitor_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[int] = mapped_column(Integer)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    offering_department: Mapped[str] = mapped_column(String(160))
    ects: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mandatory: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    department: Mapped[Department] = relationship(back_populates="courses")
    sections: Mapped[list["Section"]] = relationship(back_populates="course")


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(12))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    course: Mapped[Course] = relationship(back_populates="sections")
    sessions: Mapped[list["ClassSession"]] = relationship(back_populates="section")


class ClassSession(Base):
    __tablename__ = "class_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    day: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    room_type: Mapped[str] = mapped_column(String(64))
    session_type: Mapped[str] = mapped_column(String(16))
    classroom: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instructor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    source_marker: Mapped[str | None] = mapped_column(String(4), nullable=True)
    source_page: Mapped[int] = mapped_column(Integer)
    section: Mapped[Section] = relationship(back_populates="sessions")

    @property
    def delivery_mode(self) -> str:
        if self.room_type == "ONLINE DERS":
            return "online"
        if self.room_type == "KURUM DIŞI EĞİTİM":
            return "off_campus"
        return "campus"


class StudentPreference(Base):
    __tablename__ = "student_preferences"
    id: Mapped[int] = mapped_column(primary_key=True)
    visitor_id: Mapped[int | None] = mapped_column(ForeignKey("visitor_sessions.id"), unique=True, nullable=True)
    selected_course_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    excluded_section_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    preferred_free_days: Mapped[list[int]] = mapped_column(JSON, default=list)
    free_days_hard: Mapped[bool] = mapped_column(Boolean, default=False)
    earliest_time: Mapped[str] = mapped_column(String(5), default="08:00")
    latest_time: Mapped[str] = mapped_column(String(5), default="18:30")
    max_campus_days: Mapped[int] = mapped_column(Integer, default=6)
    max_ects: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimize_gaps: Mapped[bool] = mapped_column(Boolean, default=True)


class SavedSchedule(Base):
    __tablename__ = "saved_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    visitor_id: Mapped[int | None] = mapped_column(ForeignKey("visitor_sessions.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    score: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="valid", server_default="valid")
    invalid_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    items: Mapped[list["SavedScheduleItem"]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class SavedScheduleItem(Base):
    __tablename__ = "saved_schedule_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("saved_schedules.id"))
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    schedule: Mapped[SavedSchedule] = relationship(back_populates="items")
    section: Mapped[Section] = relationship()
