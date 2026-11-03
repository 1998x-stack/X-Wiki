#!/usr/bin/env python3
"""Independent deterministic golden-set evaluation for Wiki lint rules.

The fixtures are manually specified synthetic cases, not model-generated
answers and not an evaluation of natural-language claim correctness.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from wiki_lint import lint_wiki


@dataclass(frozen=True)
class CaseResult:
    identifier: str
    expected: tuple[str, ...]
    observed: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


def evaluate(golden_path: Path) -> list[CaseResult]:
    dataset = json.loads(golden_path.read_text(encoding="utf-8"))
    if dataset.get("version") != 1:
        raise ValueError("Unsupported golden evaluation schema")
    results: list[CaseResult] = []
    seen: set[str] = set()
    for case in dataset["cases"]:
        identifier = case["id"]
        if identifier in seen:
            raise ValueError(f"Duplicate golden case: {identifier}")
        seen.add(identifier)
        with tempfile.TemporaryDirectory(prefix="xwiki-golden-") as temp:
            repo = Path(temp)
            for name, content in case["files"].items():
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Unsafe fixture path: {name}")
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            actual = tuple(sorted({item.code for item in lint_wiki(repo)}))
            expected = tuple(sorted(set(case["expected_codes"])))
            results.append(CaseResult(identifier, expected, actual))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evaluation/golden/wiki_cases.json",
    )
    args = parser.parse_args()
    results = evaluate(args.golden)
    failures = [
        {"case": item.identifier, "expected": item.expected, "observed": item.observed}
        for item in results
        if not item.passed
    ]
    report = {
        "dataset": str(args.golden),
        "total": len(results),
        "passed": sum(item.passed for item in results),
        "failed": len(failures),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
