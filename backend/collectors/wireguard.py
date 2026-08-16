"""Collector WireGuard — status tuneli na podstawie `wg show all dump`.

Format dumpa (sekcja 5/4.3): tabela rozdzielana tabulatorami, jedna linia na
interfejs lub peera, każda linia zaczyna się nazwą interfejsu:

  linia interfejsu (5 pól):  iface  klucz_prywatny  klucz_publiczny  port  fwmark
  linia peera      (9 pól):  iface  klucz_publiczny  psk  endpoint  allowed_ips
                             ostatni_handshake(unix)  rx_bajty  tx_bajty  keepalive

Surowy timestamp handshake'u przeliczamy na czytelny opis ("aktywny",
"5 min temu", "nigdy") — wymóg specyfikacji. Klucze publiczne peerów mapujemy
na przyjazne nazwy z config.yaml (collectors.wireguard.peer_names), bo klucz
w base64 nic nie mówi na ekranie.

UWAGA — UPRAWNIENIA: jak w smart.py — `sudo -n` + wąski wpis w sudoers
(deploy/sudoers-outer-haven-hub). Argumenty wywołania i wpis w sudoers
muszą być identyczne co do znaku.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

from .base import Collector, STATUS_OK, STATUS_WARNING, STATE_MUTED, run_standalone

WG_PATH = "/usr/bin/wg"

# WireGuard przy aktywnym ruchu odnawia handshake mniej więcej co 2 minuty,
# więc handshake młodszy niż 3 minuty oznacza żywy, używany tunel.
HANDSHAKE_ACTIVE_S = 180
HISTORY_LEN = 36


def _describe_handshake(timestamp: int, now: float) -> tuple[str, str]:
    """Unix handshake timestamp → (label, metric state)."""
    if timestamp == 0:
        return "never", STATE_MUTED  # configured peer, never connected
    age_s = max(0, int(now - timestamp))
    if age_s < HANDSHAKE_ACTIVE_S:
        return "active", STATUS_OK
    if age_s < 3600:
        return f"{age_s // 60}m ago", STATE_MUTED
    if age_s < 86400:
        return f"{age_s // 3600}h ago", STATE_MUTED
    return f"{age_s // 86400}d ago", STATE_MUTED


class WireguardCollector(Collector):
    id = "wireguard"
    label = "VPN (zdalny dostęp)"
    icon = "lock"
    refresh_interval = 10

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        # Mapa: klucz publiczny peera -> przyjazna nazwa (z config.yaml).
        self.peer_names: dict[str, str] = dict(self.settings.get("peer_names") or {})
        # Historia przepustowości (KiB/s) między kolejnymi odczytami.
        self._rx_rate_hist: deque[float] = deque(maxlen=HISTORY_LEN)
        self._tx_rate_hist: deque[float] = deque(maxlen=HISTORY_LEN)
        self._prev_totals: tuple[int, int, float] | None = None  # rx, tx, monotonic

    async def _run_wg_dump(self) -> str:
        # Argumenty muszą być identyczne z deploy/sudoers-outer-haven-hub!
        argv = ["sudo", "-n", WG_PATH, "show", "all", "dump"]
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip() or f"kod wyjścia {process.returncode}"
            raise RuntimeError(f"wg show nie zadziałał: {detail}")
        return stdout.decode()

    def _peer_label(self, public_key: str) -> str:
        # Bez wpisu w config.yaml pokazujemy skrót klucza — lepsze to niż nic,
        # a od razu widać, który klucz warto nazwać.
        return self.peer_names.get(public_key) or f"peer {public_key[:8]}…"

    async def collect(self) -> dict:
        dump = await self._run_wg_dump()
        now = time.time()

        # interfejs -> {"port": ..., "peers": [...]}
        interfaces: dict[str, dict] = {}
        for line in dump.splitlines():
            fields = line.rstrip("\n").split("\t")
            if len(fields) == 5:
                iface, _private_key, _public_key, port, _fwmark = fields
                interfaces[iface] = {"port": port, "peers": []}
            elif len(fields) == 9:
                iface, public_key, _psk, _endpoint, _allowed_ips, handshake, rx, tx, _keepalive = fields
                interfaces.setdefault(iface, {"port": "?", "peers": []})["peers"].append({
                    "public_key": public_key,
                    "handshake_ts": int(handshake),
                    "rx": int(rx),
                    "tx": int(tx),
                })

        # Mała karta + wykres: tylko liczby. Linie statusu (iface/peer)
        # były ucinane w połowie przez overflow na 7".
        active_peers = 0
        peer_total = 0
        for info in interfaces.values():
            peer_total += len(info["peers"])
            for peer in info["peers"]:
                _text, state = _describe_handshake(peer["handshake_ts"], now)
                if state == STATUS_OK:
                    active_peers += 1

        metrics = [
            {"label": "LIVE", "value": active_peers, "type": "number"},
            {"label": "PEERS", "value": peer_total, "type": "number"},
            # TUNNELS = ile interfejsów wg* (np. wg0) — czytelniej niż IFACE.
            {"label": "TUNNELS", "value": len(interfaces), "type": "number"},
        ]

        # Sumaryczny transfer wszystkich interfejsów → próbka prędkości na wykres.
        grand_rx = grand_tx = 0
        for info in interfaces.values():
            for peer in info["peers"]:
                grand_rx += peer["rx"]
                grand_tx += peer["tx"]

        mono = time.monotonic()
        if self._prev_totals is not None:
            prev_rx, prev_tx, prev_t = self._prev_totals
            dt = max(mono - prev_t, 0.001)
            # KiB/s — wygodniejsza skala na mini-wykresie niż surowe bajty.
            self._rx_rate_hist.append(max(0.0, (grand_rx - prev_rx) / dt / 1024))
            self._tx_rate_hist.append(max(0.0, (grand_tx - prev_tx) / dt / 1024))
        self._prev_totals = (grand_rx, grand_tx, mono)

        chart = None
        if len(self._rx_rate_hist) >= 2:
            chart = {
                "type": "line",
                "series": [
                    # DOWN/UP zamiast RX/TX — czytelniej na kiosku.
                    {"label": "DOWN", "role": "accent", "points": [round(v, 2) for v in self._rx_rate_hist]},
                    {"label": "UP", "role": "muted", "points": [round(v, 2) for v in self._tx_rate_hist]},
                ],
            }

        return {
            "metrics": metrics,
            "chart": chart,
            "_interface_count": len(interfaces),
            "_active_peers": active_peers,
        }

    def get_status(self, data: dict) -> str:
        # Brak interfejsów = coś nie gra z konfiguracją (warning). Nieaktywni
        # peerzy to normalność (telefon śpi) — nie obniżają statusu karty.
        return STATUS_OK if data["_interface_count"] > 0 else STATUS_WARNING


if __name__ == "__main__":  # test w izolacji: python -m collectors.wireguard
    run_standalone(WireguardCollector())
