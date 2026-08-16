"""Collector Pi-hole — statystyki DNS/blokowania przez API Pi-hole v6.

Autentykacja jest sesyjna (sekcja 5/4.1 specyfikacji): logujemy się przez
POST /api/auth hasłem aplikacji (z pliku .env, NIGDY z kodu) i dostajemy SID.
SID wygasa po okresie bezczynności, więc przy odpowiedzi 401 collector
automatycznie loguje się ponownie i ponawia zapytanie.

Akcje z ekranu (POST /api/dns/blocking):
  - block_off_5 / block_off_15 — wyłączenie blokowania na N minut (timer w API),
  - block_on — ponowne włączenie.

ODSTĘPSTWO OD SPECYFIKACJI (jawnie, zgodnie z zasadami projektu):
specyfikacja wymienia endpoint `GET /api/stats/overTimeData10mins` — to nazwa
z API v5. Skoro autentykacja idzie przez POST /api/auth + SID (czyli API v6),
dane historyczne do wykresu bierzemy z odpowiednika w v6: `GET /api/history`
(te same kubełki 10-minutowe z ostatnich 24 h). Cel i zawartość — identyczne.
"""

from __future__ import annotations

import os

import httpx

from .base import Collector, STATUS_OK, STATUS_WARNING, run_standalone

HTTP_TIMEOUT_S = 5.0

# id akcji → (blocking_enabled, timer_sekundy | None)
_ACTIONS = {
    "block_off_5": (False, 5 * 60),
    "block_off_15": (False, 15 * 60),
    "block_on": (True, None),
}


def _fmt_count(n: int) -> str:
    """Formatuje licznik do postaci czytelnej z odległości: 12437 -> "12.4k"."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class PiholeCollector(Collector):
    id = "pihole"
    label = "Pi-hole"
    icon = "shield"
    refresh_interval = 10

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        # Adres bazowy z config.yaml; domyślnie Pi-hole na tej samej maszynie.
        self.base_url = str(self.settings.get("base_url", "http://127.0.0.1")).rstrip("/")
        self._sid: str | None = None
        self._client: httpx.AsyncClient | None = None

    # --------------------------------------------------------- sesja / HTTP

    @property
    def _password(self) -> str:
        # Hasło czytamy leniwie (dopiero przy pierwszym zapytaniu), żeby brak
        # .env nie wywracał całego backendu przy starcie — tylko tę kartę.
        password = os.environ.get("PIHOLE_APP_PASSWORD", "")
        if not password:
            raise RuntimeError(
                "Brak PIHOLE_APP_PASSWORD w backend/.env — "
                "wygeneruj hasło aplikacji w Pi-hole (Settings → Web Interface/API)"
            )
        return password

    def _ensure_client(self) -> httpx.AsyncClient:
        # Jeden klient HTTP na cały czas życia collectora — utrzymuje
        # połączenie keep-alive zamiast otwierać TCP przy każdym odpytaniu.
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=HTTP_TIMEOUT_S)
        return self._client

    async def _login(self) -> None:
        response = await self._ensure_client().post("/api/auth", json={"password": self._password})
        if response.status_code != 200:
            raise RuntimeError(
                f"Logowanie do Pi-hole nieudane (HTTP {response.status_code}) — "
                "sprawdź hasło aplikacji w backend/.env"
            )
        session = response.json().get("session") or {}
        if not session.get("valid") or not session.get("sid"):
            raise RuntimeError("Pi-hole odrzucił hasło aplikacji")
        self._sid = session["sid"]

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """HTTP z SID; przy 401 jednorazowy re-login. Puste ciało → {}."""
        client = self._ensure_client()
        for attempt in (1, 2):
            if self._sid is None:
                await self._login()
            response = await client.request(
                method, path, headers={"X-FTL-SID": self._sid}, **kwargs
            )
            if response.status_code == 401 and attempt == 1:
                self._sid = None
                continue
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
        raise RuntimeError("Pi-hole odrzuca sesję mimo ponownego logowania")

    async def _get(self, path: str) -> dict:
        return await self._request("GET", path)

    # --------------------------------------------------------------- akcje

    def list_actions(self, data: dict) -> list[dict]:
        # Stały zestaw — krótkie etykiety pod duże cele dotykowe na 7".
        blocking_on = bool(data.get("_blocking_enabled", True))
        return [
            {"id": "block_off_5", "label": "Pauza 5 min", "style": "warn", "group": "block"},
            {"id": "block_off_15", "label": "Pauza 15 min", "style": "warn", "group": "block"},
            {
                "id": "block_on",
                "label": "Włącz",
                # Podświetl „Włącz” gdy blokowanie jest wyłączone — to wtedy
                # główna akcja naprawcza na karcie.
                "style": "accent" if not blocking_on else "default",
                "group": "block",
            },
        ]

    async def run_action(self, action_id: str) -> dict:
        if action_id not in _ACTIONS:
            raise RuntimeError(f"nieznana akcja: {action_id}")

        enabled, timer = _ACTIONS[action_id]
        body: dict = {"blocking": enabled}
        if timer is not None:
            body["timer"] = timer

        # Pi-hole v6: POST /api/dns/blocking
        await self._request("POST", "/api/dns/blocking", json=body)

        if enabled:
            return {"message": "Blokada włączona"}
        minutes = (timer or 0) // 60
        return {"message": f"Blokada wyłączona na {minutes} min"}

    # ------------------------------------------------------------ kontrakt

    async def collect(self) -> dict:
        summary = await self._get("/api/stats/summary")
        blocking = await self._get("/api/dns/blocking")
        history = await self._get("/api/history")

        queries = summary.get("queries", {})
        clients = summary.get("clients") or {}

        total = int(queries.get("total", 0))
        blocked = int(queries.get("blocked", 0))
        percent = float(queries.get("percent_blocked", 0.0))
        active_clients = clients.get("active")

        # "enabled" / "disabled"; wyłączone blokowanie to nie awaria, ale
        # powinno rzucać się w oczy (status warning + wyraźny wpis na karcie).
        blocking_enabled = blocking.get("blocking") == "enabled"
        timer = blocking.get("timer")  # sekundy do automatycznego włączenia, albo None

        points = history.get("history", [])
        # stacked_bar: frontend składa blocked (dół) + (total−blocked) (góra).
        # Kolejność serii: BLOCKED (accent) potem TOTAL (muted) — patrz base.py.
        chart = {
            "type": "stacked_bar",
            "series": [
                {
                    "label": "BLOCKED",
                    "role": "accent",
                    "points": [p.get("blocked", 0) for p in points],
                },
                {
                    "label": "TOTAL",
                    "role": "muted",
                    "points": [p.get("total", 0) for p in points],
                },
            ],
        }

        if blocking_enabled:
            block_value = "ON"
        elif timer:
            block_value = f"OFF {int(timer) // 60}M"
        else:
            block_value = "OFF"

        metrics: list[dict] = [
            {"label": "TODAY", "value": _fmt_count(total), "type": "number"},
            {"label": "BLOCKED", "value": _fmt_count(blocked), "type": "number"},
            {"label": "% BLOCK", "value": round(percent, 1), "type": "percent"},
        ]
        if active_clients is not None:
            metrics.append({"label": "CLIENTS", "value": int(active_clients), "type": "number"})

        metrics.append({
            "label": "BLOCK",
            "value": block_value,
            "type": "status",
            "state": STATUS_OK if blocking_enabled else STATUS_WARNING,
        })

        return {
            "metrics": metrics,
            "chart": chart,
            "layout": "hero",
            "_blocking_enabled": blocking_enabled,
        }

    def get_status(self, data: dict) -> str:
        # Nieosiągalne API = wyjątek w collect() = karta "error" (obsługa w main.py).
        return STATUS_OK if data["_blocking_enabled"] else STATUS_WARNING


if __name__ == "__main__":  # test w izolacji: python -m collectors.pihole
    run_standalone(PiholeCollector())
