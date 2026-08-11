"""Rejestr wtyczek (registry pattern) — sekcja 3.2 specyfikacji.

DODANIE NOWEGO ŹRÓDŁA DANYCH (np. Nextcloud za pół roku) to w tym pliku
dokładnie dwie linie: import + wpis na liście ALL_COLLECTOR_CLASSES.
Trzecia (i ostatnia) zmiana to wpis w config.yaml. Nic więcej — ani main.py,
ani frontend, ani istniejące collectory nie wymagają modyfikacji.
"""

from __future__ import annotations

import logging

from .base import Collector
from .pihole import PiholeCollector
from .services import ServicesCollector
from .smart import SmartCollector
from .system import SystemCollector
from .wireguard import WireguardCollector

log = logging.getLogger("hub.registry")

# Wszystkie DOSTĘPNE collectory. O tym, które faktycznie działają (i w jakiej
# kolejności pojawiają się na ekranie), decyduje lista w config.yaml —
# włączanie/wyłączanie źródła nie wymaga dotykania kodu (sekcja 3.4).
ALL_COLLECTOR_CLASSES: list[type[Collector]] = [
    PiholeCollector,
    SmartCollector,
    SystemCollector,
    WireguardCollector,
    ServicesCollector,
    # <- nowy collector dopisujesz tutaj (plus import wyżej)
]


def build_enabled_collectors(config: dict) -> list[Collector]:
    """Tworzy instancje collectorów włączonych w config.yaml.

    Każda instancja dostaje swoją sekcję ustawień (collectors.<id>), więc
    konfiguracja źródła mieszka w jednym pliku YAML, nie w kodzie.
    """
    available = {cls.id: cls for cls in ALL_COLLECTOR_CLASSES}
    enabled_ids = config.get("enabled_collectors") or []
    all_settings = config.get("collectors") or {}

    instances: list[Collector] = []
    for collector_id in enabled_ids:
        cls = available.get(collector_id)
        if cls is None:
            # Literówka w config.yaml nie powinna wywracać całego backendu —
            # logujemy i jedziemy dalej z resztą.
            log.warning(
                "config.yaml wymienia nieznany collector %r (dostępne: %s) — pomijam",
                collector_id, ", ".join(sorted(available)),
            )
            continue
        instances.append(cls(all_settings.get(collector_id) or {}))

    if not instances:
        log.warning("Żaden collector nie jest włączony — dashboard będzie pusty. Sprawdź config.yaml.")
    return instances
