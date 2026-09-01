/**
 * DASHBOARD/static/js/tracker.js
 * Passive behavioral telemetry collector.
 *
 * This is the piece that was missing: everything else in this system
 * (ml_engine.py, the "Manual Classifier" panel) only ever scored numbers
 * you typed in by hand. This file watches REAL mouse movement, clicks,
 * keystrokes, and scrolling on whatever page includes it, turns that into
 * the same 8 features the model expects, and sends a snapshot to /predict
 * every 5 seconds -- same as a real visitor (or bot) would generate.
 *
 * Include on any page you want protected:
 *   <script src="/static/js/tracker.js"></script>
 *
 * Everything below runs automatically once the script loads. Nothing to
 * call manually.
 */

(function () {
  const REPORT_INTERVAL_MS = 5000;

  // --- raw event state, reset after every report ---
  let clickTimestamps = [];       // ms epoch, one per click
  let clickTargetCounts = {};     // element id/tag -> click count (for max_element_click_rate)
  let mouseSamples = [];          // {t, x, y}, one per mousemove (throttled)
  let scrollEvents = 0;
  let keystrokeCount = 0;
  let lastMouseSampleTime = 0;
  const MOUSE_SAMPLE_THROTTLE_MS = 50; // don't sample every single pixel of movement

  function onClick(e) {
    clickTimestamps.push(Date.now());
    const key = (e.target && (e.target.id || e.target.tagName)) || "unknown";
    clickTargetCounts[key] = (clickTargetCounts[key] || 0) + 1;
  }

  function onMouseMove(e) {
    const now = Date.now();
    if (now - lastMouseSampleTime < MOUSE_SAMPLE_THROTTLE_MS) return;
    lastMouseSampleTime = now;
    mouseSamples.push({ t: now, x: e.clientX, y: e.clientY });
  }

  function onScroll() {
    scrollEvents += 1;
  }

  function onKeyDown() {
    keystrokeCount += 1;
  }

  // --- feature computation, matching ML/FEATURES definitions used at training time ---

  function computeClickIntervals() {
    const sorted = clickTimestamps.slice().sort((a, b) => a - b);
    const intervals = [];
    for (let i = 1; i < sorted.length; i++) intervals.push(sorted[i] - sorted[i - 1]);
    return intervals;
  }

  function mean(arr) {
    if (!arr.length) return 0;
    return arr.reduce((a, b) => a + b, 0) / arr.length;
  }

  function variance(arr) {
    if (arr.length < 2) return 0;
    const m = mean(arr);
    return mean(arr.map((v) => (v - m) ** 2));
  }

  function shannonEntropy(intervals) {
    // Bucket intervals into 100ms bins, then compute entropy of the
    // resulting distribution -- humans are irregular (higher entropy),
    // scripted bots are metronomic (near-zero entropy).
    if (intervals.length < 2) return 0;
    const bins = {};
    intervals.forEach((v) => {
      const bucket = Math.round(v / 100);
      bins[bucket] = (bins[bucket] || 0) + 1;
    });
    const total = intervals.length;
    let entropy = 0;
    Object.values(bins).forEach((count) => {
      const p = count / total;
      entropy -= p * Math.log2(p);
    });
    return entropy;
  }

  function mouseVelocityVariance() {
    if (mouseSamples.length < 2) return 0;
    const velocities = [];
    for (let i = 1; i < mouseSamples.length; i++) {
      const a = mouseSamples[i - 1];
      const b = mouseSamples[i];
      const dt = Math.max(b.t - a.t, 1);
      const dist = Math.hypot(b.x - a.x, b.y - a.y);
      velocities.push(dist / dt); // px per ms
    }
    return variance(velocities);
  }

  function maxElementClickRate() {
    const counts = Object.values(clickTargetCounts);
    if (!counts.length) return 0;
    // fraction of all clicks that landed on the single most-clicked element
    const totalClicks = clickTimestamps.length;
    return totalClicks ? Math.max(...counts) / totalClicks : 0;
  }

  function buildSnapshot() {
    const intervals = computeClickIntervals();
    return {
      click_count: clickTimestamps.length,
      avg_click_interval: mean(intervals),
      click_interval_variance: variance(intervals),
      click_interval_entropy: shannonEntropy(intervals),
      mouse_velocity_variance: mouseVelocityVariance(),
      max_element_click_rate: maxElementClickRate(),
      scroll_events: scrollEvents,
      keystroke_count: keystrokeCount,
    };
  }

  function resetWindow() {
    clickTimestamps = [];
    clickTargetCounts = {};
    mouseSamples = [];
    scrollEvents = 0;
    keystrokeCount = 0;
  }

  async function report() {
    const snapshot = buildSnapshot();
    // Skip sending empty windows (nobody touched the page in the last 5s)
    if (snapshot.click_count === 0 && snapshot.scroll_events === 0 && snapshot.keystroke_count === 0) {
      resetWindow();
      return;
    }
    try {
      await fetch("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(snapshot),
      });
    } catch (e) {
      console.warn("tracker.js: failed to report snapshot", e);
    }
    resetWindow();
  }

  document.addEventListener("click", onClick, true);
  document.addEventListener("mousemove", onMouseMove, true);
  document.addEventListener("scroll", onScroll, true);
  document.addEventListener("keydown", onKeyDown, true);

  setInterval(report, REPORT_INTERVAL_MS);

  console.info("tracker.js active — reporting real behavior every 5s to /predict");
})();
