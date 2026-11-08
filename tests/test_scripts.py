"""The other scripts, run the way the README runs them."""

import os

import pytest

from conftest import free_port, only_recording, script, talk
from self_test import judge


@pytest.fixture
def recording(sim, tmp_path):
    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 4, "--label", "rest",
               "--out", tmp_path / "rec", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    return only_recording(tmp_path / "rec")[0]


def test_self_test(sim, tmp_path):
    r = script("self_test.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 1, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ch8:" in r.stdout and "Board OK: every channel under 5 µV RMS (250 samples)" in r.stdout


def test_self_test_without_board_is_not_a_pass(sim, tmp_path):
    # The real PiEEG Server answers "Device OK" with 0 samples when no board is mounted
    talk(sim, {"cmd": "sim_board", "present": False})
    r = script("self_test.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 1, cwd=tmp_path)
    assert r.returncode == 1
    assert "No usable test: 0 of 250 samples" in r.stdout
    assert "Internal noise within spec" not in r.stdout     # the server's false verdict is not shown


def test_judge_noise_results():
    ok = {"rms": [1.0] * 8, "duration": 3, "samples_collected": 750}
    assert judge(ok)[1] is None and judge(ok)[0].startswith("Board OK")
    assert judge({**ok, "samples_collected": 0})[1] == "no samples"
    assert judge({**ok, "rms": [1.0] * 7 + [20.0]})[1] == "high noise"
    assert judge({**ok, "rms": [1.0] * 7 + [8.0]})[0].startswith("Marginal")


def test_check_setup_against_the_simulator(sim, tmp_path):
    md = tmp_path / "check.md"
    r = script("check_setup.py", "--host", "127.0.0.1", "--port", sim, "--dashboard-port", free_port(),
               "--noise-test", "--markdown", md, cwd=tmp_path)
    out = r.stdout
    assert "[ok] Channels: 8" in out
    assert "[ok] Samples:" in out and "0 gaps" in out
    assert "[ok] Noise test: Board OK" in out
    assert "[FAIL] Dashboard" in out            # the simulator has no dashboard
    assert "[FAIL] Hardware mode: MOCK" in out  # and it is, of course, a mock
    assert r.returncode == 1
    assert "| ✅ | Channels | 8, PiEEG-8 mode |" in md.read_text(encoding="utf-8")


def test_check_setup_without_board(sim, tmp_path):
    talk(sim, {"cmd": "sim_board", "present": False})
    r = script("check_setup.py", "--host", "127.0.0.1", "--port", sim, "--dashboard-port", free_port(),
               "--noise-test", cwd=tmp_path)
    assert "[FAIL] Samples: none in 3 s" in r.stdout
    assert "[warn] Noise test: skipped" in r.stdout
    assert r.returncode == 1


def test_spectrum(recording, tmp_path):
    r = script("spectrum.py", recording, "--save", tmp_path / "spectrum.png", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "alpha peak" in r.stdout
    assert (tmp_path / "spectrum.png").stat().st_size > 10_000


def test_mission_1_runs_on_a_raw_recording(recording, tmp_path):
    r = script("mission_1_notch.py", recording, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FAIL hum peak" in r.stdout             # remove_mains() is still the empty starter
    assert "Note:" not in r.stdout                 # raw data, nothing to warn about


def test_mission_3_converts_the_recording(recording, tmp_path):
    r = script("mission_3_nwb.py", recording, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    nwb = tmp_path / "nwb" / (recording.stem + ".nwb")
    assert nwb.exists() and nwb.stat().st_size > 0
    assert "nwbinspector" in r.stdout


def test_live_view_rejects_channel_0(tmp_path):
    r = script("live_view.py", "--channels", "0", cwd=tmp_path)
    assert r.returncode == 2
    assert "between 1 and 8" in r.stderr


@pytest.mark.skipif(os.environ.get("PIEEG_NETWORK_TESTS") != "1",
                    reason="downloads from GitHub, set PIEEG_NETWORK_TESTS=1")
def test_get_example_data(tmp_path):
    r = script("get_example_data.py", "alpha", "--out", tmp_path / "rec", cwd=tmp_path, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    path, meta = only_recording(tmp_path / "rec")
    assert path.name == "example_alpha.csv"
    assert path.read_text().splitlines()[0] == "t,n,ch1,ch2,ch3,ch4,ch5,ch6,ch7,ch8"
    assert meta["n_samples"] > 5000
