"""
MISSION 1: kill the 50 Hz hum.

Every wall socket in Berlin runs at 50 Hz, and your body picks it up like an
antenna. In the raw signal it can be bigger than your brain waves.

Your job: write remove_mains() so the 50 Hz peak disappears from the spectrum
but the alpha peak (8 to 13 Hz) stays untouched.

Test it:
    python mission_1_notch.py recordings/<your_file>.csv

Done when: the script prints PASS for both checks.

Hints, only if you want them:
  - scipy.signal.iirnotch(w0=50, Q=..., fs=250) and filtfilt
  - what happens at 100 Hz? (harmonics, and also: what is Nyquist here?)
  - bonus: compare a notch with simply low pass filtering at 40 Hz. When is each better?
"""

import sys

import numpy as np
from scipy import signal

from spectrum import load, sidecar_notes

FS = 250


def remove_mains(x: np.ndarray) -> np.ndarray:
    # TODO: your code here
    return x


def band_power(x, lo, hi):
    f, p = signal.welch(x - x.mean(), fs=FS, nperseg=2 * FS)
    m = (f >= lo) & (f <= hi)
    return np.trapezoid(p[m], f[m])


def hum_excess(x):
    """How much the 49 to 51 Hz band sticks out above its neighbours (45 to 48 and 52 to 55 Hz).

    On battery power a recording can have almost no hum. Then "95 % less" would be measured
    against the noise floor, which no filter can lower, and the test could never pass. This
    measures the hum peak above the floor instead: zero means 50 Hz is no louder than 47 or 53 Hz.
    """
    hum = band_power(x, 49, 51)
    floor = (band_power(x, 45, 48) + band_power(x, 52, 55)) / 2 * (2 / 3)  # 3 Hz bands scaled to 2 Hz
    return max(hum - floor, 0.0), hum


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for note in sidecar_notes(sys.argv[1]):
        print("Note:", note)
    x = load(sys.argv[1], channel=1)
    y = remove_mains(x)
    excess_before, hum_before = hum_excess(x)
    excess_after, hum_after = hum_excess(y)
    a_before, a_after = band_power(x, 8, 13), band_power(y, 8, 13)
    print(f"50 Hz power:  {hum_before:10.2f} -> {hum_after:10.2f} µV²  (above the floor: "
          f"{excess_before:.2f} -> {excess_after:.2f})")
    print(f"alpha power:  {a_before:10.2f} -> {a_after:10.2f} µV²")
    ok2 = abs(a_after - a_before) < 0.1 * a_before
    if excess_before < 0.05 * a_before:
        print("SKIP hum check: this recording has almost no 50 Hz hum to remove (battery power does that), "
              "so it can't show whether your filter works.\n     Use example_dry.csv from Mission 0, or "
              "record with the cables hanging free, see docs/missions.md.")
    else:
        ok1 = excess_after < 0.05 * excess_before
        print("PASS" if ok1 else "FAIL", "hum peak above the floor reduced by more than 95 %")
    print("PASS" if ok2 else "FAIL", "alpha changed by less than 10 %")
