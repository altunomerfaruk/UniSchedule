import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PreferenceInput(BaseModel):
    selected_course_ids: list[int] = Field(default_factory=list)
    excluded_section_ids: list[int] = Field(default_factory=list)
    preferred_free_days: list[int] = Field(default_factory=list)
    free_days_hard: bool = False
    earliest_time: str = "08:00"
    latest_time: str = "18:30"
    max_campus_days: int = Field(default=6, ge=1, le=6)
    max_ects: int | None = Field(default=None, ge=1, le=60)
    minimize_gaps: bool = True

    @field_validator("earliest_time", "latest_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
            raise ValueError("Use zero-padded HH:MM time format")
        hour, minute = int(value[:2]), int(value[3:])
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Use HH:MM time format")
        return value

    @field_validator("selected_course_ids", "excluded_section_ids", "preferred_free_days")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate IDs are not allowed")
        return value

    @field_validator("preferred_free_days")
    @classmethod
    def valid_days(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 5 for day in value):
            raise ValueError("Days must be 0–5 (Monday–Saturday)")
        return value

    @model_validator(mode="after")
    def valid_range(self):
        if self.earliest_time >= self.latest_time:
            raise ValueError("Earliest time must be before latest time")
        return self


class SaveScheduleInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    section_ids: list[int] = Field(min_length=1)

    @field_validator("section_ids")
    @classmethod
    def unique_sections(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate sections are not allowed")
        return value


class CourseInput(BaseModel):
    code: str = Field(max_length=24)
    name: str = Field(max_length=160)
    offering_department: str = Field(max_length=160)
    ects: int | None = Field(default=None, ge=0)
    credit: int | None = Field(default=None, ge=0)
    mandatory: bool | None = None

    @field_validator("code", "name", "offering_department")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class SectionInput(BaseModel):
    label: str = Field(max_length=12)

    @field_validator("label")
    @classmethod
    def required_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Section number is required")
        return value


class SessionInput(BaseModel):
    day: int = Field(ge=0, le=5)
    start_time: str
    end_time: str
    session_type: Literal["lecture", "laboratory", "online", "external_training"]
    classroom: str | None = Field(default=None, max_length=64)
    instructor: str | None = Field(default=None, max_length=120)

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_session_time(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
            raise ValueError("Use zero-padded HH:MM time format")
        hour, minute = int(value[:2]), int(value[3:])
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Use HH:MM time format")
        return value

    @field_validator("classroom", "instructor")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def valid_session_range(self):
        if self.start_time >= self.end_time:
            raise ValueError("End time must be after start time")
        return self
