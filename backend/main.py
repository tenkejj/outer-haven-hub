"""Outer Haven Hub — punkt wejścia backendu (agregatora).

Rola tego pliku (celowo mała — cała wiedza o źródłach siedzi we wtyczkach):
  1. wczytać config.yaml i zbudować włączone collectory (registry),
  2. wystawić GET /api/dashboard — równoległa agregacja wyników wszystkich
     collectorów, z cache per źródło i pełną izolacją błędów,
  3. wystawić POST /api/collectors/{id}/actions/{action} — akcje z ekranu,
  4. serwować statyczny frontend (katalog ../frontend).

BEZPIECZEŃSTWO (sekcja 7 specyfikacji): backend nasłuchuje WYŁĄCZNIE na
127.0.0.1:8090 — patrz deploy/outer-haven-hub.service. Na sieć LAN/WireGuard
wystawia go dopiero Caddy jako reverse proxy. Frontend i API są same-origin,
więc nie potrzebujemy (i nie włączamy) CORS.

Uruchomienie deweloperskie (z katalogu backend/):
    uvicorn main:app --host 127.0.0.1 --port 8090
    HUB_DEMO=1 uvicorn main:app --host 127.0.0.1 --port 8090   # sztuczne dane
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import time
from collections.abc import AsyncIterator
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response, StreamingResponse
from starlette.types import Scope

from collectors.base import Collector, STATUS_ERROR, STATUS_OK

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

# Twardy limit czasu na pojedynczy collect() — jedno wiszące źródło (np.
# nieodpowiadające API) nie może przytrzymać całej odpowiedzi /api/dashboard.
COLLECT_TIMEOUT_S = 10.0

# Co ile sekund strumień SSE wypycha nowy stan. Nie jest to częstotliwość
# odpytywania źródeł — te mają własny refresh_interval w cache.
STREAM_INTERVAL_S = 2.0

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hub")

# Sekrety (hasło aplikacji Pi-hole) — z pliku .env obok main.py.
# W wersji produkcyjnej ten sam plik wskazuje EnvironmentFile= w systemd.
load_dotenv(BACKEND_DIR / ".env")


def load_config() -> dict:
    """Wczytuje config.yaml z korzenia repo (albo ze ścieżki w HUB_CONFIG)."""
    path = Path(os.environ.get("HUB_CONFIG", REPO_ROOT / "config.yaml"))
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class CachedCollector:
    """Opakowanie na collector: cache wyniku + izolacja błędów (Faza 4).

    Po co cache: frontend odpytuje /api/dashboard co ~5 s, ale różne źródła
    mają różny koszt i sensowną częstotliwość odświeżania (SMART co 60 s,
    metryki systemowe co 5 s). Każdy collector deklaruje swoje
    refresh_interval, a my trzymamy ostatni wynik i odświeżamy go dopiero,
    gdy się zestarzeje.

    Po co izolacja: wyjątek albo timeout JEDNEGO collectora zamieniamy na
    kartę o statusie "error" z komunikatem — reszta dashboardu działa dalej
    normalnie. To wymóg specyfikacji (Faza 4), wbudowany w rdzeń, nie
    doklejony na końcu.
    """

    def __init__(self, collector: Collector) -> None:
        self.collector = collector
        self._payload: dict | None = None
        self._fetched_at = 0.0  # time.monotonic() — odporne na zmiany zegara (NTP)
        self._lock = asyncio.Lock()

    def _is_fresh(self) -> bool:
        return (
            self._payload is not None
            and (time.monotonic() - self._fetched_at) < self.collector.refresh_interval
        )

    def invalidate(self) -> None:
        """Wymusza ponowne zbieranie przy następnym get() — po akcji z ekranu."""
        self._payload = None
        self._fetched_at = 0.0

    async def get(self) -> dict:
        if self._is_fresh():
            return self._payload

        async with self._lock:
            # Podwójne sprawdzenie: gdy dwa zapytania przyszły naraz, pierwsze
            # odświeżyło cache, a drugie czekało na locku — nie zbieraj drugi raz.
            if self._is_fresh():
                return self._payload

            try:
                payload = await asyncio.wait_for(
                    self.collector.snapshot(), timeout=COLLECT_TIMEOUT_S
                )
            except TimeoutError:
                log.warning("collector %s: timeout po %.0f s", self.collector.id, COLLECT_TIMEOUT_S)
                payload = self._error_payload(f"no response within {COLLECT_TIMEOUT_S:.0f}s")
            except Exception as exc:
                # Celowo szeroki wyjątek: dowolna awaria źródła (sieć, parsowanie,
                # uprawnienia) ma dać kartę "error", nigdy HTTP 500 całego API.
                log.warning("collector %s: %s", self.collector.id, exc)
                payload = self._error_payload(str(exc) or exc.__class__.__name__)

            payload["updated_at"] = int(time.time())
            self._payload = payload
            self._fetched_at = time.monotonic()
            return payload

    def _error_payload(self, message: str) -> dict:
        return {
            "id": self.collector.id,
            "label": self.collector.label,
            "icon": self.collector.icon,
            "status": STATUS_ERROR,
            "metrics": [],
            "chart": None,
            "actions": [],
            "layout": "default",
            "error": message,
        }


def build_runners() -> list[CachedCollector]:
    if os.environ.get("HUB_DEMO") == "1":
        # Tryb deweloperski: sztuczne dane, patrz collectors/demo.py.
        from collectors.demo import DEMO_COLLECTORS
        log.warning("HUB_DEMO=1 — serwuję SZTUCZNE dane (tryb deweloperski)")
        instances = DEMO_COLLECTORS
    else:
        from collectors.registry import build_enabled_collectors
        instances = build_enabled_collectors(load_config())
        log.info("Włączone collectory: %s", ", ".join(c.id for c in instances) or "(żaden)")
    return [CachedCollector(c) for c in instances]


RUNNERS = build_runners()
RUNNERS_BY_ID = {runner.collector.id: runner for runner in RUNNERS}

# Do wyliczania zbiorczego statusu: bierzemy najgorszy ze wszystkich kart.
_SEVERITY = {STATUS_OK: 0, "warning": 1, STATUS_ERROR: 2}

app = FastAPI(title="Outer Haven Hub", version="1.0")


def _uptime_human() -> str:
    """Uptime hosta (Pi) do footera — krótki format jak na karcie SYSTEM."""
    try:
        seconds = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return "—"
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


async def _collect_all() -> tuple[list[dict], str]:
    """Wszystkie karty RÓWNOLEGLE + zbiorczy (najgorszy) status."""
    # gather = wszystkie collectory RÓWNOLEGLE (sekcja 3.2 specyfikacji);
    # wolne źródło nie opóźnia szybkich, bo każdy get() i tak ma swój cache.
    cards = list(await asyncio.gather(*(runner.get() for runner in RUNNERS)))
    overall = max(
        (card["status"] for card in cards),
        key=lambda status: _SEVERITY.get(status, 2),
        default=STATUS_OK,
    )
    return cards, overall


def _envelope(cards: list[dict], overall: str) -> dict:
    return {
        "generated_at": int(time.time()),
        "host": os.environ.get("HUB_NAME") or platform.node(),
        "uptime": _uptime_human(),
        # Footer zawsze LIVE — HUB_DEMO dotyczy tylko źródeł danych, nie etykiety UI.
        "mode": "LIVE",
        "status": overall,
        "collectors": cards,
    }


@app.get("/api/dashboard")
async def dashboard() -> dict:
    """Pełny stan RAZEM z punktami wykresów — używa go stary frontend."""
    cards, overall = await _collect_all()
    return _envelope(cards, overall)


def _without_history(card: dict) -> dict:
    """Karta bez punktów wykresu.

    Historia Pi-hole to 144 punkty × 2 serie — wożenie tego w każdym tiku
    strumienia jest marnotrawstwem, bo wykres widać tylko na jednej stronie.
    Panel dociąga go osobno przez /api/history/<id>, gdy go potrzebuje.
    """
    lean = dict(card)
    chart = card.get("chart")
    lean["chart"] = None
    lean["has_chart"] = bool(chart and chart.get("series"))
    return lean


async def _state_payload() -> dict:
    cards, overall = await _collect_all()
    return _envelope([_without_history(card) for card in cards], overall)


@app.get("/api/state")
async def state() -> dict:
    """Lekki stan (bez historii wykresów) — dla panelu instrumentowego."""
    return await _state_payload()


@app.get("/api/history/{collector_id}")
async def history(collector_id: str) -> dict:
    """Same punkty wykresu jednego źródła — dociągane, gdy panel je pokazuje.

    Nie wymusza nowego collect(): czyta ten sam cache co /api/state, więc
    wejście na stronę z wykresem nie generuje ruchu do Pi-hole ani sudo.
    """
    runner = RUNNERS_BY_ID.get(collector_id)
    if runner is None:
        raise HTTPException(status_code=404, detail=f"nieznany collector: {collector_id}")
    card = await runner.get()
    return {"id": collector_id, "chart": card.get("chart")}


@app.get("/api/stream")
async def stream() -> StreamingResponse:
    """Server-Sent Events ze stanem — panel nie musi pollować.

    Po co: przy pollingu frontend przebudowywał cały DOM co 5 s, więc nie
    dało się animować pojedynczej wartości. Push pozwala aktualizować
    konkretne pola w miejscu.

    SSE, nie WebSocket — jednokierunkowy strumień w zwykłym HTTP, bez nowej
    zależności (akcje nadal idą przez POST). Za Caddy trzeba pamiętać, że
    reverse_proxy potrafi buforować odpowiedzi; panel ma watchdog i przy
    ciszy dłuższej niż kilka sekund sam wraca do pollowania /api/state.
    """

    async def events() -> AsyncIterator[bytes]:
        while True:
            payload = await _state_payload()
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
            await asyncio.sleep(STREAM_INTERVAL_S)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Wyłącza buforowanie w typowych proxy (nginx honoruje to wprost).
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/collectors/{collector_id}/actions/{action_id}")
async def collector_action(collector_id: str, action_id: str) -> dict:
    """Uruchamia akcję zadeklarowaną przez collector (ekran dotykowy).

    Frontend nie zna semantyki akcji — zna tylko id z pola `actions` karty.
    Po sukcesie invalidujemy cache tego źródła, żeby kolejny poll pokazał
    świeży stan (np. „blokowanie WYŁĄCZONE”).
    """
    runner = RUNNERS_BY_ID.get(collector_id)
    if runner is None:
        raise HTTPException(status_code=404, detail=f"nieznany collector: {collector_id}")

    try:
        result = await asyncio.wait_for(
            runner.collector.run_action(action_id),
            timeout=COLLECT_TIMEOUT_S,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="akcja przekroczyła limit czasu") from exc
    except Exception as exc:
        log.warning("akcja %s/%s: %s", collector_id, action_id, exc)
        raise HTTPException(status_code=400, detail=str(exc) or exc.__class__.__name__) from exc

    runner.invalidate()
    return {"ok": True, "collector": collector_id, "action": action_id, **(result or {})}


# Frontend montujemy NA KOŃCU — trasy /api/* mają pierwszeństwo przed plikami.
# Kiosk Chromium potrafi trzymać stary style.css mimo git pull — no-cache
# na HTML/CSS/JS wymusza świeży layout po restarcie serwisu.


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles z Cache-Control: no-cache dla assetów UI (nie fontów/obrazów)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        lower = path.lower()
        if lower.endswith((".html", ".css", ".js")) or lower in ("", "/", "index.html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


app.mount("/", NoCacheStaticFiles(directory=REPO_ROOT / "frontend", html=True), name="frontend")
