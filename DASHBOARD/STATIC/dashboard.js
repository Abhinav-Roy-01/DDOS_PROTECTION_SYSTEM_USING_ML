(() => {
  "use strict";

  const keyInput = document.querySelector("#admin-key");
  const connectButton = document.querySelector("#connect");
  const connectionStatus = document.querySelector("#connection-status");
  const errorOutput = document.querySelector("#error");
  const counterLabels = [
    ["predict_allowed", "Allowed"],
    ["predict_captcha", "CAPTCHA"],
    ["predict_blocked", "Blocked"],
    ["captcha_solved", "CAPTCHA solved"],
    ["captcha_failed", "CAPTCHA failed"],
    ["contact_ok", "Messages accepted"],
    ["contact_rejected", "Messages rejected"],
  ];
  let refreshTimer;

  keyInput.value = sessionStorage.getItem("ddosShieldAdminKey") || "";

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  async function fetchJson(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      cache: "no-store",
      headers: {
        "X-Admin-Key": keyInput.value,
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || data.error || `Request failed (${response.status}).`);
    }
    return data;
  }

  function renderCounters(counters) {
    const list = document.querySelector("#verdict-counters");
    list.replaceChildren();
    counterLabels.forEach(([key, label]) => {
      const wrapper = node("div");
      wrapper.append(node("dt", label), node("dd", String(counters[key] || 0)));
      list.append(wrapper);
    });
  }

  function renderHistogram(histogram) {
    const canvas = document.querySelector("#score-chart");
    const context = canvas.getContext("2d");
    const bins = Object.entries(histogram)
      .map(([bin, count]) => [Number(bin), Number(count)])
      .sort((left, right) => left[0] - right[0]);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#94a5b8";
    context.font = "11px Segoe UI";
    if (!bins.length) {
      context.fillText("No prediction scores yet.", 18, 38);
      return;
    }
    const maxCount = Math.max(...bins.map(([, count]) => count), 1);
    const gap = 5;
    const slot = (canvas.width - 44) / bins.length;
    bins.forEach(([bin, count], index) => {
      const height = (count / maxCount) * (canvas.height - 60);
      const x = 28 + index * slot;
      const y = canvas.height - 31 - height;
      context.fillStyle = "#49bfa1";
      context.fillRect(x, y, Math.max(2, slot - gap), height);
      if (bins.length <= 16 || index % Math.ceil(bins.length / 16) === 0) {
        context.fillStyle = "#94a5b8";
        context.fillText(bin.toFixed(2), x, canvas.height - 10);
      }
    });
    context.fillStyle = "#94a5b8";
    context.fillText("samples", 4, 14);
  }

  function renderTraffic(timeline) {
    const canvas = document.querySelector("#traffic-chart");
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    const maxCount = Math.max(
      ...timeline.map((slot) => slot.allowed + slot.blocked),
      1,
    );
    const slotWidth = canvas.width / Math.max(timeline.length, 1);
    timeline.forEach((slot, index) => {
      const x = index * slotWidth;
      const allowedHeight = (slot.allowed / maxCount) * (canvas.height - 42);
      const blockedHeight = (slot.blocked / maxCount) * (canvas.height - 42);
      context.fillStyle = "#49bfa1";
      context.fillRect(x, canvas.height - 24 - allowedHeight, Math.max(1, slotWidth - 1), allowedHeight);
      context.fillStyle = "#ff8e84";
      context.fillRect(x, canvas.height - 24 - allowedHeight - blockedHeight, Math.max(1, slotWidth - 1), blockedHeight);
    });
    context.fillStyle = "#94a5b8";
    context.font = "11px Segoe UI";
    context.fillText("Allowed", 12, 14);
    context.fillStyle = "#49bfa1";
    context.fillRect(61, 6, 9, 9);
    context.fillStyle = "#94a5b8";
    context.fillText("Blocked", 82, 14);
    context.fillStyle = "#ff8e84";
    context.fillRect(132, 6, 9, 9);
  }

  function renderThreats(rows) {
    const body = document.querySelector("#threat-rows");
    body.replaceChildren();
    rows.forEach((entry) => {
      const row = node("tr");
      row.append(
        node("td", entry.ip),
        node("td", String(entry.total)),
        node("td", String(entry.blocked)),
        node("td", entry.threat),
      );
      body.append(row);
    });
    if (!body.children.length) {
      const row = node("tr");
      const cell = node("td", "No client activity.", "");
      cell.colSpan = 4;
      row.append(cell);
      body.append(row);
    }
  }

  function renderRequests(requests) {
    const body = document.querySelector("#request-rows");
    body.replaceChildren();
    requests.slice(-20).reverse().forEach((request) => {
      const row = node("tr");
      row.append(
        node("td", request.time || "—"),
        node("td", `${request.method || ""} ${request.path || ""}`),
        node("td", request.ip || "—"),
        node("td", String(request.status_code || "—")),
      );
      body.append(row);
    });
    if (!body.children.length) {
      const row = node("tr");
      const cell = node("td", "No requests recorded.");
      cell.colSpan = 4;
      row.append(cell);
      body.append(row);
    }
  }

  function renderBans(bans) {
    const list = document.querySelector("#ban-list");
    list.replaceChildren();
    if (!bans.length) {
      list.append(node("li", "No active bans."));
      return;
    }
    bans.forEach((ban) => {
      const item = node("li");
      const row = node("div", undefined, "ban-row");
      row.append(node("span", `${ban.ip} · until ${ban.until}`));
      const button = node("button", "Unban");
      button.type = "button";
      button.addEventListener("click", async () => {
        await mutate("/api/unban", { ip: ban.ip });
      });
      row.append(button);
      item.append(row);
      list.append(item);
    });
  }

  function renderMessages(messages) {
    const list = document.querySelector("#messages");
    list.replaceChildren();
    if (!messages.length) {
      list.append(node("p", "No verified messages.", "muted"));
      return;
    }
    messages.forEach((message) => {
      const article = node("article", undefined, "message-card");
      article.append(
        node("strong", `${message.name} · ${message.email}`),
        node("span", ` · ${message.received_at || ""}`, "muted"),
        node("p", message.message),
      );
      list.append(article);
    });
  }

  async function refresh() {
    errorOutput.textContent = "";
    const [overview, stats, matrix, messages, retrain] = await Promise.all([
      fetchJson("/api/overview"),
      fetchJson("/api/stats"),
      fetchJson("/api/matrix"),
      fetchJson("/api/messages?limit=20"),
      fetchJson("/api/retrain/status"),
    ]);
    document.querySelector("#total-requests").textContent = String(stats.total_requests);
    document.querySelector("#blocked-requests").textContent = String(stats.blocked_requests);
    document.querySelector("#active-bans").textContent = String(stats.banned_ips);
    document.querySelector("#pending-feedback").textContent = String(overview.feedback.pending);
    const modelPill = document.querySelector("#model-status");
    modelPill.textContent = overview.model.degraded ? "Degraded" : "Ready";
    modelPill.classList.toggle("ready", !overview.model.degraded);
    document.querySelector("#model-version").textContent =
      `Version ${overview.model.model_version || "unavailable"} · human ${overview.feedback.human} · bot ${overview.feedback.bot}`;
    renderCounters(overview.counters);
    renderHistogram(overview.score_histogram);
    renderTraffic(matrix.timeline || []);
    renderThreats(matrix.ip_matrix || []);
    renderRequests(stats.recent_requests || []);
    renderBans(stats.banned_list || []);
    renderMessages(messages.messages || []);
    document.querySelector("#retrain-status").textContent =
      `Latest run: ${retrain.status}${retrain.finished_at ? ` · ${retrain.finished_at}` : ""}`;
    connectionStatus.textContent = "Connected · refreshes every 10 seconds";
  }

  async function mutate(path, payload) {
    try {
      await fetchJson(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await refresh();
    } catch (error) {
      errorOutput.textContent = error instanceof Error ? error.message : "The request failed.";
    }
  }

  connectButton.addEventListener("click", async () => {
    sessionStorage.setItem("ddosShieldAdminKey", keyInput.value);
    try {
      await refresh();
      clearInterval(refreshTimer);
      refreshTimer = setInterval(() => {
        refresh().catch((error) => {
          connectionStatus.textContent = "Connection lost";
          errorOutput.textContent = error instanceof Error ? error.message : "Refresh failed.";
        });
      }, 10_000);
    } catch (error) {
      connectionStatus.textContent = "Not connected";
      errorOutput.textContent = error instanceof Error ? error.message : "Authentication failed.";
    }
  });

  document.querySelector("#retrain-dry-run").addEventListener("click", async () => {
    document.querySelector("#retrain-status").textContent = "Running canary dry-run...";
    await mutate("/api/retrain/start", { dry_run: true });
  });

  document.querySelector("#retrain-deploy").addEventListener("click", async () => {
    if (!window.confirm("Train and deploy a candidate that passes the canary gate?")) return;
    document.querySelector("#retrain-status").textContent = "Training and validating candidate...";
    await mutate("/api/retrain/start", { dry_run: false });
  });

  document.querySelector("#ban-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await mutate("/api/ban", { ip: document.querySelector("#ban-ip").value.trim() });
    event.currentTarget.reset();
  });
})();
