"""record.py against simulate.py: raw data, filters restored, and no data lost on reconnects.

simulate.py behaves like PiEEG Server: its bandpass is on by default and changes the data
for every client, and it keeps one sample counter for all connections.
"""

import csv
import time

import numpy as np
from scipy import signal

from conftest import free_port, only_recording, script, talk


def read_csv(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    header, data = rows[0], np.array(rows[1:], dtype=float)
    return header, data


def hum_power(x, fs=250):
    f, p = signal.welch(x - x.mean(), fs=fs, nperseg=fs)
    band = (f >= 49) & (f <= 51)
    return np.trapezoid(p[band], f[band])


def test_raw_recording_switches_server_filters_off_and_back_on(sim, tmp_path):
    raw_dir, filtered_dir = tmp_path / "raw", tmp_path / "filtered"
    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 3, "--label", "raw",
               "--out", raw_dir, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    path, meta = only_recording(raw_dir)
    header, data = read_csv(path)
    assert header == ["t", "n", *[f"ch{i}" for i in range(1, 9)]]
    assert len(data) == meta["n_samples"] == 750
    assert np.all(np.diff(data[:, 1]) == 1), "sample numbers must be consecutive"
    assert meta["complete"] is True
    assert meta["server_filters_at_start"] == {"bandpass": True, "notch": False, "notch_freq": 60.0}
    assert meta["data_filtering"].startswith("none")
    assert meta["electrodes"]["ch1"].startswith("Fp1")
    events = [e["event"] for e in meta["events"]]
    assert events == ["connected", "server filters switched off", "server filters switched back on"]

    welcome = talk(sim)
    assert welcome["filter"] is True and welcome["notch_filter"] is False, "filters must be back on"

    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 3, "--label", "filtered",
               "--keep-server-filters", "--out", filtered_dir, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    path_f, meta_f = only_recording(filtered_dir)
    assert meta_f["data_filtering"].startswith("PiEEG Server filters")
    assert [e["event"] for e in meta_f["events"]] == ["connected"]
    _, data_f = read_csv(path_f)
    # the 1 to 40 Hz bandpass removes most of the 50 Hz hum, the raw file keeps it
    assert hum_power(data[:, 2]) > 5 * hum_power(data_f[:, 2])


def test_notch_state_is_restored_with_its_frequency(sim, tmp_path):
    talk(sim, {"cmd": "set_notch", "enabled": True, "freq": 50})
    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 1, "--out", tmp_path / "r",
               cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    welcome = talk(sim)
    assert welcome["filter"] is True and welcome["notch_filter"] is True and welcome["notch_freq"] == 50


def test_wifi_drop_keeps_all_data_and_reconnects(sim, tmp_path):
    p = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 10, "--label", "drop",
               "--out", tmp_path / "r", cwd=tmp_path, background=True)
    time.sleep(3)
    talk(sim, {"cmd": "sim_outage", "seconds": 4})
    out, _ = p.communicate(timeout=60)
    assert p.returncode == 0, out
    path, meta = only_recording(tmp_path / "r")
    _, data = read_csv(path)
    steps = np.diff(data[:, 1])
    assert np.all(steps >= 1)
    assert (steps > 1).sum() == 1, "exactly one gap, where the outage was"
    assert meta["missing_samples"] == int(steps.max() - 1) > 500
    assert meta["n_samples"] == len(data) > 1250
    assert data[-1, 0] - data[0, 0] < 10, "still ends at the planned time, by the Pi's clock"
    assert meta["complete"] is False
    assert meta["end_reason"] == "planned time span reached"
    events = [e["event"] for e in meta["events"]]
    assert "disconnected" in events and "reconnected" in events
    assert "connection lost" in out


def test_server_restart_filters_switched_off_again(sim, tmp_path):
    p = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 6, "--label", "restart",
               "--out", tmp_path / "r", cwd=tmp_path, background=True)
    time.sleep(2.5)
    talk(sim, {"cmd": "sim_restart"})
    out, _ = p.communicate(timeout=60)
    assert p.returncode == 0, out
    _, meta = only_recording(tmp_path / "r")
    events = [e["event"] for e in meta["events"]]
    assert events.count("server filters switched off") == 2
    assert meta["sample_counter_resets"] == 1
    assert meta["data_filtering"].startswith("none")
    assert talk(sim)["filter"] is True


def test_filters_switched_on_by_another_client_are_detected(sim, tmp_path):
    p = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 6, "--label", "probe",
               "--check-every", 1, "--out", tmp_path / "r", cwd=tmp_path, background=True)
    time.sleep(2.5)
    talk(sim, {"cmd": "set_filter", "enabled": True, "lowcut": 1, "highcut": 40})
    out, _ = p.communicate(timeout=60)
    assert p.returncode == 0, out
    _, meta = only_recording(tmp_path / "r")
    events = [e["event"] for e in meta["events"]]
    assert "server filters found on" in events
    assert events.count("server filters switched off") == 2
    (first, last), = meta["possibly_filtered_samples"]
    assert first is not None and last is not None and last > first
    assert meta["data_filtering"].startswith("none, except")


def test_no_board_gives_a_clear_message_and_restores_filters(sim, tmp_path):
    talk(sim, {"cmd": "sim_board", "present": False})     # like the real Pi without the PiEEG-8
    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 2,
               "--wait-for-samples", 5, "--out", tmp_path / "r", cwd=tmp_path)
    assert r.returncode != 0
    assert "no samples arrived" in r.stderr and "PiEEG-8" in r.stderr
    assert not list((tmp_path / "r").glob("*.csv"))
    assert talk(sim)["filter"] is True, "filters must be back on even when nothing was recorded"


def test_no_server_gives_a_clear_error(tmp_path):
    r = script("record.py", "--host", "127.0.0.1", "--port", free_port(), "--seconds", 1,
               "--connect-timeout", 2, "--out", tmp_path / "r", cwd=tmp_path)
    assert r.returncode != 0
    assert "No connection to PiEEG Server" in r.stderr
    assert not list((tmp_path / "r").glob("*.csv"))

def test_subject_age_and_sex_reach_the_sidecar(sim, tmp_path):
    """When record.py is given the subject metadata, the sidecar carries it, so the NWB file
    can hold a real age and sex instead of the unknown form."""
    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 2,
               "--age", "P29Y", "--sex", "F", "--out", tmp_path, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _, meta = only_recording(tmp_path)
    assert meta["subject_age"] == "P29Y"
    assert meta["subject_sex"] == "F"


def test_subject_metadata_is_absent_when_not_given(sim, tmp_path):
    """Absent keys, not invented ones: mission_3_nwb.py reads that as 'not recorded'."""
    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 2,
               "--out", tmp_path, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _, meta = only_recording(tmp_path)
    assert "subject_age" not in meta
    assert "subject_sex" not in meta


def test_an_age_that_is_not_an_iso_duration_is_refused(sim, tmp_path):
    r = script("record.py", "--host", "127.0.0.1", "--port", sim, "--seconds", 2,
               "--age", "29", "--out", tmp_path, cwd=tmp_path)
    assert r.returncode != 0
    assert "ISO 8601" in r.stderr
    assert not list(tmp_path.glob("*.csv")), "nothing should be recorded before the arguments are valid"
