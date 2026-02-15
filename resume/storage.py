"""Local file storage helpers for resumes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from resume import utils

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "resumes"
TEMPLATE_PATH = BASE_DIR / "resume.json"


def ensure_storage_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_resume_path(uid: str) -> Path:
    safe_uid = utils.sanitize_uid(uid)
    return DATA_DIR / f"{safe_uid}.json"


def resume_exists(uid: str) -> bool:
    try:
        return get_resume_path(uid).exists()
    except ValueError:
        return False


def load_template() -> Dict[str, Any]:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as template_file:
        return json.load(template_file)


def read_resume(uid: str) -> Dict[str, Any]:
    path = get_resume_path(uid)
    if not path.exists():
        raise FileNotFoundError
    with path.open("r", encoding="utf-8") as resume_file:
        return json.load(resume_file)


def save_resume(uid: str, data: Dict[str, Any]) -> None:
    ensure_storage_dir()
    path = get_resume_path(uid)
    tmp_path = path.with_suffix(".json.tmp")

    with tmp_path.open("w", encoding="utf-8") as resume_file:
        json.dump(data, resume_file, ensure_ascii=False, indent=2)

    tmp_path.replace(path)
