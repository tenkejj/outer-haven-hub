/* Outer Haven Hub — cards from /api/dashboard + touch actions.
   Frontend only knows the base.py contract (metrics / chart / actions).

   Pages: Home | Net | Host | Apps  (#hub #net #host #apps)
   Collector `services` skips the Home grid. */

const POLL_MS = 5000;
const STATUS_CODE = { ok: "OK", warning: "WARN", error: "ERR" };
const STATUS_LABEL = { ok: "ONLINE", warning: "CAUTION", error: "ALERT" };
const CHART_MAX_POINTS = 48;
const PAGES = ["hub", "net", "host", "apps"];
const PAGE_TITLE = {
  hub: "Home",
  net: "Net",
  host: "Host",
  apps: "Apps",
};
/* Old deep-links from the 8-tab UI → new pages */
const PAGE_ALIASES = {
  dns: "net",
  ads: "net",
  disk: "host",
  sys: "host",
  svc: "apps",
  media: "apps",
  mc: "apps",
  minecraft: "apps",
};
const HUB_SYSTEM_LABELS = new Set(["CPU", "RAM", "TEMP"]);
const SYS_EXTRA_LABELS = new Set(["CPU", "RAM", "TEMP", "LOAD", "SWAP", "THRTL"]);
const NET_LAN_LABELS = new Set(["IFACE", "NET IN", "NET OUT"]);

const grid = document.getElementById("dashboard-grid");
const netGrid = document.getElementById("net-grid");
const hostGrid = document.getElementById("host-grid");
const appsGrid = document.getElementById("apps-grid");
const pageNav = document.getElementById("page-nav");
const footPageEl = document.getElementById("foot-page");
const overallEl = document.getElementById("overall");
const clockTimeEl = document.getElementById("clock-time");
const clockDateEl = document.getElementById("clock-date");
const toastEl = document.getElementById("toast");
const footUptimeEl = document.getElementById("foot-uptime");
const footModeEl = document.getElementById("foot-mode");

let toastTimer = 0;
let actionBusy = false;
/** Ostatni payload dashboardu — przełączanie stron bez czekania na poll. */
let lastDashboard = null;
let currentPage = "hub";

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

/** Hero Pi-hole: BLOCK status — LED + short word (BLOCKING / PAUSED). */
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

function seriesRole(s) {
  if (s.role === "accent" || s.role === "warn") return s.role;
  return "muted";
}

function chartLegend(series) {
  return series.map((s) => {
    const role = seriesRole(s);
    return `<div class="chart-legend-row lg-${role}">
      <span class="lg-swatch"></span>
      <span class="lg-name">${esc(s.label || role)}</span>
    </div>`;
  }).join("");
}

function chartGuides(width, height, padX, padY) {
  return [0.25, 0.5, 0.75].map((t) => {
    const y = (padY + t * (height - padY * 2)).toFixed(1);
    return `<line class="chart-guide" x1="${padX}" y1="${y}" x2="${width - padX}" y2="${y}" />`;
  }).join("");
}

/** Linie — metryki systemowe (CPU / RAM / temp). */
function renderLinePlot(series, width, height, padX, padY) {
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

  const lines = series.map((s) => {
    const role = seriesRole(s);
    return `<path class="chart-line chart-line-${role}" d="${pathFor(s.points)}" />`;
  }).join("");

  return `${chartGuides(width, height, padX, padY)}${lines}`;
}

/** Słupki warstwowe — Pi-hole: dół = blocked (accent), góra = permitted (muted).
    Seria muted = TOTAL zapytań; permitted = max(0, total − blocked). */
function renderStackedBarPlot(series, width, height, padX, padY) {
  const blocked = series.find((s) => seriesRole(s) === "accent")
    || series.find((s) => seriesRole(s) === "warn");
  const total = series.find((s) => seriesRole(s) === "muted");
  if (!blocked || !total) return "";

  const len = Math.max(blocked.points.length, total.points.length, 1);
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;
  const gap = 1;
  const barW = Math.max(1, (plotW - gap * Math.max(len - 1, 0)) / len);

  let maxTotal = 0;
  for (let i = 0; i < len; i++) {
    const t = Number(total.points[i]) || 0;
    const b = Number(blocked.points[i]) || 0;
    maxTotal = Math.max(maxTotal, t, b);
  }
  const yMax = Math.max(maxTotal * 1.05, 1);

  function hAt(v) {
    return (Math.max(0, Number(v) || 0) / yMax) * plotH;
  }

  const bars = [];
  for (let i = 0; i < len; i++) {
    const rawTotal = Math.max(0, Number(total.points[i]) || 0);
    const rawBlocked = Math.max(0, Number(blocked.points[i]) || 0);
    // Edge case: total < blocked → przytnij blocked, permitted = 0.
    const bVal = Math.min(rawBlocked, rawTotal);
    const pVal = Math.max(0, rawTotal - bVal);
    const x = (padX + i * (barW + gap)).toFixed(2);
    const hB = hAt(bVal);
    const hP = hAt(pVal);
    const yBase = height - padY;
    const yBlocked = (yBase - hB).toFixed(2);
    const yPermitted = (yBase - hB - hP).toFixed(2);
    const w = barW.toFixed(2);

    if (hP > 0.05) {
      bars.push(
        `<rect class="chart-bar chart-bar--muted" x="${x}" y="${yPermitted}" width="${w}" height="${hP.toFixed(2)}" />`,
      );
    }
    if (hB > 0.05) {
      bars.push(
        `<rect class="chart-bar chart-bar--accent" x="${x}" y="${yBlocked}" width="${w}" height="${hB.toFixed(2)}" />`,
      );
    }
  }

  return `${chartGuides(width, height, padX, padY)}${bars.join("")}`;
}

function renderChart(chart, options = {}) {
  const type = chart && chart.type;
  if (!chart || (type !== "line" && type !== "stacked_bar")
      || !Array.isArray(chart.series) || !chart.series.length) {
    return "";
  }

  const wide = Boolean(options.wide);
  const tall = Boolean(options.tall);
  const dimmed = Boolean(options.dimmed);
  // Tall focus pages: more plot pixels, less number chrome.
  const width = tall ? 960 : (wide ? 520 : 300);
  const height = tall ? 300 : (wide ? 168 : 128);
  const padX = tall ? 8 : 4;
  const padY = tall ? 12 : 7;

  const series = chart.series.map((s) => ({
    ...s,
    points: downsample(s.points, tall ? 96 : CHART_MAX_POINTS),
  })).filter((s) => s.points.length);

  if (!series.length) return "";

  const plot = type === "stacked_bar"
    ? renderStackedBarPlot(series, width, height, padX, padY)
    : renderLinePlot(series, width, height, padX, padY);

  if (!plot) return "";

  const title = chart.title
    ? `<div class="chart-title">${esc(chart.title)}</div>`
    : "";
  const caption = chart.caption
    ? `<div class="chart-caption">${esc(chart.caption)}</div>`
    : "";
  const wrapClass = [
    "chart-wrap",
    wide ? "chart-wrap--wide" : "",
    tall ? "chart-wrap--tall" : "",
    dimmed ? "chart-wrap--dim" : "",
  ].filter(Boolean).join(" ");

  return `<div class="${wrapClass}" aria-hidden="true">
    ${title}
    ${caption}
    <div class="chart-legend">${chartLegend(series)}</div>
    <div class="chart">
      <svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="none">
        ${plot}
      </svg>
    </div>
  </div>`;
}

/** Compact SVG ring for a percent metric — visual first on Host. */
function renderGauge(metric) {
  // Values often arrive as "46%" / "30%" — parseFloat, not Number().
  const pct = Math.max(0, Math.min(100, parseFloat(String(metric.value)) || 0));
  const state = metric.state || "";
  const r = 34;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return `<div class="gauge" data-state="${esc(state)}">
    <svg viewBox="0 0 80 80" class="gauge-svg" aria-hidden="true">
      <circle class="gauge-track" cx="40" cy="40" r="${r}" />
      <circle class="gauge-fill" cx="40" cy="40" r="${r}"
        stroke-dasharray="${dash.toFixed(1)} ${c.toFixed(1)}"
        transform="rotate(-90 40 40)" />
    </svg>
    <div class="gauge-readout">
      <span class="gauge-num">${esc(String(Math.round(pct)))}<span class="gauge-unit">%</span></span>
      <span class="gauge-label">${esc(metric.label)}</span>
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

function renderCard(collector, index, options = {}) {
  const status = collector.status || "error";
  const metrics = collector.metrics || [];
  const layout = collector.layout || "default";
  const isHero = layout === "hero";
  // chartFocus = stacked metrics-on-top / chart-fills-rest (Host cards).
  // Never combine with hero — hero keeps proven left|right split.
  const chartFocus = Boolean(options.chartFocus) && !isHero;
  const idx = String(index + 1).padStart(2, "0");
  const chartDimmed = isHero && status === "warning";

  const big = metrics.filter((m) => m.type === "number" || m.type === "percent");
  const statusMetrics = metrics.filter((m) => m.type === "status");
  const rest = metrics.filter(
    (m) => m.type !== "number" && m.type !== "percent" && m.type !== "status",
  );
  const gauges = chartFocus
    ? big.filter((m) => {
      const lab = String(m.label).toUpperCase();
      return m.type === "percent" || lab === "RAM" || lab === "CPU";
    })
    : [];

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
    const right = `<div class="hero-right">${renderChart(collector.chart, { wide: true, tall: true, dimmed: chartDimmed })}</div>`;
    body = left + right;
    if (collector.error) {
      body += `<div class="card-error">${esc(collector.error)}</div>`;
    }
  } else if (chartFocus) {
    // Compact strip + gauges; chart MUST fill remaining height (see CSS height:0 trick).
    const gaugeHtml = gauges.length
      ? `<div class="gauge-row">${gauges.slice(0, 3).map(renderGauge).join("")}</div>`
      : "";
    const otherBig = big.filter((m) => !gauges.includes(m));
    const strip = otherBig.length
      ? `<div class="metrics-row metrics-row--strip metrics-row--${Math.min(otherBig.length, 4)}">${otherBig.map(renderMetric).join("")}</div>`
      : (!gauges.length && big.length
        ? `<div class="metrics-row metrics-row--strip metrics-row--${Math.min(big.length, 4)}">${big.map(renderMetric).join("")}</div>`
        : "");
    body = `
      <div class="focus-top">
        ${gaugeHtml}
        ${strip}
        ${statusMetrics.map(renderMetric).join("")}
      </div>
      <div class="focus-chart">${renderChart(collector.chart, { wide: true, tall: true })}</div>`;
    if (collector.error) {
      body += `<div class="card-error">${esc(collector.error)}</div>`;
    }
  } else {
    body = `<div class="card-main">
      ${big.length ? `<div class="metrics-row metrics-row--${Math.min(big.length, 4)}">${big.map(renderMetric).join("")}</div>` : ""}
      ${statusMetrics.map(renderMetric).join("")}
      ${rest.map(renderMetric).join("")}
    </div>`;
    body += renderChart(collector.chart, { wide: Boolean(options.wideChart) });
    if (collector.error) {
      body += `<div class="card-error">${esc(collector.error)}</div>`;
    }
  }

  const layoutClass = [
    isHero ? "card--hero" : "",
    chartFocus ? "card--chart-focus" : "",
  ].filter(Boolean).join(" ");
  return `<article class="card${layoutClass ? ` ${layoutClass}` : ""}" data-id="${esc(collector.id)}" data-status="${esc(status)}">
    <header class="card-head">
      <span class="card-index">${idx}</span>
      <span class="card-title">${esc(collector.label)}</span>
      <span class="card-code">${STATUS_CODE[status] || "ERR"}</span>
    </header>
    <div class="card-body${isHero ? " card-body--hero" : ""}${chartFocus ? " card-body--focus" : ""}">${body}</div>
  </article>`;
}

/* ---------- Svc / Media / Minecraft / focus pages ---------- */

function findCollector(data, id) {
  return (data.collectors || []).find((c) => c.id === id) || null;
}

function servicesCollector(data) {
  return findCollector(data, "services");
}

function serviceStatusMetrics(collector) {
  return (collector.metrics || []).filter((m) => m.type === "status");
}

function serviceSummary(collector) {
  const nums = (collector.metrics || []).filter((m) => m.type === "number");
  const up = nums.find((m) => String(m.label).toUpperCase() === "UP");
  const down = nums.find((m) => String(m.label).toUpperCase() === "DOWN");
  return { up: up ? up.value : "—", down: down ? down.value : "—" };
}

function withMetrics(collector, labelSet) {
  if (!collector) return null;
  return {
    ...collector,
    metrics: (collector.metrics || []).filter((m) =>
      labelSet.has(String(m.label || "").toUpperCase()),
    ),
  };
}

function metricValue(collector, label) {
  const m = (collector?.metrics || []).find(
    (x) => String(x.label).toUpperCase() === label,
  );
  return m ? m.value : "—";
}

/** Visual status tile — color + name, almost no prose. */
function renderServiceTile(metric, index, options = {}) {
  const status = metric.state || "error";
  const size = options.size || "";
  const note = options.showNote && metric.note
    ? `<div class="svc-tile-note">${esc(metric.note)}</div>`
    : "";
  const art = options.art || "";
  const sizeClass = size ? ` svc-tile--${size}` : "";
  return `<article class="svc-tile${sizeClass}" data-id="${esc(metric.id || metric.label)}" data-status="${esc(status)}">
    <div class="svc-tile-bar" aria-hidden="true"></div>
    ${art}
    <div class="svc-tile-name">${esc(metric.label)}</div>
    <div class="svc-tile-led" data-state="${esc(status)}"></div>
    <div class="svc-tile-state">${esc(metric.value)}</div>
    ${note}
  </article>`;
}

function renderMcPanel(metric) {
  const status = metric.state || "error";
  return `<article class="mc-hero" data-status="${esc(status)}">
    <div class="mc-hero-led" data-state="${esc(status)}" aria-hidden="true"></div>
    <div class="mc-hero-label">MINECRAFT</div>
    <div class="mc-hero-state" data-state="${esc(status)}">${esc(metric.value)}</div>
    ${metric.note ? `<div class="mc-hero-note">${esc(metric.note)}</div>` : ""}
  </article>`;
}

function cardOrEmpty(collector, emptyMsg, options = {}) {
  if (!collector) return `<div class="empty-state">${esc(emptyMsg || "offline")}</div>`;
  if (collector.error && !(collector.metrics || []).length) {
    return `<div class="empty-state">${esc(collector.error)}</div>`;
  }
  return renderCard(collector, 0, options);
}

/** Net = Pi-hole (controls + chart) + VPN traffic — not a Home clone. */
function renderNetView(data) {
  if (!netGrid) return;
  const pihole = findCollector(data, "pihole");
  const vpn = findCollector(data, "wireguard");

  netGrid.innerHTML = `
    <div class="page-slot page-slot--ads">${cardOrEmpty(pihole, "pihole offline")}</div>
    <div class="page-slot page-slot--vpn">${cardOrEmpty(vpn, "vpn offline", { chartFocus: true })}</div>`;
}

/** Host = System + Disk, charts fill each column. */
function renderHostView(data) {
  if (!hostGrid) return;
  const rawSys = findCollector(data, "system");
  const sys = withMetrics(rawSys, SYS_EXTRA_LABELS);
  const painted = sys && rawSys
    ? { ...sys, chart: rawSys.chart, status: rawSys.status, label: "System" }
    : sys;
  const disk = findCollector(data, "smart");

  hostGrid.innerHTML = `
    <div class="page-slot page-slot--sys">${cardOrEmpty(painted, "system offline", { chartFocus: true })}</div>
    <div class="page-slot page-slot--disk">${cardOrEmpty(disk, "disk offline", { chartFocus: true })}</div>`;
}

/** Apps = only the few that matter (no long systemd dump). */
const APPS_SHOW = ["minecraft", "jellyfin", "samba", "pihole", "caddy", "hub"];

function renderAppsView(collector) {
  if (!appsGrid) return;
  if (!collector) {
    appsGrid.innerHTML = `<div class="empty-state">services offline</div>`;
    return;
  }
  if (collector.error && !serviceStatusMetrics(collector).length) {
    appsGrid.innerHTML = `<div class="empty-state">${esc(collector.error)}</div>`;
    return;
  }

  const byId = new Map(
    serviceStatusMetrics(collector).map((m) => [String(m.id || "").toLowerCase(), m]),
  );
  const parts = [];
  for (const id of APPS_SHOW) {
    const m = byId.get(id);
    if (!m) continue;
    if (id === "minecraft") {
      parts.push(`<div class="apps-feature apps-feature--mc">${renderMcPanel(m)}</div>`);
    } else {
      parts.push(`<div class="apps-feature">${renderServiceTile(m, 0, {
        showNote: Boolean(m.media || m.note),
        size: "lg",
      })}</div>`);
    }
  }

  appsGrid.innerHTML = parts.length
    ? `<div class="apps-featured apps-featured--six">${parts.join("")}</div>`
    : `<div class="empty-state">no apps configured</div>`;
}

/* ---------- page navigation ---------- */

function pageFromHash() {
  const raw = (location.hash || "").replace(/^#/, "").toLowerCase();
  if (PAGES.includes(raw)) return raw;
  if (PAGE_ALIASES[raw]) return PAGE_ALIASES[raw];
  return "hub";
}

function setPage(page, options = {}) {
  const next = PAGES.includes(page) ? page : "hub";
  currentPage = next;

  document.querySelectorAll(".view").forEach((el) => {
    const on = el.dataset.page === next;
    el.classList.toggle("is-active", on);
    el.hidden = !on;
  });

  if (pageNav) {
    pageNav.querySelectorAll(".page-tab").forEach((btn) => {
      const on = btn.dataset.page === next;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  if (footPageEl) footPageEl.textContent = PAGE_TITLE[next] || next;

  if (options.updateHash !== false) {
    const want = `#${next}`;
    if (location.hash !== want) {
      history.replaceState(null, "", want);
    }
  }

  if (lastDashboard) {
    paintPage(lastDashboard);
  }
}

function paintPage(data) {
  const svc = servicesCollector(data);
  if (currentPage === "hub") {
    // Home = overview only (classic cards). Deep charts live on Net / Host.
    const collectors = (data.collectors || [])
      .filter((c) => c.id !== "services")
      .map((c) => (c.id === "system" ? withMetrics(c, HUB_SYSTEM_LABELS) : c));
    if (!collectors.length) {
      grid.innerHTML = `<div class="empty-state">no active modules</div>`;
    } else {
      grid.innerHTML = collectors.map((c, i) => renderCard(c, i)).join("");
    }
  } else if (currentPage === "net") {
    renderNetView(data);
  } else if (currentPage === "host") {
    renderHostView(data);
  } else if (currentPage === "apps") {
    renderAppsView(svc);
  }
}

if (pageNav) {
  pageNav.addEventListener("click", (event) => {
    const btn = event.target.closest(".page-tab");
    if (!btn || !pageNav.contains(btn)) return;
    setPage(btn.dataset.page);
  });
}

window.addEventListener("hashchange", () => {
  setPage(pageFromHash(), { updateHash: false });
});

/* Keyboard: 1–4 or arrows */
document.addEventListener("keydown", (event) => {
  if (event.target && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
  const key = event.key;
  const digit = key >= "1" && key <= "4" ? Number(key) - 1 : -1;
  if (digit >= 0 && digit < PAGES.length) setPage(PAGES[digit]);
  else if (key === "ArrowLeft" || key === "ArrowRight") {
    const i = PAGES.indexOf(currentPage);
    const delta = key === "ArrowRight" ? 1 : -1;
    setPage(PAGES[(i + delta + PAGES.length) % PAGES.length]);
  }
});

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
    lastDashboard = data;

    setOverall(data.status);
    paintPage(data);
    footUptimeEl.textContent = `UP ${data.uptime || "—"}`;
    footModeEl.textContent = "LIVE";
  } catch (err) {
    setOverall("error");
    footModeEl.textContent = "DOWN";
    if (currentPage === "hub" && grid && !grid.children.length) {
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

/* Akcje też na stronach fokusowych (DNS ma przyciski Pi-hole). */
document.querySelector(".shell")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || grid?.contains(button)) return;
  runAction(button.dataset.collector, button.dataset.action, button);
});

tickClock();
setInterval(tickClock, 1000);

/* Start na hashu (np. kiosk z zakładką #mc) */
setPage(pageFromHash(), { updateHash: true });

/* Boot splash → fade out */
function runBootSplash() {
  const splash = document.getElementById("boot-splash");
  const label = document.getElementById("boot-label");
  if (!splash || !label) {
    refreshDashboard();
    setInterval(refreshDashboard, POLL_MS);
    return;
  }

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
