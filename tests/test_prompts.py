from datetime import datetime, timezone
from pathlib import Path

from research_agents.prompts import archive, resolve


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_resolve_prefers_dated_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPT_TZ", "UTC")
    today = datetime.now(timezone.utc).date().isoformat()
    _write(tmp_path / f"{today}.md", "dated brief")
    _write(tmp_path / "queue" / "a.md", "queued brief")
    _write(tmp_path / "default.md", "default brief")

    r = resolve(tmp_path)
    assert r.text == "dated brief"
    assert r.from_queue is False


def test_resolve_queue_oldest_first_then_default(tmp_path):
    _write(tmp_path / "queue" / "01.md", "first")
    _write(tmp_path / "queue" / "02.md", "second")
    _write(tmp_path / "default.md", "default brief")

    r = resolve(tmp_path)
    assert r.text == "first"
    assert r.from_queue is True


def test_resolve_falls_back_to_default(tmp_path):
    _write(tmp_path / "default.md", "default brief")

    r = resolve(tmp_path)
    assert r.text == "default brief"
    assert r.from_queue is False


def test_frontmatter_sets_category_and_strips_body(tmp_path):
    _write(tmp_path / "default.md", "---\ncategory: Security\n---\nbody text")

    r = resolve(tmp_path)
    assert r.category == "Security"
    assert r.text == "body text"


def test_empty_prompt_falls_through(tmp_path):
    _write(tmp_path / "queue" / "empty.md", "   \n")
    _write(tmp_path / "default.md", "default brief")

    r = resolve(tmp_path)
    assert r.text == "default brief"


def test_archive_moves_queue_prompt_to_used(tmp_path):
    _write(tmp_path / "queue" / "a.md", "queued")
    _write(tmp_path / "default.md", "d")

    r = resolve(tmp_path)
    dest = archive(r)

    assert dest is not None and dest.exists()
    assert dest.parent.name == "used"
    assert not (tmp_path / "queue" / "a.md").exists()


def test_archive_is_noop_for_non_queue_prompt(tmp_path):
    _write(tmp_path / "default.md", "d")

    r = resolve(tmp_path)
    assert archive(r) is None
