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
      "type": "line" | "stacked_bar",
      "series": [
        {"label": "zablokowane",  "role": "accent", "points": [3, 11, ...]},
        {"label": "zapytania",    "role": "muted",  "points": [12, 40, ...]}
      ]
    }

Typy wykresu:
  - "line"        — linie (metryki systemowe: CPU / RAM / temp).
  - "stacked_bar" — pionowe słupki warstwowe (Pi-hole: klasyczny UI).
    Frontend bierze serię "accent" jako dolny segment (blocked) oraz
    serię "muted" jako TOTAL; górny segment = max(0, total - blocked).
    Gdy total < blocked, blocked jest przycięty do total (brak ujemnego
    „permitted”). Świadome odejście od wcześniejszej decyzji „tylko linie”
    (sekcja 10 / .cursorrules) — słupki warstwowe są czytelniejsze dla
    historii zapytań DNS niż nakładające się pathy.

"role" mówi frontendowi, którym kolorem z palety narysować serię
("accent" = kolor akcentu, "muted" = stonowany, "warn" = ostrzeżenie) —
collector nie zna konkretnych kolorów, to decyzja warstwy prezentacji.

--------------------------------------------------------------------------
WARSTWA SEMANTYCZNA (dodana dla panelu instrumentowego, frontend/panel/)
--------------------------------------------------------------------------

Pierwotny kontrakt mówił frontendowi JAK coś narysować ("type": "bar",
"layout": "hero"). To okazało się pułapką: prezentacja wyciekła do
collectorów, więc każda zmiana układu ekranu wymagała walki z CSS-em
i psuła pozostałe strony.

Dlatego `snapshot()` dokłada teraz do każdej metryki pola opisujące
ZNACZENIE, a nie wygląd — frontend sam decyduje, co z tym zrobi przy
danym rozmiarze ekranu:

    "importance": "primary" | "detail"   # waga NA WŁASNEJ stronie
    "rail":       True | False           # dodatkowo w szynie „na każdej stronie"
    "rail_label": "SSD"                  # krótki podpis w szynie (gdy rail)
    "num":   46.0     # wartość liczbowa wyłuskana z "46%" (albo None)
    "unit":  "%"      # jednostka wyłuskana z wartości
    "range": [0, 100] # zakres do wskaźników (albo None)

`importance` i `rail` są ORTOGONALNE — i to jest ważne. Jedna metryka może
być jednocześnie wielką liczbą na swojej stronie i wskaźnikiem w szynie
(tak jest z CPU). Gdyby to był jeden wspólny „poziom istotności", trzeba by
wybierać: albo szyna, albo scena.

Znaczenie:
  - primary — JEDNA wielka liczba na scenie; to, po co patrzysz na ekran.
  - detail  — mała wartość w prawym doku / drugim planie scenu.
  - rail    — cienki wskaźnik w lewej szynie, widoczny na KAŻDEJ stronie.

Collector deklaruje to atrybutami klasy (patrz `primary_metric`,
`vital_metrics`, `metric_ranges`). Nic nie musi — bez deklaracji pierwsza
metryka liczbowa awansuje na `primary`, reszta to `detail`. Stary frontend
tych pól nie czyta, więc zmiana jest w pełni wstecznie zgodna.

Dzięki temu nowe źródło danych = nowy plik + registry + config, a panel
dostaje kolejną stronę BEZ zmian w JS/CSS (wymóg .cursorrules).
"""

from __future__ import annotations

import asyncio
import json
import re
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

# Waga metryki na własnej stronie — patrz docstring modułu.
IMPORTANCE_PRIMARY = "primary"
IMPORTANCE_DETAIL = "detail"

# Metryki bywają stringami z jednostką ("46%", "43°", "142GB") — historycznie
# rozbijał je regexem frontend, co dało błąd Number("46%") → NaN (wskaźniki
# pokazywały 0%). Robimy to raz, po stronie backendu.
_VALUE_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(.*)$")

# Typy metryk, które mają sens jako „wielka liczba” na scenie.
_NUMERIC_TYPES = frozenset({"number", "percent", "bar"})


def split_value(value: Any) -> tuple[float | None, str]:
    """Rozdziela wartość metryki na liczbę i jednostkę.

    "46%"    -> (46.0, "%")
    "142GB"  -> (142.0, "GB")
    "1,25"   -> (1.25, "")      # przecinek dziesiętny (locale PL)
    "OFF"    -> (None, "")      # wartość nieliczbowa — brak wskaźnika
    """
    if isinstance(value, bool):
        return None, ""
    if isinstance(value, (int, float)):
        return float(value), ""
    match = _VALUE_RE.match(str(value))
    if match is None:
        return None, ""
    return float(match.group(1).replace(",", ".")), match.group(2).strip()


class Collector(ABC):
    """Bazowa klasa dla każdego źródła danych w dashboardzie."""

    # --- metadane, każda klasa potomna MUSI je nadpisać ---
    id: str = "base"            # unikalny identyfikator, np. "pihole" (musi zgadzać się z config.yaml)
    label: str = "???"          # nazwa wyświetlana na karcie, np. "Pi-hole"
    icon: str = "box"           # nazwa ikony znanej frontendowi (patrz ICONS w frontend/app.js)
    refresh_interval: int = 10  # co ile sekund odświeżać dane TEGO źródła (cache w main.py)

    # --- semantyka metryk (opcjonalna, patrz docstring modułu) ---

    # Etykieta metryki, która ma być WIELKĄ liczbą na scenie panelu.
    # None = pierwsza metryka liczbowa awansuje automatycznie.
    primary_metric: str | None = None

    # Metryki do lewej szyny panelu (widoczne na każdej stronie).
    # Klucz = etykieta metryki, wartość = krótki podpis w szynie —
    # dzięki temu dwie różne metryki „TEMP" (CPU i SSD) da się rozróżnić.
    vital_metrics: dict[str, str] = {}

    # Jawny zakres dla wskaźnika, gdy nie wynika z jednostki.
    # Procenty dostają [0, 100] automatycznie; temperatura Pi nie ma
    # naturalnego zakresu, więc podajemy sensowne widełki.
    metric_ranges: dict[str, tuple[float, float]] = {}

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

    def annotate_metrics(self, metrics: list[dict]) -> list[dict]:
        """Dokłada do metryk warstwę semantyczną (patrz docstring modułu).

        Nie modyfikuje dictów zwróconych przez collect() — zwraca kopie,
        więc collector może bezpiecznie trzymać własne struktury.

        `importance`:
          1. etykieta == `primary_metric`                  -> "primary"
          2. brak deklaracji: pierwsza metryka liczbowa    -> "primary"
          3. wszystko pozostałe                            -> "detail"

        `rail` ustawiamy NIEZALEŻNIE od powyższego — metryka może być
        i wielką liczbą, i wskaźnikiem w szynie (np. CPU).
        """
        rails = {key.upper(): caption for key, caption in self.vital_metrics.items()}
        ranges = {key.upper(): value for key, value in self.metric_ranges.items()}
        declared_primary = (self.primary_metric or "").upper()
        primary_taken = False

        annotated: list[dict] = []
        for metric in metrics:
            item = dict(metric)
            label = str(item.get("label", "")).upper()
            metric_type = item.get("type") or "text"

            num, unit = split_value(item.get("value"))
            # type "percent" trzyma samą liczbę, a "%" dokleja dopiero UI.
            if metric_type == "percent" and not unit:
                unit = "%"

            if declared_primary:
                is_primary = label == declared_primary
            else:
                is_primary = (
                    not primary_taken
                    and metric_type in _NUMERIC_TYPES
                    and num is not None
                )
            if is_primary:
                primary_taken = True

            span = ranges.get(label)
            if span is None and (unit == "%" or metric_type in ("percent", "bar")):
                span = (0.0, 100.0)

            item["importance"] = IMPORTANCE_PRIMARY if is_primary else IMPORTANCE_DETAIL
            item["rail"] = label in rails
            if item["rail"]:
                item["rail_label"] = rails[label]
            item["num"] = num
            item["unit"] = unit
            item["range"] = list(span) if span else None
            annotated.append(item)

        return annotated

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
            "metrics": self.annotate_metrics(data.get("metrics", [])),
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
