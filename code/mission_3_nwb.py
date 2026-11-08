"""
MISSION 3: turn a recording into a Neurodata Without Borders (NWB) file.

NWB is the standard format neuroscience labs use to share data.

Input:  recordings/<file>.csv  plus its .json sidecar (written by record.py)
Output: nwb/<file>.nwb

    python mission_3_nwb.py recordings/example_alpha.csv
    nwbinspector nwb/

Done when nwbinspector reports no critical issues. Read the file back with
pynwb.NWBHDF5IO(path).read() and the channel data is in .acquisition["eeg"].

Docs: https://pynwb.readthedocs.io  ·  https://nwbinspector.readthedocs.io
Install: pip install pynwb nwbinspector
"""

import csv
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pynwb import NWBFile, NWBHDF5IO
from pynwb.ecephys import ElectricalSeries
from pynwb.file import Subject

from spectrum import load


def start_time(meta: dict) -> datetime:
    """The sidecar carries an ISO time with a UTC offset, which NWB requires.

    Example datasets have no start time at all. Rather than invent one, the
    conversion time is used and the session description says so.
    """
    raw = meta.get("start_time")
    if raw:
        return datetime.fromisoformat(raw)
    return datetime.now(timezone.utc)


def _locations(meta: dict, n_channels: int) -> list:
    """One location string per channel, from the sidecar's electrode map."""
    electrodes = meta.get("electrodes")
    out = []
    for i in range(1, n_channels + 1):
        loc = "not documented"
        if isinstance(electrodes, dict):
            loc = electrodes.get(f"ch{i}") or "not documented"
        out.append(loc)
    return out


def _sample_numbers(csv_path: Path):
    """The n column is PiEEG Server's sample counter. A jump means lost samples."""
    with open(csv_path) as f:
        rows = csv.reader(f)
        header = next(rows)
        if "n" not in header:
            return None
        col = header.index("n")
        out = []
        for row in rows:
            if len(row) != len(header):
                continue
            try:
                out.append(int(float(row[col])))
            except ValueError:
                continue
    return np.array(out) if out else None


def _invalid_intervals(csv_path: Path, meta: dict, fs: float) -> list:
    """Time ranges a reader should skip: gaps in the sample counter, and the
    ranges another client may have filtered while recording."""
    out = []
    ns = _sample_numbers(csv_path)
    if ns is not None and len(ns) > 1:
        for i in np.nonzero(np.diff(ns) != 1)[0]:
            start, stop = (ns[i] + 1) / fs, ns[i + 1] / fs
            if stop > start:
                out.append((float(start), float(stop), "gap in the sample counter"))
    for first, last in meta.get("possibly_filtered_samples") or []:
        last = first if last is None else last
        out.append((float(first) / fs, float(last + 1) / fs,
                    "possibly filtered by another client during the recording"))
    return out


def _subject(meta: dict) -> Subject:
    """Subject with whatever the sidecar knows.

    NWB has no value for "not recorded": sex "U" is its vocabulary for unknown,
    and an age range with both bounds blank is the format's open range. Both are
    set to the unknown form when record.py was not asked for them.
    """
    return Subject(
        subject_id=str(meta.get("subject", "sub-01")),
        species="Homo sapiens",
        description=str(meta.get("recorded_by", "recorded with pieeg-home-lab")),
        sex=str(meta.get("subject_sex", "U")).upper(),
        age=str(meta.get("subject_age", "/")),
    )


def _device(nwbfile):
    """The PiEEG-8 shield as an NWB Device.

    pynwb 4 moved the manufacturer onto a DeviceModel, older versions take it on the device
    itself. Both write the same NWB, so this uses whichever the installed pynwb has.
    """
    name = "PiEEG-8"
    description = "8 channel ADS1299 EEG shield for the Raspberry Pi"
    if hasattr(nwbfile, "create_device_model"):
        model = nwbfile.create_device_model(name=name, manufacturer="PiEEG")
        return nwbfile.create_device(name=name, description=description, model=model)
    return nwbfile.create_device(name=name, description=description, manufacturer="PiEEG")


def add_recording(nwbfile, data_uv, meta, csv_path, fs, n_channels):
    """Add the shield, its electrodes and the EEG series to an open NWBFile.

    csv_to_nwb below calls this, so one recording becomes the same NWB objects every time:
    one electrode per channel carrying the position the sidecar documents, the signal stored
    in microvolts and reported in volts through the conversion factor, and the ranges a
    reader should skip.
    """
    device = _device(nwbfile)
    group = nwbfile.create_electrode_group(
        name="electrodes",
        description="10-20 positions on skin without hair, reference and bias on the mastoids",
        device=device,
        location="scalp",
    )
    for location in _locations(meta, n_channels):
        nwbfile.add_electrode(group=group, location=location, group_name=group.name)
    electrodes = nwbfile.electrodes.create_region(
        name="electrodes",
        region=list(range(n_channels)),
        description="the channels of this series",
    )

    nwbfile.add_acquisition(ElectricalSeries(
        name="eeg",
        description="EEG from the PiEEG-8. Stored in microvolts, conversion scales to volts.",
        data=data_uv,
        electrodes=electrodes,
        rate=fs,
        conversion=1e-6,
        filtering=str(meta.get("data_filtering", "not documented in the sidecar")),
    ))

    for start, stop, why in _invalid_intervals(csv_path, meta, fs):
        # the invalid_times table has no description column, its labels are tags
        nwbfile.add_invalid_time_interval(start_time=start, stop_time=stop, tags=[why])


def csv_to_nwb(csv_path: Path, out_dir: Path = Path("nwb")) -> Path:
    meta = json.loads(csv_path.with_suffix(".json").read_text())
    if str(meta.get("units", "")).lower() not in ("microvolts", "uv", "µv"):
        raise ValueError(f"conversion to volts assumes microvolts, sidecar says {meta.get('units')!r}")
    n_channels = int(meta["n_channels"])
    fs = float(meta["sample_rate_hz"])
    data_uv = np.column_stack([load(csv_path, c) for c in range(1, n_channels + 1)])

    described = meta.get("description") or meta.get("label", "PiEEG recording")
    if not meta.get("start_time"):
        described += " (start time unknown: set to the conversion time)"

    notes = str(meta.get("notes", "") or "")
    nwbfile = NWBFile(
        session_description=described,
        identifier=str(uuid.uuid4()),
        session_start_time=start_time(meta),
        experiment_description=notes or None,
    )

    nwbfile.subject = _subject(meta)

    add_recording(nwbfile, data_uv, meta, csv_path, fs, n_channels)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{csv_path.stem}.nwb"
    with NWBHDF5IO(out, "w") as io:
        io.write(nwbfile)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    written = csv_to_nwb(Path(sys.argv[1]))
    print("Wrote", written)
    print("Next: nwbinspector nwb/")
