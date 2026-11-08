# Lab notebook

What was measured with this kit, in order. One entry per session, one block per finished mission. Each entry names the recording it rests on (`code/recordings/` is not in the repository, the file names are the reference) and the sidecar's `complete` flag, so every number here can be traced to a file with a known montage and known filtering.

Conventions: times are local (Europe/Berlin), subjects are pseudonyms (`sub-01` is the kit's owner), amplitudes are PiEEG Server's µV, which read against the ADS1299 datasheet are half the true value ([README note](../README.md#step-7--check-the-signal), [Mission 5](missions.md#mission-5-read-the-datasheet)). Plots go in `images/notebook/` as PNG at about 1600 px wide (`spectrum.py --save`, `dpi=130`), one per entry, so the folder stays small.

---

## Sessions

### YYYY-MM-DD · first test

| | |
|---|---|
| Subject | sub-01 |
| Montage | `fp1`: E1 Fp1, Ref M1, Bias M2 |
| Power | powerbank, laptop on battery |
| Check | `check_setup.py --noise-test`: all `[ok]`, worst channel _x.xx_ µV RMS |
| Recordings | `YYYYMMDD_HHMMSS_sub-01_eyes_open.csv`, `..._eyes_closed.csv`, both `complete: true` |

What happened: blinks visible as _…_ µV spikes on channel 1; eye movements as steps; jaw clench as EMG bursts. Eyes closed for 30 s: _describe the alpha bump or its absence_.

![alpha, eyes open vs closed](images/notebook/YYYY-MM-DD-alpha.png)

Notes: _anything unusual: cable movement, 50 Hz level, what was changed_.

---

## Missions

### Mission 0 · real data first

Detector: `code/…` (commit `…`). Found _n_ of 10 chews and _n_ of 10 blinks in `example_artifacts.csv`. Method in one paragraph: _…_. What fooled it: _…_.

### Mission 1 · 50 Hz

`remove_mains()` is a _notch at 50 Hz, Q = …, zero phase (filtfilt)_. On `…_hum_test.csv`: hum peak above the floor _x_ → _y_ µV² (PASS), alpha _a_ → _b_ µV² (PASS). Compared with a 40 Hz low pass: _…_.

### Mission 2 · individual alpha frequency

Peak at _xx.x_ Hz (eyes closed), alpha power _x_ vs _y_ µV² open vs closed, from `spectrum.py` on `…`. Repeated on _date_: _xx.x_ Hz.

### Mission 3 · NWB

`nwb/….nwb`, `nwbinspector` result: _no critical issues_ / _list_. Gaps and possibly filtered ranges marked as invalid time intervals: _yes/no_.

### Mission 4 · bare skin montage

`--montage bare_skin`, recording `…`. Horizontal EOG (E3 − E4) plot: ![](images/notebook/….png). Blink rate: _n_ per minute.

### Mission 5 · datasheet

Bytes → two's complement → counts → volts → µV, each step with the datasheet section it comes from: _…_. PiEEG's constant vs the datasheet: _agree / differ by …_. Upstream issue: _link_.
