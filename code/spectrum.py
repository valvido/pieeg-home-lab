"""
Find your alpha peak in a recording.

    python spectrum.py recordings/20261225_190000_eyes_open.csv recordings/20261225_190130_eyes_closed.csv

Plots the power spectrum (Welch) of each file for one channel and prints
the alpha peak frequency and alpha power. Eyes closed should show a clearly
higher peak somewhere between 8 and 13 Hz.
"""

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

FS = 250


def load(path, channel):
    """One channel of a recording as a NumPy array (µV). Skips an incomplete last line."""
    with open(path) as f:
        r = csv.reader(f)
        header = next(r)
        col = header.index(f"ch{channel}")
        values = []
        for row in r:
            if len(row) != len(header):
                continue
            try:
                values.append(float(row[col]))
            except ValueError:
                continue
        return np.array(values)


def sidecar_notes(path):
    """Warnings from the .json sidecar that change how to read the spectrum."""
    side = Path(path).with_suffix(".json")
    if not side.exists():
        return []
    try:
        meta = json.loads(side.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    notes = []
    filtering = str(meta.get("data_filtering", "none"))
    if not filtering.startswith("none"):
        notes.append("recorded WITH PiEEG Server filters, not raw")
    if meta.get("possibly_filtered_samples"):
        notes.append("part of it may be filtered (possibly_filtered_samples in the sidecar)")
    if meta.get("missing_samples"):
        notes.append(f"{meta['missing_samples']} samples missing (connection gaps), the spectrum treats it as continuous")
    return notes


def alpha_stats(x):
    sos = signal.butter(4, [1, 40], btype="band", fs=FS, output="sos")
    x = signal.sosfiltfilt(sos, x - x.mean())
    f, p = signal.welch(x, fs=FS, nperseg=2 * FS)
    band = (f >= 8) & (f <= 13)
    peak = f[band][np.argmax(p[band])]
    power = np.trapezoid(p[band], f[band])
    return f, p, peak, power


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--channel", type=int, default=1)
    ap.add_argument("--save", help="save the figure instead of showing it")
    a = ap.parse_args()

    fig, ax = plt.subplots(figsize=(8, 4))
    for path in a.files:
        x = load(path, a.channel)
        f, p, peak, power = alpha_stats(x)
        name = Path(path).stem
        print(f"{name:40s} alpha peak {peak:5.1f} Hz   alpha power {power:8.1f} µV²")
        for note in sidecar_notes(path):
            print(f"{'':40s} note: {note}")
        ax.semilogy(f, p, label=f"{name} (peak {peak:.1f} Hz)")
    ax.axvspan(8, 13, alpha=0.12)
    ax.set_xlim(0, 45)
    ax.set_xlabel("Hz")
    ax.set_ylabel("µV²/Hz")
    ax.set_title(f"Power spectrum, ch{a.channel}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    if a.save:
        fig.savefig(a.save, dpi=130)
        print(f"Saved {a.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
