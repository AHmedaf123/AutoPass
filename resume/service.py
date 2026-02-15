"""Business logic for resume CRUD operations."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Tuple

from fastapi import HTTPException, status
from pydantic import ValidationError

from resume import schemas, storage, utils


def create_resume(uid: str) -> Dict[str, Any]:
    try:
        safe_uid = utils.sanitize_uid(uid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if storage.resume_exists(safe_uid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume already exists for this uid",
        )

    template = storage.load_template()
    normalized, _ = _normalize_resume_data(template)
    storage.save_resume(safe_uid, normalized)
    return normalized


def get_resume(uid: str) -> Dict[str, Any]:
    return _load_resume(uid)


def update_object_section(uid: str, section_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if section_name not in utils.OBJECT_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid object section")

    resume = _load_resume(uid)

    try:
        parsed = schemas.parse_object_payload(section_name, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())

    if section_name == "summary":
        resume[section_name]["content"] = parsed.content
    elif section_name == "basic_info":
        current = resume.get("basic_info", {}).get("content") or {}
        updates = parsed.content.model_dump(exclude_unset=True)
        merged = {**current, **updates}
        _assert_basic_info_email(merged)
        resume[section_name] = {"content": merged}

    storage.save_resume(uid, resume)
    return resume[section_name]


def add_array_item(uid: str, section_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if section_name not in utils.ARRAY_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid array section")

    resume = _load_resume(uid)

    try:
        parsed = schemas.parse_array_payload(section_name, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())

    item = parsed.model_dump(exclude_unset=True)
    item["id"] = utils.generate_item_id()

    resume[section_name]["content"].append(item)
    storage.save_resume(uid, resume)
    return item


def update_array_item(uid: str, section_name: str, item_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if section_name not in utils.ARRAY_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid array section")

    resume = _load_resume(uid)

    try:
        parsed = schemas.parse_array_payload(section_name, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())

    items = resume.get(section_name, {}).get("content", [])
    for item in items:
        if str(item.get("id")) == str(item_id):
            item.update(parsed.model_dump(exclude_unset=True))
            storage.save_resume(uid, resume)
            return item

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")


def delete_array_item(uid: str, section_name: str, item_id: str) -> None:
    if section_name not in utils.ARRAY_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid array section")

    resume = _load_resume(uid)
    items = resume.get(section_name, {}).get("content", [])
    remaining = [item for item in items if str(item.get("id")) != str(item_id)]

    if len(remaining) == len(items):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    resume[section_name]["content"] = remaining
    storage.save_resume(uid, resume)


def _load_resume(uid: str) -> Dict[str, Any]:
    try:
        raw_resume = storage.read_resume(uid)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    normalized, changed = _normalize_resume_data(raw_resume)
    if changed:
        storage.save_resume(uid, normalized)
    return normalized


def _normalize_resume_data(raw_data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    normalized = deepcopy(raw_data)
    changed = False

    for section in utils.OBJECT_SECTIONS:
        section_value = normalized.get(section)
        if isinstance(section_value, dict) and "content" in section_value:
            normalized[section] = {"content": section_value.get("content")}
        else:
            normalized[section] = {"content": section_value if section_value is not None else None}
            changed = True

    for section in utils.ARRAY_SECTIONS:
        section_value = normalized.get(section)
        raw_content = []

        if isinstance(section_value, dict) and "content" in section_value:
            raw_content = section_value.get("content")
        elif isinstance(section_value, list):
            raw_content = section_value
            changed = True
        elif section_value is None:
            raw_content = []
            changed = True
        else:
            raw_content = []
            changed = True

        if isinstance(raw_content, dict):
            raw_content = [raw_content]
            changed = True
        if raw_content is None:
            raw_content = []

        normalized_items = []
        for entry in raw_content:
            if not isinstance(entry, dict):
                changed = True
                continue
            item_copy = dict(entry)
            if not item_copy.get("id"):
                item_copy["id"] = utils.generate_item_id()
                changed = True
            normalized_items.append(item_copy)

        normalized[section] = {"content": normalized_items}

    try:
        validated = schemas.Resume.model_validate(normalized)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())

    validated_data = validated.model_dump()
    _assert_basic_info_email(validated_data.get("basic_info", {}).get("content"))
    return validated_data, changed


def _assert_basic_info_email(basic_info_content: Dict[str, Any] | None) -> None:
    email = None
    if isinstance(basic_info_content, dict):
        email = basic_info_content.get("email")

    if email is None or str(email).strip() == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="basic_info.email is required",
        )
