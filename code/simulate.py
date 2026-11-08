"""
Fake PiEEG Server for testing without hardware.

Behaves like PiEEG Server where it matters for this repo:
  - one stream for all clients, the sample number n keeps counting across reconnections
  - the welcome message with sample rate, channel count and filter state
  - server side filters that change the data for EVERY client, like the real server:
    bandpass 1 to 40 Hz ON by default, notch OFF, switched with
    {"cmd": "set_filter", "enabled": ...} and {"cmd": "set_notch", "enabled": ..., "freq": 50}
  - the noise self test {"cmd": "noise_test"}: for a few seconds every client gets
    the shorted input signal, exactly why you don't run self_test.py during a recording

The signal: an alpha rhythm (10 Hz) that gets stronger every other 10 seconds
("eyes closed"), blinks on channels 1 and 2, 50 Hz mains hum, slow drift and noise.

    python simulate.py
    python live_view.py --host localhost      # in a second Terminal tab

Test hooks, used by tests/: {"cmd": "sim_outage", "seconds": 4} stops all traffic like a
WiFi drop, {"cmd": "sim_restart"} closes every connection and resets the server like
a restart of the pieeg-server service, {"cmd": "sim_board", "present": false} behaves like
the real server without a PiEEG-8: welcome message, but no samples, and a noise test
that reports "Device OK" with zero samples.
"""

import argparse
import asyncio
import json
import math
import random
import time

import numpy as np
import websockets
from scipy import signal

FS = 250
N_CH = 8


def make_sample(n: int, rng: random.Random):
    t = n / FS
    eyes_closed = int(t // 10) % 2 == 1
    alpha_amp = 25.0 if eyes_closed else 6.0
    blink = 0.0
    phase = t % 4.0
    if not eyes_closed and 1.0 < phase < 1.25:
        blink = 150.0 * math.sin(math.pi * (phase - 1.0) / 0.25)
    out = []
    for ch in range(N_CH):
        wax = 0.65 + 0.35 * math.sin(2 * math.pi * 0.35 * t + ch)  # alpha waxes and wanes
        v = alpha_amp * wax * math.sin(2 * math.pi * 10.0 * t + ch * 0.3)
        v += 12.0 * math.sin(2 * math.pi * 50.0 * t)          # mains hum
        v += 8.0 * math.sin(2 * math.pi * 0.2 * t + ch)        # slow drift
        v += rng.gauss(0, 4.0)
        if ch < 2:
            v += blink                                         # Fp1, Fp2
        out.append(v)
    return out


class LiveFilter:
    """Causal filter with memory, applied sample by sample like PiEEG Server does."""

    def __init__(self, sos):
        self.sos = sos
        self.zi = np.zeros((sos.shape[0], 2, N_CH))

    def apply(self, x):
        y, self.zi = signal.sosfilt(self.sos, np.asarray(x, dtype=float)[None, :], axis=0, zi=self.zi)
        return y[0]


class FakeServer:
    def __init__(self):
        self.clients = set()
        self.rng = random.Random(1)
        self.n = 0
        self.outage_until = 0.0
        self.shorted_until = 0.0
        self.board = True
        self.reset()

    def reset(self):
        """Server defaults: bandpass on, notch off (as in PiEEG Server's PiEEGServer.__init__)."""
        self.set_filter(True)
        self.notch = None
        self.notch_freq = 60.0

    def set_filter(self, enabled, lowcut=1.0, highcut=40.0):
        if not enabled:
            self.bandpass = None
        elif 0 < lowcut < highcut < FS / 2:      # out of range: ignored, like the real server
            self.bandpass = LiveFilter(signal.butter(5, [lowcut, highcut], btype="band", fs=FS, output="sos"))

    def set_notch(self, enabled, freq=60.0, q=30.0):
        if not enabled:
            self.notch = None
        elif 1 <= freq < FS / 2 and 1 <= q <= 1000:
            b, a = signal.iirnotch(freq, q, fs=FS)
            self.notch, self.notch_freq = LiveFilter(signal.tf2sos(b, a)), freq

    def welcome(self):
        return {"status": "connected", "sample_rate": FS, "channels": N_CH,
                "filter": self.bandpass is not None, "notch_filter": self.notch is not None,
                "notch_freq": self.notch_freq if self.notch else 60.0,
                "mock": True, "simulated": True}

    async def handler(self, ws):
        while time.monotonic() < self.outage_until:
            await asyncio.sleep(0.1)          # a dead network: no welcome, no data
        self.clients.add(ws)
        try:
            await ws.send(json.dumps(self.welcome()))
            async for raw in ws:
                await self.command(ws, raw)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)

    async def command(self, ws, raw):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(msg, dict):
            return
        cmd = msg.get("cmd")
        try:
            if cmd == "set_filter":
                self.set_filter(msg.get("enabled", True), float(msg.get("lowcut", 1.0)),
                                float(msg.get("highcut", 40.0)))
            elif cmd == "set_notch":
                self.set_notch(msg.get("enabled", True), float(msg.get("freq", 60.0)),
                               float(msg.get("q", 30.0)))
            elif cmd == "noise_test":
                await self.noise_test(ws, msg)
            elif cmd == "sim_outage":
                self.outage_until = time.monotonic() + float(msg.get("seconds", 4))
            elif cmd == "sim_restart":
                self.reset()
                self.n = 0
                for c in list(self.clients):
                    await c.close(1012, "simulated restart")
            elif cmd == "sim_board":
                self.board = bool(msg.get("present", True))
        except (TypeError, ValueError):
            pass

    async def noise_test(self, ws, msg):
        duration = min(max(float(msg.get("duration", 3)), 1), 10)
        await ws.send(json.dumps({"noise_test_status": "running"}))
        if self.board:
            self.shorted_until = time.monotonic() + duration + 0.5
            await asyncio.sleep(duration + 0.5)
            rms = [round(random.uniform(0.6, 1.6), 2) for _ in range(N_CH)]
            collected = int(duration * FS)
        else:
            rms, collected = [0.0] * N_CH, 0        # what the real server reports without a board
        await ws.send(json.dumps({"noise_test_result": {
            "rms": rms, "max_rms": max(rms),
            "verdict": "Device OK. Internal noise within spec. (simulated)",
            "recommendation": "This is the simulator, not real hardware.",
            "duration": duration, "samples_collected": collected}}))

    async def produce(self):
        start, k = time.monotonic(), 0
        while True:
            k += 1
            delay = start + k / FS - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            if not self.board:
                continue                      # no chip, no DRDY, no samples
            self.n += 1
            now = time.monotonic()
            if now < self.shorted_until:
                x = [self.rng.gauss(0, 1.0) for _ in range(N_CH)]   # inputs shorted inside the chip
            else:
                x = make_sample(self.n, self.rng)
            if self.bandpass:
                x = self.bandpass.apply(x)
            if self.notch:
                x = self.notch.apply(x)
            if now < self.outage_until or not self.clients:
                continue
            frame = json.dumps({"t": round(time.time(), 6), "n": self.n,
                                "channels": [round(float(v), 2) for v in x]})
            for c in list(self.clients):
                try:
                    await c.send(frame)
                except websockets.exceptions.ConnectionClosed:
                    self.clients.discard(c)


async def main(port: int, host: str):
    server = FakeServer()
    async with websockets.serve(server.handler, host, port):
        print(f"Simulated PiEEG streaming on ws://{host}:{port}  (Ctrl+C to stop)")
        await server.produce()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=1616)
    p.add_argument("--bind", default="127.0.0.1", help="use 0.0.0.0 to reach it from other devices")
    a = p.parse_args()
    try:
        asyncio.run(main(a.port, a.bind))
    except KeyboardInterrupt:
        pass
