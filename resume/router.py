"""FastAPI router exposing resume CRUD endpoints."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, status

from resume import schemas, service

router = APIRouter(prefix="/resume", tags=["Resume"])


@router.post("/{uid}", response_model=schemas.Resume, status_code=status.HTTP_201_CREATED)
async def create_resume(uid: str) -> schemas.Resume:
    return service.create_resume(uid)


@router.get("/{uid}", response_model=schemas.Resume)
async def get_resume(uid: str) -> schemas.Resume:
    return service.get_resume(uid)


@router.patch("/{uid}/{section_name}")
async def update_object_section(uid: str, section_name: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return service.update_object_section(uid, section_name, payload)


@router.post("/{uid}/{section_name}", status_code=status.HTTP_201_CREATED)
async def add_array_item(uid: str, section_name: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return service.add_array_item(uid, section_name, payload)


@router.put("/{uid}/{section_name}/{item_id}")
async def update_array_item(
    uid: str,
    section_name: str,
    item_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    return service.update_array_item(uid, section_name, item_id, payload)


@router.delete("/{uid}/{section_name}/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_array_item(uid: str, section_name: str, item_id: str) -> None:
    service.delete_array_item(uid, section_name, item_id)
