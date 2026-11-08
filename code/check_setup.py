"""
Check the whole chain from your laptop to the PiEEG-8 in about 10 seconds.

    python check_setup.py                        # Pi on tina.local
    python check_setup.py --host 192.168.1.50   # or its IP address
    python check_setup.py --noise-test           # also the board noise test (never during a recording)
    python check_setup.py --markdown check.md    # also save the results as a table

Read only: it changes nothing on the Pi. Only --noise-test shorts the board's inputs
for a few seconds, like self_test.py.

What it checks, in order:
  1. The Pi's name resolves to an address
  2. PiEEG Server answers on port 1616, and which version runs
  3. The dashboard answers on port 1617
  4. The welcome message: 8 channels, 250 Hz, real hardware (not mock mode)
  5. Samples arrive, about 250 per second: the board is mounted and talking
  6. With --noise-test: inputs shorted, every channel under 5 µV RMS

Works on macOS, Windows and Linux.
"""

import argparse
import asyncio
import json
import platform
import socket
import sys
import time
import urllib.request
from datetime import datetime

import websockets

from eeg_stream import DEFAULT_PORT, SAMPLE_RATE, ServerFilters, parse_message, parse_welcome
from self_test import judge, run as run_noise_test

PINNED_VERSION = "0.49.0"     # the PiEEG Server version docs/setup-raspberry-pi.md installs
DASHBOARD_PORT = 1617
LISTEN_S = 3.0
OK, WARN, FAIL = "ok", "warn", "FAIL"
MARK = {OK: "✅", WARN: "⚠️", FAIL: "❌"}


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status: str, check: str, detail: str):
        self.rows.append((status, check, detail))
        print(f"  [{status}] {check}: {detail}")

    def failed(self):
        return [r for r in self.rows if r[0] == FAIL]

    def markdown(self, host: str) -> str:
        when = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"Setup check, {when}, from a {platform.system()} laptop to `{host}`:", "",
                 "| | Check | Result |", "|---|---|---|"]
        lines += [f"| {MARK[s]} | {c} | {d.replace('|', '/')} |" for s, c, d in self.rows]
        return "\n".join(lines) + "\n"


def http_get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


async def listen(url: str, seconds: float):
    """The welcome message and every data frame that arrives within `seconds`."""
    frames = []
    async with websockets.connect(url, open_timeout=8, max_queue=None) as ws:
        welcome = parse_welcome(await asyncio.wait_for(ws.recv(), timeout=8))
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=left)
            except asyncio.TimeoutError:
                break
            s = parse_message(raw)
            if s is not None:
                frames.append(s)
    return welcome, frames


def check(a, rep: Report) -> bool:
    """Run the checks. True if samples arrived (the board talks)."""
    try:
        ip = socket.getaddrinfo(a.host, a.port, proto=socket.IPPROTO_TCP)[0][4][0]
        rep.add(OK, "Address", f"{a.host} is {ip}")
    except socket.gaierror as e:
        rep.add(FAIL, "Address", f"{a.host} not found ({e}). Is the Pi on and in the same WiFi? "
                                 "Try its IP address, see docs/troubleshooting.md")
        return False

    try:
        socket.create_connection((a.host, a.port), timeout=5).close()
    except OSError as e:
        rep.add(FAIL, "PiEEG Server", f"nothing answers on port {a.port} ({e}). Pi still booting? "
                                      "Otherwise ssh in and run: systemctl status pieeg-server")
        return False
    try:
        version = json.loads(http_get(f"http://{a.host}:{a.port}/api/info")[1]).get("version")
        if version == PINNED_VERSION:
            rep.add(OK, "PiEEG Server", f"version {version}, the version this repo was checked against")
        else:
            rep.add(WARN, "PiEEG Server", f"version {version}, this repo was checked against {PINNED_VERSION}")
    except Exception:
        rep.add(WARN, "PiEEG Server", "answers, but didn't report its version")

    try:
        status, _ = http_get(f"http://{a.host}:{a.dashboard_port}/")
        rep.add(OK if status == 200 else WARN, "Dashboard", f"http://{a.host}:{a.dashboard_port} answers")
    except Exception as e:
        rep.add(FAIL, "Dashboard", f"http://{a.host}:{a.dashboard_port} doesn't answer ({type(e).__name__})")

    try:
        welcome, frames = asyncio.run(listen(f"ws://{a.host}:{a.port}", LISTEN_S))
    except Exception as e:
        rep.add(FAIL, "Stream", f"the WebSocket connection failed ({type(e).__name__}: {e})")
        return False
    if welcome is None:
        rep.add(FAIL, "Stream", "the server didn't start with its welcome message")
        return False

    ch, rate, mock = welcome.get("channels"), welcome.get("sample_rate"), welcome.get("mock")
    if ch == 8:
        rep.add(OK, "Channels", "8, PiEEG-8 mode")
    else:
        rep.add(FAIL, "Channels", f"{ch}: the service needs --device pieeg8 (docs/setup-raspberry-pi.md, step 4)")
    rep.add(OK if rate == SAMPLE_RATE else WARN, "Sample rate", f"{rate} Hz")
    if mock is False:
        rep.add(OK, "Hardware mode", "real board, not mock mode")
    elif mock is True:
        rep.add(FAIL, "Hardware mode", "MOCK: the server makes up its data (started with --mock?)")
    else:
        rep.add(WARN, "Hardware mode", "not reported")
    rep.add(OK, "Server filters", f"{ServerFilters.from_welcome(welcome).describe()} "
                                  "(for viewing; record.py switches them off while it records)")

    if not frames:
        rep.add(FAIL, "Samples", f"none in {LISTEN_S:g} s. The server runs, but no data comes from the board. "
                                 "Is the PiEEG-8 mounted and pressed onto all 40 pins? "
                                 "(docs/troubleshooting.md, 'No samples from the board')")
        return False
    per_s = len(frames) / LISTEN_S
    gaps = sum(1 for x, y in zip(frames, frames[1:]) if y.n - x.n != 1)
    sizes = sorted({len(f.uv) for f in frames})
    good = 0.8 * SAMPLE_RATE <= per_s <= 1.2 * SAMPLE_RATE and gaps == 0
    rep.add(OK if good else WARN, "Samples",
            f"{len(frames)} in {LISTEN_S:g} s (about {per_s:.0f} per second), {gaps} gaps, "
            f"{'/'.join(map(str, sizes))} values each")
    stuck = [i + 1 for i in range(min(sizes)) if len({f.uv[i] for f in frames}) == 1]
    if stuck:
        rep.add(WARN, "Values", f"channel(s) {stuck} never change. Board seated? Electrodes connected?")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="tina.local")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--dashboard-port", type=int, default=DASHBOARD_PORT)
    p.add_argument("--noise-test", action="store_true",
                   help="also run the board noise test (shorts the inputs for about 4 s)")
    p.add_argument("--markdown", help="also write the results as a Markdown table to this file")
    a = p.parse_args()

    print(f"Checking the PiEEG setup at {a.host} ...")
    rep = Report()
    board_talks = check(a, rep)
    if a.noise_test:
        if not board_talks and rep.failed():
            rep.add(WARN, "Noise test", "skipped, fix the problems above first")
        else:
            try:
                r = asyncio.run(run_noise_test(a.host, a.port, 3, quiet=True))
                verdict, problem = judge(r)
                worst = max([float(v) for v in r.get("rms", [])] or [0.0])
                status = FAIL if problem else (WARN if worst >= 5 else OK)
                rep.add(status, "Noise test", verdict)
            except (Exception, SystemExit) as e:
                rep.add(FAIL, "Noise test", f"didn't run ({e})")

    print()
    failed = rep.failed()
    if failed:
        print(f"{len(failed)} problem(s). Start with the first one, the others often follow from it.")
    elif any(s == WARN for s, _, _ in rep.rows):
        print("Works, with warnings above.")
    else:
        print("All good: laptop, WiFi, Pi, PiEEG Server and board work together.")
        if not a.noise_test:
            print("With a new or freshly mounted board, run it once more with --noise-test.")
    if a.markdown:
        with open(a.markdown, "w", encoding="utf-8") as fh:
            fh.write(rep.markdown(a.host))
        print(f"Saved the results to {a.markdown}")
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # older Windows consoles can't print every symbol
    sys.exit(main())
