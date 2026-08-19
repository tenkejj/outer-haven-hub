/* Outer Haven Hub — panel instrumentowy.
   Nie renderuje kart. Renderuje STRONY: jedna strona = jeden collector,
   a na stronie jedna wielka liczba (metryka `importance: "primary"`).

   Trzy różnice względem starego app.js — to one były źródłem problemów:

   1. SKALA RÓWNOMIERNA. Stary UI robił scale(sx, sy) osobno w każdej osi,
      więc font i linie były rozciągane („przybliżone i ściśnięte").
      Tu jest jedno `scale(s)` = min(w/1024, h/600); na panelu 1024×600
      wypada 1.0, czyli piksel w piksel.

   2. PUNKTOWE AKTUALIZACJE. Stary UI robił grid.innerHTML = ... co 5 s,
      co uniemożliwiało jakąkolwiek animację. Tu DOM strony budujemy raz
      (albo dopiero gdy zmieni się KSZTAŁT danych), a potem wpisujemy
      wartości w węzły [data-k].

   3. BRAK PARSOWANIA STRINGÓW. Backend przysyła gotowe `num` / `unit` /
      `range` (patrz collectors/base.py), więc UI nie zgaduje, czy "46%"
      to liczba. To był realny bug: Number("46%") → NaN → wskaźnik 0%.

   Strony biorą się z listy collectorów w odpowiedzi API — nowe źródło
   danych dostaje własną stronę bez dotykania tego pliku. */

const DESIGN_W = 1024;
const DESIGN_H = 600;

const POLL_MS = 3000;          // fallback, gdy SSE nie działa (np. bufor w proxy)
const WATCHDOG_MS = 8000;      // cisza w strumieniu dłuższa niż to → wróć do pollingu
const HISTORY_MS = 20000;      // jak często odświeżać punkty sparkline
const CYCLE_MS = 12000;        // auto-przełączanie stron (tryb „tablica przylotów")
const CYCLE_HOLD_MS = 45000;   // po dotknięciu ekranu wstrzymaj rotację
const TOAST_MS = 4200;
const SPARK_POINTS = 120;      // do tylu punktów downsamplujemy serie

/* Reguła kształtu: źródło z wieloma statusami (systemd) pokazuje siatkę
   lampek zamiast sparkline. Decyduje POSTAĆ DANYCH, nie id collectora —
   dzięki temu przyszły collector z listą kontenerów dostanie to samo. */
const CHIPS_MIN = 5;

const STATE_WORD = { ok: "ONLINE", warning: "CAUTION", error: "ALERT" };

const el = {
  panel: document.getElementById("panel"),
  rail: document.getElementById("rail"),
  stage: document.getElementById("stage"),
  dock: document.getElementById("dock"),
  dockHair: document.getElementById("dock-hair"),
  nav: document.getElementById("nav"),
  overall: document.getElementById("overall"),
  clockTime: document.getElementById("clock-time"),
  clockUp: document.getElementById("clock-up"),
  hostName: document.getElementById("host-name"),
  toast: document.getElementById("toast"),
  cycleBtn: document.getElementById("cycle-btn"),
  boot: document.getElementById("boot"),
  bootWord: document.getElementById("boot-word"),
};

let payload = null;        // ostatni stan z /api/state (albo SSE)
let pageId = null;         // id aktualnie pokazywanego collectora
let stageShape = "";       // klucz kształtu — zmiana wymusza przebudowę DOM
let navShape = "";
let railShape = "";
let histories = new Map(); // collector id → chart (punkty sparkline)
let historyAt = new Map(); // collector id → timestamp ostatniego pobrania
let actionBusy = false;
let toastTimer = 0;
let cycleOn = false;
let cycleTimer = 0;
let holdUntil = 0;
let source = null;
let pollTimer = 0;
let watchdog = 0;

/* ---------- viewport: jedna, równomierna skala ---------- */

function fit() {
  const scale = Math.min(window.innerWidth / DESIGN_W, window.innerHeight / DESIGN_H);
  el.panel.style.transform = `scale(${scale})`;
  el.panel.style.left = `${Math.round((window.innerWidth - DESIGN_W * scale) / 2)}px`;
  el.panel.style.top = `${Math.round((window.innerHeight - DESIGN_H * scale) / 2)}px`;
}

/* ---------- helpers ---------- */

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** Liczba do wyświetlenia: bez zbędnych zer, ale i bez fałszywej precyzji. */
function fmtNum(num) {
  if (num === null || num === undefined || !Number.isFinite(num)) return "—";
  const abs = Math.abs(num);
  if (Number.isInteger(num)) return String(num);
  if (abs >= 100) return String(Math.round(num));
  if (abs >= 10) return num.toFixed(1);
  return num.toFixed(abs < 1 ? 2 : 1);
}

/** Ułamek 0–1 pozycji wartości w zadeklarowanym zakresie (do wskaźników). */
function ratio(metric) {
  if (!metric || metric.num === null || !Array.isArray(metric.range)) return null;
  const [lo, hi] = metric.range;
  if (!(hi > lo)) return null;
  return Math.max(0, Math.min(1, (metric.num - lo) / (hi - lo)));
}

function metricsOf(card) {
  return Array.isArray(card?.metrics) ? card.metrics : [];
}

/** Jedno miejsce, które rozdziela metryki na strefy ekranu.
    Dzięki temu ta sama wartość nie może trafić naraz na scenę i do doku —
    a to był realny problem starego UI (Pi-hole widoczne na dwóch stronach). */
function partition(card) {
  const metrics = metricsOf(card);
  const primary = metrics.find((m) => m.importance === "primary") || null;
  const statuses = metrics.filter((m) => m.type === "status");
  // Wiele statusów = siatka lampek zamiast sparkline (np. lista systemd).
  const useChips = statuses.length >= CHIPS_MIN;

  // Kandydaci na drugi plan: bez primary, bez statusów (te mają płytkę
  // albo siatkę) i bez metryk z szyny (te i tak widać zawsze po lewej).
  const rest = metrics.filter((m) => m !== primary && m.type !== "status" && !m.rail);
  const asides = useChips ? [] : rest.filter((m) => m.num !== null).slice(0, 2);
  const dock = rest.filter((m) => !asides.includes(m)).slice(0, 4);

  return { primary, statuses, useChips, asides, dock };
}

function cards() {
  return Array.isArray(payload?.collectors) ? payload.collectors : [];
}

function cardById(id) {
  return cards().find((c) => c.id === id) || null;
}

function showToast(message, kind = "") {
  el.toast.hidden = false;
  el.toast.dataset.kind = kind;
  el.toast.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.toast.hidden = true; }, TOAST_MS);
}

/* ---------- sparkline ---------- */

function downsample(points, max) {
  const src = (points || []).map(Number).filter(Number.isFinite);
  if (src.length <= max) return src;
  const out = [];
  const bucket = src.length / max;
  for (let i = 0; i < max; i++) {
    const from = Math.floor(i * bucket);
    const to = Math.max(from + 1, Math.floor((i + 1) * bucket));
    let sum = 0;
    for (let j = from; j < to && j < src.length; j++) sum += src[j];
    out.push(sum / (to - from));
  }
  return out;
}

/** Sparkline jako TŁO scenu: obszar + linia, bez osi i bez ramki.
    Rysujemy w układzie 1000×200 i rozciągamy przez preserveAspectRatio. */
function sparkSvg(chart) {
  const series = (chart?.series || [])
    .map((s) => ({ role: s.role || "muted", points: downsample(s.points, SPARK_POINTS) }))
    .filter((s) => s.points.length > 1);
  if (!series.length) return "";

  const W = 1000;
  const H = 200;
  const all = series.flatMap((s) => s.points);
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  // Margines skali, żeby płaska seria (temp 28–31) też miała amplitudę —
  // ale mały, bo za duży spłaszczał przebieg do cienkiego paska.
  const span = Math.max(hi - lo, Math.abs(hi) * 0.08, 1);
  const yLo = lo - span * 0.08;
  const yHi = hi + span * 0.12;

  const x = (i, len) => (i / Math.max(len - 1, 1)) * W;
  const y = (v) => H - ((v - yLo) / (yHi - yLo)) * H;

  const path = (pts) =>
    pts.map((v, i) => `${i ? "L" : "M"} ${x(i, pts.length).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");

  // Główna seria = accent, jeśli jest; inaczej pierwsza.
  const main = series.find((s) => s.role === "accent") || series[0];
  const other = series.filter((s) => s !== main);

  const area = `${path(main.points)} L ${W} ${H} L 0 ${H} Z`;
  const extra = other
    .map((s) => `<path class="spark-line-2" d="${path(s.points)}" />`)
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <path class="spark-area" d="${area}" />
    ${extra}
    <path class="spark-line" d="${path(main.points)}" />
    <line class="spark-base" x1="0" y1="${H - 0.5}" x2="${W}" y2="${H - 0.5}" />
  </svg>`;
}

async function loadHistory(id, force = false) {
  const last = historyAt.get(id) || 0;
  if (!force && Date.now() - last < HISTORY_MS) return;
  historyAt.set(id, Date.now());
  try {
    const res = await fetch(`/api/history/${encodeURIComponent(id)}`, { cache: "no-store" });
    if (!res.ok) return;
    const body = await res.json();
    histories.set(id, body.chart || null);
    if (id === pageId) paintSpark();
  } catch (err) {
    console.warn("history failed:", err);
  }
}

function paintSpark() {
  const host = el.stage.querySelector(".spark");
  if (!host) return;
  const chart = histories.get(pageId);
  const svg = chart ? sparkSvg(chart) : "";
  if (host.dataset.filled === "1" && !svg) return;
  host.innerHTML = svg;
  host.dataset.filled = svg ? "1" : "0";
}

/* ---------- rail: wskaźniki życia (wszystkie collectory razem) ---------- */

function vitals() {
  const out = [];
  for (const card of cards()) {
    for (const m of metricsOf(card)) {
      if (!m.rail) continue;
      out.push({ ...m, cap: m.rail_label || m.label, key: `${card.id}:${m.label}` });
    }
  }
  return out;
}

function paintRail() {
  const items = vitals();
  const shape = items.map((v) => v.key).join("|");

  if (shape !== railShape) {
    railShape = shape;
    el.rail.innerHTML = items.map((v) => `
      <div class="vital" data-key="${esc(v.key)}">
        <span class="vital-cap">${esc(v.cap)}</span>
        <span class="vital-val" data-k="val">—</span>
        <div class="vital-track"><div class="vital-bar" data-k="bar"></div></div>
      </div>`).join("");
  }

  for (const v of items) {
    const node = el.rail.querySelector(`.vital[data-key="${CSS.escape(v.key)}"]`);
    if (!node) continue;
    node.dataset.state = v.state || "ok";
    const val = node.querySelector('[data-k="val"]');
    const unit = v.unit ? `<span class="vital-unit">${esc(v.unit)}</span>` : "";
    val.innerHTML = `${esc(fmtNum(v.num))}${unit}`;
    const r = ratio(v);
    const bar = node.querySelector('[data-k="bar"]');
    bar.style.width = r === null ? "0" : `${(r * 100).toFixed(1)}%`;
  }
}

/* ---------- nav ---------- */

function paintNav() {
  const list = cards();
  const shape = list.map((c) => c.id).join("|");

  if (shape !== navShape) {
    navShape = shape;
    el.nav.innerHTML = list.map((c) => `
      <button type="button" class="tab" role="tab" data-page="${esc(c.id)}">
        <span class="tab-led" aria-hidden="true"></span>
        <span class="tab-name">${esc(c.label)}</span>
      </button>`).join("");
  }

  for (const c of list) {
    const btn = el.nav.querySelector(`.tab[data-page="${CSS.escape(c.id)}"]`);
    if (!btn) continue;
    btn.dataset.status = c.status || "error";
    const on = c.id === pageId;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  }
}

/* ---------- stage ---------- */

/** Klucz kształtu — DOM przebudowujemy tylko, gdy zmieni się struktura
    (inna strona, inny zestaw metryk), a nie gdy zmienią się wartości. */
function shapeKey(card) {
  const { useChips } = partition(card);
  return [
    card.id,
    card.error ? "err" : "ok",
    useChips ? "chips" : "spark",
    metricsOf(card).map((m) => `${m.label}/${m.importance}/${m.type}`).join(","),
  ].join("#");
}

function buildStage(card) {
  const { primary, statuses, useChips, asides } = partition(card);

  if (card.error && !metricsOf(card).length) {
    return `
      <div class="stage-head"><span class="stage-title">${esc(card.label)}</span></div>
      <div class="stage-error">${esc(card.error)}</div>`;
  }

  const chips = statuses;
  // Płytka stanu — tylko gdy statusów jest mało (inaczej robimy z nich siatkę).
  const plate = !useChips ? chips[0] : null;

  const spark = useChips ? "" : `<div class="spark" data-k="spark"></div>`;

  const head = `
    <div class="stage-head">
      <span class="stage-title">${esc(card.label)}</span>
      <span class="stage-tag" data-k="tag"></span>
    </div>`;

  const plateHtml = plate
    ? `<div class="plate" data-k="plate">
         <span class="plate-led" aria-hidden="true"></span>
         <span class="plate-cap">${esc(plate.label)}</span>
         <span class="plate-val" data-k="plateval">—</span>
       </div>`
    : "";

  const main = `
    <div class="stage-main">
      <span class="big" data-k="big">—</span>
      <span class="big-cap" data-k="bigcap">${esc(primary ? primary.label : "")}</span>
      ${plateHtml}
    </div>`;

  const chipsHtml = useChips
    ? `<div class="chips">${chips.map((m) => `
        <div class="chip" data-chip="${esc(m.id || m.label)}">
          <span class="chip-led" aria-hidden="true"></span>
          <span class="chip-name">${esc(m.label)}</span>
        </div>`).join("")}</div>`
    : "";

  const foot = asides.length
    ? `<div class="stage-foot">${asides.map((m) => `
        <div class="aside-num" data-aside="${esc(m.label)}">
          <span class="aside-cap">${esc(m.label)}</span>
          <span class="aside-val" data-k="asideval">—</span>
        </div>`).join("")}</div>`
    : (useChips ? "" : `<div class="stage-foot"></div>`);

  const errorHtml = card.error
    ? `<div class="stage-error">${esc(card.error)}</div>`
    : "";

  return spark + head + main + chipsHtml + foot + errorHtml;
}

function paintStage() {
  const card = cardById(pageId);
  if (!card) {
    el.stage.innerHTML = `<div class="stage-head"><span class="stage-title">—</span></div>`;
    return;
  }

  const shape = shapeKey(card);
  if (shape !== stageShape) {
    stageShape = shape;
    el.stage.innerHTML = buildStage(card);
    paintSpark();
  }

  el.stage.dataset.status = card.status || "error";

  const { primary, statuses, useChips } = partition(card);

  const tag = el.stage.querySelector('[data-k="tag"]');
  if (tag) tag.textContent = STATE_WORD[card.status] || "—";

  const big = el.stage.querySelector('[data-k="big"]');
  if (big && primary) {
    if (primary.num === null) {
      // Wartość nieliczbowa (np. "ON") — mniejszy stopień, żeby się zmieściła.
      big.classList.add("big--text");
      big.textContent = String(primary.value ?? "—");
    } else {
      big.classList.remove("big--text");
      const unit = primary.unit ? `<span class="big-unit">${esc(primary.unit)}</span>` : "";
      big.innerHTML = `${esc(fmtNum(primary.num))}${unit}`;
    }
  }

  const plate = el.stage.querySelector('[data-k="plate"]');
  if (plate) {
    const m = statuses[0];
    plate.dataset.state = m?.state || "ok";
    const val = plate.querySelector('[data-k="plateval"]');
    if (val) val.textContent = String(m?.value ?? "—");
  }

  for (const node of el.stage.querySelectorAll("[data-aside]")) {
    const m = metricsOf(card).find((x) => x.label === node.dataset.aside);
    const val = node.querySelector('[data-k="asideval"]');
    if (!m || !val) continue;
    const unit = m.unit ? `<span class="aside-unit">${esc(m.unit)}</span>` : "";
    val.innerHTML = `${esc(fmtNum(m.num))}${unit}`;
  }

  for (const node of el.stage.querySelectorAll("[data-chip]")) {
    const m = statuses.find((x) => String(x.id || x.label) === node.dataset.chip);
    node.dataset.state = m?.state || "error";
  }

  // Historię ciągniemy tylko dla stron, które faktycznie mają wykres —
  // karta z błędem albo siatka lampek nie ma czego rysować.
  if (!useChips && card.has_chart) loadHistory(card.id);
}

/* ---------- dock ---------- */

/** Pi-hole pokazuje pozostały czas („OFF 14M"), nie wybrany preset —
    aktywny OFF bierzemy więc z ostatniej udanej akcji. */
function blockMode(card) {
  const m = metricsOf(card)
    .filter((x) => x.type === "status")
    .find((x) => String(x.label).toUpperCase() === "BLOCK");
  if (!m) return null;
  const raw = String(m.value || "").toUpperCase();
  if (raw.startsWith("ON")) {
    try { sessionStorage.removeItem("oh-off"); } catch (_) { /* ignore */ }
    return { on: true, off: null };
  }
  let off = "any";
  try {
    const saved = sessionStorage.getItem("oh-off");
    if (saved) off = saved;
  } catch (_) { /* ignore */ }
  return { on: false, off };
}

function paintDock() {
  const card = cardById(pageId);
  if (!card) return;

  // Dok bierze dokładnie to, czego nie wzięła scena — patrz partition().
  const details = partition(card).dock;
  const actions = Array.isArray(card.actions) ? card.actions : [];

  // Brak treści → dok znika, a scena poszerza się o jego 156 px.
  // To celowa reguła: pusty dok to dokładnie ta „pustka”, która psuła stary UI.
  const empty = !details.length && !actions.length;
  el.dock.hidden = empty;
  el.dockHair.hidden = empty;
  if (empty) return;

  const mode = blockMode(card);
  const key = [
    card.id,
    details.map((m) => m.label).join(","),
    actions.map((a) => a.id).join(","),
  ].join("#");

  if (el.dock.dataset.key !== key) {
    el.dock.dataset.key = key;
    const list = details.map((m) => `
      <div class="detail" data-detail="${esc(m.label)}">
        <span class="detail-cap">${esc(m.label)}</span>
        <span class="detail-val" data-k="v">—</span>
      </div>`).join("");
    const acts = actions.map((a) => `
      <button type="button" class="act" data-act="${esc(a.id)}"
        data-style="${esc(a.style || "default")}">
        <span class="act-led" aria-hidden="true"></span>
        <span>${esc(a.label)}</span>
      </button>`).join("");
    el.dock.innerHTML =
      (list ? `<div class="dock-list">${list}</div>` : `<div class="dock-list"></div>`)
      + (acts ? `<div class="acts">${acts}</div>` : "");
  }

  for (const node of el.dock.querySelectorAll("[data-detail]")) {
    const m = metricsOf(card).find((x) => x.label === node.dataset.detail);
    const val = node.querySelector('[data-k="v"]');
    if (!m || !val) continue;
    node.dataset.state = m.state || "";
    if (m.num === null) {
      val.classList.add("detail-val--sm");
      val.textContent = String(m.value ?? "—");
    } else {
      val.classList.remove("detail-val--sm");
      const unit = m.unit ? `<span class="detail-unit">${esc(m.unit)}</span>` : "";
      val.innerHTML = `${esc(fmtNum(m.num))}${unit}`;
    }
  }

  for (const btn of el.dock.querySelectorAll("[data-act]")) {
    const id = btn.dataset.act;
    let on = false;
    if (mode) {
      if (id === "block_on") on = mode.on;
      else if (id === "block_off_5") on = !mode.on && (mode.off === "5" || mode.off === "any");
      else if (id === "block_off_15") on = !mode.on && (mode.off === "15" || mode.off === "any");
    }
    btn.classList.toggle("is-on", on);
    btn.disabled = actionBusy;
  }
}

/* ---------- strony ---------- */

function setPage(id, options = {}) {
  const list = cards();
  const next = list.some((c) => c.id === id) ? id : (list[0]?.id || null);
  if (!next) return;
  const changed = next !== pageId;
  pageId = next;

  if (changed) {
    stageShape = "";
    el.dock.dataset.key = "";
    if (cardById(next)?.has_chart) loadHistory(next, true);
  }
  if (options.hash !== false && location.hash !== `#${next}`) {
    history.replaceState(null, "", `#${next}`);
  }
  paint();
}

function pageFromHash() {
  return (location.hash || "").replace(/^#/, "").toLowerCase() || null;
}

function step(delta) {
  const list = cards();
  if (!list.length) return;
  const i = Math.max(0, list.findIndex((c) => c.id === pageId));
  setPage(list[(i + delta + list.length) % list.length].id);
}

/* ---------- auto-rotacja ---------- */

function setCycle(on) {
  cycleOn = on;
  el.cycleBtn.setAttribute("aria-pressed", on ? "true" : "false");
  clearInterval(cycleTimer);
  if (!on) return;
  cycleTimer = setInterval(() => {
    if (Date.now() < holdUntil) return;
    step(1);
  }, CYCLE_MS);
}

/** Dotyk zawsze wstrzymuje rotację — nikt nie chce, żeby ekran uciekł
    spod palca w trakcie czytania. */
function holdCycle() {
  holdUntil = Date.now() + CYCLE_HOLD_MS;
}

/* ---------- rysowanie całości ---------- */

function paint() {
  if (!payload) return;
  el.panel.dataset.status = payload.status || "error";
  el.overall.dataset.status = payload.status || "error";
  el.overall.textContent = STATE_WORD[payload.status] || "LINK";
  el.clockUp.textContent = `UP ${payload.uptime || "—"}`;
  if (payload.host) el.hostName.textContent = String(payload.host).toUpperCase();

  paintRail();
  paintNav();
  paintStage();
  paintDock();
}

function apply(next) {
  payload = next;
  if (!pageId) {
    const wanted = pageFromHash();
    setPage(wanted && cards().some((c) => c.id === wanted) ? wanted : cards()[0]?.id, {
      hash: Boolean(wanted),
    });
    return;
  }
  paint();
}

/* ---------- transport: SSE z fallbackiem na polling ---------- */

function armWatchdog() {
  clearTimeout(watchdog);
  watchdog = setTimeout(() => {
    console.warn("stream silent — switching to polling");
    stopStream();
    startPolling();
  }, WATCHDOG_MS);
}

function stopStream() {
  clearTimeout(watchdog);
  if (source) {
    source.close();
    source = null;
  }
}

function startStream() {
  if (!("EventSource" in window)) {
    startPolling();
    return;
  }
  source = new EventSource("/api/stream");
  source.onmessage = (event) => {
    armWatchdog();
    try {
      apply(JSON.parse(event.data));
      finishBoot();
    } catch (err) {
      console.warn("bad stream payload:", err);
    }
  };
  source.onerror = () => {
    stopStream();
    startPolling();
  };
  armWatchdog();
}

async function pollOnce() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    apply(await res.json());
    finishBoot();
  } catch (err) {
    el.overall.dataset.status = "error";
    el.overall.textContent = "DOWN";
    console.warn("state failed:", err);
  }
}

function startPolling() {
  if (pollTimer) return;
  pollOnce();
  pollTimer = setInterval(pollOnce, POLL_MS);
}

/* ---------- akcje ---------- */

async function runAction(actionId, button) {
  if (actionBusy || !pageId) return;
  actionBusy = true;
  button.disabled = true;
  try {
    const res = await fetch(
      `/api/collectors/${encodeURIComponent(pageId)}/actions/${encodeURIComponent(actionId)}`,
      { method: "POST" },
    );
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    try {
      if (actionId === "block_off_5") sessionStorage.setItem("oh-off", "5");
      else if (actionId === "block_off_15") sessionStorage.setItem("oh-off", "15");
      else if (actionId === "block_on") sessionStorage.removeItem("oh-off");
    } catch (_) { /* ignore */ }
    showToast(body.message || "done", actionId.includes("off") ? "warn" : "");
  } catch (err) {
    showToast(String(err.message || err), "error");
  } finally {
    actionBusy = false;
    button.disabled = false;
    pollOnce();
  }
}

/* ---------- zdarzenia ---------- */

el.nav.addEventListener("click", (event) => {
  const btn = event.target.closest(".tab");
  if (!btn) return;
  holdCycle();
  setPage(btn.dataset.page);
});

el.dock.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-act]");
  if (!btn) return;
  holdCycle();
  runAction(btn.dataset.act, btn);
});

el.cycleBtn.addEventListener("click", () => setCycle(!cycleOn));

/* Przesunięcie palcem w poprzek scenu = następna / poprzednia strona. */
let touchX = 0;
el.stage.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
el.stage.addEventListener("touchend", (e) => {
  const dx = e.changedTouches[0].clientX - touchX;
  if (Math.abs(dx) < 60) return;
  holdCycle();
  step(dx < 0 ? 1 : -1);
}, { passive: true });

window.addEventListener("hashchange", () => {
  const id = pageFromHash();
  if (id) setPage(id, { hash: false });
});

document.addEventListener("keydown", (event) => {
  const list = cards();
  const digit = Number(event.key);
  if (Number.isInteger(digit) && digit >= 1 && digit <= list.length) {
    holdCycle();
    setPage(list[digit - 1].id);
  } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    holdCycle();
    step(event.key === "ArrowRight" ? 1 : -1);
  } else if (event.key === "c") {
    setCycle(!cycleOn);
  }
});

window.addEventListener("resize", fit);
window.addEventListener("orientationchange", fit);

/* ---------- zegar / boot ---------- */

function tickClock() {
  el.clockTime.textContent = new Date().toLocaleTimeString("pl-PL", { hour12: false });
}

let booted = false;
function finishBoot() {
  if (booted) return;
  booted = true;
  el.bootWord.textContent = "LINK ESTABLISHED";
  el.bootWord.classList.add("is-ok");
  setTimeout(() => el.boot.classList.add("is-done"), 420);
  setTimeout(() => el.boot.remove(), 800);
}

fit();
tickClock();
setInterval(tickClock, 1000);

// Auto-rotacja z URL: ?cycle=1 — dla trybu „kiosk bez dotykania".
if (new URLSearchParams(location.search).get("cycle") === "1") setCycle(true);

startStream();
// Pierwszy stan pobieramy od razu, nie czekając na tik strumienia.
pollOnce().then(() => {
  if (source) {
    clearInterval(pollTimer);
    pollTimer = 0;
  }
});
