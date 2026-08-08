"""Collector metryk systemowych Raspberry Pi (CPU, RAM, temperatura, uptime).

Czyta bezpośrednio z /proc i /sys zamiast używać biblioteki psutil —
specyfikacja (sekcja 5/4.4) dopuszcza obie drogi, a rezygnacja z psutil
to jedna zależność mniej (filozofia minimalizmu zasobów na Pi).
Uwaga: przez to moduł działa tylko na Linuksie — na tym sprzęcie to
żadne ograniczenie.
"""

from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path

from .base import Collector, STATUS_OK, STATUS_WARNING, run_standalone

# Progi ostrzeżeń. SoC Raspberry Pi zaczyna zwalniać zegary (throttling)
# przy ~80°C, więc ostrzegamy odpowiednio wcześniej.
TEMP_WARNING_C = 70.0
MEM_WARNING_PCT = 90.0
CPU_WARNING_PCT = 95.0

# Okno historii na mini-wykres (~3 min przy refresh_interval=5).
HISTORY_LEN = 36


class SystemCollector(Collector):
    id = "system"
    label = "SYSTEM PI"
    icon = "cpu"
    refresh_interval = 5  # metryki systemowe są tanie w odczycie, mogą być "żywe"

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        # Liczniki CPU z poprzedniego odczytu — użycie CPU to zawsze RÓŻNICA
        # między dwoma punktami w czasie, nie pojedynczy odczyt.
        self._prev_cpu: tuple[int, int] | None = None
        self._cpu_hist: deque[int] = deque(maxlen=HISTORY_LEN)
        self._mem_hist: deque[int] = deque(maxlen=HISTORY_LEN)
        self._temp_hist: deque[float] = deque(maxlen=HISTORY_LEN)

    # ------------------------------------------------------------------ CPU

    @staticmethod
    def _read_cpu_counters() -> tuple[int, int]:
        """Zwraca (czas_bezczynności, czas_łączny) z pierwszej linii /proc/stat.

        Format linii: "cpu  user nice system idle iowait irq softirq steal ..."
        — wartości w tyknięciach zegara, sumowane od startu systemu.
        """
        fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        values = [int(v) for v in fields]
        idle = values[3] + values[4]  # idle + iowait (czekanie na dysk to też bezczynność CPU)
        return idle, sum(values)

    async def _cpu_percent(self) -> float:
        """Użycie CPU w % od poprzedniego wywołania collect().

        Collector żyje przez cały czas działania backendu, więc odstęp między
        wywołaniami (refresh_interval) daje naturalne okno pomiaru. Tylko przy
        PIERWSZYM wywołaniu robimy krótką próbkę 0.25 s, żeby mieć dwa punkty.
        """
        if self._prev_cpu is None:
            self._prev_cpu = self._read_cpu_counters()
            await asyncio.sleep(0.25)
        prev_idle, prev_total = self._prev_cpu
        idle, total = self._read_cpu_counters()
        self._prev_cpu = (idle, total)

        delta_total = total - prev_total
        if delta_total <= 0:
            return 0.0
        busy_ratio = 1.0 - (idle - prev_idle) / delta_total
        return max(0.0, min(100.0, busy_ratio * 100.0))

    # ------------------------------------------------------------------ RAM

    @staticmethod
    def _memory() -> tuple[float, float, float]:
        """Zwraca (użycie_w_%, użyte_GiB, całkowite_GiB) na bazie /proc/meminfo.

        Liczymy względem MemAvailable (a nie MemFree), bo Linux celowo trzyma
        w RAM cache dyskowy — "wolne" bywa mylące, "dostępne" mówi prawdę.
        """
        info: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0])  # wartości w kB

        total_kb = info["MemTotal"]
        available_kb = info.get("MemAvailable", info.get("MemFree", 0))
        used_pct = 100.0 * (1.0 - available_kb / total_kb)
        kb_per_gib = 1024 * 1024
        return used_pct, (total_kb - available_kb) / kb_per_gib, total_kb / kb_per_gib

    # ------------------------------------------------- temperatura / load / uptime

    @staticmethod
    def _temperature() -> float | None:
        """Temperatura SoC w °C; na Raspberry Pi thermal_zone0 to czujnik procesora."""
        path = Path("/sys/class/thermal/thermal_zone0/temp")
        try:
            return int(path.read_text().strip()) / 1000.0  # plik podaje tysięczne °C
        except (FileNotFoundError, ValueError):
            return None  # np. maszyna deweloperska bez tego czujnika

    @staticmethod
    def _loadavg() -> tuple[float, float, float]:
        parts = Path("/proc/loadavg").read_text().split()
        return float(parts[0]), float(parts[1]), float(parts[2])

    @staticmethod
    def _uptime_human() -> str:
        seconds = float(Path("/proc/uptime").read_text().split()[0])
        days, rest = divmod(int(seconds), 86400)
        hours, rest = divmod(rest, 3600)
        minutes = rest // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    # ------------------------------------------------------------ kontrakt

    async def collect(self) -> dict:
        cpu_pct = await self._cpu_percent()
        mem_pct, _mem_used_gib, _mem_total_gib = self._memory()
        temp_c = self._temperature()

        # Jednostka w wartości (nie CSS ::after) — stabilniejszy layout na wąskiej karcie.
        metrics: list[dict] = [
            {
                "label": "CPU",
                "value": f"{round(cpu_pct)}%",
                "type": "number",
                "state": STATUS_WARNING if cpu_pct >= CPU_WARNING_PCT else STATUS_OK,
            },
            {
                "label": "RAM",
                "value": f"{round(mem_pct)}%",
                "type": "number",
                "state": STATUS_WARNING if mem_pct >= MEM_WARNING_PCT else STATUS_OK,
            },
            {
                "label": "TEMP",
                "value": f"{round(temp_c)}°" if temp_c is not None else "—",
                "type": "number",
                "state": (
                    STATUS_WARNING
                    if temp_c is not None and temp_c >= TEMP_WARNING_C
                    else STATUS_OK
                ),
            },
        ]

        self._cpu_hist.append(round(cpu_pct))
        self._mem_hist.append(round(mem_pct))
        if temp_c is not None:
            self._temp_hist.append(round(temp_c, 1))

        series = [
            {"label": "CPU", "role": "accent", "points": list(self._cpu_hist)},
            {"label": "RAM", "role": "muted", "points": list(self._mem_hist)},
        ]
        # Temp °C na tej samej skali co % — na Pi typowo 40–70, więc czytelnie
        # miesci się obok CPU/RAM (role "warn" = osobny kolor linii).
        if self._temp_hist:
            series.append({
                "label": "TEMP",
                "role": "warn",
                "points": list(self._temp_hist),
            })

        return {
            "metrics": metrics,
            "chart": {"type": "line", "series": series},
            # Surowe wartości dla get_status() — nie trafiają do API (prefiks "_").
            "_cpu_pct": cpu_pct,
            "_mem_pct": mem_pct,
            "_temp_c": temp_c,
        }

    def get_status(self, data: dict) -> str:
        too_hot = data["_temp_c"] is not None and data["_temp_c"] >= TEMP_WARNING_C
        if too_hot or data["_mem_pct"] >= MEM_WARNING_PCT or data["_cpu_pct"] >= CPU_WARNING_PCT:
            return STATUS_WARNING
        return STATUS_OK


if __name__ == "__main__":  # test w izolacji: python -m collectors.system
    run_standalone(SystemCollector())
