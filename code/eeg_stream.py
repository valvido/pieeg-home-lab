"""
Read live EEG samples from PiEEG Server over WebSocket.

PiEEG Server runs on the Raspberry Pi and sends one JSON message per sample:

    {"t": 1711234567.123, "n": 42, "channels": [12.34, -5.67, ...]}

    t         Unix time in seconds
    n         sample number from the server, counts up by 1 for every sample the board made
    channels  microvolts, one value per channel (8 for PiEEG-8)

Right after connecting, the server sends a welcome message with its settings:

    {"status": "connected", "sample_rate": 250, "channels": 8,
     "filter": true, "notch_filter": false, "notch_freq": 60.0, ...}

"filter" and "notch_filter" matter. PiEEG Server filters the data it sends to EVERY
client, and its 1 to 40 Hz bandpass is on by default. With raw=True, EEGStream switches
the server filters off, checks every few seconds that they stay off (the server doesn't
announce changes, so it reads a fresh welcome message on a second connection), and
switches them back on in stop().

If the connection drops (WiFi, server restart), EEGStream reconnects by itself and
writes what happened to .events.

Usage:
    from eeg_stream import stream_samples
    for t, n, uv in stream_samples("tina.local"):
        print(n, uv[0])
"""

import asyncio
import json
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import websockets

DEFAULT_HOST = "tina.local"
DEFAULT_PORT = 1616
SAMPLE_RATE = 250               # Hz, PiEEG default
SERVER_BANDPASS = (1.0, 40.0)   # PiEEG Server's default bandpass, what stop() switches back on
SILENCE_TIMEOUT = 3.0           # s without any message: the connection is treated as dead
SETTLE_S = 0.5                  # s of samples dropped after switching the server filters off


@dataclass
class Sample:
    t: float
    n: int
    uv: list


@dataclass
class ServerFilters:
    """Filter state from a welcome message. None means the server didn't say."""
    bandpass: bool | None
    notch: bool | None
    notch_freq: float | None

    @classmethod
    def from_welcome(cls, w: dict) -> "ServerFilters":
        def flag(key):
            v = w.get(key)
            return v if isinstance(v, bool) else None
        f = w.get("notch_freq")
        return cls(flag("filter"), flag("notch_filter"),
                   float(f) if isinstance(f, (int, float)) and not isinstance(f, bool) else None)

    def any_on(self) -> bool:
        return bool(self.bandpass) or bool(self.notch)

    def unknown(self) -> bool:
        return self.bandpass is None or self.notch is None

    def describe(self) -> str:
        def word(v):
            return "unknown" if v is None else ("on" if v else "off")
        notch = word(self.notch)
        if self.notch and self.notch_freq:
            notch += f" at {self.notch_freq:g} Hz"
        return f"bandpass {word(self.bandpass)}, notch {notch}"


def parse_message(raw: str):
    """Return a Sample for a data frame, None for anything else."""
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(msg, dict):
        return None
    ch = msg.get("channels")
    if "n" not in msg or not isinstance(ch, list):
        return None  # the welcome message has "channels": 8, an int
    try:
        return Sample(t=float(msg.get("t", 0.0)), n=int(msg["n"]), uv=[float(v) for v in ch])
    except (TypeError, ValueError):
        return None


def parse_welcome(raw: str):
    """Return the server's welcome dict ({"status": "connected", "channels": 8, ...}) or None."""
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(msg, dict) and msg.get("status") == "connected":
        return msg
    return None


class EEGStream:
    """Background reader. Call .get_new() to drain the samples received so far.

    raw=True      make sure the samples are unfiltered (see the module docstring)
    check_every   seconds between checks of the server filter state, only with raw=True
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 raw: bool = False, check_every: float = 5.0):
        self.url = f"ws://{host}:{port}"
        self.raw = raw
        self.check_every = check_every if raw else None
        self.server_info: dict = {}      # the latest welcome message: sample_rate, channels, filter, ...
        self.filters_at_start = None     # ServerFilters from the first welcome message
        self.events: list = []           # what happened, with wall clock time and the last sample number
        self.possibly_filtered: list = []  # [first_n, last_n] ranges that may hold filtered samples
        self.discarded = 0               # samples dropped while the server filters settled
        self.samples_received = 0        # data frames received, all connections together
        self.ever_connected = False
        self.last_error = None           # why the last connection attempt failed or ended
        self.error = None                # unexpected failure of the reader itself
        self._q: "queue.Queue[Sample]" = queue.Queue()
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._last_n = None
        self._last_clean_n = None
        self._settle_until = 0.0
        self._switched_off = False
        self._need_off = False
        self._next_check = 0.0

    # ---- public ---------------------------------------------------------

    def start(self):
        self._thread.start()
        return self

    def stop(self, timeout: float = 5.0):
        """Stop reading. With raw=True this also switches the server filters back on."""
        self._stop.set()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout)

    def wait_connected(self, timeout: float) -> bool:
        """True once the server's welcome message has arrived."""
        return self._connected.wait(timeout)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def get_new(self):
        items = []
        while True:
            try:
                items.append(self._q.get_nowait())
            except queue.Empty:
                return items

    def channel_warning(self):
        """Text to show if the server runs in 16 channel mode instead of PiEEG-8 mode."""
        n = self.server_info.get("channels")
        if isinstance(n, int) and n != 8:
            return (f"Server reports {n} channels. For the PiEEG-8, start it with --device pieeg8 "
                    "(docs/setup-raspberry-pi.md, step 4).")
        return None

    # ---- internals ------------------------------------------------------

    def _log(self, event: str, detail: str = ""):
        self.events.append({"time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                            "last_n": self._last_n, "event": event, "detail": detail})

    def _run(self):
        try:
            asyncio.run(self._main())
        except Exception as e:  # shown to the user by the calling script
            self.error = e

    async def _sleep(self, seconds: float):
        end = time.monotonic() + seconds
        while not self._stop.is_set() and time.monotonic() < end:
            await asyncio.sleep(0.05)

    async def _main(self):
        delay = 0.5
        while not self._stop.is_set():
            try:
                async with websockets.connect(self.url, max_queue=4096, open_timeout=5) as ws:
                    await self._session(ws)
                    if self._connected.is_set():
                        delay = 0.5   # this connection worked, so retry quickly
                    if self._stop.is_set():
                        await self._restore(ws)
                        return
            except (OSError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as e:
                self.last_error = f"{type(e).__name__}: {e}"
            finally:
                if self._connected.is_set():
                    self._connected.clear()
                    if not self._stop.is_set():
                        self._log("disconnected", self.last_error or "connection closed")
            await self._sleep(delay)
            delay = min(delay * 2, 5.0)
        await self._restore(None)  # stopped while disconnected

    async def _session(self, ws):
        last_msg = time.monotonic()
        got_frame = False
        probe = None
        try:
            while not self._stop.is_set():
                if self._need_off:
                    self._need_off = False
                    await self._switch_off(ws, "found on during the recording")
                if (self.check_every and self._connected.is_set()
                        and time.monotonic() >= self._next_check
                        and (probe is None or probe.done())):
                    self._next_check = time.monotonic() + self.check_every
                    probe = asyncio.create_task(self._probe())
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    if time.monotonic() - last_msg > SILENCE_TIMEOUT:
                        # The server answered but sends nothing: no board, or the WiFi is gone
                        self.last_error = (f"no data for {SILENCE_TIMEOUT:g} s" if got_frame
                                           else "the server answers but sends no samples")
                        return
                    continue
                last_msg = time.monotonic()
                s = parse_message(raw)
                if s is not None:
                    got_frame = True
                    self.samples_received += 1
                    self._last_n = s.n
                    if time.monotonic() < self._settle_until:
                        self.discarded += 1
                        continue
                    self._q.put(s)
                    continue
                w = parse_welcome(raw)
                if w is not None:
                    await self._on_welcome(ws, w)
        finally:
            if probe is not None and not probe.done():
                probe.cancel()

    async def _on_welcome(self, ws, w: dict):
        self.server_info.clear()
        self.server_info.update(w)
        state = ServerFilters.from_welcome(w)
        if not self.ever_connected:
            self.ever_connected = True
            self.filters_at_start = state
            self._log("connected", f"server filters: {state.describe()}")
        else:
            self._log("reconnected", f"server filters: {state.describe()}")
        self._connected.set()
        self.last_error = None
        if self.raw and (state.any_on() or state.unknown()):
            await self._switch_off(ws, "they were on" if state.any_on() else "their state was unknown")
        self._next_check = time.monotonic() + (self.check_every or 0)

    async def _switch_off(self, ws, why: str):
        await ws.send(json.dumps({"cmd": "set_filter", "enabled": False}))
        await ws.send(json.dumps({"cmd": "set_notch", "enabled": False}))
        self._switched_off = True
        self._settle_until = time.monotonic() + SETTLE_S
        if self.possibly_filtered and self.possibly_filtered[-1][1] is None:
            self.possibly_filtered[-1][1] = self._last_n
        self._log("server filters switched off", why)

    async def _probe(self):
        """Read a fresh welcome message: PiEEG Server doesn't announce filter changes."""
        try:
            async with websockets.connect(self.url, open_timeout=3, max_queue=16) as p:
                w = parse_welcome(await asyncio.wait_for(p.recv(), timeout=3))
        except Exception:
            return  # best effort, the next check tries again
        if w is None:
            return
        state = ServerFilters.from_welcome(w)
        if state.any_on():
            self.possibly_filtered.append([self._last_clean_n, None])
            since = "the start" if self._last_clean_n is None else f"n={self._last_clean_n}"
            self._log("server filters found on",
                      f"{state.describe()}, another client switched them on. Samples after "
                      f"{since} up to the next switch off may be filtered")
            self._need_off = True
        else:
            self._last_clean_n = self._last_n

    async def _restore(self, ws):
        st = self.filters_at_start
        if not (self.raw and self._switched_off) or st is None:
            return
        self._switched_off = False
        if not st.any_on():
            if st.unknown():
                self._log("server filters not restored", "their state at the start was unknown")
            return
        cmds = []
        if st.bandpass:
            lo, hi = SERVER_BANDPASS
            cmds.append({"cmd": "set_filter", "enabled": True, "lowcut": lo, "highcut": hi})
        if st.notch:
            cmds.append({"cmd": "set_notch", "enabled": True, "freq": st.notch_freq or 50.0})
        try:
            if ws is None:
                async with websockets.connect(self.url, open_timeout=3) as fresh:
                    for c in cmds:
                        await fresh.send(json.dumps(c))
            else:
                for c in cmds:
                    await ws.send(json.dumps(c))
            restored = ServerFilters(st.bandpass, st.notch, st.notch_freq).describe()
            if st.bandpass:
                restored = restored.replace("bandpass on", f"bandpass on {SERVER_BANDPASS[0]:g} to "
                                                           f"{SERVER_BANDPASS[1]:g} Hz")
            self._log("server filters switched back on", restored)
        except Exception as e:
            self._log("could not switch the server filters back on", f"{type(e).__name__}: {e}")


def stream_samples(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Simple blocking generator of (t, n, uv) tuples."""
    s = EEGStream(host, port).start()
    try:
        while True:
            for x in s.get_new():
                yield x.t, x.n, x.uv
            if s.error:
                raise s.error
            threading.Event().wait(0.02)
    finally:
        s.stop()
