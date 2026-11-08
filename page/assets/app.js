/* PiEEG Home Lab page. No dependencies. Live websocket, sample fallback, one canvas. */
(function () {
  "use strict";

  var SR = 250;                 // server sample rate
  var WINDOW_S = 4;             // seconds on screen
  var MAX = SR * WINDOW_S;
  var CH = 8;
  var LABELS = ["CH1 Fp1", "CH2 Fp2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"];
  var RANGE = 80;               // microvolts, half height of a lane

  /* ---------------- state ---------------- */

  var buf = [];
  for (var i = 0; i < CH; i++) buf.push(new Float32Array(MAX));
  var head = 0;                 // next write index
  var filled = 0;               // how many valid samples
  var mode = "connecting";      // connecting | live | sample
  var sample = null;            // parsed sample.json
  var playStart = 0;            // performance.now when playback began
  var playNext = 0;             // next sample index to push
  var ws = null;

  var badge = document.getElementById("badge");
  var badgeLabel = document.getElementById("badge-label");
  var note = document.getElementById("signal-note");
  var demoNote = document.getElementById("demo-note");

  function setMode(next, why) {
    mode = next;
    badge.className = "badge " + (next === "live" ? "live" : (next === "waiting" ? "waiting" : "sample"));
    badge.dataset.state = next;
    badgeLabel.textContent = next === "live" ? "Live from the Pi"
      : (next === "waiting" ? "Connected, no data yet"
      : (next === "sample" ? "Sample, not live" : "Connecting"));
    if (note) {
      note.textContent = next === "live"
        ? "The last four seconds of your own signal, all eight channels, in microvolts."
        : (next === "waiting"
          ? "The socket to the Pi is open, but no samples are arriving. With no shield mounted the server has nothing to read. Fit the PiEEG-8, or run it with --mock to watch the page move."
          : (next === "sample"
            ? "A six second simulated recording, so the page still works with the Pi switched off. Not your head."
            : "Looking for the Pi on ws://" + hostName() + ":1616"));
    }
    if (why && window.console) console.info("signal mode:", next, why);
  }

  function hostName() {
    if (location.protocol === "http:" && location.hostname) return location.hostname;
    return "tina.local";
  }

  function push(channels) {
    for (var c = 0; c < CH; c++) {
      var v = channels[c];
      buf[c][head] = (typeof v === "number" && isFinite(v)) ? v : 0;
    }
    head = (head + 1) % MAX;
    if (filled < MAX) filled++;
  }

  function at(c, age) {           // age 0 = newest
    var idx = (head - 1 - age + MAX * 2) % MAX;
    return buf[c][idx];
  }

  function laneMean(c, n) {       // mean of the newest n samples of one channel
    var sum = 0;
    for (var k = 0; k < n; k++) sum += at(c, k);
    return n ? sum / n : 0;
  }

  /* ---------------- transport ---------------- */

  // The Pi restarts, the WiFi drops, pieeg-server gets restarted: the socket closes.
  // The page then shows the sample and tries again, first after 2 s, then 4, 8, up to 15 s,
  // for as long as the page is open. Nothing to click.
  var RETRY_MIN_MS = 2000;
  var RETRY_MAX_MS = 15000;
  var retryDelay = RETRY_MIN_MS;
  var retryTimer = null;
  var canRetry = true;

  function scheduleRetry(reason) {
    if (!canRetry || retryTimer) return;
    retryTimer = setTimeout(function () {
      retryTimer = null;
      tryLive();
    }, retryDelay);
    if (window.console) console.info("next connection attempt in " + (retryDelay / 1000) + " s (" + reason + ")");
    retryDelay = Math.min(retryDelay * 2, RETRY_MAX_MS);
  }

  function tryLive() {
    if (location.protocol === "https:") {
      canRetry = false;
      loadSample("https page cannot open a plain websocket");
      return;
    }
    var host = hostName();
    var local = host === "127.0.0.1" || host === "localhost" || host === "::1";
    var forced = /[?&]live=1/.test(location.search);
    if (local && !forced) {
      // served from a dev machine: do not fire a doomed request, it only pollutes the console
      canRetry = false;
      loadSample("page is not being served by the Pi, add ?live=1 to force a connection attempt");
      return;
    }
    var url = "ws://" + host + ":1616";
    var settled = false;
    var sock;

    var timer = setTimeout(function () {
      if (settled) return;
      settled = true;
      try { sock.close(); } catch (e) {}
      loadSample("no answer from " + url + " within 2.5s");
      scheduleRetry("timeout");
    }, 2500);

    try {
      sock = new WebSocket(url);
    } catch (e) {
      clearTimeout(timer);
      loadSample("websocket refused to open");
      scheduleRetry("refused");
      return;
    }
    ws = sock;

    sock.onopen = function () {
      if (sock !== ws) { try { sock.close(); } catch (e) {} return; }
      if (settled) { try { sock.close(); } catch (e) {} return; }
      settled = true;
      clearTimeout(timer);
      setMode("waiting");
    };

    sock.onmessage = function (ev) {
      if (sock !== ws || typeof ev.data !== "string") return;
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg && msg.channels && msg.channels.length === CH) {
        push(msg.channels);
        if (mode !== "live") {
          setMode("live");
          retryDelay = RETRY_MIN_MS;   // this connection worked, so the next retry can be quick
        }
      }
    };

    sock.onerror = function () { /* onclose handles the fallback */ };

    sock.onclose = function () {
      if (sock !== ws) return;         // an old socket, already replaced
      clearTimeout(timer);
      if (!settled) {
        settled = true;
        loadSample("socket closed before it opened");
      } else {
        // live or waiting: either way the Pi is gone for now
        loadSample(mode === "live" ? "socket closed" : "socket closed while waiting for samples");
      }
      scheduleRetry("closed");
    };
  }

  function loadSample(reason) {
    setMode("sample", reason);
    if (sample) return;
    fetch("assets/sample.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        sample = data;
        playStart = performance.now();
      })
      .catch(function () {
        if (window.console) console.warn("sample.json missing, nothing to draw");
      });
  }

  function playback(now) {
    if (!sample || mode !== "sample") return;
    var len = sample.data[0].length;
    var want = Math.floor(((now - playStart) / 1000) * SR);
    if (want - playNext > SR) playNext = want - SR;   // tab was hidden, do not flood
    while (playNext <= want) {
      var i = playNext % len;
      var frame = [];
      for (var c = 0; c < CH; c++) frame.push(sample.data[c][i]);
      push(frame);
      playNext++;
    }
  }

  /* ---------------- canvas ---------------- */

  var canvas = document.getElementById("traces");
  var ctx = canvas.getContext("2d");
  var cssW = 0, cssH = 0, dpr = 1;

  function sizeCanvas() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    var rect = canvas.getBoundingClientRect();
    cssW = Math.max(280, Math.round(rect.width));
    cssH = Math.max(240, Math.round(rect.height));
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  var css = getComputedStyle(document.documentElement);
  function colour(name, fallback) {
    var v = css.getPropertyValue(name);
    return (v && v.trim()) || fallback;
  }
  var INK = colour("--fg", "#ffffff");
  var MUTED = colour("--muted", "rgba(255,255,255,0.56)");
  var HAIR = colour("--hair", "rgba(255,255,255,0.12)");
  var ACCENT = colour("--e1", "#4b4bff");          // CH1 is E1, drawn in its lead color
  var PAPER = colour("--bg", "#0b0d33");

  var labelW = 74;

  function draw() {
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = PAPER;
    ctx.fillRect(0, 0, cssW, cssH);

    var laneH = cssH / CH;
    var plotW = cssW - labelW - 8;

    ctx.font = "12px " + (css.getPropertyValue("--mono") || "monospace");
    ctx.textBaseline = "middle";

    for (var lane = 0; lane < CH; lane++) {
      var midY = laneH * (lane + 0.5);

      // lane rule
      ctx.strokeStyle = HAIR;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(labelW, Math.round(midY) + 0.5);
      ctx.lineTo(cssW - 8, Math.round(midY) + 0.5);
      ctx.stroke();

      // label
      ctx.fillStyle = MUTED;
      ctx.fillText(LABELS[lane], 0, midY);

      if (filled < 2) continue;

      var n = Math.min(filled, MAX);
      var px = plotW / n;

      // Each electrode sits at its own DC offset, often millivolts, far outside the lane.
      // Only the wiggle matters, so the lane is centred on the mean of what is on screen.
      var mean = laneMean(lane, n);

      ctx.strokeStyle = (lane === 0) ? ACCENT : MUTED;
      ctx.lineWidth = 1.15;
      ctx.beginPath();
      for (var k = 0; k < n; k++) {
        var age = n - 1 - k;
        var v = at(lane, age) - mean;
        var y = midY - (v / RANGE) * (laneH * 0.42);
        if (y < midY - laneH * 0.5) y = midY - laneH * 0.5;    // clip to the lane instead of
        if (y > midY + laneH * 0.5) y = midY + laneH * 0.5;    // drawing over the neighbours
        var x = labelW + 8 + k * px;
        if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  /* ---------------- band power (for the demo readout) ---------------- */

  function goertzel(channel, freq) {
    var n = Math.min(filled, SR * 2);
    if (n < SR) return 0;
    var mean = laneMean(channel, n);   // the DC offset of the electrode is not a brain rhythm
    var w = 2 * Math.PI * (freq / SR);
    var coeff = 2 * Math.cos(w);
    var s0 = 0, s1 = 0, s2 = 0;
    for (var k = 0; k < n; k++) {
      var v = at(channel, n - 1 - k) - mean;
      s0 = v + coeff * s1 - s2;
      s2 = s1;
      s1 = s0;
    }
    var power = (s1 * s1 + s2 * s2 - coeff * s1 * s2) / (n * n);
    return Math.sqrt(Math.max(0, power));
  }

  var demo = "none";             // none | eyes | math
  var shown = { focus: 0, relax: 0 };
  var focusEl = document.getElementById("score-focus");
  var relaxEl = document.getElementById("score-relax");

  function updateScores() {
    var target;
    if (demo === "eyes") target = { focus: 0.14, relax: 0.72 };
    else if (demo === "math") target = { focus: 0.70, relax: 0.12 };
    else {
      // real readout from CH1 (Fp1), the one channel of the start montage
      var alpha = goertzel(0, 10);
      var beta = goertzel(0, 20);
      target = {
        focus: Math.max(0.02, Math.min(0.95, beta / 6)),
        relax: Math.max(0.02, Math.min(0.95, alpha / 12))
      };
    }
    shown.focus += (target.focus - shown.focus) * 0.08;
    shown.relax += (target.relax - shown.relax) * 0.08;
    focusEl.textContent = shown.focus.toFixed(2);
    relaxEl.textContent = shown.relax.toFixed(2);

    if (demoNote) {
      demoNote.textContent = demo === "none"
        ? (mode === "live" ? "Computed from your live signal right now." : "Computed from the sample.")
        : "Simulated response, to show the shape of the effect. Release to go back to the real readout.";
    }
  }

  function wireDemo() {
    var eyes = document.getElementById("demo-eyes");
    var math = document.getElementById("demo-math");
    if (!eyes || !math) return;

    function set(which, on) {
      demo = on ? which : "none";
      eyes.setAttribute("aria-pressed", String(demo === "eyes"));
      math.setAttribute("aria-pressed", String(demo === "math"));
    }

    eyes.addEventListener("pointerdown", function () { set("eyes", true); });
    math.addEventListener("pointerdown", function () { set("math", true); });
    ["pointerup", "pointerleave", "pointercancel"].forEach(function (ev) {
      eyes.addEventListener(ev, function () { set("eyes", false); });
      math.addEventListener(ev, function () { set("math", false); });
    });
    // keyboard and click fallback: toggle
    eyes.addEventListener("click", function () { set("eyes", demo !== "eyes"); });
    math.addEventListener("click", function () { set("math", demo !== "math"); });
  }

  /* ---------------- checklist ---------------- */

  var KIT_KEY = "tina-kit-v2";

  function readKit() {
    try { return JSON.parse(localStorage.getItem(KIT_KEY) || "{}"); }
    catch (e) { return {}; }
  }

  function wireKit() {
    var list = document.getElementById("kit");
    var count = document.getElementById("kit-count");
    var reset = document.getElementById("kit-reset");
    if (!list || !count) return;

    var saved = readKit();
    var boxes = list.querySelectorAll("input[type=checkbox]");

    function sync() {
      var on = 0;
      Array.prototype.forEach.call(boxes, function (box) {
        var li = box.closest("li");
        if (li) li.classList.toggle("done", box.checked);
        if (box.checked) on++;
      });
      count.textContent = on + " of 8";
      return on;
    }

    Array.prototype.forEach.call(boxes, function (box) {
      box.checked = !!saved[box.dataset.kit];
      box.addEventListener("change", function () {
        saved[box.dataset.kit] = box.checked;
        try { localStorage.setItem(KIT_KEY, JSON.stringify(saved)); } catch (e) {}
        sync();
      });
    });

    if (reset) {
      reset.addEventListener("click", function () {
        saved = {};
        try { localStorage.removeItem(KIT_KEY); } catch (e) {}
        Array.prototype.forEach.call(boxes, function (b) { b.checked = false; });
        sync();
      });
    }
    sync();
  }

  /* ---------------- choices ---------------- */

  function wireChoices() {
    var groups = document.querySelectorAll(".choices");
    Array.prototype.forEach.call(groups, function (group) {
      var buttons = group.querySelectorAll(".choice");
      Array.prototype.forEach.call(buttons, function (btn) {
        btn.addEventListener("click", function () {
          var already = btn.getAttribute("aria-pressed") === "true";
          Array.prototype.forEach.call(buttons, function (other) {
            other.setAttribute("aria-pressed", "false");
            var v = other.querySelector(".verdict");
            if (v) v.textContent = "press to check";
          });
          if (!already) {
            btn.setAttribute("aria-pressed", "true");
            var verdict = btn.querySelector(".verdict");
            if (verdict) verdict.textContent = btn.dataset.verdict || "";
          }
        });
      });
    });
  }

  /* ---------------- copy buttons ---------------- */

  function wireCopy() {
    Array.prototype.forEach.call(document.querySelectorAll(".copy"), function (btn) {
      btn.addEventListener("click", function () {
        var pre = btn.parentNode.querySelector("pre");
        if (!pre) return;
        var text = pre.textContent;
        function done() {
          btn.textContent = "Copied";
          btn.classList.add("done");
          setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1600);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { fallback(text, done); });
        } else {
          fallback(text, done);
        }
      });
    });

    function fallback(text, done) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (e) {}
      document.body.removeChild(ta);
    }
  }

  /* ---------------- boot ---------------- */

  function tick(now) {
    playback(now);
    updateScores();
    draw();
    requestAnimationFrame(tick);
  }

  function boot() {
    sizeCanvas();
    window.addEventListener("resize", sizeCanvas);
    wireKit();
    wireChoices();
    wireCopy();
    wireDemo();
    setMode("connecting");
    tryLive();
    requestAnimationFrame(tick);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

/* Hero chips: the three ways in, each with its command. */
(function () {
  var chips = document.querySelectorAll(".chips button");
  var cmd = document.getElementById("hero-cmd");
  var note = document.getElementById("hero-note");
  if (!chips.length || !cmd) return;
  Array.prototype.forEach.call(chips, function (chip) {
    chip.addEventListener("click", function () {
      Array.prototype.forEach.call(chips, function (c) { c.setAttribute("aria-pressed", c === chip ? "true" : "false"); });
      cmd.textContent = chip.getAttribute("data-cmd");
      if (note) note.textContent = chip.getAttribute("data-note");
    });
  });
})();
