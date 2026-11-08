"""The page and the SSH welcome in deploy/: every file they point to exists, and the shell script parses."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "page"


def test_page_references_exist():
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    refs = {r.split("?")[0] for r in re.findall(r'(?:src|href)="(assets/[^"]+)"', html)}
    assert refs, "no assets referenced"
    missing = [r for r in refs if not (PAGE / r).is_file()]
    assert not missing, missing


def test_sample_matches_the_page():
    sample = json.loads((PAGE / "assets" / "sample.json").read_text())
    assert sample["sample_rate"] == 250
    assert len(sample["data"]) == 8
    assert {len(ch) for ch in sample["data"]} == {250 * sample["duration_s"]}
    assert "SIMULATED" in sample["note"]


def test_welcome_script_parses():
    subprocess.run(["sh", "-n", str(ROOT / "deploy" / "update-motd.d" / "05-welcome")], check=True)


def test_assets_are_versioned():
    """Browsers keep old copies of style.css and app.js; the ?v= in index.html is the first 8 hex
    digits of each file's SHA-256, so every change gets a new URL. Update it when a file changes.
    Hashes are taken over LF bytes: git may hand the checkout CRLF endings on Windows, and a
    browser gets the same bytes either way."""
    import hashlib
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    for f in ("assets/style.css", "assets/app.js"):
        crlf, lf = bytes((13, 10)), bytes((10,))
        blob = (PAGE / f).read_bytes().replace(crlf, lf)
        h = hashlib.sha256(blob).hexdigest()[:8]
        assert f"{f}?v={h}" in html, f"{f} changed: set ?v={h} in page/index.html"
