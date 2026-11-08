# Missions

Each mission is small enough for one evening. Do them in order or not, they're yours. Every mission works on your own recordings, on someone else's ([recording someone else](recording-someone-else.md)), or on PiEEG's published example data.

---

## Mission 0: real data first

Before anyone wears electrodes, work with real PiEEG recordings. PiEEG publishes three example files from their own hardware. One command downloads them and converts them to this repo's format:

```bash
python get_example_data.py
python spectrum.py recordings/example_*.csv
```

| File | What's in it |
|---|---|
| `example_dry.csv` | 77 s, 8 channels, dry Ag/AgCl electrodes on the 10-20 system |
| `example_artifacts.csv` | 20 s: chewing 4, 3, 2, 1 times and blinking 4, 3, 2, 1 times |
| `example_alpha.csv` | 40 s, the file PiEEG uses in their own alpha plotting example |

Tasks:
1. Plot `example_artifacts.csv` and find all 10 chewing bursts and all 10 blinks by eye. Then write code that finds them.
2. Run [Mission 1](#mission-1-kill-the-50-hz-hum) on `example_dry.csv`. It has real 50 Hz hum.
3. Which channel in `example_alpha.csv` has the strongest alpha? What does that suggest about where it sat on the head?

Done when your artifact detector finds 10 chews and 10 blinks.

For more practice data, [OpenNeuro](https://openneuro.org/) has hundreds of human EEG studies.

---

## Mission 1: kill the 50 Hz hum

Every socket in the flat runs at 50 Hz and your body picks it up like an antenna. On a raw signal it can be bigger than the brain waves. This kit runs on battery, which removes most of that hum before it reaches the file, so the mission uses a recording that has plenty of it: PiEEG's `example_dry.csv` from Mission 0, made with dry electrodes and real mains pickup.

```bash
python get_example_data.py dry
python mission_1_notch.py recordings/example_dry.csv
```

Fill in `remove_mains()` in [`code/mission_1_notch.py`](../code/mission_1_notch.py). Done when both checks print **PASS**: the 50 Hz peak above the noise floor reduced by more than 95 %, alpha changed by less than 10 %.

Then try it on your own data: `python record.py --seconds 60 --label hum_test` and the script on that file. `record.py` records raw (it switches PiEEG Server's filters off while it records), so whatever hum your setup has is in the file. If there is almost none, the script says `SKIP` instead of judging, which is itself a result worth a line in the notebook: battery power did the filter's job. To see the hum anyway, record 30 s with **no electrodes on anyone** and the cables hanging free: open inputs pick up the room's 50 Hz like antennas.

<details><summary>Hints</summary>

- `scipy.signal.iirnotch` plus `filtfilt`
- What's the Nyquist frequency at 250 Hz, and what happens to the 100 Hz harmonic?
- Bonus: compare the notch with a plain 40 Hz low pass. When would you pick which?
- Bonus: record 60 s with `--keep-server-filters` and compare the 50 Hz power with a raw recording. PiEEG Server's 1 to 40 Hz bandpass (Butterworth, order 5, applied live) is on by default. How much hum does it leave, and what does a live filter do to the phase?
</details>

---

## Mission 2: find your alpha peak

Your individual alpha frequency (IAF) is a personal number, usually somewhere between 8 and 12 Hz.

```bash
python record.py --seconds 60 --label eyes_open
python record.py --seconds 60 --label eyes_closed
python spectrum.py recordings/*eyes_open.csv recordings/*eyes_closed.csv
```

Done when you know your peak to 0.5 Hz and the eyes closed power is clearly higher than eyes open.

Bonus: blocks of 30 s open / 30 s closed in one recording, then a spectrogram (`scipy.signal.spectrogram`) where you can see alpha switch on and off.

---

## Mission 3: make it NWB

[Neurodata Without Borders](https://www.nwb.org/) is the standard format neuroscience labs use to share data.

```bash
python mission_3_nwb.py recordings/<file>.csv
nwbinspector nwb/
```

The converter in [`code/mission_3_nwb.py`](../code/mission_3_nwb.py) is done. `nwbinspector` reports no critical issues on the converted example datasets, and the numbers in the file are the numbers in the recording when it is read back.

What it writes:

- **Subject, device and electrodes from the sidecar**: subject id, electrode positions per channel, `data_filtering` in the series' `filtering` field.
- **`ElectricalSeries` in volts.** The CSV stays in microvolts and `conversion=1e-6` does the step, so nothing is rescaled on disk.
- **Gaps and maybes marked.** A jump in the sample counter, and the ranges `possibly_filtered_samples` names, become invalid time intervals tagged with the reason. Anyone analysing the file can skip them.
- **Unknown metadata is written as unknown.** NWB has no value for "not recorded": when the sidecar has no `subject_age` and `subject_sex`, the file gets `U` and an open age range `/`, and the inspector still passes. Real values from the sidecar are written instead.

<details><summary>What is still open</summary>

- `record.py` does not yet ask for the subject's age and sex, so every file carries the unknown form. One flag each would fix it.

</details>

---

## Mission 4: more channels on bare skin

You have 60 stickers and 10 clip cables, but stickers only hold on skin without hair. That still leaves several real EEG and EOG positions:

| Pin | Sticker on | 10-20 / EOG name | What you'll see |
|---|---|---|---|
| E1 | left forehead | Fp1 | blinks, frontal EEG |
| E2 | right forehead | Fp2 | blinks, compare left vs right |
| E3 | left temple, at the outer corner of the eye | LOC / near F7 | horizontal eye movements |
| E4 | right temple, at the outer corner of the eye | ROC / near F8 | horizontal eye movements, opposite sign |

Record with `--montage bare_skin`, so the sidecar (and later the NWB file) knows where each channel was:

```bash
python record.py --montage bare_skin --seconds 60 --label eye_movements
```

Tasks:
1. Record 60 s while looking left, centre, right in a fixed rhythm. Plot E3 minus E4: that's horizontal EOG, a simple eye tracker.
2. Build a blink detector on E1 and E2 (threshold plus refractory period). Count blinks per minute.
3. Compare alpha on E1 with eyes closed against E3 and E4. Where is it strongest?

Done when you have 4 channels recording cleanly and an eye movement plot that shows left and right.

Getting alpha from the back of the head (O1, O2) needs electrodes that work through hair. That's a later upgrade: dry comb electrodes and a head strap, following the [PiEEG DIY cap guide](https://pieeg.com/?p=633).

---

## Mission 5: read the datasheet

Each sample arrives as 3 bytes per channel from the ADS1299. PiEEG converts them to µV in software, and this repo's reading of the datasheet says that conversion is off by a factor of two ([README note](../README.md#step-7--check-the-signal)). This mission is to check that claim independently, the way a reviewer would, and then to report it.

1. Read the official conversion in the [PiEEG-8 specification](https://docs.pieeg.com/hardware/devices/pieeg-8/specification/#converting-to-microvolts) and in `_decode_channels` in [PiEEG Server hardware.py](https://github.com/pieeg-club/PiEEG-server/blob/9bf350310bb492e1373edfe5b0714857f1fe04e9/pieeg_server/hardware.py): `uv = 4.5e6 * raw / 16777215`, negatives as `raw - 16777214`.
2. In the [ADS1299 datasheet](https://www.ti.com/lit/ds/symlink/ads1299.pdf), find the table of ideal output code versus input signal (data format section): which code is +FS, which is −FS, what +FS is in volts at a given gain, and what one LSB is. Note the gain PiEEG programs (`CHnSET = 0x00`).
3. Write down every step from 3 bytes to µV with the datasheet section each comes from. Then answer: by what factor do the two formulas differ, and is PiEEG's negative branch (`− 16777214`) the two's complement the datasheet describes?
4. Check it on the chip if you can: the ADS1299 has an internal test signal (`CONFIG2`, `CHnSET = 0x05`) of known amplitude. PiEEG Server exposes `reg_write` over the WebSocket. What amplitude does the server report for it, and which formula does that agree with?

Done when your write up in the [lab notebook](lab-notebook.md#mission-5--datasheet) reaches a conclusion with evidence, and, if it confirms the discrepancy, when the issue is filed on [PiEEG-server](https://github.com/pieeg-club/PiEEG-server/issues) with the datasheet reference and, ideally, the test signal measurement. That is a small, real contribution to an open source instrument, which is exactly what this kit is for.

Bonus: PiEEG sets `BIAS_SENSP` and `BIAS_SENSN` to `0x00` (in PiEEG Server and in the official scripts). Look both registers up in the datasheet. What does the bias amplifier do with that setting, and what would change with `0xFF`?

---

## Ideas after that

- **A first open source contribution.** PiEEG Server's noise test answers "Device OK" when it collected zero samples, for example with no board mounted ([validation](validation.md) shows how it was found). Read `_run_noise_test` in [server.py](https://github.com/pieeg-club/PiEEG-server/blob/9bf350310bb492e1373edfe5b0714857f1fe04e9/pieeg_server/server.py), find why zero samples give an RMS of 0, and open an issue with the steps to reproduce, or a pull request that checks `samples_collected`
- Blink detector that toggles something on the laptop
- Eyes closed alarm: alpha above a threshold for 5 s
- Heart rate (ECG): sticker on the left wrist → E1, right wrist → Ref, a leg or ankle → Bias. One channel, then R peak detection. Record with `--electrodes "ch1=left wrist,ref=right wrist,bias=left ankle"`. **Never on anyone with a pacemaker or other implant**
- Stream to [LSL](https://labstreaminglayer.org/) from the dashboard and analyse live in MNE
