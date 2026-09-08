import pytest

import main


@pytest.mark.parametrize(
    "argv",
    [
        ["--topic", "x", "--brief-file", "b.md"],
        ["--topic", "x", "--manual"],
        ["--brief-file", "b.md", "--manual"],
    ],
)
def test_brief_sources_are_mutually_exclusive(argv, monkeypatch):
    """--topic / --brief-file / --manual cannot be combined (argparse exits 2)."""
    monkeypatch.setattr("sys.argv", ["main.py", *argv])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 2
