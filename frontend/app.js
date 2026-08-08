/* Outer Haven Hub — renderowanie kart z /api/dashboard + akcje dotykowe.
   Frontend zna wyłącznie kontrakt z base.py (metryki / chart / actions). */

const POLL_MS = 5000;
/* Status na karcie (krótko) vs badge w topbarze (MGS-owo, bez 0x…). */
const STATUS_CODE = { ok: "OK", warning: "WARN", error: "ERR" };
const STATUS_LABEL = { ok: "ONLINE", warning: "CAUTION", error: "ALERT" };
const CHART_MAX_POINTS = 48;

const grid = document.getElementById("dashboard-grid");
const overallEl = document.getElementById("overall");
const clockTimeEl = document.getElementById("clock-time");
const clockDateEl = document.getElementById("clock-date");
const toastEl = document.getElementById("toast");
const footUptimeEl = document.getElementById("foot-uptime");
const footModeEl = document.getElementById("foot-mode");

let toastTimer = 0;
let actionBusy = false;

/* ---------- kiosk viewport scale ----------
   Layout żyje w stałym canvasie 1024×600 (gęsty HUD). Skalujemy non-uniform
   do okna: scale(innerW/1024, innerH/600) — wypełnia ekran bez letterboxingu.
   Transform jest tylko wizualny; metryki/wykresy liczą w px design size.
   Czarny pasek poza Chromium (X / --window-size) — patrz DEPLOY.md. */

const DESIGN_W = 1024;
const DESIGN_H = 600;

function scaleKioskViewport() {
  const shell = document.querySelector(".shell");
  if (!shell) return;
  const sx = Math.max(0.01, window.innerWidth / DESIGN_W);
  const sy = Math.max(0.01, window.innerHeight / DESIGN_H);
  shell.style.transform = `scale(${sx}, ${sy})`;
}

scaleKioskViewport();
window.addEventListener("resize", scaleKioskViewport);
window.addEventListener("orientationchange", scaleKioskViewport);

/* ---------- zegar ---------- */

function tickClock() {
  const now = new Date();
  clockTimeEl.textContent = now.toLocaleTimeString("pl-PL", { hour12: false });
  clockDateEl.textContent = now.toLocaleDateString("pl-PL", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/* ---------- helpers ---------- */

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showToast(message, kind = "ok") {
  toastEl.hidden = false;
  toastEl.dataset.kind = kind === "ok" ? "" : kind;
  toastEl.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, 4800);
}

/** Stan blokowania Pi-hole z metryki BLOCK — do podświetlenia przycisków.
    API pokazuje pozostały czas („OFF 14M”), nie preset 5/15 — więc aktywny
    OFF bierzemy z ostatniej udanej akcji (sessionStorage), a gdy go brak —
    podświetlamy oba OFF. */
function piholeBlockMode(collector) {
  const m = (collector.metrics || []).find(
    (x) => x.type === "status" && String(x.label).toUpperCase() === "BLOCK",
  );
  if (!m) return { on: true };
  const v = String(m.value || "").toUpperCase();
  if (v === "ON" || v.startsWith("ON ")) {
    try { sessionStorage.removeItem("oh-pihole-off"); } catch (_) { /* ignore */ }
    return { on: true };
  }
  let off = "any";
  try {
    const saved = sessionStorage.getItem("oh-pihole-off");
    if (saved === "5" || saved === "15") off = saved;
  } catch (_) { /* ignore */ }
  return { on: false, off };
}

/* ---------- metryki ---------- */

function renderMetric(metric) {
  const type = metric.type || "text";
  const state = metric.state || "";
  const label = esc(metric.label);
  const value = esc(metric.value);

  if (type === "number" || type === "percent") {
    // Jednostkę (% ° k GB…) oddzielamy. Niewidoczny „pad” z lewej równoważy
    // optycznie suffix z prawej — cyfra siedzi idealnie pod etykietą.
    let shown = type === "percent" ? `${value}%` : String(metric.value ?? "");
    const unitMatch = String(shown).match(/^(-?[\d.,]+)(.*)$/);
    const num = unitMatch ? unitMatch[1] : shown;
    const unit = unitMatch ? unitMatch[2] : "";
    const padHtml = unit
      ? `<span class="metric-pad" aria-hidden="true">${esc(unit)}</span>`
      : "";
    const unitHtml = unit
      ? `<span class="metric-unit">${esc(unit)}</span>`
      : "";
    return `<div class="metric metric--number" data-state="${esc(state)}">
      <span class="metric-label">${label}</span>
      <span class="metric-value">${padHtml}<span class="metric-num">${esc(num)}</span>${unitHtml}</span>
    </div>`;
  }

  if (type === "bar") {
    const pct = Math.max(0, Math.min(100, Number(metric.value) || 0));
    return `<div class="metric metric--bar" data-state="${esc(state)}">
      <div class="bar-meta">
        <span class="metric-label">${label}</span>
        <span class="metric-value">${pct}%</span>
      </div>
      <div class="bar-track"><div class="bar-fill" data-state="${esc(state)}" style="width:${pct}%"></div></div>
    </div>`;
  }

  if (type === "status") {
    return `<div class="metric metric--status" data-state="${esc(state)}">
      <span class="mark" data-state="${esc(state || "muted")}"></span>
      <span class="metric-label">${label}</span>
      <span class="metric-value">${value}</span>
    </div>`;
  }

  return `<div class="metric metric--text" data-state="${esc(state)}">
    <span class="metric-label">${label}</span>
    <span class="metric-value">${value}</span>
  </div>`;
}

/** Hero Pi-hole: status BLOCK — LED + jedno słowo (BLOCKING / PAUSED). */
function renderBlockPlate(metric) {
  const state = metric.state || "ok";
  const raw = String(metric.value || "—").toUpperCase();
  let word = "BLOCKING";
  let timer = "";
  if (raw === "ON" || raw.startsWith("ON ")) {
    word = "BLOCKING";
  } else {
    word = "PAUSED";
    const m = raw.match(/(\d+)\s*M/);
    if (m) timer = `${m[1]}M`;
    else if (raw.includes("OFF")) timer = "—";
  }
  const timerHtml = timer
    ? `<span class="block-led-timer">${esc(timer)}</span>`
    : "";
  return `<div class="block-led" data-state="${esc(state)}">
    <span class="block-led-dot" aria-hidden="true"></span>
    <span class="block-led-word">${esc(word)}</span>
    ${timerHtml}
  </div>`;
}

/* ---------- wykres ---------- */

/** Średnia w kubełkach — 144 punkty Pi-hole → czytelne ~48. */
function downsample(points, maxPoints) {
  const src = (points || []).map(Number).filter(Number.isFinite);
  if (src.length <= maxPoints) return src;
  const out = [];
  const bucket = src.length / maxPoints;
  for (let i = 0; i < maxPoints; i++) {
    const start = Math.floor(i * bucket);
    const end = Math.max(start + 1, Math.floor((i + 1) * bucket));
    let sum = 0;
    for (let j = start; j < end && j < src.length; j++) sum += src[j];
    out.push(sum / (end - start));
  }
  return out;
}

function renderChart(chart, options = {}) {
  if (!chart || chart.type !== "line" || !Array.isArray(chart.series) || !chart.series.length) {
    return "";
  }

  const wide = Boolean(options.wide);
  const dimmed = Boolean(options.dimmed);
  const width = wide ? 520 : 300;
  const height = wide ? 160 : 112;
  const padX = 4;
  const padY = 7;

  const series = chart.series.map((s) => ({
    ...s,
    points: downsample(s.points, CHART_MAX_POINTS),
  })).filter((s) => s.points.length);

  if (!series.length) return "";

  const allPoints = series.flatMap((s) => s.points);
  const dataMin = Math.min(...allPoints);
  const dataMax = Math.max(...allPoints);
  // Skala z marginesem — nawet płaskie serie (temp 28–31) zajmują wysokość wykresu.
  const span = Math.max(dataMax - dataMin, Math.abs(dataMax) * 0.08, 1);
  const yMin = dataMin - span * 0.12;
  const yMax = dataMax + span * 0.12;
  const yRange = yMax - yMin;
  const len = Math.max(...series.map((s) => s.points.length), 1);

  function xAt(i) {
    return padX + (i / Math.max(len - 1, 1)) * (width - padX * 2);
  }

  function yAt(v) {
    return height - padY - ((Number(v) - yMin) / yRange) * (height - padY * 2);
  }

  function pathFor(points) {
    if (!points.length) return "";
    return points.map((y, i) =>
      `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(y).toFixed(1)}`
    ).join(" ");
  }

  // Poziome linie pomocnicze (płaskie, bez glow).
  const guides = [0.25, 0.5, 0.75].map((t) => {
    const y = (padY + t * (height - padY * 2)).toFixed(1);
    return `<line class="chart-guide" x1="${padX}" y1="${y}" x2="${width - padX}" y2="${y}" />`;
  }).join("");

  function seriesRole(s) {
    if (s.role === "accent" || s.role === "warn") return s.role;
    return "muted";
  }

  const lines = series.map((s) => {
    const role = seriesRole(s);
    return `<path class="chart-line chart-line-${role}" d="${pathFor(s.points)}" />`;
  }).join("");

  const legend = series.map((s) => {
    const role = seriesRole(s);
    return `<div class="chart-legend-row lg-${role}">
      <span class="lg-swatch"></span>
      <span class="lg-name">${esc(s.label || role)}</span>
    </div>`;
  }).join("");

  const title = chart.title
    ? `<div class="chart-title">${esc(chart.title)}</div>`
    : "";
  const caption = chart.caption
    ? `<div class="chart-caption">${esc(chart.caption)}</div>`
    : "";

  return `<div class="chart-wrap${wide ? " chart-wrap--wide" : ""}${dimmed ? " chart-wrap--dim" : ""}" aria-hidden="true">
    ${title}
    ${caption}
    <div class="chart-legend">${legend}</div>
    <div class="chart">
      <svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="none">
        ${guides}
        ${lines}
      </svg>
    </div>
  </div>`;
}

/* ---------- akcje ---------- */

function actionButton(action, options = {}) {
  const active = Boolean(options.active);
  const confirmArmed = Boolean(options.confirmArmed);
  const mark = options.mark
    ? `<span class="action-mark" aria-hidden="true"></span>`
    : "";
  const label = confirmArmed ? (action.confirm_label || "CONFIRM") : action.label;
  const style = confirmArmed ? "warn" : (action.style || "default");
  const cls = [
    "action",
    active ? "is-active" : "",
    confirmArmed ? "is-confirm" : "",
    options.compact ? "action--compact" : "",
  ].filter(Boolean).join(" ");
  return `<button type="button"
    class="${cls}"
    data-collector="${esc(options.collectorId)}"
    data-action="${esc(action.id)}"
    data-confirm="${action.confirm ? "1" : "0"}"
    data-style="${esc(style)}">${mark}${esc(label)}</button>`;
}

function splitActions(collector) {
  const actions = collector.actions || [];
  const block = [];
  const util = [];
  const tool = [];
  for (const a of actions) {
    const g = a.group || "tool";
    if (g === "block") block.push(a);
    else if (g === "util") util.push(a);
    else tool.push(a);
  }
  // Stare akcje bez group (gdyby coś zostało) — traktuj jak block dla pihole
  if (!block.length && !util.length && !tool.length && actions.length) {
    return { block: actions, util: [], tool: [] };
  }
  return { block, util, tool };
}

function renderBlockActions(collector) {
  const { block } = splitActions(collector);
  if (!block.length) return "";
  const mode = piholeBlockMode(collector);
  return `<div class="actions actions--segment">
    ${block.map((action) => {
      let active = false;
      if (action.id === "block_on") active = mode.on;
      else if (action.id === "block_off_5") {
        active = !mode.on && (mode.off === "5" || mode.off === "any");
      } else if (action.id === "block_off_15") {
        active = !mode.on && (mode.off === "15" || mode.off === "any");
      }
      return actionButton(action, {
        collectorId: collector.id,
        active,
        mark: true,
      });
    }).join("")}
  </div>`;
}

function renderUtilActions(collector) {
  return "";
}

function renderToolActions(collector) {
  return "";
}

/* ---------- karta ---------- */

function renderCard(collector, index) {
  const status = collector.status || "error";
  const metrics = collector.metrics || [];
  const layout = collector.layout || "default";
  const isHero = layout === "hero";
  const idx = String(index + 1).padStart(2, "0");
  const chartDimmed = isHero && status === "warning";

  const big = metrics.filter((m) => m.type === "number" || m.type === "percent");
  const statusMetrics = metrics.filter((m) => m.type === "status");
  const rest = metrics.filter(
    (m) => m.type !== "number" && m.type !== "percent" && m.type !== "status",
  );

  let body = "";

  if (collector.error && !metrics.length) {
    body = `<div class="card-error">${esc(collector.error)}</div>`;
  } else if (isHero) {
    const blockHtml = renderBlockActions(collector);
    const left = `
      <div class="hero-left">
        ${big.length ? `<div class="metrics-row metrics-row--${Math.min(big.length, 4)}">${big.map(renderMetric).join("")}</div>` : ""}
        <div class="hero-rail">
          <div class="hero-status">${statusMetrics.map(renderBlockPlate).join("")}</div>
          ${blockHtml}
        </div>
        ${rest.map(renderMetric).join("")}
      </div>`;
    const right = `<div class="hero-right">${renderChart(collector.chart, { wide: true, dimmed: chartDimmed })}</div>`;
    body = left + right;
    if (collector.error) {
      body += `<div class="card-error">${esc(collector.error)}</div>`;
    }
  } else {
    body = `<div class="card-main">
      ${big.length ? `<div class="metrics-row metrics-row--${Math.min(big.length, 4)}">${big.map(renderMetric).join("")}</div>` : ""}
      ${statusMetrics.map(renderMetric).join("")}
      ${rest.map(renderMetric).join("")}
    </div>`;
    body += renderChart(collector.chart);
    if (collector.error) {
      body += `<div class="card-error">${esc(collector.error)}</div>`;
    }
  }

  const layoutClass = isHero ? " card--hero" : "";
  return `<article class="card${layoutClass}" data-id="${esc(collector.id)}" data-status="${esc(status)}">
    <header class="card-head">
      <span class="card-index">0x${idx}</span>
      <span class="card-title">${esc(collector.label)}</span>
      <span class="card-code">${STATUS_CODE[status] || "ERR"}</span>
    </header>
    <div class="card-body${isHero ? " card-body--hero" : ""}">${body}</div>
  </article>`;
}

/* ---------- dashboard ---------- */

function setOverall(status) {
  const key = STATUS_LABEL[status] ? status : "error";
  const prev = overallEl.dataset.status;
  overallEl.dataset.status = key;
  overallEl.textContent = STATUS_LABEL[key];

  // Alert pulse — tylko przy wejściu w ERROR (nie przy każdym pollu)
  if (key === "error" && prev !== "error") {
    overallEl.classList.remove("is-alert-pulse");
    // reflow, żeby animacja odpaliła się ponownie
    void overallEl.offsetWidth;
    overallEl.classList.add("is-alert-pulse");
  }
  if (key !== "error") {
    overallEl.classList.remove("is-alert-pulse");
  }
}

async function refreshDashboard() {
  if (actionBusy) return;

  try {
    const response = await fetch("/api/dashboard", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    setOverall(data.status);

    const collectors = data.collectors || [];
    if (!collectors.length) {
      grid.innerHTML = `<div class="empty-state">no active modules</div>`;
      return;
    }
    grid.innerHTML = collectors.map(renderCard).join("");
    footUptimeEl.textContent = `UP ${data.uptime || "—"}`;
    footModeEl.textContent = "LIVE";
  } catch (err) {
    setOverall("error");
    footModeEl.textContent = "DOWN";
    if (!grid.children.length) {
      grid.innerHTML = `<div class="empty-state">link down · ${esc(err.message)}</div>`;
    }
    console.warn("dashboard refresh failed:", err);
  }
}

async function runAction(collectorId, actionId, button) {
  if (actionBusy) return;

  actionBusy = true;
  button.classList.add("is-busy");
  button.disabled = true;

  try {
    const response = await fetch(
      `/api/collectors/${encodeURIComponent(collectorId)}/actions/${encodeURIComponent(actionId)}`,
      { method: "POST" },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    if (collectorId === "pihole") {
      try {
        if (actionId === "block_off_5") sessionStorage.setItem("oh-pihole-off", "5");
        else if (actionId === "block_off_15") sessionStorage.setItem("oh-pihole-off", "15");
        else if (actionId === "block_on") sessionStorage.removeItem("oh-pihole-off");
      } catch (_) { /* ignore */ }
    }
    showToast(payload.message || "done", actionId.startsWith("block_off") ? "warn" : "ok");
  } catch (err) {
    showToast(String(err.message || err), "error");
  } finally {
    actionBusy = false;
    await refreshDashboard();
  }
}

grid.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !grid.contains(button)) return;
  runAction(button.dataset.collector, button.dataset.action, button);
});

tickClock();
setInterval(tickClock, 1000);

/* Codec boot splash — CONNECTING → LINK ESTABLISHED → fade out */
function runBootSplash() {
  const splash = document.getElementById("boot-splash");
  const label = document.getElementById("boot-label");
  if (!splash || !label) {
    refreshDashboard();
    setInterval(refreshDashboard, POLL_MS);
    return;
  }

  // Dashboard ładuje się w tle pod splash
  refreshDashboard();
  setInterval(refreshDashboard, POLL_MS);

  setTimeout(() => {
    label.textContent = "LINK ESTABLISHED";
    label.classList.add("is-ok");
    splash.classList.add("is-linked");
  }, 900);

  setTimeout(() => {
    splash.classList.add("is-done");
  }, 1500);

  setTimeout(() => {
    splash.hidden = true;
    splash.remove();
  }, 1900);
}

runBootSplash();
