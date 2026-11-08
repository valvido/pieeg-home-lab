"""The same facts appear in several places (README, setup guide, the Pi's page, the code).
These tests fail when one copy is changed and another is not.

docs/setup-raspberry-pi.md is the reference for the Pi setup; page/index.html repeats the
walkthrough so the page works offline, and must say the same things.
"""

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETUP = (ROOT / "docs" / "setup-raspberry-pi.md").read_text(encoding="utf-8")
PAGE = html.unescape((ROOT / "page" / "index.html").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
WELCOME = (ROOT / "deploy" / "update-motd.d" / "05-welcome").read_text(encoding="utf-8")
CHECK_SETUP = (ROOT / "code" / "check_setup.py").read_text(encoding="utf-8")

PINNED_COMMIT = "9bf350310bb492e1373edfe5b0714857f1fe04e9"
PINNED_VERSION = re.search(r'PINNED_VERSION = "([^"]+)"', CHECK_SETUP).group(1)


def test_pinned_pieeg_server_commit_and_version_agree():
    for name, text in (("setup guide", SETUP), ("page", PAGE)):
        assert PINNED_COMMIT in text, f"{name} must pin PiEEG Server to commit {PINNED_COMMIT}"
        assert PINNED_VERSION in text, f"{name} must name PiEEG Server version {PINNED_VERSION}"


def test_setup_commands_on_the_page_match_the_setup_guide():
    shared = [
        "sudo apt install -y git python3-dev build-essential",
        f"git checkout -b homelab {PINNED_COMMIT}",
        "bash setup.sh",
        "sudo sed -i 's|bin/pieeg-server|bin/pieeg-server --device pieeg8|' /etc/systemd/system/pieeg-server.service",
        "sudo systemctl daemon-reload",
        "sudo systemctl restart pieeg-server",
        "pieeg-server doctor",
    ]
    for cmd in shared:
        assert cmd in SETUP, f"setup guide lost: {cmd}"
        assert cmd in PAGE, f"page differs from the setup guide: {cmd}"
    assert "./setup.sh" not in PAGE and "./setup.sh" not in SETUP.replace("`./setup.sh` fails", ""), \
        "setup.sh is not executable in PiEEG's repository, run it with bash"
    assert "!authenticate" not in PAGE, "never advise switching the sudo password off"


def test_the_pi_has_one_name_everywhere():
    for name, text in (("README", README), ("setup guide", SETUP), ("page", PAGE), ("welcome", WELCOME)):
        assert "tina.local" in text, f"{name} must use tina.local"
        assert "raspberrypi.local" not in text.replace("hostname `raspberrypi` answers to `raspberrypi.local`", ""), \
            f"{name} still mentions the old host name"


def test_ports_agree():
    for name, text in (("README", README), ("page", PAGE), ("welcome", WELCOME)):
        assert "tina.local:1617" in text, f"{name}: dashboard port"
    assert "tina.local:8080" in README and "tina.local:8080" in WELCOME
    assert "ws://tina.local:1616" in WELCOME
    assert 'DEFAULT_PORT = 1616' in (ROOT / "code" / "eeg_stream.py").read_text(encoding="utf-8")


def test_electrode_montage_is_the_same_in_every_document():
    first_test = (ROOT / "docs" / "first-test.md").read_text(encoding="utf-8")
    for name, text in (("README", README), ("first test", first_test), ("page", PAGE)):
        low = text.lower()
        assert "left forehead" in low and "fp1" in low, f"{name}: E1 at Fp1, left forehead"
        assert "behind the left ear" in low, f"{name}: Ref behind the left ear (M1)"
        assert "behind the right ear" in low, f"{name}: Bias behind the right ear (M2)"


def test_author_and_citation_are_consistent():
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert 'family-names: "Vidović"' in cff and 'given-names: "Valentina"' in cff
    assert "Valentina Vidović" in README
    assert "Valentina Vidović" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "10.1109/ICEECCOT52851.2021.9707969" in cff and "10.1109/ICEECCOT52851.2021.9707969" in README
    for family in ("Rakhmatulin", "Zhanikeev", "Parfenov"):
        assert family in cff and family in README, f"paper author {family} missing somewhere"
