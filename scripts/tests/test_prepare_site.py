from __future__ import annotations

from pathlib import Path

import pytest
from prepare_site import convert_links, prepare, reset_output


def test_convert_links_handles_public_private_and_missing(tmp_path: Path) -> None:
    current = tmp_path / "wiki" / "current.md"
    target = tmp_path / "wiki" / "target.md"
    current.parent.mkdir()
    target.write_text("# Target", encoding="utf-8")
    source = (
        "[[wiki/target|目标]] [[target|相对目标]] "
        "[[raw/voice/private|私有证据]] [[wiki/missing|缺页]]"
    )

    converted = convert_links(source, current, tmp_path)

    assert converted.count("[目标](target.md)") == 1
    assert "[相对目标](target.md)" in converted
    assert 'class="local-evidence"' in converted
    assert 'class="unresolved-link"' in converted
    assert "raw/voice/private" not in converted


def test_prepare_copies_site_assets_and_never_raw(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    output = tmp_path / "output"
    (repo / "wiki").mkdir(parents=True)
    (repo / "sites" / "assets" / "images").mkdir(parents=True)
    (repo / "raw").mkdir()
    (repo / "index.md").write_text("# Home", encoding="utf-8")
    (repo / "wiki" / "topic.md").write_text("# Topic", encoding="utf-8")
    (repo / "sites" / "assets" / "images" / "image.txt").write_text("asset", encoding="utf-8")
    (repo / "raw" / "private.md").write_text("secret", encoding="utf-8")

    prepare(repo, output)

    assert (output / "sites" / "assets" / "images" / "image.txt").is_file()
    assert not (output / "raw").exists()


def test_output_guard_rejects_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="protected"):
        reset_output(tmp_path, tmp_path)
