"""Demo data — HUB_DEMO=1 only (no Pi-hole / WireGuard / SMART required)."""

from __future__ import annotations

import math
import random
import time
from collections import deque

from .base import Collector, STATUS_ERROR, STATUS_OK, STATUS_WARNING

HISTORY_LEN = 36


def _wave(n: int = 36, base: float = 40, amp: float = 25, phase: float = 0) -> list[float]:
    return [
        max(0, base + amp * math.sin(i / n * 2 * math.pi + phase) + random.uniform(-4, 4))
        for i in range(n)
    ]


class DemoPihole(Collector):
    id = "pihole"
    label = "Pi-hole"
    icon = "shield"
    refresh_interval = 5
    primary_metric = "% BLOCK"

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        self._blocking = True
        self._off_until = 0.0

    def _sync_timer(self) -> None:
        if not self._blocking and self._off_until and time.monotonic() >= self._off_until:
            self._blocking = True
            self._off_until = 0.0

    def list_actions(self, data: dict) -> list[dict]:
        blocking_on = bool(data.get("_blocking_enabled", self._blocking))
        return [
            {"id": "block_off_5", "label": "OFF 5M", "style": "warn", "group": "block"},
            {"id": "block_off_15", "label": "OFF 15M", "style": "warn", "group": "block"},
            {
                "id": "block_on",
                "label": "ON",
                "style": "accent" if not blocking_on else "default",
                "group": "block",
            },
        ]

    async def run_action(self, action_id: str) -> dict:
        if action_id == "block_on":
            self._blocking = True
            self._off_until = 0.0
            return {"message": "blocking enabled"}
        if action_id == "block_off_5":
            self._blocking = False
            self._off_until = time.monotonic() + 5 * 60
            return {"message": "blocking disabled for 5 min"}
        if action_id == "block_off_15":
            self._blocking = False
            self._off_until = time.monotonic() + 15 * 60
            return {"message": "blocking disabled for 15 min"}
        raise RuntimeError(f"unknown action: {action_id}")

    async def collect(self) -> dict:
        self._sync_timer()
        total = random.randint(12_300, 12_600)
        blocked = int(total * random.uniform(0.24, 0.27))

        points_total, points_blocked = [], []
        for i in range(144):
            hour = i / 6
            daily_wave = 55 + 45 * math.sin((hour - 7) / 24 * 2 * math.pi)
            value = max(4, daily_wave + random.uniform(-12, 12))
            points_total.append(round(value))
            points_blocked.append(round(value * random.uniform(0.18, 0.34)))

        # Tylko kluczowe liczby — reszta (cache/forward/gravity) szum na kiosku.
        if self._blocking:
            block_value = "ON"
        else:
            remain = max(0, int(self._off_until - time.monotonic()))
            block_value = f"OFF {remain // 60}M" if remain else "OFF"

        return {
            "layout": "hero",
            "metrics": [
                {"label": "TODAY", "value": f"{total / 1000:.1f}k", "type": "number"},
                {"label": "BLOCKED", "value": f"{blocked / 1000:.1f}k", "type": "number"},
                {"label": "% BLOCK", "value": round(100 * blocked / total, 1), "type": "percent"},
                {"label": "CLIENTS", "value": 7, "type": "number"},
                {
                    "label": "BLOCK",
                    "value": block_value,
                    "type": "status",
                    "state": STATUS_OK if self._blocking else STATUS_WARNING,
                },
            ],
            "chart": {
                "type": "line",
                "series": [
                    {"label": "TOTAL", "role": "muted", "points": points_total},
                    {"label": "BLOCKED", "role": "accent", "points": points_blocked},
                ],
            },
            "_blocking_enabled": self._blocking,
        }

    def get_status(self, data: dict) -> str:
        return STATUS_OK if data["_blocking_enabled"] else STATUS_WARNING


class DemoWireguard(Collector):
    id = "wireguard"
    label = "VPN"
    icon = "lock"
    refresh_interval = 5
    primary_metric = "LIVE"

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        self._rx = deque((round(v, 2) for v in _wave(HISTORY_LEN, 12, 8, 0.2)), maxlen=HISTORY_LEN)
        self._tx = deque((round(v, 2) for v in _wave(HISTORY_LEN, 6, 4, 1.1)), maxlen=HISTORY_LEN)

    async def collect(self) -> dict:
        self._rx.append(round(max(0, self._rx[-1] + random.uniform(-3, 3)), 2))
        self._tx.append(round(max(0, self._tx[-1] + random.uniform(-2, 2)), 2))
        # Same liczby + wykres — linie statusu (wg0/peer) i tak były ucinane na 7".
        return {
            "metrics": [
                {"label": "LIVE", "value": 1, "type": "number"},
                {"label": "PEERS", "value": 3, "type": "number"},
                # TUNNELS = liczba interfejsów wg* (dawniej IFACE — żargon netowy).
                {"label": "TUNNELS", "value": 1, "type": "number"},
            ],
            "chart": {
                "type": "line",
                "series": [
                    # DOWN = ruch do Pi, UP = z Pi (dawniej RX/TX — mniej oczywiste).
                    {"label": "DOWN", "role": "accent", "points": list(self._rx)},
                    {"label": "UP", "role": "muted", "points": list(self._tx)},
                ],
            },
        }

    def get_status(self, data: dict) -> str:
        return STATUS_OK


class DemoSystem(Collector):
    id = "system"
    label = "System"
    icon = "cpu"
    refresh_interval = 5
    primary_metric = "CPU"
    vital_metrics = {"CPU": "CPU", "RAM": "RAM", "TEMP": "TEMP"}
    metric_ranges = {"TEMP": (30.0, 85.0)}

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        self._cpu = deque((round(v) for v in _wave(HISTORY_LEN, 34, 10, 0)), maxlen=HISTORY_LEN)
        self._ram = deque((round(v) for v in _wave(HISTORY_LEN, 42, 4, 1.7)), maxlen=HISTORY_LEN)
        self._temp = deque((round(v) for v in _wave(HISTORY_LEN, 43, 3, 0.8)), maxlen=HISTORY_LEN)

    async def collect(self) -> dict:
        cpu = max(5, min(95, self._cpu[-1] + random.randint(-4, 4)))
        ram = max(20, min(90, self._ram[-1] + random.randint(-2, 2)))
        temp = max(35, min(75, self._temp[-1] + random.randint(-1, 1)))
        self._cpu.append(cpu)
        self._ram.append(ram)
        self._temp.append(temp)
        rx = random.randint(8, 420)
        tx = random.randint(4, 180)
        return {
            "metrics": [
                {"label": "CPU", "value": f"{cpu}%", "type": "number", "state": STATUS_OK},
                {"label": "RAM", "value": f"{ram}%", "type": "number", "state": STATUS_OK},
                {"label": "TEMP", "value": f"{temp}°", "type": "number", "state": STATUS_OK},
                {"label": "LOAD", "value": f"{random.uniform(0.1, 1.4):.2f}", "type": "number", "state": STATUS_OK},
                {"label": "SWAP", "value": "OFF", "type": "number", "state": STATUS_OK},
                {"label": "THRTL", "value": "OK", "type": "status", "state": STATUS_OK},
                {"label": "IFACE", "value": "eth0", "type": "text", "state": STATUS_OK},
                {"label": "NET IN", "value": f"{rx}K/s", "type": "number", "state": STATUS_OK},
                {"label": "NET OUT", "value": f"{tx}K/s", "type": "number", "state": STATUS_OK},
            ],
            "chart": {
                "type": "line",
                "series": [
                    {"label": "CPU", "role": "accent", "points": list(self._cpu)},
                    {"label": "RAM", "role": "muted", "points": list(self._ram)},
                    {"label": "TEMP", "role": "warn", "points": list(self._temp)},
                ],
            },
        }

    def get_status(self, data: dict) -> str:
        return STATUS_OK


class DemoSmart(Collector):
    id = "smart"
    label = "Disk"
    icon = "hard-drive"
    refresh_interval = 5
    primary_metric = "FREE"
    vital_metrics = {"HEALTH": "SSD"}

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        self._temp = deque((round(v) for v in _wave(HISTORY_LEN, 34, 3, 0.5)), maxlen=HISTORY_LEN)
        self._health = 98

    async def collect(self) -> dict:
        t = max(28, min(48, self._temp[-1] + random.choice([-1, 0, 0, 1])))
        self._temp.append(t)
        # HEALTH prawie stałe (wear) — tylko metryka, nie wykres.
        self._health = max(95, min(100, self._health + random.choice([0, 0, 0, -1, 1])))
        return {
            "metrics": [
                {"label": "TEMP", "value": f"{t}°", "type": "number", "state": STATUS_OK},
                {"label": "FREE", "value": "142GB", "type": "number"},
                {"label": "HEALTH", "value": f"{self._health}%", "type": "number", "state": STATUS_OK},
            ],
            "chart": {
                "type": "line",
                "series": [
                    {"label": "TEMP", "role": "accent", "points": list(self._temp)},
                ],
            },
        }

    def get_status(self, data: dict) -> str:
        return STATUS_OK


class DemoServices(Collector):
    """Fake systemd statuses — HUB_DEMO, Svc / Media / MC pages."""

    id = "services"
    label = "Services"
    icon = "box"
    refresh_interval = 5
    primary_metric = "UP"

    # Stała lista jak w config.yaml — UI da się stylować bez Pi.
    _UNITS = [
        {"id": "jellyfin", "label": "Jellyfin", "media": True,
         "note": "http://mother-base:8096"},
        {"id": "samba", "label": "Files", "media": True,
         "note": "smb://mother-base"},
        {"id": "minecraft", "label": "Minecraft", "game": True,
         "note": "mother-base:25565", "critical": False},
        {"id": "nmbd", "label": "NMBD"},
        {"id": "winbind", "label": "Winbind", "critical": False},
        {"id": "wsdd2", "label": "WSDD"},
        {"id": "caddy", "label": "Caddy"},
        {"id": "pihole", "label": "Pi-hole"},
        {"id": "unbound", "label": "Unbound"},
        {"id": "hub", "label": "Hub"},
        {"id": "ssh", "label": "SSH"},
        {"id": "nm", "label": "Net"},
        {"id": "avahi", "label": "Avahi", "critical": False},
        {"id": "bluetooth", "label": "BT", "critical": False},
        {"id": "cron", "label": "Cron", "critical": False},
        {"id": "smart", "label": "SMART", "critical": False},
    ]

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        # Lekka fluktuacja: większość UP, czasem jeden DOWN.
        self._down_id: str | None = None
        self._tick = 0

    async def collect(self) -> dict:
        self._tick += 1
        if self._tick % 8 == 0:
            self._down_id = random.choice(["nmbd", "wsdd2", "minecraft", None, None])
        metrics: list[dict] = []
        unit_states: list[dict] = []
        for u in self._UNITS:
            active = u["id"] != self._down_id
            state = STATUS_OK if active else STATUS_ERROR
            unit_states.append({
                "id": u["id"],
                "state": "active" if active else "inactive",
                "metric_state": state,
                "critical": u.get("critical", True),
            })
            metrics.append({
                "id": u["id"],
                "label": u["label"],
                "value": "ON" if active else "OFF",
                "type": "status",
                "state": state,
                "note": u.get("note") or "",
                "media": bool(u.get("media")),
                "game": bool(u.get("game")),
            })
        up = sum(1 for s in unit_states if s["state"] == "active")
        down = len(unit_states) - up
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
        if any(s["metric_state"] == STATUS_ERROR for s in states):
            return STATUS_ERROR
        return STATUS_OK


DEMO_COLLECTORS: list[Collector] = [
    DemoPihole(),
    DemoWireguard(),
    DemoSystem(),
    DemoSmart(),
    DemoServices(),
]
