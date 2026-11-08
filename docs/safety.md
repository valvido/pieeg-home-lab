# Safety

The PiEEG-8 connects your skin directly to the electronics and has **no isolation circuitry**. It's safe as long as nothing in the chain touches mains power. These rules follow the official [PiEEG-8 safety page](https://docs.pieeg.com/hardware/devices/pieeg-8/safety/).

## Rules

1. **Battery only.** The Raspberry Pi and the PiEEG-8 run from the powerbank while electrodes are on a person.
2. **Don't charge the powerbank during a session.** A powerbank that's plugged into the wall while powering the Pi is a mains connection. Charge it before, never during.
3. **No cable to anything on the mains.** No wall charger, no HDMI to a TV or monitor, no USB to a plugged in computer, and **no Ethernet cable** (the Pi 3 has a network port, leave it empty).
4. **Laptop on battery, WiFi only.** Unplug the laptop's charger before the electrodes go on. The laptop never gets a cable to the Pi.
5. **Not a medical device.** Learning and research only. No diagnosis, monitoring or treatment of anything. PiEEG: the board "has not been certified by any regulator for use with the human body".
6. **Implants.** Don't put electrodes on anyone with a pacemaker or other implanted electronic device without a physician's approval. The Bias electrode is connected to an amplifier output on the board (see [below](#what-the-bias-electrode-does)), and an implant isn't designed with that in mind. Without approval, be the researcher and [record someone else](recording-someone-else.md). Skip ECG experiments (wrists, chest) for that person entirely.
7. **Skin.** Clean, intact skin only. Stop if a sticker itches or burns.
8. **Bare board.** The PiEEG-8 has no case. Hold it by the edges, touch something metal first to discharge static, keep drinks away. Check the cables before each session.

## Connection order

Power goes on last and comes off first, so nobody handles the pins of a powered board.

| Start | Finish |
|---|---|
| 1. Pi unplugged, PiEEG-8 seated on the Pi | 1. Unplug the powerbank |
| 2. Stickers on the skin, cables on the board's pins, clips on the stickers | 2. Clips off, stickers off |
| 3. Powerbank into **PWR IN**, last | 3. Recharge the powerbank, with nothing connected to it |

> [!IMPORTANT]
> **Stop the session if** a sticker itches, burns or tingles, the participant feels anything unusual or wants to stop, anything in the setup ends up connected to mains power, the board or powerbank gets hot or smells, or a cable is damaged. Stopping means: unplug the powerbank first, then remove the clips.

## Safe and unsafe setups

| Setup | With electrodes on |
|---|---|
| Pi + PiEEG-8 on a charged powerbank, laptop on battery over WiFi | ✅ Safe |
| Powerbank plugged into the wall while powering the Pi | ❌ Never |
| Pi on its wall power supply | ❌ Never |
| HDMI to a TV or monitor on a wall socket | ❌ Never |
| Ethernet or USB cable to a mains powered device | ❌ Never |
| Laptop charging while connected over WiFi | ❌ Unplug the charger first |

## Why

A wall power supply, a charging laptop or a charging powerbank can, if it develops a fault, put mains voltage on its low voltage side. With electrodes on the skin that path would go through you. A battery that isn't charging can't do that. As a bonus, battery operation also removes most of the 50 Hz hum.

## What the Bias electrode does

Facts from the register values PiEEG Server writes to the ADS1299 ([hardware.py](https://github.com/pieeg-club/PiEEG-server/blob/9bf350310bb492e1373edfe5b0714857f1fe04e9/pieeg_server/hardware.py), the version this kit installs), read with the [ADS1299 datasheet](https://www.ti.com/lit/ds/symlink/ads1299.pdf):

| Register | Value | Meaning |
|---|---|---|
| CONFIG3 | `0xFF` | Bias amplifier powered, its reference generated inside the chip at (AVDD + AVSS) / 2, the middle of the analog supply |
| BIAS_SENSP, BIAS_SENSN | `0x00` | No channel is fed into the bias amplifier, so it holds that fixed voltage instead of following the measured signals |
| LOFF_SENSP, LOFF_SENSN | `0x00` | Lead off detection off: no test current is sent through any electrode |
| CONFIG4 | `0x00` | Lead off comparators off |

So the Bias electrode connects the body to a fixed voltage driven by an amplifier, a common design in EEG amplifiers. It's still a direct electrical connection to the body, on a board that isn't certified for medical use, and PiEEG's [specification](https://docs.pieeg.com/hardware/devices/pieeg-8/specification/) and safety pages give no leakage current figure. That's the reason for rule 6. Nobody should read these facts as a safety approval for an implant: only a physician can give that.

Official pages: [PiEEG-8 safety](https://docs.pieeg.com/hardware/devices/pieeg-8/safety/) · [liability notice](https://pieeg.com/liability/)
