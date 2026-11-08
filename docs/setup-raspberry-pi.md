# Raspberry Pi setup

The MicroSD in the box is ready: put it in the Pi, power it, and it streams. This page says what's on the card, how to reach the Pi from the laptop, how to check that everything works, and how to redo the setup from scratch.

## The card in the box

| | |
|---|---|
| Name on the network | `tina`, reachable as **`tina.local`** ([renaming a card that still says `raspberrypi`](#renaming-the-pi)) |
| User | `jure`, the password chosen when the card was flashed |
| System | Raspberry Pi OS Lite, 64 bit, Debian 13 "trixie" (image of 6 October 2026) |
| WiFi | your home network, country DE. The Pi 3 only uses 2.4 GHz |
| SSH | on, with password or key |
| PiEEG Server | version 0.49.0 (commit `9bf3503`), starts by itself on every boot, in 8 channel mode |
| SPI | on, with `core_freq_fixed=1` |

Checked on the real Pi on 31 October 2026, results in [validation](validation.md).

## Connect from the laptop

No monitor or keyboard needed. Laptop and Pi only have to be on the same WiFi.

| What | How |
|---|---|
| **The graphical view** | The **dashboard**, in any browser: **[http://tina.local:1617](http://tina.local:1617)** |
| Python | The scripts in `code/` run on the laptop and read the stream over WiFi ([README, Code](../README.md#code)) |
| A terminal on the Pi | `ssh jure@tina.local`, in Terminal on a Mac or PowerShell on Windows |

If you also push to this repository from the laptop, GitHub wants a personal access token instead of the account password. On a Mac, `git config --global credential.helper osxkeychain` makes git remember it after the first push; on Windows, Git for Windows does the same by default.

**Why there's no desktop on the Pi.** The card runs Raspberry Pi OS **Lite**, without a desktop, on purpose: the Pi 3 has 1 GB of RAM, and PiEEG Server, the WiFi stream and a desktop would compete for it. Everything graphical happens on the laptop instead, in the dashboard and in Python, which is also how PiEEG's own "headless option" works. Nothing in this repo needs the Pi's desktop.

If `tina.local` doesn't resolve, use the Pi's IP address instead (router page, or `hostname -I` in an SSH session), e.g. `http://192.168.1.50:1617`. See [troubleshooting](troubleshooting.md#tinalocal-is-not-found).

## Check that it works

From `code/` on the laptop, after the [code setup](../README.md#setup-once):

```bash
python check_setup.py                 # about 10 seconds, changes nothing on the Pi
python check_setup.py --noise-test    # also PiEEG's board noise test, with the PiEEG-8 mounted
```

It checks the whole chain in order: the Pi's address, PiEEG Server and its version, the dashboard, 8 channel mode, real hardware (not mock mode), and samples arriving at about 250 per second. Every line `[ok]` means the setup is complete. Without the PiEEG-8 mounted, the line `Samples` fails: the server runs, but no data comes from the board.

The PiEEG doctor on the Pi checks the software side: `ssh jure@tina.local pieeg-server doctor`. Its two warnings about ports 1616 and 1617 being in use just mean the service already runs. It also announces newer PiEEG Server versions. This kit stays on 0.49.0 on purpose, see [updating](#updating-pieeg-server-later).

## Power during setup

With electrodes on anyone: **powerbank only** ([safety](safety.md)). For setup and updates without electrodes, a wall supply is fine, but it has to be strong enough: Raspberry Pi specifies 5 V and 2.5 A for the Pi 3. A 0.7 A phone charger is not: the Pi then runs on too low a voltage, slows itself down, and can corrupt the card while writing to it.

To check, over SSH:

```bash
vcgencmd get_throttled     # throttled=0x0 is good. 0x50005 means: under voltage right now and since boot
```

## Set it up from scratch

How the card in the box was made, to redo it on a new card. About 45 to 90 minutes, most of it waiting: a Pi 3 is slow at updates and installs. This follows the official [PiEEG-8 How to Start](https://docs.pieeg.com/hardware/devices/pieeg-8/setup/) guide, adapted for a **Raspberry Pi 3 Model B** used **headless** (no monitor, controlled from the laptop over WiFi).

| | Official PiEEG guide | This kit |
|---|---|---|
| Raspberry Pi | 4 or 5 | 3 Model B (V1.2, 1 GB, 2.4 GHz WiFi) |
| OS | Raspberry Pi OS 64 bit with desktop | Raspberry Pi OS **Lite** 64 bit (no desktop, leaves RAM for the server) |
| Screen | Battery powered monitor, wired keyboard | None. Dashboard on a battery powered laptop, as in PiEEG's "headless option" |
| PiEEG Server | Newest version, installed with one line | One fixed version (commit `9bf3503`), so it behaves exactly like the version this repo was checked against |
| Electrodes | Cap + 2 ear clips | Stick on Ag/AgCl electrodes on forehead and mastoids |

## 1. Flash the MicroSD

1. On the laptop (Mac or Windows) install **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)** and put the MicroSD into a card reader. Everything on the card gets erased.
2. Choose device **Raspberry Pi 3**, then **Raspberry Pi OS Lite (64-bit)** (under Raspberry Pi OS (other)), then the MicroSD as storage.
3. In the **customisation** step (Imager asks before writing):
   - Hostname: `tina`
   - Username and password: your choice, write them down
   - WiFi: home network name and password. The Pi 3 only sees **2.4 GHz**. A router that sends 2.4 and 5 GHz under one name is fine
   - Wireless LAN country: **DE**, time zone Europe/Berlin
   - **Enable SSH** with password authentication
4. Write, wait until Imager says it's done, put the card in the Pi.

Current Raspberry Pi OS applies these settings on the first boot with cloud-init: Imager writes them to the files `user-data` and `network-config` on the card ([Raspberry Pi: cloud-init on Raspberry Pi OS](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/)).

## 2. First boot

Power the Pi from the powerbank or a 2.5 A supply (no electrodes during setup, see [power](#power-during-setup)). Wait 2 to 5 minutes, the first boot takes longer. Then in Terminal (Mac) or PowerShell (Windows):

```bash
ssh <username>@tina.local
```

Can't find it? See [troubleshooting](troubleshooting.md#tinalocal-is-not-found).

## 3. Install PiEEG Server, one fixed version

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-dev build-essential
git clone https://github.com/pieeg-club/PiEEG-server.git ~/PiEEG-server
cd ~/PiEEG-server
git checkout -b homelab 9bf350310bb492e1373edfe5b0714857f1fe04e9
bash setup.sh
sudo reboot
```

PiEEG's own one line installer (`curl ... install.sh | bash`) clones the newest version and then runs exactly this `setup.sh`. In the repository the script isn't marked executable, so it runs with `bash setup.sh`. Running `setup.sh` from a checkout of one commit gives the same installation, pinned to version 0.49.0 from 16 September 2026, the code this repo's notes about filters and registers refer to. `python3-dev` and `build-essential` are there in case pip has to compile `spidev`.

What `setup.sh` does: enables SPI, builds a Python environment in `~/PiEEG-server/.venv`, installs the server, and creates the `pieeg-server` service that starts on every boot. It recognises the Pi 3 and sets the right GPIO chip (`/dev/gpiochip0`) by itself. It also adds `core_freq_fixed=1` to `/boot/firmware/config.txt`: the SPI clock is derived from the Pi's core clock, and when that clock scales up and down, ADS1299 frames get corrupted (PiEEG's note in `setup.sh`). The setting needs firmware from September 2024 or newer, which current Raspberry Pi OS has (`setup.sh` warns otherwise). Side effect: the core clock no longer drops when the Pi is idle.

## 4. Switch the service to PiEEG-8

The service starts in **16 channel mode** by default. The PiEEG-8 has one ADS1299, so add `--device pieeg8`. This is the official command, run it **once**:

```bash
ssh <username>@tina.local
sudo sed -i 's|bin/pieeg-server|bin/pieeg-server --device pieeg8|' /etc/systemd/system/pieeg-server.service
grep ExecStart /etc/systemd/system/pieeg-server.service      # must contain --device pieeg8 exactly once
sudo systemctl daemon-reload
sudo systemctl restart pieeg-server
```

If you ran it twice and see `--device pieeg8` twice, edit the line by hand: `sudo nano /etc/systemd/system/pieeg-server.service`.

## 5. Check

On the Pi:

```bash
pieeg-server doctor                     # checks Pi model, SPI, GPIO, ports, service
systemctl status pieeg-server           # should say active (running)
journalctl -u pieeg-server -n 30        # last log lines
vcgencmd get_throttled                  # throttled=0x0, see power above
```

Then from the laptop, with the PiEEG-8 mounted:

```bash
cd pieeg-home-lab/code && source .venv/bin/activate
python check_setup.py --noise-test      # every line [ok]
```

Open **http://tina.local:1617** in the browser and click **Connect**. The dashboard must show **8** channels. Sixteen means step 4 didn't apply.

## 6. Test on yourself

Do the [first test](first-test.md) once with your own forehead. Blink, see spikes. If that works, everything works.

## 7. Back up the card

Once everything works, an image of the card saves the whole setup. Shut the Pi down first (`sudo shutdown -h now`, wait until the green LED stops blinking), then put the card in the laptop's reader.

On a Mac:

```bash
diskutil list                             # find the card: external, about 16 GB, e.g. /dev/disk4
diskutil unmountDisk /dev/disk4
sudo dd if=/dev/rdisk4 bs=4m | gzip > ~/pieeg-sd-backup.img.gz
```

Double check the disk number: `dd` only reads here, but the restore writes. On Windows, [Win32 Disk Imager](https://sourceforge.net/projects/win32diskimager/) does the same with its **Read** button: pick a file name and the card's drive letter.

To restore, write the image with Raspberry Pi Imager (**Use custom**). The image contains the WiFi password, keep it private.

## Renaming the Pi

A card flashed with the hostname `raspberrypi` answers to `raspberrypi.local`. To make it `tina.local` without flashing again, over SSH:

```bash
sudo hostnamectl set-hostname tina
sudo sed -i 's/\braspberrypi\b/tina/' /etc/hosts
sudo reboot
```

After the reboot, `ssh jure@tina.local` works and the old name stops answering. The laptop may remember the old host key under the new name; if `ssh` complains, `ssh-keygen -R tina.local` clears it.

## Updating PiEEG Server later

On purpose only, it may change behaviour this repo relies on:

```bash
cd ~/PiEEG-server
git checkout main && git pull
bash setup.sh
```

`setup.sh` writes the service file again, so do step 4 once more. To go back: `git checkout homelab && bash setup.sh`, then step 4.

## Optional: the official Python SDK

PiEEG's original scripts talk to the ADS1299 directly, without the server. Good for learning the registers. Stop the server first, both can't use the SPI bus at the same time.

```bash
sudo systemctl stop pieeg-server
sudo apt install -y python3-venv python3-dev git
python3 -m venv --system-site-packages ~/pieeg-env
source ~/pieeg-env/bin/activate
pip install spidev matplotlib scipy pandas openpyxl RPi.GPIO
git clone https://github.com/pieeg-club/PiEEG-8.git
cd PiEEG-8/1.GUI
python save_data_short_Pi4.py           # the Pi 4 scripts are the right ones for a Pi 3
sudo systemctl start pieeg-server       # when done
```

- The script saves to Excel after 10,000 samples (40 s at 250 Hz). Change that number in the script for longer recordings.
- The live graph scripts (`1.8_ch_Pi4.py`) open a window, so they need a screen on the Pi. Headless, use the `save_data` scripts.
- If `RPi.GPIO` fails with an edge detection error on a recent kernel, install the drop in replacement `pip install rpi-lgpio`, the same fix PiEEG gives for the Pi 5.
- `Permission denied` on SPI or GPIO: `sudo usermod -aG spi,gpio $USER`, then log out and in again.

Source: [PiEEG-8 Software](https://docs.pieeg.com/hardware/devices/pieeg-8/software/).
