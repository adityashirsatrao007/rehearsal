"""Prompt assembly and output parsing for the coach calls.

Gemma 2B does not follow complex schemas reliably, so parsing here is defensive:
strict line-prefix parsing first, then a tolerant fallback, and finally a
graceful degradation to raw model text rather than an exception.
"""

from __future__ import annotations

import re

from . import prompts
from .scenarios import Scenario

_LABELLED = re.compile(
    r"^\s*(?:\*\*)?(CORRECTED|WHY|BETTER|SCORE_FLUENCY|SCORE_ACCURACY|SCORE_VOCABULARY|SUMMARY|NEXT)"
    r"(?:\*\*)?\s*[:\-–]\s*(?:\*\*)?\s*(.+?)\s*$",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    """Drop stray markdown emphasis a small model likes to sprinkle in."""
    return value.strip().strip("*").strip()


def partner_system(scenario: Scenario) -> str:
    return prompts.PARTNER_SYSTEM.format(role_line=scenario.role_line)


def correction_system(learner_message: str) -> str:
    return prompts.CORRECTION_SYSTEM.format(learner_message=learner_message.strip())


def summary_system(scenario_title: str, turns: list[str]) -> str:
    transcript = "\n".join(f"- {t.strip()}" for t in turns if t.strip())
    return prompts.SUMMARY_SYSTEM.format(
        scenario=scenario_title,
        count=len(turns),
        transcript=transcript or "(empty)",
    )


def parse_correction(raw: str) -> dict:
    """Turn the model's three labelled lines into a correction card."""
    found: dict[str, str] = {}
    for line in (raw or "").splitlines():
        match = _LABELLED.match(line)
        if match:
            found[match.group(1).upper()] = _clean(match.group(2))
    why = found.get("WHY", "")
    better = found.get("BETTER", "")
    corrected = found.get("CORRECTED", "")

    # Fallback: labels stripped or reformatted — surface whatever text we have
    # rather than throwing the feedback away.
    if not corrected and not why and not better:
        text = re.sub(r"^#+\s*", "", (raw or "").strip(), flags=re.MULTILINE)
        return {
            "corrected": "",
            "why": "",
            "better": "",
            "raw": text.strip(),
            "parsed": False,
        }

    return {
        "corrected": corrected,
        "why": why or "Clear and natural.",
        "better": better,
        "raw": (raw or "").strip(),
        "parsed": bool(found),
    }


def parse_summary(raw: str) -> dict:
    """Extract the scorecard. Any field the model omits falls back to a neutral 5."""
    found: dict[str, str] = {}
    for line in (raw or "").splitlines():
        match = _LABELLED.match(line)
        if match:
            found[match.group(1).upper()] = _clean(match.group(2))

    def score(key: str) -> int:
        try:
            value = int(re.search(r"-?\d+", found.get(key, "") or "").group())
        except (AttributeError, ValueError):
            return 5
        return max(1, min(10, value))

    return {
        "fluency": score("SCORE_FLUENCY"),
        "accuracy": score("SCORE_ACCURACY"),
        "vocabulary": score("SCORE_VOCABULARY"),
        "summary": found.get("SUMMARY", "").strip() or "Session complete.",
        "next_step": found.get("NEXT", "").strip()
        or "Keep practising — try the same scenario again.",
    }
