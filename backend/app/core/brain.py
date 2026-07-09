"""
Brain Layer — repositório de conhecimento estruturado.
Agentes leem e escrevem aqui para persistir conhecimento entre sessões.
Arquivos JSON/JSONL versionados, nunca apagados.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging import logger

# Brain root: PROJECT_ROOT/brain/  (configurável via env)
_BRAIN_ROOT = Path(os.getenv("BRAIN_PATH", Path(__file__).resolve().parent.parent.parent.parent / "brain"))


def _path(*parts: str) -> Path:
    p = _BRAIN_ROOT.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read(key: str, tenant_id: str | None = None, default: Any = None) -> Any:
    """Read a JSON file from the Brain.
    key examples: 'rules/global', 'offers/diabetes_kit/brief',
                  'clients/{tenant_id}/history'
    """
    if tenant_id:
        key = key.replace("{tenant_id}", tenant_id)
    p = _path(f"{key}.json")
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("brain.read_error", key=key, error=str(exc))
        return default


def read_lines(key: str, tenant_id: str | None = None, limit: int = 100) -> list[dict]:
    """Read a JSONL file (append log) from the Brain."""
    if tenant_id:
        key = key.replace("{tenant_id}", tenant_id)
    p = _path(f"{key}.jsonl")
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines[-limit:] if l.strip()]
    except Exception as exc:
        logger.warning("brain.read_lines_error", key=key, error=str(exc))
        return []


def read_text(key: str, tenant_id: str | None = None) -> str:
    """Read a markdown or text file from the Brain."""
    if tenant_id:
        key = key.replace("{tenant_id}", tenant_id)
    for ext in (".md", ".txt", ""):
        p = _path(f"{key}{ext}")
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write(key: str, data: Any, tenant_id: str | None = None) -> None:
    """Write (overwrite) a JSON file to the Brain."""
    if tenant_id:
        key = key.replace("{tenant_id}", tenant_id)
    p = _path(f"{key}.json")
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.debug("brain.write", key=key)


def append(key: str, data: dict, tenant_id: str | None = None) -> None:
    """Append a record to a JSONL file in the Brain. Never overwrites."""
    if tenant_id:
        key = key.replace("{tenant_id}", tenant_id)
    p = _path(f"{key}.jsonl")
    record = {**data, "_ts": datetime.utcnow().isoformat()}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_text(key: str, content: str, tenant_id: str | None = None) -> None:
    """Write a markdown file to the Brain."""
    if tenant_id:
        key = key.replace("{tenant_id}", tenant_id)
    ext = ".md" if not key.endswith((".md", ".txt")) else ""
    p = _path(f"{key}{ext}")
    p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Structured helpers agents actually use
# ---------------------------------------------------------------------------

def get_rules(tenant_id: str) -> dict:
    """Return merged rules: global defaults overridden by tenant rules."""
    global_rules = read("rules/global") or {}
    tenant_rules = read(f"rules/{tenant_id}") or {}
    return {**global_rules, **tenant_rules}


def get_offer(offer_id: str) -> dict:
    return read(f"offers/{offer_id}/brief") or {}


def get_playbook(objective: str) -> dict:
    """e.g. objective='lead_gen' → brain/playbooks/lead_gen.json"""
    return read(f"playbooks/{objective}") or {}


def get_lessons(lesson_type: str = "what_works", limit: int = 20) -> list[dict]:
    return read_lines(f"lessons/{lesson_type}", limit=limit)


def get_agent_prompt(agent_name: str, version: int | None = None) -> str:
    """Load a versioned system prompt for an agent."""
    if version:
        text = read_text(f"prompts/{agent_name}/v{version}")
        if text:
            return text
    # Latest version: highest numbered file
    prompt_dir = _path(f"prompts/{agent_name}")
    if prompt_dir.exists():
        versions = sorted(prompt_dir.glob("v*.md"), reverse=True)
        if versions:
            return versions[0].read_text(encoding="utf-8")
    return ""


def save_lesson(lesson: dict) -> None:
    """Append a learning to the appropriate lessons file."""
    lesson_type = lesson.get("type", "what_works")
    file_key = f"lessons/{lesson_type}"
    append(file_key, lesson)


def save_decision(tenant_id: str, decision: dict) -> None:
    append("decisions/decision_log", {**decision, "tenant_id": tenant_id})


def get_client_history(tenant_id: str, limit: int = 50) -> list[dict]:
    return read_lines(f"clients/{tenant_id}/history", limit=limit)


def save_client_event(tenant_id: str, event: dict) -> None:
    append(f"clients/{tenant_id}/history", event)
