"""Safe and deterministic wikilink parsing shared by lint and site generation."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

WIKILINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
FENCE = re.compile(r"^\s*(" + r"`{3,}|~{3,}" + r")")
INLINE_CODE = re.compile(r"(`[^`\n]*`)")
SAFE_ANCHOR = re.compile(r"^[\w\-]+$", re.UNICODE)


@dataclass(frozen=True)
class WikiLink:
    target: str
    label: str
    line: int


@dataclass(frozen=True)
class ResolvedLink:
    kind: str
    path: Path | None
    fragment: str


def _content_segments(text: str):
    """Yield (line number, segment, eligible) without touching fenced/inline code."""
    fence_char = ""
    fence_length = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        fence = FENCE.match(line)
        if fence is not None:
            marker = fence.group(1)
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length:
                fence_char = ""
            yield line_number, line, False
            continue
        if fence_char:
            yield line_number, line, False
            continue
        for index, part in enumerate(INLINE_CODE.split(line)):
            yield line_number, part, index % 2 == 0


def iter_wikilinks(text: str):
    for line, segment, eligible in _content_segments(text):
        if not eligible:
            continue
        for match in WIKILINK.finditer(segment):
            inner = match.group(1)
            target, _, alias = inner.partition("|")
            target = target.strip()
            label = (alias.strip() if "|" in inner else target.split("#", 1)[0].split("/")[-1])
            yield WikiLink(target, label, line)


def resolve_link(link: WikiLink, current: Path, root: Path) -> ResolvedLink:
    """Resolve a link without permitting absolute paths or directory traversal."""
    target = link.target
    base, marker, fragment = target.partition("#")
    if (
        not base
        or base.startswith(("/", "~"))
        or "\\" in base
        or ":" in base
        or "%" in base
        or any(part in ("", ".", "..") for part in base.split("/"))
        or base.endswith(".md")
        or (marker and (not fragment or not SAFE_ANCHOR.fullmatch(fragment)))
    ):
        raise ValueError(f"unsafe wikilink target: {target}")
    if base.startswith("raw/"):
        if not (base.startswith("raw/voice/") or base.startswith("raw/references/")):
            raise ValueError(f"unsupported raw namespace: {target}")
        if marker:
            raise ValueError(f"private evidence links cannot expose fragments: {target}")
        return ResolvedLink("private", root / (base + ".md"), "")
    if base.startswith("wiki/"):
        path = root / (base + ".md")
    else:
        path = current.parent / (base + ".md")
    # No absolute/traversing input was accepted above; this also guards
    # against manually introduced symlinks that could point outside root.
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"wikilink escapes documentation root: {target}")
    return ResolvedLink("public", path, fragment)


def convert_links(
    text: str, current: Path, site_root: Path, *, strict: bool = False
) -> str:
    """Render wikilinks; strict mode fails closed on unresolved references."""
    output: list[str] = []
    for line, part, eligible in _content_segments(text):
        if not eligible:
            output.append(part)
            continue

        def replace(match: re.Match[str]) -> str:
            inner = match.group(1)
            target, separator, label = inner.partition("|")
            link = WikiLink(
                target.strip(),
                label.strip() if separator else target.split("#", 1)[0].split("/")[-1]
                .replace("-", " ").title(),
                line,
            )
            try:
                resolved = resolve_link(link, current, site_root)
            except ValueError as error:
                if strict:
                    raise ValueError(f"{current}:{line}: {error}") from error
                return (
                    '<span class="unresolved-link" title="页面尚未建立">'
                    + html.escape(link.label, quote=True)
                    + "</span>"
                )
            if resolved.kind == "private":
                return (
                    '<span class="local-evidence" title="原始证据仅保留在本机">'
                    + html.escape(link.label, quote=True)
                    + "</span>"
                )
            if resolved.path is None or not resolved.path.is_file():
                if strict:
                    raise ValueError(f"{current}:{line}: unresolved wikilink: {link.target}")
                return (
                    '<span class="unresolved-link" title="页面尚未建立">'
                    + html.escape(link.label, quote=True)
                    + "</span>"
                )
            relative = Path(os.path.relpath(resolved.path, current.parent)).as_posix()
            destination = quote(relative, safe="/-._~")
            if resolved.fragment:
                destination += "#" + quote(resolved.fragment, safe="-_")
            safe_label = html.escape(link.label, quote=False)
            for char in ("\\", "[", "]"):
                safe_label = safe_label.replace(char, "\\" + char)
            return f"[{safe_label}]({destination})"

        output.append(WIKILINK.sub(replace, part))
    return "".join(output)
