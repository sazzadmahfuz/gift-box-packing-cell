"""The files describe the work itself: no plan document names, part numbers or stage letters."""

import re
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[2]
CHECKED = [SOFTWARE / name for name in ("cell_live", "cell_sim", "cell_ui")]
SUFFIXES = {".py", ".md", ".json", ".js", ".css", ".html"}
PLAN_WORDS = re.compile(r"\bparts? ?[1-5]\b|guide" + r"line|\bstages? [a-d]\b", re.IGNORECASE)


def _files():
    yield SOFTWARE.parent / "CLAUDE.md"
    for folder in CHECKED:
        yield from (path for path in folder.rglob("*") if path.suffix in SUFFIXES and "__pycache__" not in path.parts)


def test_no_file_names_a_plan_part_guide_or_stage():
    found = []
    for path in _files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PLAN_WORDS.search(line):
                found.append(f"{path.relative_to(SOFTWARE.parent)}:{number}: {line.strip()[:80]}")
    assert found == []
