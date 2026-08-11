"""Collector statusu jednostek systemd (Jellyfin, Samba, Caddy, Pi-hole, …).

Czyta stan przez `systemctl is-active <unit>` — bez dodatkowych zależności
i bez sudo (is-active działa dla zwykłego użytkownika na jednostkach
systemowych). Frontend używa tych samych metryk na stronach SVC i MEDIA
(MEDIA filtruje po fladze media / id jellyfin+samba).

Kształt metryk (kontrakt base.py):
  - number: UP / DOWN (podsumowanie)
  - status: jedna metryka na jednostkę (ACTIVE / DOWN / FAILED)
  - opcjonalne pola poza speką (id, note, media) — frontend stron SVC/MEDIA
    je czyta; generyczny render karty HUB i tak omija collector `services`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .base import STATUS_ERROR, STATUS_OK, STATUS_WARNING, Collector, run_standalone

log = logging.getLogger("hub.services")

# Domyślna lista — gdy config.yaml nie poda `units`. Kolejność = kolejność kart.
DEFAULT_UNITS: list[dict[str, Any]] = [
    {"id": "jellyfin", "unit": "jellyfin.service", "label": "JELLYFIN", "media": True,
     "note": "http://mother-base:8096"},
    {"id": "samba", "unit": "smbd.service", "label": "SMB", "media": True,
     "note": "smb://mother-base"},
    {"id": "nmbd", "unit": "nmbd.service", "label": "NMBD"},
    {"id": "wsdd2", "unit": "wsdd2.service", "label": "WSDD2"},
    {"id": "caddy", "unit": "caddy.service", "label": "CADDY"},
    {"id": "pihole", "unit": "pihole-FTL.service", "label": "PIHOLE"},
    {"id": "unbound", "unit": "unbound.service", "label": "UNBOUND"},
    {"id": "hub", "unit": "outer-haven-hub.service", "label": "HUB"},
]


class ServicesCollector(Collector):
    id = "services"
    label = "SERVICES"
    icon = "box"
    refresh_interval = 10

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        raw = self.settings.get("units")
        self._units: list[dict[str, Any]] = list(raw) if raw else list(DEFAULT_UNITS)

    @staticmethod
    async def _is_active(unit: str) -> str:
        """Zwraca surowy stan z systemctl: active / inactive / failed / …

        Exit code ≠ 0 jest normalny gdy jednostka nie jest active — czytamy
        stdout, nie kod wyjścia.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl",
                "is-active",
                unit,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            state = (out.decode("utf-8", errors="replace") or "").strip().lower()
            return state or "unknown"
        except FileNotFoundError:
            raise RuntimeError("brak polecenia systemctl — ten collector wymaga Linuksa") from None
        except OSError as exc:
            raise RuntimeError(f"systemctl is-active {unit}: {exc}") from exc

    @staticmethod
    def _display_value(state: str) -> str:
        if state == "active":
            return "ACTIVE"
        if state == "failed":
            return "FAILED"
        if state in ("inactive", "dead"):
            return "DOWN"
        if state == "activating":
            return "STARTING"
        if state == "deactivating":
            return "STOPPING"
        # unknown / not-found / …
        return state.upper() or "DOWN"

    @staticmethod
    def _metric_state(state: str) -> str:
        if state == "active":
            return STATUS_OK
        if state in ("activating", "deactivating", "reloading"):
            return STATUS_WARNING
        return STATUS_ERROR

    async def collect(self) -> dict:
        metrics: list[dict] = []
        # Prywatne — do get_status(); nie trafiają do API (prefiks "_").
        unit_states: list[dict] = []

        for entry in self._units:
            unit_name = str(entry.get("unit") or "").strip()
            if not unit_name:
                continue
            uid = str(entry.get("id") or unit_name)
            label = str(entry.get("label") or uid).upper()
            note = str(entry.get("note") or entry.get("url") or "").strip()
            media = bool(entry.get("media"))
            # critical: false → DOWN nie psuje zbiorczego statusu karty
            critical = entry.get("critical", True)

            state = await self._is_active(unit_name)
            mstate = self._metric_state(state)
            unit_states.append({
                "id": uid,
                "state": state,
                "metric_state": mstate,
                "critical": critical,
            })

            metrics.append({
                "id": uid,
                "label": label,
                "value": self._display_value(state),
                "type": "status",
                "state": mstate,
                # Pola poza speką — strony SVC/MEDIA (patrz komentarz w module).
                "note": note,
                "media": media,
            })

        up = sum(1 for u in unit_states if u["state"] == "active")
        down = len(unit_states) - up
        # Podsumowanie na górze listy — UI stron może je pokazać osobno.
        summary = [
            {"label": "UP", "value": up, "type": "number", "state": STATUS_OK},
            {
                "label": "DOWN",
                "value": down,
                "type": "number",
                "state": STATUS_ERROR if down else STATUS_OK,
            },
        ]

        return {
            "metrics": summary + metrics,
            "chart": None,
            "_unit_states": unit_states,
        }

    def get_status(self, data: dict) -> str:
        states = data.get("_unit_states") or []
        if not states:
            return STATUS_WARNING
        worst = STATUS_OK
        order = {STATUS_OK: 0, STATUS_WARNING: 1, STATUS_ERROR: 2}
        for u in states:
            if not u.get("critical", True):
                continue
            s = u.get("metric_state") or STATUS_ERROR
            if order.get(s, 2) > order.get(worst, 0):
                worst = s
        return worst


if __name__ == "__main__":  # test: python -m collectors.services
    run_standalone(ServicesCollector())
