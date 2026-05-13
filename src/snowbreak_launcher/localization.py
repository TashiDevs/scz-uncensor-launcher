from __future__ import annotations

import re
from pathlib import Path


LOCALIZATION_LINE = "localization = 1"


def ensure_localization_enabled(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    original = ""
    if path.exists():
        original = path.read_text(encoding="utf-8", errors="ignore")

    updated = _updated_localization_text(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return f"Updated {path.name}."
    return f"{path.name} is already enabled."


def is_localization_enabled(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"(?im)^\s*localization\s*=\s*1\s*$", text):
        return True
    return text.strip() == "1"


def _updated_localization_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return LOCALIZATION_LINE + "\n"
    if stripped in {"0", "1"}:
        return LOCALIZATION_LINE + "\n"

    pattern = re.compile(r"(?im)^(\s*localization\s*=\s*)\d+\s*$")
    if pattern.search(text):
        updated = pattern.sub(r"\g<1>1", text)
    else:
        updated = text.rstrip() + "\n" + LOCALIZATION_LINE

    if not updated.endswith("\n"):
        updated += "\n"
    return updated
