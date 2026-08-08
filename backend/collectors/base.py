"""Kontrakt danych dashboardu — bazowa klasa każdego collectora.

To jest serce rozszerzalności całego projektu (sekcja 3 specyfikacji).
Każde źródło danych (Pi-hole, SMART, WireGuard, metryki systemowe, ...)
to osobny moduł z klasą dziedziczącą po `Collector`. Backend i frontend
znają WYŁĄCZNIE ten kontrakt — nie wiedzą nic o konkretnych źródłach.
Dzięki temu dodanie nowego serwisu = nowy plik + wpis w registry.py
+ wpis w config.yaml, zero zmian w istniejącym kodzie.

Znormalizowany kształt karty (to zwraca `snapshot()`, to konsumuje frontend):

    {
      "id": "pihole",
      "label": "Pi-hole",
      "icon": "shield",
      "status": "ok" | "warning" | "error",
      "metrics": [ ...lista metryk, patrz niżej... ],
      "chart": { ...opcjonalny wykres, patrz niżej... } | None,
      "actions": [ ...opcjonalne przyciski akcji, patrz niżej... ]
    }

Kształt akcji (ekran dotykowy — deklarowane przez collector, renderowane generycznie):

    {
      "id": "block_off_5",   # identyfikator dla POST /api/collectors/<id>/actions/<id>
      "label": "OFF 5M",     # krótki tekst na przycisku (miejsce na 7")
      "style": "warn"        # "default" | "accent" | "warn" — tylko styl, nie logika
    }

Kształt pojedynczej metryki:

    {
      "label": "Zapytania dziś",       # podpis widoczny na karcie
      "value": "12.4k",                 # wartość (string lub liczba)
      "type":  "number",                # sposób renderowania, patrz niżej
      "state": "ok"                     # OPCJONALNE kolorowanie tej jednej metryki
    }

Typy metryk (frontend renderuje je generycznie, bez wiedzy o źródle):
  - "number"  — duża liczba (główne statystyki karty)
  - "percent" — duża liczba z sufiksem % (value = liczba 0-100)
  - "bar"     — pasek postępu z procentem (value = liczba 0-100)
  - "status"  — kropka stanu + tekst (np. peer WireGuard, wynik SMART)
  - "text"    — zwykły wiersz "podpis: wartość"

Pole "state" metryki: "ok" | "warning" | "error" | "muted" — koloruje kropkę
lub pasek TEJ metryki (np. nieaktywny peer = "muted"). Statusy CAŁEJ karty
(get_status) to tylko "ok" | "warning" | "error".

Kształt wykresu (opcjonalny; specyfikacja sekcja 3.1 przewiduje pole "chart"):

    {
      "type": "line",
      "series": [
        {"label": "zapytania",    "role": "muted",  "points": [12, 40, ...]},
        {"label": "zablokowane",  "role": "accent", "points": [3, 11, ...]}
      ]
    }

"role" mówi frontendowi, którym kolorem z palety narysować serię
("accent" = kolor akcentu, "muted" = stonowany) — collector nie zna
konkretnych kolorów, to decyzja warstwy prezentacji.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any

# Statusy karty, od najlepszego do najgorszego. Frontend koloruje kartę,
# a backend wylicza z nich zbiorczy status całego dashboardu (pasek górny).
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

# Dodatkowy stan dostępny TYLKO dla pojedynczych metryk (szara kropka,
# np. peer WireGuard, który od dawna się nie odzywał — to nie jest błąd).
STATE_MUTED = "muted"


class Collector(ABC):
    """Bazowa klasa dla każdego źródła danych w dashboardzie."""

    # --- metadane, każda klasa potomna MUSI je nadpisać ---
    id: str = "base"            # unikalny identyfikator, np. "pihole" (musi zgadzać się z config.yaml)
    label: str = "???"          # nazwa wyświetlana na karcie, np. "Pi-hole"
    icon: str = "box"           # nazwa ikony znanej frontendowi (patrz ICONS w frontend/app.js)
    refresh_interval: int = 10  # co ile sekund odświeżać dane TEGO źródła (cache w main.py)

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        # `settings` to sekcja `collectors.<id>` z config.yaml — dzięki temu
        # konfiguracja (np. ścieżka dysku, nazwy peerów) nie jest zaszyta w kodzie.
        self.settings: dict[str, Any] = settings or {}

    @abstractmethod
    async def collect(self) -> dict:
        """Zbiera dane ze źródła i zwraca dict z kluczami "metrics" (lista metryk)
        oraz opcjonalnie "chart".

        Klucze zaczynające się od "_" są prywatne — nie trafiają do API,
        ale get_status() może z nich skorzystać (np. surowa temperatura,
        zanim została sformatowana do stringa "42°C").

        Błędy NALEŻY zgłaszać wyjątkiem (z czytelnym komunikatem po polsku) —
        warstwa agregująca w main.py zamieni go na kartę "error", nie
        wywracając reszty dashboardu (Faza 4 specyfikacji).
        """

    @abstractmethod
    def get_status(self, data: dict) -> str:
        """Zwraca STATUS_OK / STATUS_WARNING / STATUS_ERROR na podstawie danych
        zwróconych przez collect() — używane do kolorowania karty."""

    def list_actions(self, data: dict) -> list[dict]:
        """Opcjonalne akcje na karcie (dotyk). Domyślnie brak.

        `data` to wynik collect() — akcje mogą zależeć od stanu
        (np. inne przyciski gdy blokowanie Pi-hole jest wyłączone).
        Nadpisz w collectorze, który obsługuje interakcję.
        """
        return []

    async def run_action(self, action_id: str) -> dict:
        """Wykonuje akcję zadeklarowaną w list_actions().

        Zwraca dict z przynajmniej {"ok": True, "message": "..."}.
        Nieznana akcja / błąd → wyjątek (endpoint zamieni na HTTP 400/500).
        """
        raise RuntimeError(f"Collector {self.id!r} nie obsługuje akcji {action_id!r}")

    async def snapshot(self) -> dict:
        """Składa pełną, znormalizowaną kartę (metadane + dane + status + akcje).

        To jedyna metoda wołana przez warstwę agregującą — dzięki temu
        format karty jest zdefiniowany w JEDNYM miejscu, a collectory
        implementują tylko collect() / get_status() (+ opcjonalnie akcje).
        """
        data = await self.collect()
        return {
            "id": self.id,
            "label": self.label,
            "icon": self.icon,
            "status": self.get_status(data),
            "metrics": data.get("metrics", []),
            "chart": data.get("chart"),
            "actions": self.list_actions(data),
            # Opcjonalny układ karty — frontend zna "default" i "hero"
            # (szeroka karta na górze). Collectory bez tego pola = default.
            "layout": data.get("layout") or "default",
        }


def run_standalone(collector: Collector) -> None:
    """Uruchamia pojedynczy collector z linii poleceń i wypisuje wynik.

    Każdy moduł collectora ma na końcu blok `if __name__ == "__main__"`,
    dzięki czemu można go przetestować W IZOLACJI, bez startowania
    całego backendu (wymóg Fazy 2 specyfikacji: "każdy testowalny osobno"):

        cd backend
        python -m collectors.system
    """
    payload = asyncio.run(collector.snapshot())
    print(json.dumps(payload, indent=2, ensure_ascii=False))
