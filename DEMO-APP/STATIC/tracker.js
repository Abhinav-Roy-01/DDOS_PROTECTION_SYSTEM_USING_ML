(async () => {
  "use strict";

  const form = document.querySelector("#contact-form");
  const button = document.querySelector("#submit-button");
  const result = document.querySelector("#result");
  const clickTimes = [];
  const clickTargets = new Map();
  const pointerSamples = [];
  let scrollEvents = 0;
  let keystrokeCount = 0;
  let lastPointerSample = 0;

  document.addEventListener("click", (event) => {
    clickTimes.push(performance.now());
    const target = event.target.closest("button, a, input, textarea, label");
    const key = target ? `${target.tagName}:${target.name || target.id || target.type || ""}` : "other";
    clickTargets.set(key, (clickTargets.get(key) || 0) + 1);
  }, { passive: true });

  document.addEventListener("pointermove", (event) => {
    const now = performance.now();
    if (now - lastPointerSample < 80) return;
    pointerSamples.push({ x: event.clientX, y: event.clientY, t: now });
    lastPointerSample = now;
  }, { passive: true });

  document.addEventListener("scroll", () => { scrollEvents += 1; }, { passive: true });
  form.addEventListener("keydown", (event) => {
    if (event.key.length === 1) keystrokeCount += 1;
  });

  function average(values) {
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  }

  function variance(values) {
    if (values.length < 2) return 0;
    const mean = average(values);
    return average(values.map((value) => (value - mean) ** 2));
  }

  function entropy(values) {
    if (!values.length) return 0;
    const bins = new Map();
    values.forEach((value) => {
      const bin = Math.floor(value / 250);
      bins.set(bin, (bins.get(bin) || 0) + 1);
    });
    return [...bins.values()].reduce((total, count) => {
      const probability = count / values.length;
      return total - probability * Math.log(probability);
    }, 0);
  }

  function collectFeatures() {
    const intervals = clickTimes.slice(1).map((time, index) => time - clickTimes[index]);
    const speeds = [];
    for (let index = 1; index < pointerSamples.length; index += 1) {
      const previous = pointerSamples[index - 1];
      const current = pointerSamples[index];
      const elapsed = current.t - previous.t;
      if (elapsed <= 0) continue;
      const distance = Math.hypot(current.x - previous.x, current.y - previous.y);
      const diagonal = Math.hypot(window.innerWidth, window.innerHeight) || 1;
      speeds.push((distance / elapsed) * 1000 / diagonal);
    }

    const elapsedSeconds = Math.max((performance.now() - (clickTimes[0] || performance.now())) / 1000, 1);
    const maxElementClickRate = clickTargets.size
      ? Math.max(...clickTargets.values()) / elapsedSeconds
      : 0;
    return {
      click_count: clickTimes.length,
      avg_click_interval: average(intervals),
      click_interval_variance: variance(intervals),
      click_interval_entropy: entropy(intervals),
      mouse_velocity_variance: variance(speeds),
      max_element_click_rate: maxElementClickRate,
      scroll_events: scrollEvents,
      keystroke_count: keystrokeCount,
    };
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("The server returned an unreadable response.");
    }
    return { response, data };
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    result.textContent = "";
    result.dataset.state = "";
    button.disabled = true;
    try {
      const scoring = await postJson("/predict", { features: collectFeatures() });
      if (scoring.data.status === "captcha_required") {
        const values = new FormData(form);
        sessionStorage.setItem("ddosShieldPendingContact", JSON.stringify({
          name: values.get("name"),
          email: values.get("email"),
          message: values.get("message"),
          website: values.get("website"),
        }));
        window.location.assign(scoring.data.redirect);
        return;
      }
      if (!scoring.response.ok || scoring.data.status !== "allowed") {
        throw new Error(scoring.data.message || "This request could not continue.");
      }

      const values = new FormData(form);
      const contact = await postJson("/contact", {
        name: values.get("name"),
        email: values.get("email"),
        message: values.get("message"),
        website: values.get("website"),
      });
      if (!contact.response.ok || contact.data.status !== "ok") {
        throw new Error(contact.data.message || "The message could not be sent.");
      }
      form.reset();
      result.textContent = "Your message was accepted by the protected demo.";
      result.dataset.state = "success";
    } catch (error) {
      result.textContent = error instanceof Error ? error.message : "The request could not be completed.";
      result.dataset.state = "error";
    } finally {
      button.disabled = false;
    }
  });

  if (new URLSearchParams(window.location.search).get("captcha") === "solved") {
    const savedMessage = sessionStorage.getItem("ddosShieldPendingContact");
    if (savedMessage) {
      button.disabled = true;
      result.textContent = "Verification passed. Sending your message...";
      try {
        const { response, data } = await postJson("/contact", JSON.parse(savedMessage));
        if (!response.ok || data.status !== "ok") {
          throw new Error(data.message || "The message could not be sent.");
        }
        sessionStorage.removeItem("ddosShieldPendingContact");
        form.reset();
        result.textContent = "Your message was accepted by the protected demo.";
        result.dataset.state = "success";
      } catch (error) {
        result.textContent = error instanceof Error ? error.message : "The request could not be completed.";
        result.dataset.state = "error";
      } finally {
        button.disabled = false;
      }
    }
  }
})();
