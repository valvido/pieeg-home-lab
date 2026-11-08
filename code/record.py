"""
Record EEG from PiEEG Server to a CSV file on your laptop.

    python record.py --seconds 60 --label eyes_closed
    python record.py --subject sub-02 --label eyes_closed       # recording someone else
    python record.py --montage bare_skin --label eog            # Mission 4 positions
    python record.py --host localhost --seconds 30              # from simulate.py

Writes  recordings/<date>_<subject>_<label>.csv  with columns t, n, ch1 ... ch8,
and a .json sidecar next to it: settings, electrode positions, and everything that
happened during the recording.

Raw data. PiEEG Server filters the stream it sends to every client, and its 1 to 40 Hz
bandpass is on by default. record.py switches the server filters off while it records,
so the file holds the unfiltered signal, and switches them back on at the end (bandpass
1 to 40 Hz, notch at the frequency it had). While it records, the dashboard shows the
raw signal too. Don't touch the dashboard filters during a recording: record.py checks
every 5 seconds, switches them off again and marks the affected samples in the sidecar.
--keep-server-filters records what the server sends instead, and the sidecar says so.

Never loses data. Every sample is written to disk as it arrives. If the WiFi drops,
record.py reconnects and carries on, and the sidecar lists the gap. The recording still
ends at the planned time (by the Pi's clock), so a protocol like "60 s eyes closed" stays
60 s. Ctrl+C or a lost connection still leaves a complete, readable file.
"""

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from eeg_stream import DEFAULT_PORT, SAMPLE_RATE, SERVER_BANDPASS, EEGStream

MONTAGES = {
    # First test, README steps 2 and 3
    "fp1": {
        "ch1": "Fp1, left forehead",
        "ref": "M1, left mastoid (bony bump behind the left ear)",
        "bias": "M2, right mastoid (bony bump behind the right ear)",
    },
    # First test plus the optional second forehead sticker
    "fp1_fp2": {
        "ch1": "Fp1, left forehead",
        "ch2": "Fp2, right forehead",
        "ref": "M1, left mastoid",
        "bias": "M2, right mastoid",
    },
    # Mission 4: four channels on skin without hair
    "bare_skin": {
        "ch1": "Fp1, left forehead",
        "ch2": "Fp2, right forehead",
        "ch3": "LOC, outer corner of the left eye (near F7)",
        "ch4": "ROC, outer corner of the right eye (near F8)",
        "ref": "M1, left mastoid",
        "bias": "M2, right mastoid",
    },
    "none": {},
}

ELECTRODE_KEYS = [f"ch{i}" for i in range(1, 9)] + ["ref", "bias"]
NO_SAMPLE_TIMEOUT = 15.0   # s after connecting without a single sample: give up


AGE_PART = re.compile(r"P(?:\d+Y)?(?:\d+M)?(?:\d+W)?(?:\d+D)?")


def valid_age(text: str) -> bool:
    """ISO 8601 duration, or a range with a blank bound: P29Y, P23W, P90Y/."""
    left, sep, right = text.partition("/")
    parts = (left, right) if sep else (left,)
    return any(parts) and all(
        part == "" or (AGE_PART.fullmatch(part) and any(c.isdigit() for c in part)) for part in parts
    )


def parse_electrodes(text: str) -> dict:
    """'ch1=Fp1,ch2=Fp2,ref=M1,bias=M2' -> {'ch1': 'Fp1', ...}"""
    out = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        key, sep, value = part.partition("=")
        key = key.strip().lower()
        if not sep or key not in ELECTRODE_KEYS or not value.strip():
            raise ValueError(f"'{part}' should look like ch1=Fp1 (keys: ch1 to ch8, ref, bias)")
        out[key] = value.strip()
    return out


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "x"


def unique_path(folder: Path, stem: str) -> Path:
    path, k = folder / f"{stem}.csv", 2
    while path.exists() or path.with_suffix(".json").exists():
        path, k = folder / f"{stem}_{k}.csv", k + 1
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="tina.local")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--label", default="session")
    p.add_argument("--subject", default="sub-01",
                   help="pseudonym of the person recorded, never a real name (sub-01, sub-02, ...)")
    p.add_argument("--montage", default="fp1", choices=list(MONTAGES),
                   help="electrode positions stored in the sidecar (default: fp1, the first test)")
    p.add_argument("--electrodes",
                   help="your own positions instead of a montage, e.g. \"ch1=Fp1,ch2=Fp2,ref=M1,bias=M2\"")
    p.add_argument("--notes", default="", help="free text for the sidecar, e.g. \"sneezed at 40 s\"")
    p.add_argument("--age",
                   help="subject's age as an ISO 8601 duration (P29Y, P23W), or a range with a blank "
                        "bound (P90Y/). Goes to the sidecar so NWB files carry a real age")
    p.add_argument("--sex", choices=["M", "F", "O", "U"],
                   help="subject's sex the way NWB spells it, written to the sidecar")
    p.add_argument("--keep-server-filters", action="store_true",
                   help="record what the server sends, filters included (not raw)")
    p.add_argument("--check-every", type=float, default=5.0, help=argparse.SUPPRESS)
    p.add_argument("--connect-timeout", type=float, default=15.0, help=argparse.SUPPRESS)
    p.add_argument("--wait-for-samples", type=float, default=NO_SAMPLE_TIMEOUT, help=argparse.SUPPRESS)
    p.add_argument("--out", default="recordings")
    a = p.parse_args()
    if a.seconds <= 0:
        p.error("--seconds must be more than 0")
    if a.age and not valid_age(a.age):
        p.error("--age should be an ISO 8601 duration like P29Y, or a range with a blank bound like P90Y/")
    try:
        electrodes = parse_electrodes(a.electrodes) if a.electrodes else MONTAGES[a.montage]
    except ValueError as e:
        p.error(f"--electrodes: {e}")
    montage = "custom" if a.electrodes else a.montage
    raw = not a.keep_server_filters

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = unique_path(out, f"{stamp}_{safe_name(a.subject)}_{safe_name(a.label)}")

    stream = EEGStream(a.host, a.port, raw=raw, check_every=a.check_every).start()
    print(f"Connecting to {stream.url} ...")
    if not stream.wait_connected(a.connect_timeout):
        stream.stop()
        raise SystemExit(f"No connection to PiEEG Server at {stream.url} ({stream.last_error or 'no answer'}).\n"
                         "Is the Pi on and in the same WiFi? See docs/troubleshooting.md")

    start_filters = stream.filters_at_start
    if raw and start_filters.any_on():
        print(f"Server filters were on ({start_filters.describe()}). Switched off for a raw recording,\n"
              "they go back on when the recording ends. The dashboard shows the raw signal meanwhile.")
    elif raw and start_filters.unknown():
        print("The server didn't report its filter state. Sent 'filters off' anyway; check the sidecar.")
    elif not raw:
        print(f"Recording WITH the server filters ({start_filters.describe()}). The file is not raw.")
    if stream.channel_warning():
        print("Warning:", stream.channel_warning())

    fs = stream.server_info.get("sample_rate")
    fs = fs if isinstance(fs, (int, float)) and not isinstance(fs, bool) and fs > 0 else SAMPLE_RATE
    target = int(round(a.seconds * fs))
    print(f"Recording {a.seconds:g} s to {csv_path} (Ctrl+C stops early and keeps the data)")

    n_rows, n_ch, first, last = 0, None, None, None
    gaps, missing, resets, skipped = 0, 0, 0, 0
    end_reason = None
    t_connected, t_first, last_note, waiting_noted = time.monotonic(), None, 0.0, False
    f = csv_path.open("w", newline="")
    w = csv.writer(f)
    try:
        while end_reason is None:
            for s in stream.get_new():
                if n_ch is None:
                    n_ch = len(s.uv)
                    w.writerow(["t", "n", *[f"ch{i}" for i in range(1, n_ch + 1)]])
                if len(s.uv) != n_ch:
                    skipped += 1   # the server changed its channel count mid recording
                    continue
                if first is not None and s.t - first.t >= a.seconds:
                    end_reason = "planned time span reached"   # by the Pi's clock, after a gap
                    break
                if last is not None:
                    step = s.n - last.n
                    if step > 1:
                        gaps, missing = gaps + 1, missing + step - 1
                    elif step <= 0:
                        resets += 1   # server restarted, its sample counter began again
                w.writerow([s.t, s.n, *s.uv])
                n_rows += 1
                first, last = first or s, s
                if t_first is None:
                    t_first = time.monotonic()
                if n_rows >= target:
                    end_reason = "planned number of samples reached"
                    break
            f.flush()
            if end_reason:
                break
            if stream.error:
                end_reason = f"reader error: {stream.error}"
                break
            now = time.monotonic()
            if t_first is None:
                if now - t_connected > a.wait_for_samples:
                    end_reason = "no samples received"
                    break
                if not waiting_noted and now - t_connected > 4:
                    print(f"  connected, but no samples yet. Waiting up to {a.wait_for_samples:g} s ...")
                    waiting_noted = True
            elif now - t_first > a.seconds + 3:
                end_reason = "connection lost before the planned end"
                break
            elif not stream.connected and now - last_note > 2:
                print(f"  connection lost ({stream.last_error}), reconnecting ...")
                last_note = now
            time.sleep(0.05)
    except KeyboardInterrupt:
        end_reason = "stopped with Ctrl+C"
    finally:
        f.close()
        stream.stop()

    if n_rows == 0:
        csv_path.unlink(missing_ok=True)
        if end_reason == "no samples received" and stream.samples_received == 0:
            raise SystemExit("Nothing saved: PiEEG Server answers, but no samples arrived. Is the PiEEG-8 "
                             "mounted and pressed onto all 40 pins? See docs/troubleshooting.md, "
                             "'No samples from the board'.")
        raise SystemExit(f"Nothing saved ({end_reason}). See docs/troubleshooting.md")

    if not raw:
        filtering = (f"PiEEG Server filters, applied live on the Pi: {start_filters.describe()} at the start "
                     f"(bandpass cutoffs not reported by the server, its default is {SERVER_BANDPASS[0]:g} to "
                     f"{SERVER_BANDPASS[1]:g} Hz). Changes during the recording were not tracked.")
    elif stream.possibly_filtered:
        filtering = ("none, except the ranges in possibly_filtered_samples: another client switched the "
                     "server filters on during the recording")
    else:
        filtering = "none: record.py kept PiEEG Server's filters off, the file holds the unfiltered signal"

    meta = {
        "label": a.label,
        "subject": a.subject,
        "notes": a.notes,
        "start_time": datetime.fromtimestamp(first.t).astimezone().isoformat(timespec="milliseconds"),
        "end_time": datetime.fromtimestamp(last.t).astimezone().isoformat(timespec="milliseconds"),
        "time_note": "Pi's clock, written in the laptop's time zone with its UTC offset (NWB wants an offset)",
        "planned_duration_s": a.seconds,
        "duration_s": round(n_rows / fs, 3),
        "sample_rate_hz": fs,
        "n_samples": n_rows,
        "n_channels": n_ch,
        "units": "microvolts",
        "units_note": "As converted by PiEEG Server (4.5 V / 16777215 per count). Read against the ADS1299 datasheet that is half the true value at gain 1; see the README note and Mission 5. Kept unchanged so files stay comparable with PiEEG's dashboard and example data.",
        "montage": montage,
        "electrodes": electrodes,
        "data_filtering": filtering,
        "server_filters_at_start": asdict(start_filters) if start_filters else None,
        "possibly_filtered_samples": stream.possibly_filtered,
        "complete": end_reason.startswith("planned") and missing == 0 and resets == 0 and skipped == 0,
        "end_reason": end_reason,
        "sample_number_gaps": gaps,
        "missing_samples": missing,
        "sample_counter_resets": resets,
        "samples_skipped_channel_count_changed": skipped,
        "samples_dropped_while_filters_settled": stream.discarded,
        "events": stream.events,
        "source": f"PiEEG Server at {stream.url}",
        "server": {k: stream.server_info[k] for k in ("sample_rate", "channels", "mock", "simulated")
                   if k in stream.server_info},
        "recorded_with": "pieeg-home-lab code/record.py",
    }
    if a.age:
        meta["subject_age"] = a.age
    if a.sex:
        meta["subject_sex"] = a.sex
    csv_path.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    print(f"Saved {n_rows} samples ({n_rows / fs:.1f} s) to {csv_path}  [{end_reason}]")
    if gaps or resets:
        print(f"Note: {missing} samples missing in {gaps} gap(s), {resets} counter reset(s). "
              "Details in the .json sidecar under events.")
    if stream.possibly_filtered:
        print("Note: the server filters were switched on during the recording. "
              "See possibly_filtered_samples in the sidecar.")
    for e in stream.events:
        if e["event"].startswith("could not"):
            print(f"Warning: {e['event']} ({e['detail']}). Check the dashboard filter buttons.",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
