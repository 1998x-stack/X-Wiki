"""Tests that the independently curated synthetic golden suite is enforced."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evaluate_wiki import evaluate


def golden() -> Path:
    return Path(__file__).resolve().parents[2] / "evaluation" / "golden" / "wiki_cases.json"


def test_synthetic_golden_cases_match_expected_findings() -> None:
    results = evaluate(golden())
    assert len(results) >= 8
    assert all(result.passed for result in results)


def test_deliberately_wrong_expected_result_is_detected(tmp_path: Path) -> None:
    document = json.loads(golden().read_text(encoding="utf-8"))
    document["cases"][0]["expected_codes"] = ["BROKEN_LINK"]
    target = tmp_path / "wrong.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    results = evaluate(target)
    assert not results[0].passed


def test_rejects_fixture_escape(tmp_path: Path) -> None:
    data = {"version": 1, "cases": [
        {"id": "escape", "files": {"../private.txt": "not allowed"}, "expected_codes": []}
    ]}
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe fixture"):
        evaluate(path)
