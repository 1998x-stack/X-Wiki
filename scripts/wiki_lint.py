#!/usr/bin/env python3
"""Deterministic public wiki lint: links, schema, provenance and privacy."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from wiki_links import iter_wikilinks, resolve_link

KNOWN_TYPES = {
    "concepts": "concept",
    "entities": "entity",
    "decisions": "decision",
    "projects": "project",
    "synthesis": "synthesis",
}
FRONTMATTER_LINE = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*):\s*(.*?)\s*$")
H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)
SOURCES = re.compile(r"^##\s+来源\s*$", re.MULTILINE)
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
PRIVATE_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "token": re.compile(
        r"(?:github_pat_[A-Za-z0-9_]{15,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
        r"sk-[A-Za-z0-9_-]{24,}|xox[baprs]-[A-Za-z0-9-]{15,})"
    ),
    "credential": re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9_+./=-]{16,}",
        re.IGNORECASE,
    ),
    "home-path": re.compile(r"(?<![\w/])/(?:Users|home)/[^\s/\"']+/"),
    "email": re.compile(r"(?<![\w.+-])[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    line: int
    message: str


def split_frontmatter(text: str) -> tuple[dict[str, str] | None, str, str | None]:
    """Minimal scalar YAML frontmatter parser; legacy pages may have none."""
    if not text.startswith("---\n"):
        return None, text, None
    lines = text.splitlines(keepends=True)
    closing = next((n for n in range(1, len(lines)) if lines[n].strip() == "---"), None)
    if closing is None:
        return None, text, "unterminated frontmatter"
    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = FRONTMATTER_LINE.fullmatch(line.strip())
        if match is None:
            return None, text, "invalid scalar frontmatter"
        key, value = match.groups()
        if key in fields:
            return None, text, f"duplicate frontmatter field: {key}"
        fields[key] = value.strip("\"'")
    return fields, "".join(lines[closing + 1 :]), None


def lint_wiki(repo: Path) -> list[Finding]:
    """Return stable, actionable findings; no model/network calls."""
    repo = repo.resolve()
    findings: list[Finding] = []

    def add(severity: str, code: str, path: Path, line: int, message: str) -> None:
        findings.append(Finding(severity, code, path.relative_to(repo).as_posix(), line, message))

    wiki = repo / "wiki"
    if not wiki.is_dir():
        add("error", "MISSING_WIKI", repo, 0, "wiki directory is missing")
        return findings
    paths = sorted(wiki.rglob("*.md"))
    if not paths:
        add("error", "EMPTY_WIKI", wiki, 0, "no knowledge pages found")
    public_pages = [repo / "index.md", *paths]
    if (repo / "log.md").is_file():
        public_pages.append(repo / "log.md")
    public_pages.extend(sorted((repo / "raw" / "references").rglob("*.md")))
    public_pages.extend(sorted((repo / "sites" / "content").rglob("*.md")))
    public_pages.extend(sorted((repo / "sites" / "overrides").rglob("*.html")))
    ids: dict[str, Path] = {}
    slugs: dict[str, Path] = {}

    for file in public_pages:
        if file.is_symlink():
            add("error", "SYMLINK", file, 0, "public content must not be a symlink")
            continue
        if not file.is_file():
            add("error", "MISSING_FILE", file, 0, "public file is missing")
            continue
        text = file.read_text(encoding="utf-8")
        metadata, _, _ = split_frontmatter(text)
        if metadata is not None and (
            metadata.get("visibility", "").lower() == "private"
            or metadata.get("privacy_scope", "").lower() == "private"
            or metadata.get("published", "").lower() == "false"
        ):
            add("error", "PRIVATE_PUBLICATION", file, 1, "private page in public tree")
        for code, pattern in PRIVATE_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                add("error", "PRIVATE_" + code.upper().replace("-", "_"), file, line,
                    f"possible sensitive content ({code}); review before publishing")
        for link in iter_wikilinks(text):
            try:
                resolved = resolve_link(link, file, repo)
                if resolved.kind == "public" and (
                    resolved.path is None or not resolved.path.is_file()
                ):
                    add("error", "BROKEN_LINK", file, link.line, link.target)
                elif (
                    resolved.kind == "private"
                    and link.target.startswith("raw/references/")
                    and (resolved.path is None or not resolved.path.is_file())
                ):
                    add("error", "BROKEN_REFERENCE", file, link.line, link.target)
            except ValueError as error:
                add("error", "UNSAFE_LINK", file, link.line, str(error))

        if file not in paths:
            continue
        relative = file.relative_to(wiki)
        expected_type = KNOWN_TYPES.get(relative.parts[0])
        if expected_type is None:
            add("error", "UNKNOWN_PAGE_TYPE", file, 0, "page must live in a known wiki category")
        if not IDENTIFIER.fullmatch(file.stem):
            add("error", "BAD_SLUG", file, 0, "use a stable lowercase ASCII kebab-case slug")
        if file.stem in slugs:
            add("error", "DUPLICATE_SLUG", file, 0,
                f"slug also exists in {slugs[file.stem].relative_to(repo)}")
        else:
            slugs[file.stem] = file
        metadata, body, error = split_frontmatter(text)
        if error:
            add("error", "BAD_FRONTMATTER", file, 1, error)
        if metadata is not None:
            if metadata.get("type") != expected_type:
                add("error", "BAD_PAGE_TYPE", file, 1, f"expected type: {expected_type}")
            if not metadata.get("title"):
                add("error", "MISSING_TITLE_METADATA", file, 1, "frontmatter requires title")
            if "id" in metadata:
                identifier = metadata["id"]
                if not IDENTIFIER.fullmatch(identifier):
                    add("error", "BAD_ID", file, 1, "page id must be lowercase ASCII")
                if identifier in ids:
                    add("error", "DUPLICATE_ID", file, 1,
                        f"id also exists in {ids[identifier].relative_to(repo)}")
                else:
                    ids[identifier] = file
        if not H1.search(body):
            add("error", "MISSING_H1", file, 1, "wiki page requires a level-one heading")
        source_sections = list(SOURCES.finditer(body))
        if len(source_sections) != 1:
            add("error", "SOURCES_SECTION", file, 1, "exactly one ## 来源 section is required")
        else:
            source_body = body[source_sections[0].end():]
            if re.search(r"^##\s+", source_body, re.MULTILINE):
                add("error", "SOURCES_NOT_LAST", file, 1, "## 来源 must be the last section")
            source_links = [
                item for item in iter_wikilinks(source_body)
                if item.target.startswith(("raw/voice/", "raw/references/"))
            ]
            if not source_links:
                add("error", "MISSING_PROVENANCE", file, 1,
                    "add at least one private raw source in ## 来源")
    return sorted(findings, key=lambda f: (f.path, f.line, f.code))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true", help="fail when any error is found")
    parser.add_argument("--json", action="store_true", help="emit machine-readable findings")
    args = parser.parse_args()
    findings = lint_wiki(args.repo)
    if args.json:
        print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
    else:
        for finding in findings:
            print(
                f"{finding.path}:{finding.line}: {finding.severity.upper()} "
                f"{finding.code}: {finding.message}"
            )
        print(f"Wiki lint: {len(findings)} finding(s).")
    return int(args.strict and any(f.severity == "error" for f in findings))


if __name__ == "__main__":
    raise SystemExit(main())
