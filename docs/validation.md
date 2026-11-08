# Validation

What was checked on this kit's own hardware, and what came out. Part 1 is done. Part 2 needs the PiEEG-8 on the Pi.

## 1. Raspberry Pi and PiEEG Server

**Done on 31 October 2026**, before the PiEEG-8 arrived. Checked over SSH and from a laptop on the same WiFi, running this repo's own scripts against the real server. Nothing was installed or changed on the Pi for it.

| Check | Result |
|---|---|
| Board | Raspberry Pi 3 Model B Rev 1.2 |
| System | Raspberry Pi OS Lite, 64 bit (arm64), Debian 13 "trixie", image of 6 October 2026, kernel 6.18.50 |
| Firmware | 14 September 2026 (`core_freq_fixed=1` needs September 2024 or newer) |
| PiEEG Server | 0.49.0, commit `9bf3503`, branch `homelab` |
| Service | enabled and running, `--device pieeg8 --gpio-chip /dev/gpiochip0` |
| SPI | `dtparam=spi=on` and `core_freq_fixed=1` in `/boot/firmware/config.txt`, `/dev/spidev0.0` present |
| `pieeg-server doctor` | every check passed (its two port warnings only mean the service already runs) |
| Permissions | user `jure` in the groups `spi` and `gpio` |
| SSH | password and key login work |
| WiFi | country DE, 2.4 GHz (channel 11), signal 57 of 100 |
| Clock | Europe/Berlin, synchronised over the network (`record.py` uses the Pi's clock) |
| Storage | 14 GB, 3.3 GB used, no SD card errors since boot |
| `check_setup.py` | every check `[ok]` except `Samples`, as expected without the board |
| `record.py` | switched the real server's filters off and back on (`"filter": true` again afterwards), clear message that no samples arrived |
| `self_test.py` | "no usable test: 0 of 250 samples", where PiEEG Server's own verdict says "Device OK" |
| Power | ⚠️ under voltage (`throttled=0x50005`) on a 5 V, 0.7 A phone charger used during setup. Retest on the powerbank, part 2 |

Found and fixed during this validation:

- PiEEG Server's noise test reports "Device OK" when it collected zero samples, so a missing or badly seated board would pass. `self_test.py` and `check_setup.py` now check the sample count. Worth reporting upstream, see [missions](missions.md#ideas-after-that).
- With the server running but no board, `record.py` and `live_view.py` now say that no samples arrive, instead of reporting a lost connection.
- `./setup.sh` fails on a fresh clone of PiEEG Server (the file isn't executable in their repository). The [setup guide](setup-raspberry-pi.md) now runs `bash setup.sh`.

## 2. With the PiEEG-8

To do once the board arrives. Pi off, board on all 40 pins, powerbank with the kit's Micro USB cable.

| # | Check | Command | Pass when |
|---|---|---|---|
| 1 | Power | `ssh jure@tina.local vcgencmd get_throttled` (a minute after boot) | `throttled=0x0` |
| 2 | Whole chain and board noise | `python check_setup.py --noise-test --markdown ../docs/validation-board.md` | every line `[ok]` |
| 3 | First test with electrodes | [first test](first-test.md) | blinks show as big spikes on channel 1 |
| 4 | Alpha | `python record.py --seconds 60 --label eyes_open`, then `--label eyes_closed`, then `python spectrum.py recordings/*eyes_open.csv recordings/*eyes_closed.csv --save ../docs/images/validation-alpha.png` | eyes closed shows more power at 8 to 13 Hz |

Step 2 writes its results table to `docs/validation-board.md`. Add the alpha plot and the numbers `spectrum.py` prints, and part 2 is done.
