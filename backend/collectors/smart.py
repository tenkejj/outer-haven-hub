"""Collector S.M.A.R.T. — zdrowie dysku SSD przez smartctl.

Wywołuje `smartctl -i -H -A -j <urządzenie>` (jedno wywołanie zamiast trzech):
  -i  informacje o urządzeniu,
  -H  ogólny wynik zdrowia (PASSED / FAILED),
  -A  tabela atrybutów SMART (temperatura, wear),
  -j  wyjście w JSON.

HEALTH (wear %) jest tylko metryką — na wykresie sama TEMP (żywa linia).
FREE z df na punkcie montowania z config.yaml.

UWAGA — UPRAWNIENIA: smartctl wymaga roota. Backend NIE działa jako root;
zamiast tego wywołujemy `sudo -n`, a wąski wpis w /etc/sudoers.d/
(deploy/sudoers-outer-haven-hub) musi być identyczny z argv poniżej.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections import deque

from .base import Collector, STATUS_OK, STATUS_WARNING, STATUS_ERROR, run_standalone

HISTORY_LEN = 36

SMARTCTL_PATH = "/usr/sbin/smartctl"

TEMP_WARNING_C = 60
# Pozostałe „życie” SSD poniżej tego % → warning.
HEALTH_WARNING_PCT = 20

# Atrybuty zużycia SSD — różni producenci, różne ID; VALUE zwykle 100→0.
WEAR_ATTRIBUTE_IDS = (231, 233, 177, 173, 202, 169)


class SmartCollector(Collector):
    id = "smart"
    label = "Disk"
    icon = "hard-drive"
    refresh_interval = 60  # SMART zmienia się wolno

    # Panel: wolne miejsce to liczba, po którą sięgasz najczęściej; zdrowie
    # nośnika trafia do szyny jako czwarty wskaźnik życia (podpis „SSD”).
    primary_metric = "FREE"
    vital_metrics = {"HEALTH": "SSD"}

    def __init__(self, settings: dict | None = None) -> None:
        super().__init__(settings)
        self.device = str(self.settings.get("device", "/dev/sda"))
        self.mount = str(self.settings.get("mount", "/"))
        self._temp_hist: deque[int] = deque(maxlen=HISTORY_LEN)

    @staticmethod
    def _fmt_free(nbytes: int) -> str:
        """Wolne miejsce: 142GB / 800MB."""
        for unit, div in (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2)):
            if nbytes >= div:
                value = nbytes / div
                return f"{value:.0f}{unit}" if value >= 10 else f"{value:.1f}{unit}"
        return f"{nbytes}B"

    async def _run_smartctl(self) -> dict:
        argv = ["sudo", "-n", SMARTCTL_PATH, "-i", "-H", "-A", "-j", self.device]
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if not stdout.strip():
            detail = stderr.decode(errors="replace").strip() or f"kod wyjścia {process.returncode}"
            raise RuntimeError(f"smartctl nie zwrócił danych: {detail}")

        data = json.loads(stdout)

        if process.returncode is not None and process.returncode & 0b11:
            messages = "; ".join(
                m.get("string", "") for m in data.get("smartctl", {}).get("messages", [])
            )
            raise RuntimeError(f"smartctl: {messages or 'błąd wywołania'}")

        return data

    @staticmethod
    def _attribute_table(data: dict) -> dict[int, dict]:
        table = data.get("ata_smart_attributes", {}).get("table", [])
        return {row["id"]: row for row in table if "id" in row}

    @classmethod
    def _wear_percent(cls, attributes: dict[int, dict]) -> int | None:
        """Pozostałe życie SSD (albo None, gdy dysk nie raportuje wear)."""
        for attr_id in WEAR_ATTRIBUTE_IDS:
            row = attributes.get(attr_id)
            if row and isinstance(row.get("value"), int):
                return max(0, min(100, row["value"]))
        return None

    async def collect(self) -> dict:
        data = await self._run_smartctl()
        attributes = self._attribute_table(data)

        passed = bool(data.get("smart_status", {}).get("passed"))
        temp_c = data.get("temperature", {}).get("current")
        reallocated = attributes.get(5, {}).get("raw", {}).get("value")
        health = self._wear_percent(attributes)

        # TEMP + FREE + HEALTH — HEALTH tylko jako liczba, nie na wykresie.
        metrics: list[dict] = []
        if temp_c is not None:
            metrics.append({
                "label": "TEMP",
                "value": f"{int(temp_c)}°",
                "type": "number",
                "state": STATUS_WARNING if temp_c >= TEMP_WARNING_C else STATUS_OK,
            })

        try:
            free_bytes = shutil.disk_usage(self.mount).free
            metrics.append({
                "label": "FREE",
                "value": self._fmt_free(free_bytes),
                "type": "number",
            })
        except OSError:
            pass

        if health is not None:
            metrics.append({
                "label": "HEALTH",
                "value": f"{health}%",
                "type": "number",
                "state": STATUS_WARNING if health <= HEALTH_WARNING_PCT else STATUS_OK,
            })

        chart = None
        if temp_c is not None:
            self._temp_hist.append(int(temp_c))
            if len(self._temp_hist) >= 2:
                chart = {
                    "type": "line",
                    "series": [
                        {"label": "TEMP", "role": "accent", "points": list(self._temp_hist)},
                    ],
                }

        return {
            "metrics": metrics,
            "chart": chart,
            "_passed": passed,
            "_temp_c": temp_c,
            "_reallocated": reallocated,
            "_health": health,
        }

    def get_status(self, data: dict) -> str:
        if not data["_passed"]:
            return STATUS_ERROR
        too_hot = data["_temp_c"] is not None and data["_temp_c"] >= TEMP_WARNING_C
        has_reallocated = bool(data["_reallocated"])
        health = data.get("_health")
        worn = health is not None and health <= HEALTH_WARNING_PCT
        return STATUS_WARNING if (too_hot or has_reallocated or worn) else STATUS_OK


if __name__ == "__main__":
    run_standalone(SmartCollector())
