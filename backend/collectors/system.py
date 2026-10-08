"""Collector metryk systemowych Raspberry Pi (CPU, RAM, temp, load, throttle, LAN).

Czyta bezpośrednio z /proc i /sys zamiast używać biblioteki psutil —
specyfikacja (sekcja 5/4.4) dopuszcza obie drogi, a rezygnacja z psutil
to jedna zależność mniej (filozofia minimalizmu zasobów na Pi).
Uwaga: przez to moduł działa tylko na Linuksie — na tym sprzęcie to
żadne ograniczenie.

Dodatkowo (strony SYS / NET):
  - load average 1m, swap %, flagi throttling/undervoltage (vcgencmd / sysfs),
  - rate RX/TX na wybranym interfejsie (domyślnie eth0, fallback pierwszy non-lo).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from pathlib import Path

from .base import STATUS_ERROR, STATUS_OK, STATUS_WARNING, Collector, run_standalone

# Progi ostrzeżeń. SoC Raspberry Pi zaczyna zwalniać zegary (throttling)
# przy ~80°C, więc ostrzegamy odpowiednio wcześniej.
TEMP_WARNING_C = 70.0
MEM_WARNING_PCT = 90.0
CPU_WARNING_PCT = 95.0
SWAP_WARNING_PCT = 50.0
LOAD_WARNING_PER_CORE = 1.5  # load1 / nproc

# Okno historii na mini-wykres (~3 min przy refresh_interval=5).
HISTORY_LEN = 36

# Bitmask vcgencmd get_throttled (aktualne flagi w dolnych 16 bitach).
_THROTTLE_UV = 1 << 0
_THROTTLE_ARM = 1 << 1
_THROTTLE_THERM = 1 << 2


class SystemCollector(Collector):
    id = "system"
    label = "System"
    icon = "cpu"
    refresh_interval = 5  # metryki systemowe są tanie w odczycie, mogą być "żywe"

    # Panel: CPU na scenie, a CPU/RAM/TEMP dodatkowo w lewej szynie —
    # to jedyne trzy liczby, które chcesz widzieć na KAŻDEJ stronie.
    primary_metric = "CPU"
    vital_metrics = {"CPU": "CPU", "RAM": "RAM", "TEMP": "TEMP"}
    # Temperatura nie ma naturalnego zakresu 0–100; widełki dla Pi 4
    # (poniżej 40°C to zimno, 85°C to twardy throttling).
    metric_ranges = {"TEMP": (30.0, 85.0)}

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        # Liczniki CPU z poprzedniego odczytu — użycie CPU to zawsze RÓŻNICA
        # między dwoma punktami w czasie, nie pojedynczy odczyt.
        self._prev_cpu: tuple[int, int] | None = None
        self._cpu_hist: deque[int] = deque(maxlen=HISTORY_LEN)
        self._mem_hist: deque[int] = deque(maxlen=HISTORY_LEN)
        self._temp_hist: deque[float] = deque(maxlen=HISTORY_LEN)
        # (rx_bytes, tx_bytes, monotonic_ts) — rate na NET IN/OUT
        self._prev_net: tuple[int, int, float] | None = None
        self._iface = str(self.settings.get("iface") or "eth0")

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

    @staticmethod
    def _nproc() -> int:
        try:
            return max(1, Path("/proc/cpuinfo").read_text().count("\nprocessor"))
        except OSError:
            return 1

    @staticmethod
    def _swap_percent() -> float | None:
        """Użycie swap w %; None gdy swap wyłączony (częste na Pi)."""
        info: dict[str, int] = {}
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0])
        except (OSError, ValueError):
            return None
        total = info.get("SwapTotal", 0)
        if total <= 0:
            return None
        free = info.get("SwapFree", 0)
        return 100.0 * (1.0 - free / total)

    async def _throttle_label(self) -> tuple[str, str]:
        """Zwraca (etykieta, state) na bazie vcgencmd get_throttled.

        Gdy brak vcgencmd (dev PC) → OK / ok — nie fałszywy alarm.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "vcgencmd",
                "get_throttled",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            raw = (out.decode("utf-8", errors="replace") or "").strip()
            # Format: throttled=0x0  lub  throttled=0x50005
            hex_part = raw.split("=", 1)[-1].strip()
            flags = int(hex_part, 0)
        except (FileNotFoundError, ValueError, OSError):
            return "OK", STATUS_OK

        now = flags & 0xFFFF
        if now & (_THROTTLE_UV | _THROTTLE_ARM | _THROTTLE_THERM):
            if now & _THROTTLE_UV:
                return "UV", STATUS_ERROR
            if now & _THROTTLE_THERM:
                return "HOT", STATUS_WARNING
            return "THROT", STATUS_WARNING
        # Historyczne flagi w górnych bitach — świadomość, nie panika
        if flags & 0xFFFF0000:
            return "PAST", STATUS_WARNING
        return "OK", STATUS_OK

    def _pick_iface(self) -> str | None:
        """Wybiera interfejs do pomiaru ruchu: settings.iface, inaczej eth0 / pierwszy non-lo."""
        path = Path("/proc/net/dev")
        try:
            lines = path.read_text().splitlines()[2:]  # pomiń nagłówki
        except OSError:
            return None
        names: list[str] = []
        for line in lines:
            if ":" not in line:
                continue
            name = line.split(":", 1)[0].strip()
            if name and name != "lo":
                names.append(name)
        if not names:
            return None
        if self._iface in names:
            return self._iface
        for preferred in ("eth0", "enp0s3", "wlan0", "end0"):
            if preferred in names:
                return preferred
        return names[0]

    @staticmethod
    def _read_iface_bytes(iface: str) -> tuple[int, int] | None:
        try:
            for line in Path("/proc/net/dev").read_text().splitlines():
                if ":" not in line:
                    continue
                name, _, rest = line.partition(":")
                if name.strip() != iface:
                    continue
                parts = rest.split()
                # rx_bytes = [0], tx_bytes = [8]
                return int(parts[0]), int(parts[8])
        except (OSError, ValueError, IndexError):
            return None
        return None

    @staticmethod
    def _fmt_rate(bps: float) -> str:
        if bps < 1024:
            return f"{int(bps)}B/s"
        if bps < 1024 * 1024:
            return f"{bps / 1024:.0f}K/s"
        return f"{bps / (1024 * 1024):.1f}M/s"

    def _net_rates(self) -> tuple[str, str, str]:
        """Zwraca (iface|—, rx_label, tx_label). Pierwszy poll: 0B/s (brak delty)."""
        iface = self._pick_iface()
        if not iface:
            return "—", "—", "—"
        now = time.monotonic()
        cur = self._read_iface_bytes(iface)
        if cur is None:
            return iface, "—", "—"
        rx, tx = cur
        if self._prev_net is None:
            self._prev_net = (rx, tx, now)
            return iface, "0B/s", "0B/s"
        prev_rx, prev_tx, prev_t = self._prev_net
        self._prev_net = (rx, tx, now)
        dt = max(0.001, now - prev_t)
        return iface, self._fmt_rate((rx - prev_rx) / dt), self._fmt_rate((tx - prev_tx) / dt)

    # ------------------------------------------------------------ kontrakt

    async def collect(self) -> dict:
        cpu_pct = await self._cpu_percent()
        mem_pct, _mem_used_gib, _mem_total_gib = self._memory()
        temp_c = self._temperature()
        load1, _load5, _load15 = self._loadavg()
        nproc = self._nproc()
        swap_pct = self._swap_percent()
        thrtl_value, thrtl_state = await self._throttle_label()
        iface, rx_s, tx_s = self._net_rates()

        load_warn = load1 >= (nproc * LOAD_WARNING_PER_CORE)

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
            {
                "label": "LOAD",
                "value": f"{load1:.2f}",
                "type": "number",
                "state": STATUS_WARNING if load_warn else STATUS_OK,
            },
            {
                "label": "SWAP",
                "value": f"{round(swap_pct)}%" if swap_pct is not None else "OFF",
                "type": "number",
                "state": (
                    STATUS_WARNING
                    if swap_pct is not None and swap_pct >= SWAP_WARNING_PCT
                    else STATUS_OK
                ),
            },
            {
                "label": "THRTL",
                "value": thrtl_value,
                "type": "status",
                "state": thrtl_state,
            },
            {
                "label": "IFACE",
                "value": iface,
                "type": "text",
                "state": STATUS_OK,
            },
            {
                "label": "NET IN",
                "value": rx_s,
                "type": "number",
                "state": STATUS_OK,
            },
            {
                "label": "NET OUT",
                "value": tx_s,
                "type": "number",
                "state": STATUS_OK,
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
            "_load1": load1,
            "_nproc": nproc,
            "_swap_pct": swap_pct,
            "_thrtl_state": thrtl_state,
        }

    def get_status(self, data: dict) -> str:
        if data.get("_thrtl_state") == STATUS_ERROR:
            return STATUS_ERROR
        too_hot = data["_temp_c"] is not None and data["_temp_c"] >= TEMP_WARNING_C
        load_warn = data.get("_load1", 0) >= (data.get("_nproc", 1) * LOAD_WARNING_PER_CORE)
        swap = data.get("_swap_pct")
        swap_warn = swap is not None and swap >= SWAP_WARNING_PCT
        if (
            too_hot
            or data["_mem_pct"] >= MEM_WARNING_PCT
            or data["_cpu_pct"] >= CPU_WARNING_PCT
            or load_warn
            or swap_warn
            or data.get("_thrtl_state") == STATUS_WARNING
        ):
            return STATUS_WARNING
        return STATUS_OK


if __name__ == "__main__":  # test w izolacji: python -m collectors.system
    run_standalone(SystemCollector())
