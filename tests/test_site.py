from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from helpers import ROOT, make_message


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "docs" / "build_site.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_site_shows_every_message_with_its_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _builder()
    monkeypatch.setattr(sys, "argv", ["build_site.py", "--out", str(tmp_path)])
    site.main()
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "{{" not in index and (tmp_path / "review.html").exists()
    messages = site.inbox()
    assert index.count('class="msg"') == len(messages)
    assert index.count('class="outcome"') == len(messages)
    for target in re.findall(r'<a href="#([^"]+)"', index):  # every source link has a message
        assert f'id="{target}"' in index
    assert "merged into one item" in index and "closing an earlier item" in index
    assert "glm-5.3-flash" in index  # comparison table built from the committed reports


def test_demo_site_escapes_message_text() -> None:
    site = _builder()
    hostile = make_message('<img src=x onerror="alert(1)"> please send the deck by Friday')
    messages = [hostile]
    page = site.page(messages, site.digest_of(messages), "<table></table>", "abc1234")
    assert "<img src=x" not in page and "&lt;img src=x" in page
