# Troubleshooting

Start with two checks, they narrow down almost everything:

```bash
python check_setup.py --noise-test                     # from code/ on the laptop: WiFi, Pi, server, board
ssh jure@tina.local "pieeg-server doctor"       # on the Pi: SPI, GPIO, service, ports
```

`check_setup.py` names the first broken link in the chain. If its noise test passes (all channels under 5 µV RMS), the board is fine and any noise comes from electrodes, cables or surroundings. Based on the official [PiEEG-8 troubleshooting](https://docs.pieeg.com/hardware/devices/pieeg-8/troubleshooting/) page.

## No samples from the board

PiEEG Server runs and answers (the dashboard opens, `check_setup.py` passes everything up to `Samples`), but no data arrives: every channel flat in the dashboard, `record.py` says "no samples arrived".

1. Unplug the power. Is the PiEEG-8 pressed onto **all 40 pins**, none visible at either end, pin 1 on pin 1?
2. Power on, wait a minute, run `python check_setup.py` again.
3. Still nothing: `ssh jure@tina.local "journalctl -u pieeg-server -n 40"` and look for errors.

Without a mounted board this is exactly what happens, so it's also what the Pi shows before the PiEEG-8 arrives. Note: PiEEG Server's own noise test reports "Device OK" even when it collected zero samples. `self_test.py` and `check_setup.py` check the sample count and say "no usable test" instead.

## Power and hardware

| Problem | Fix |
|---|---|
| LED on the PiEEG-8 is off | Powerbank on and charged? Board fully seated on all 40 pins? |
| Lightning bolt, random reboots, `under-voltage` in `journalctl -k` | Not enough current. PiEEG asks for a 3 A powerbank, Raspberry Pi specifies 2.5 A for the Pi 3. Use the official cable from the kit, not a thin phone cable, and the strongest port of the powerbank. Charge it, many sag when almost empty |
| Board off by one pin | Unplug power, take it off, seat it again. Pin 1 of the board on pin 1 of the Pi |
| Thermometer icon or `vcgencmd get_throttled` not `0x0` | Too warm or too little power. `0x50005` means under voltage right now and since boot, typical for a weak phone charger. A small flat heatsink helps against heat, it must fit under the PiEEG-8 |

## Network

### The dashboard does not open

1. Wait a full 2 minutes after plugging in the powerbank.
2. Laptop and Pi on the **same WiFi network**. The Pi 3 uses 2.4 GHz, the laptop may use 5 GHz on the same router, that's fine.
3. `tina.local` not resolving, see below.
4. SSH in and check: `systemctl status pieeg-server` and `journalctl -u pieeg-server -n 50`.

### live_view.py, record.py or self_test.py can't connect, but the dashboard works

macOS blocks local network access until you allow it. System Settings → Privacy & Security → **Local Network** → turn on Terminal (and Python if listed). Run the script again.

### tina.local is not found

Macs and Windows 10 or 11 resolve `.local` names out of the box, but some routers and guest networks block it. Use the Pi's IP address instead:

- Router page (often http://192.168.1.1 or http://192.168.0.1) → list of connected devices → `tina`
- Or via a working SSH session: `hostname -I`

Then `http://<ip>:1617` and `python live_view.py --host <ip>`.

## PiEEG Server

| Problem | Fix |
|---|---|
| Dashboard shows 16 channels, or the scripts warn "Server reports 16 channels" | The service isn't in PiEEG-8 mode. See [setup step 4](setup-raspberry-pi.md#4-switch-the-service-to-pieeg-8) |
| Flat line on every channel | See [no samples from the board](#no-samples-from-the-board). Also check SPI: `ls /dev/spidev*` must list `spidev0.0`. If not: `sudo raspi-config` → Interface Options → SPI → Enable, reboot |
| `Address already in use` | The service is already running. `sudo systemctl stop pieeg-server` before starting the server by hand |
| `Permission denied` on SPI or GPIO | `sudo usermod -aG spi,gpio $USER`, log out and in again |
| Clicked **Bandpass → Enabled** and the trace got wild | That button shows the current state, clicking it switched the 1 to 40 Hz filter off. Click it again |
| Dashboard says a filter is on, but the signal looks unfiltered | Another program switched the server filter (`record.py` does it while recording, and warns if it couldn't switch it back on). Click the filter's button twice, off and on again, to bring dashboard and server back in step |
| Live log | `journalctl -u pieeg-server -f` |

## Recordings

| Problem | Fix |
|---|---|
| `connection lost (...), reconnecting ...` while recording | WiFi dropped or the server restarted. `record.py` reconnects by itself and keeps everything recorded. The sidecar lists the gap under `events` and `missing_samples` |
| A recording has almost no 50 Hz and looks smooth | It was recorded with the server filters on. Check `data_filtering` in its `.json`. `record.py` records raw unless you pass `--keep-server-filters` |
| `complete: false` in the sidecar | Samples are missing (gaps), the server restarted, or you stopped early. `end_reason` and `events` say which |
| A few seconds of almost flat signal on every channel | Someone ran `self_test.py` (or the dashboard's noise test) during the recording. The inputs were shorted inside the chip for those seconds |
| `CERTIFICATE_VERIFY_FAILED` in `get_example_data.py` | Python from python.org on a Mac. `pip install -r requirements.txt` again (it brings `certifi`), or run **Install Certificates.command** in the Python folder under Applications |

## Signal

| Problem | Likely cause and fix |
|---|---|
| All channels noisy at once | **Ref or Bias.** Fresh stickers on clean, dry skin behind the ears, clips firmly on the snaps |
| One channel huge or stuck | That electrode has no contact. New sticker, wipe the skin, press it on, the clip must bite the metal snap, not the foam |
| Strong 50 Hz hum | Something is on the mains (charger!). For viewing, turn on the **Notch** filter at **50 Hz** (the dashboard starts at 60). Recordings stay raw either way |
| Big slow spikes on channel 1 | Blinks and eye movements. That's EOG, real signal, not a fault |
| Bursts of fast noise | Jaw, face or neck muscles (EMG). Relax the face, don't talk or chew |
| Jumps when you move | Cable motion. Sit still, Pi close to your head, cables hanging free |
| No alpha with eyes closed | Expected to be weak on the forehead, alpha is strongest at the back of the head. Eyes closed at least 10 to 30 s, quiet room, look at the spectrum, not the raw line |
| Channels 2 to 8 look like noise | Normal. Nothing is connected to them |

### Quick noise checklist (from PiEEG)

- [ ] Everything on the battery, nothing on the mains, powerbank not charging
- [ ] Laptop charger unplugged
- [ ] Short cables, hanging free
- [ ] Setup on a wooden or plastic surface, away from the router, phones and chargers
- [ ] Sitting still, feet not on a metal surface

## Pi 3 specifics

- PiEEG's current docs list the Pi 4 and 5 as hosts. Elecrow lists the Pi 3, 4 and 5, and the PiEEG Server installer explicitly detects the Pi 3 and selects `/dev/gpiochip0`. If `self_test.py` passes and blinks show up, the Pi 3 works.
- Python SDK: the `*_Pi4.py` scripts are the right ones for the Pi 3 (both use `RPi.GPIO`).
- 1 GB RAM: run only the server on the Pi, analysis on the laptop.

## Still stuck

[PiEEG-8 troubleshooting](https://docs.pieeg.com/hardware/devices/pieeg-8/troubleshooting/) · [PiEEG-8 issues on GitHub](https://github.com/pieeg-club/PiEEG-8/issues) · [PiEEG Server issues on GitHub](https://github.com/pieeg-club/PiEEG-server/issues)
