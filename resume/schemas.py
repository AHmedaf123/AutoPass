"""Pydantic schemas for resume endpoints."""
from __future__ import annotations

from typing import Any, Dict, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BasicInfoContent(StrictBase):
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    email: str | None = Field(default=None)
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class BasicInfoSection(StrictBase):
    content: BasicInfoContent = Field(default_factory=BasicInfoContent)


class SummarySection(StrictBase):
    content: str | None = None


class SkillsItem(StrictBase):
    id: str | None = None
    technical: str | None = None
    tools: str | None = None
    other: str | None = None


class SkillsItemPayload(StrictBase):
    technical: str | None = None
    tools: str | None = None
    other: str | None = None


class SkillsSection(StrictBase):
    content: list[SkillsItem] = Field(default_factory=list)


class ExperienceItem(StrictBase):
    id: str | None = None
    role: str | None = None
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ExperienceItemPayload(StrictBase):
    role: str | None = None
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ExperienceSection(StrictBase):
    content: list[ExperienceItem] = Field(default_factory=list)


class EducationItem(StrictBase):
    id: str | None = None
    institution_name: str | None = None
    degree: str | None = None
    program: str | None = None
    gpa: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    core_subjects: str | None = None
    description: str | None = None
    achievements: str | None = None


class EducationItemPayload(StrictBase):
    institution_name: str | None = None
    degree: str | None = None
    program: str | None = None
    gpa: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    core_subjects: str | None = None
    description: str | None = None
    achievements: str | None = None


class EducationSection(StrictBase):
    content: list[EducationItem] = Field(default_factory=list)


class ProjectItem(StrictBase):
    id: str | None = None
    project_name: str | None = None
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ProjectItemPayload(StrictBase):
    project_name: str | None = None
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ProjectsSection(StrictBase):
    content: list[ProjectItem] = Field(default_factory=list)


class LanguageItem(StrictBase):
    id: str | None = None
    language: str | None = None
    proficiency: str | None = None


class LanguageItemPayload(StrictBase):
    language: str | None = None
    proficiency: str | None = None


class LanguagesSection(StrictBase):
    content: list[LanguageItem] = Field(default_factory=list)


class Resume(StrictBase):
    basic_info: BasicInfoSection
    summary: SummarySection
    skills: SkillsSection
    experience: ExperienceSection
    education: EducationSection
    projects: ProjectsSection
    languages: LanguagesSection


class BasicInfoUpdate(StrictBase):
    content: BasicInfoContent


class SummaryUpdate(StrictBase):
    content: str | None = None


OBJECT_SECTION_MODELS: Dict[str, Type[StrictBase]] = {
    "basic_info": BasicInfoUpdate,
    "summary": SummaryUpdate,
}

ARRAY_SECTION_PAYLOAD_MODELS: Dict[str, Type[StrictBase]] = {
    "experience": ExperienceItemPayload,
    "education": EducationItemPayload,
    "projects": ProjectItemPayload,
    "skills": SkillsItemPayload,
    "languages": LanguageItemPayload,
}

ARRAY_ITEM_RESPONSE_MODELS: Dict[str, Type[StrictBase]] = {
    "experience": ExperienceItem,
    "education": EducationItem,
    "projects": ProjectItem,
    "skills": SkillsItem,
    "languages": LanguageItem,
}


def parse_object_payload(section_name: str, payload: Dict[str, Any]) -> StrictBase:
    model_cls = OBJECT_SECTION_MODELS.get(section_name)
    if not model_cls:
        raise ValueError("Invalid object section name")
    return model_cls.model_validate(payload)


def parse_array_payload(section_name: str, payload: Dict[str, Any]) -> StrictBase:
    model_cls = ARRAY_SECTION_PAYLOAD_MODELS.get(section_name)
    if not model_cls:
        raise ValueError("Invalid array section name")
    return model_cls.model_validate(payload)