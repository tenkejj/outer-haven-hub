# Outer Haven Hub — kontekst dla LLM

Dokument przeznaczony dla innego modelu językowego: kompletny opis projektu,
żeby dało się go bezpiecznie modyfikować **bez zgadywania**. Identyfikatory
techniczne (pliki, klasy, endpointy, zmienne env) pozostawione po angielsku
jak w kodzie.

**Repo:** https://github.com/tenkejj/outer-haven-hub  
**Workspace lokalny (ten clone):** `/home/tenkej/dev/outerhaven`  
**Specyfikacja źródłowa (poza repo):** `SPECYFIKACJA-outer-haven-hub.md` (mother-base) — w tym repozytorium **nie ma** tego pliku; zasady z niej są skondensowane w `.cursorrules`, `KONTEKST.md` i w komentarzach w kodzie.

**NIE commituj sekretów.** W `.env` używaj placeholderów (`PIHOLE_APP_PASSWORD=...`).

---

## 1. Cel projektu i twarde ograniczenia

### Po co

Fizyczny **dashboard / kiosk** infrastruktury domowej na Raspberry Pi 4
(`mother-base`): jednym rzutem oka — Pi-hole, WireGuard, metryki systemu Pi,
zdrowie SSD (SMART). Nazewnictwo (Outer Haven, mother-base) inspirowane Metal Gear.

### Stack (nienegocjowalny bez jawnego komentarza)

| Warstwa | Technologia | Uwagi |
|--------|-------------|--------|
| Backend | Python 3 + **FastAPI** + uvicorn | nasłuch **wyłącznie** `127.0.0.1:8090` |
| Frontend | **vanilla** HTML / CSS / JS | **bez** React/Vue/Svelte |
| Config | `config.yaml` + `backend/.env` | sekrety tylko w `.env` |
| Deploy | systemd + wąski sudoers + opcjonalnie Caddy | backend nie jest rootem |

### Filozofia

- **Minimalizm zasobów** — to Pi 4, nie serwer produkcyjny. Nie dodawaj
  zależności/frameworków „na zapas”.
- Kod **czytelny i komentowany** — właściciel uczy się backendu.
- Każde **odchylenie od speki** musi być **jawnie skomentowane** w kodzie
  (przykład: Pi-hole history v6 zamiast v5 — `backend/collectors/pihole.py`).

### UI (MGS codec / NieR)

- Flat, geometryczny, mono (JetBrains Mono Nerd Font lokalnie).
- **Jeden** stonowany akcent oliwkowy (`--accent: #8f9a63`).
- Narożniki L, twarde krawędzie, duże cele dotykowe (`--touch: 44px`).
- **ZAKAZ:** gradienty tła, soft glow, box-shadow z poświatą, zaokrąglone
  „karty AI”, fiolet, glassmorphism, emoji.

### Decyzje otwarte speki (już rozstrzygnięte)

1. **Akcje z ekranu:** tak — `actions[]` + `POST /api/collectors/<id>/actions/<action_id>`. Start: Pi-hole OFF 5M / 15M / ON.
2. **Wykresy:** tak — linie SVG; Pi-hole 24h z `/api/history`.
3. **Alarmowe podświetlenie:** tak — status `ok|warning|error` (pasek / kod), **bez** glow.

---

## 2. Mapa katalogów

```
outerhaven/   (lub outer-haven-hub na Pi)
├── LLM-CONTEXT.md          ← ten dokument
├── KONTEKST.md             ← krótki kontekst dla człowieka
├── README.md               ← demo lokalne + link do DEPLOY
├── DEPLOY.md               ← produkcja na Pi
├── CHANGELOG.md
├── .cursorrules            ← reguły dla Cursora / agentów
├── .gitignore              ← m.in. backend/.env, .venv
├── config.yaml             ← enabled_collectors + settings per id
│
├── backend/
│   ├── main.py             ← FastAPI: dashboard, actions, static FE, cache
│   ├── requirements.txt
│   ├── .env.example        ← szablon sekretów
│   ├── .env                ← LOKALNE / NA PI — nie w gicie
│   └── collectors/
│       ├── __init__.py
│       ├── base.py         ← KONTRAKT karty (serce rozszerzalności)
│       ├── registry.py     ← lista klas + build_enabled_collectors()
│       ├── pihole.py
│       ├── wireguard.py
│       ├── system.py
│       ├── smart.py
│       ├── services.py     ← systemd units → strony SVC / MEDIA
│       └── demo.py         ← tylko HUB_DEMO=1
│
├── frontend/               ← UI #1: dashboard kart, serwowany z "/"
│   ├── index.html          ← shell + page nav HUB|SVC|MEDIA
│   ├── app.js              ← poll, pages+hash, karty, wykresy, akcje, boot
│   ├── style.css           ← canvas 1024×600, HUD, hero, charts, svc/media
│   ├── assets/             ← emblemy Outer Heaven (png)
│   ├── fonts/              ← JetBrainsMonoNerdFont-{Regular,Medium,Bold}.ttf
│   └── panel/              ← UI #2: panel instrumentowy, serwowany z "/panel/"
│       ├── index.html      ← strefy: bar / rail / stage / dock / nav
│       ├── panel.css       ← stałe strefy px (bez siatki kart)
│       └── panel.js        ← SSE + punktowe update DOM, strony z API
│
└── deploy/
    ├── outer-haven-hub.service   ← systemd
    ├── sudoers-outer-haven-hub   ← smartctl + wg (NOPASSWD, wąsko)
    └── Caddyfile.snippet         ← przykład reverse proxy
```

**Nie ma** w repo: Dockerfile, CI, SPECYFIKACJA-*.md, testów automatycznych.

---

## 3. Uruchomienie (demo vs produkcja)

### Demo lokalne (sztuczne dane, bez Pi / bez usług)

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
HUB_DEMO=1 uvicorn main:app --host 127.0.0.1 --port 8090
```

Otwórz: http://127.0.0.1:8090/

- `HUB_DEMO=1` → `main.py` ładuje `DEMO_COLLECTORS` z `collectors/demo.py`
  zamiast `registry` + `config.yaml`.
- Akcje Pi-hole w demo **działają lokalnie** (timer w pamięci procesu).
- Footer zawsze pokazuje `LIVE` (nawet w demo) — `mode` w API jest hardcodowane
  na `"LIVE"`; `HUB_DEMO` dotyczy tylko źródeł danych.

### Produkcja (Pi)

Patrz `DEPLOY.md` + sekcja 10 poniżej. **Nie** ustawiaj `HUB_DEMO` w systemd.

### Test pojedynczego collectora (izolacja)

Każdy realny collector ma `if __name__ == "__main__": run_standalone(...)`:

```bash
cd backend
. .venv/bin/activate
python -m collectors.system
python -m collectors.pihole   # wymaga .env z PIHOLE_APP_PASSWORD
```

`run_standalone` jest w `base.py` — `asyncio.run(snapshot())` + JSON na stdout.

### Zależności Pythona (`backend/requirements.txt`)

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
httpx>=0.27.0
PyYAML>=6.0.2
python-dotenv>=1.0.1
```

**Brak** psutil — system czyta `/proc` i `/sys` (świadome odstępstwo od speki).

---

## 4. Konfiguracja i sekrety

### `config.yaml` (korzeń repo)

Kontroluje:

1. **`enabled_collectors`** — lista id w kolejności kart na dashboardzie.
2. **`collectors.<id>`** — ustawienia przekazane do `__init__(settings)` collectora.

Aktualna treść (skrót semantyczny):

```yaml
enabled_collectors:
  - pihole
  - wireguard
  - system
  - smart
  - services

collectors:
  pihole:
    base_url: "http://127.0.0.1"   # lub http://127.0.0.1:8080 gdy Caddy na 80/443
  smart:
    device: "/dev/sda"             # MUSI zgadzać się z sudoers 1:1
    mount: "/"
  wireguard:
    peer_names:
      # "PUBLIC_KEY_BASE64=": "laptop"
  services:
    units:                         # SVC = wszystkie; MEDIA = media: true
      - id: jellyfin
        unit: jellyfin.service
        label: JELLYFIN
        media: true
        note: "http://mother-base:8096"
```

Ścieżka pliku: domyślnie `REPO_ROOT/config.yaml`, override:

```bash
HUB_CONFIG=/ścieżka/do/config.yaml
```

(systemd ustawia `HUB_CONFIG=/home/pi/outer-haven-hub/config.yaml`).

### `backend/.env` (sekrety — nie w gicie)

Z `.env.example`:

| Zmienna | Wymagana? | Opis |
|---------|-----------|------|
| `PIHOLE_APP_PASSWORD` | tak (prod, collector pihole) | Hasło **aplikacji** Pi-hole (Settings → Web Interface/API), **nie** główne hasło panelu |
| `HUB_NAME` | nie | Nazwa na API `host` (domyślnie `platform.node()`) |

Ładowanie: `load_dotenv(BACKEND_DIR / ".env")` na starcie `main.py`.  
W systemd: `EnvironmentFile=-/home/pi/outer-haven-hub/backend/.env`.

### Inne zmienne środowiskowe

| Zmienna | Gdzie | Efekt |
|---------|-------|--------|
| `HUB_DEMO=1` | env przed uvicorn | sztuczne collectory |
| `HUB_CONFIG` | env | ścieżka do YAML |
| `HUB_NAME` | env / .env | pole `host` w `/api/dashboard` |

### Placeholder sekretów (przykład — NIE używaj prawdziwych wartości w docs/commitach)

```
PIHOLE_APP_PASSWORD=replace-with-pihole-app-password
```

---

## 5. Architektura backendu (`backend/main.py`)

### Rola pliku (celowo mała)

1. Wczytać config / demo i zbudować listę `CachedCollector`.
2. `GET /api/dashboard` — równoległa agregacja.
3. `POST /api/collectors/{collector_id}/actions/{action_id}` — akcje.
4. Serwować `../frontend` jako static (z `Cache-Control: no-cache` dla HTML/CSS/JS).

**Brak CORS** — FE i API same-origin za Caddy / localhost.

### Startup / „lifespan”

Nie ma oficjalnego `lifespan` FastAPI. Collectory budowane są **przy imporcie
modułu**:

```python
RUNNERS = build_runners()
RUNNERS_BY_ID = {runner.collector.id: runner for runner in RUNNERS}
```

Konsekwencja: zmiana `config.yaml` / `.env` wymaga **restartu** procesu uvicorn/systemd.

### `CachedCollector`

Opakowanie wokół `Collector`:

- Cache wyniku wg `collector.refresh_interval` (sekundy), czas `time.monotonic()`.
- `asyncio.Lock` + double-check (dwa równoległe GET nie dublują collect).
- `asyncio.wait_for(snapshot(), timeout=COLLECT_TIMEOUT_S)` gdzie `COLLECT_TIMEOUT_S = 10.0`.
- Wyjątek lub timeout → karta błędu (`status: "error"`, `error: message`, puste metrics/actions) — **bez** HTTP 500 całego dashboardu.
- `invalidate()` — po udanej akcji, wymusza świeży collect przy następnym `get()`.
- Każdy payload dostaje `updated_at` (unix seconds).

### `GET /api/dashboard`

```python
cards = await asyncio.gather(*(runner.get() for runner in RUNNERS))
overall = max(card statuses by severity: ok=0, warning=1, error=2)
```

**Przykładowy kształt odpowiedzi:**

```json
{
  "generated_at": 1720000000,
  "host": "mother-base",
  "uptime": "3d 4h",
  "mode": "LIVE",
  "status": "ok",
  "collectors": [
    {
      "id": "pihole",
      "label": "Pi-hole",
      "icon": "shield",
      "status": "ok",
      "layout": "hero",
      "metrics": [ /* patrz kontrakt */ ],
      "chart": { "type": "line", "series": [ /* ... */ ] },
      "actions": [
        { "id": "block_off_5", "label": "OFF 5M", "style": "warn", "group": "block" }
      ],
      "updated_at": 1720000000
    }
  ]
}
```

Pola prywatne z `collect()` (klucze `_…`) **nie** trafiają do API — `snapshot()`
bierze tylko `metrics`, `chart`, `layout` + metadane + `actions` + `status`.

Karta błędu (cache izolacji):

```json
{
  "id": "smart",
  "label": "SSD",
  "icon": "hard-drive",
  "status": "error",
  "metrics": [],
  "chart": null,
  "actions": [],
  "layout": "default",
  "error": "smartctl nie zwrócił danych: ...",
  "updated_at": 1720000000
}
```

`uptime` w top-level to uptime **hosta** z `/proc/uptime` (nie uptime procesu).

### `GET /api/state` — lekki stan (dla `/panel/`)

Ta sama koperta co `/api/dashboard`, ale każda karta ma `chart: null`
i dodatkowe `has_chart: bool`. Powód: historia Pi-hole to 144 punkty × 2
serie, a wykres widać tylko na jednej stronie naraz.

### `GET /api/history/{collector_id}` — punkty wykresu na żądanie

`{"id": "pihole", "chart": {...}}`. Czyta ten sam cache co `/api/state`,
więc wejście na stronę z wykresem **nie** generuje ruchu do Pi-hole ani sudo.
Nieznany collector → 404.

### `GET /api/stream` — SSE ze stanem

`text/event-stream`, ramka `data: <ten sam JSON co /api/state>` co
`STREAM_INTERVAL_S` (2 s). Nie zmienia częstotliwości odpytywania źródeł —
te mają własny `refresh_interval` w cache.

Po co push, a nie polling: stary frontend przebudowywał cały DOM co 5 s,
więc nie dało się animować pojedynczej wartości.

**Pułapka:** reverse proxy potrafi buforować strumień. Panel ma watchdog
(`WATCHDOG_MS`) i przy ciszy dłuższej niż 8 s sam wraca do pollowania
`/api/state`, więc za Caddy działa nawet bez `flush_interval -1`.

### `POST /api/collectors/{collector_id}/actions/{action_id}`

- 404 — nieznany collector.
- Timeout akcji (10 s) → 504.
- Inny wyjątek z `run_action` → 400 z `detail`.
- Sukces → `invalidate()` cache + JSON:

```json
{
  "ok": true,
  "collector": "pihole",
  "action": "block_off_5",
  "message": "blocking disabled for 5 min"
}
```

### Static frontend

`NoCacheStaticFiles` montowane na `/` **na końcu** (po trasach `/api/*`).
Dla `.html` / `.css` / `.js`: `Cache-Control: no-cache, must-revalidate` —
Chromium w kiosku inaczej trzyma stary CSS po `git pull`.

W `index.html` dodatkowo query `?v=canvas-scale1` na CSS/JS (cache-bust ręczny).

---

## 6. Kontrakt collectora (`backend/collectors/base.py`) — szczegółowo

To **jedyny** format, który znają backend (agregator) i frontend. Nowy serwis
= nowa klasa dziedzicząca `Collector`, **bez** specjalnych ifów w `main.py` / `app.js`
(poza ewentualnym kosmetycznym UI, jak Pi-hole segment — patrz niżej).

### Metadane klasy (nadpisać)

| Pole | Typ | Znaczenie |
|------|-----|-----------|
| `id` | str | unikalne; musi = klucz w `config.yaml` / `enabled_collectors` |
| `label` | str | tytuł karty |
| `icon` | str | nazwa ikony (w kontrakcie); **obecny frontend NIE renderuje `icon`** — pole jest w API, UI używa tylko `label` |
| `refresh_interval` | int | sekundy cache w `CachedCollector` |

### Metody

| Metoda | Wymagana? | Opis |
|--------|-----------|------|
| `async collect() -> dict` | tak | zwraca `metrics`, opcjonalnie `chart`, `layout`, prywatne `_…` |
| `get_status(data) -> str` | tak | `"ok"` \| `"warning"` \| `"error"` |
| `list_actions(data) -> list[dict]` | nie (domyślnie `[]`) | przyciski; mogą zależeć od stanu |
| `async run_action(action_id) -> dict` | nie | domyślnie `RuntimeError`; sukces: `{"ok": True, "message": "..."}` (ok doklejane też w endpoint) |
| `async snapshot() -> dict` | nie nadpisywać | składa kartę API |

### Kształt metryki

```json
{
  "label": "CPU",
  "value": "34%",
  "type": "number",
  "state": "ok"
}
```

**Typy `type` (frontend):**

| type | Render |
|------|--------|
| `number` | duża wartość; suffix jednostek wyciągany regexem (`%`, `°`, `k`, …) |
| `percent` | jak number, dokleja `%` do value |
| `bar` | pasek 0–100 |
| `status` | kropka + label + value |
| `text` | wiersz label / value (fallback) |

**`state` metryki:** `ok` \| `warning` \| `error` \| `muted`  
(`muted` tylko dla metryk — np. nieaktywny peer; **nie** jest statusem karty).

**Status karty** (`get_status` / `status` w API): tylko `ok` \| `warning` \| `error`.

### Kształt wykresu

```json
{
  "type": "line",
  "title": "opcjonalny",
  "caption": "opcjonalny",
  "series": [
    { "label": "CPU", "role": "accent", "points": [10, 20, 15] },
    { "label": "RAM", "role": "muted", "points": [40, 42, 41] },
    { "label": "TEMP", "role": "warn", "points": [43, 44, 43] }
  ]
}
```

`role`: `accent` \| `muted` \| `warn` — kolory z CSS, nie z collectora.  
Frontend downsampluje do max **48** punktów (`CHART_MAX_POINTS`).

### Kształt akcji

```json
{
  "id": "block_off_5",
  "label": "OFF 5M",
  "style": "default" | "accent" | "warn",
  "group": "block" | "util" | "tool"
}
```

- `style` — tylko wygląd.
- `group` — frontend grupuje: `block` → segment hero Pi-hole; `util`/`tool`
  mają puste renderery (`renderUtilActions` / `renderToolActions` zwracają `""`) —
  przygotowane pod przyszłość.
- Opcjonalnie w UI: `confirm` / `confirm_label` (obsługa w `actionButton`,
  ale obecne collectory tego nie używają).

### `layout`

- `"default"` — mała karta w dolnym rzędzie siatki 3 kolumn.
- `"hero"` — `grid-column: 1 / -1`, layout liczby | wykres (Pi-hole).

Ustawiane w `collect()` jako `"layout": "hero"`, w `snapshot()`: `data.get("layout") or "default"`.

**Uwaga:** `layout` opisuje WYGLĄD i istnieje tylko dla starego UI (`/`).
Nowy panel go ignoruje i patrzy na warstwę semantyczną poniżej. Nie dodawaj
kolejnych wartości `layout` — to ślepa uliczka, która wciągnęła prezentację
do backendu.

### Warstwa semantyczna (dla `/panel/`)

`snapshot()` woła `annotate_metrics()` i dokłada do KAŻDEJ metryki:

| Pole | Typ | Znaczenie |
|------|-----|-----------|
| `importance` | `"primary"` \| `"detail"` | waga na własnej stronie |
| `rail` | bool | czy jest też w szynie widocznej na każdej stronie |
| `rail_label` | str | krótki podpis w szynie (obecne gdy `rail`) |
| `num` | float \| null | liczba wyłuskana z `value` (`"46%"` → `46.0`) |
| `unit` | str | jednostka wyłuskana z `value` (`"%"`, `"°"`, `"GB"`) |
| `range` | `[lo, hi]` \| null | zakres wskaźnika (procenty dostają `[0,100]`) |

`importance` i `rail` są **ortogonalne** — CPU jest jednocześnie wielką
liczbą na swojej stronie i stałym wskaźnikiem w szynie.

Collector deklaruje to atrybutami klasy (nic nie musi):

```python
class SystemCollector(Collector):
    primary_metric = "CPU"                                  # wielka liczba
    vital_metrics = {"CPU": "CPU", "RAM": "RAM", "TEMP": "TEMP"}  # szyna
    metric_ranges = {"TEMP": (30.0, 85.0)}                  # zakres wskaźnika
```

Bez `primary_metric` pierwsza metryka liczbowa awansuje automatycznie.

`num` / `unit` liczymy w Pythonie, nie w JS — stary frontend parsował
`"46%"` przez `Number()`, dostawał `NaN` i pokazywał wskaźniki 0%.

### Błędy w `collect()`

**Rzucaj wyjątek** z czytelnym komunikatem (PL OK). `CachedCollector` zamieni
na kartę `error`. Nie połykaj błędów cicho zwracając pustą kartę „ok”.

---

## 7. Registry i rozszerzalność

### Reguła projektowa (krytyczna)

> Nowy collector = **jeden nowy plik** + **import + wpis** w `registry.py` +
> **wpis** w `config.yaml`.  
> Jeśli potrzebujesz zmieniać więcej plików — **napraw `base.py` / kontrakt**,
> nie obchodź wzorca.

Frontend powinien renderować generycznie. Wyjątek: hero Pi-hole ma specjalny
UX (segment OFF/ON, `renderBlockPlate`) — ale nadal oparty o kontrakt
`actions` / metrykę `BLOCK` typu `status`.

### `registry.py`

```python
ALL_COLLECTOR_CLASSES = [
    PiholeCollector,
    SmartCollector,
    SystemCollector,
    WireguardCollector,
]

def build_enabled_collectors(config) -> list[Collector]:
    # kolejność = enabled_collectors
    # nieznane id → log.warning, skip
```

`demo.py` **nie** jest w registry — tylko przez `HUB_DEMO`.

---

## 8. Collectory — co zbierają

### 8.1 `pihole` — `backend/collectors/pihole.py`

| | |
|--|--|
| id / label / icon | `pihole` / `Pi-hole` / `shield` |
| refresh | 10 s |
| settings | `base_url` (domyślnie `http://127.0.0.1`) |
| auth | `POST /api/auth` + `PIHOLE_APP_PASSWORD` → SID; header `X-FTL-SID`; re-login na 401 |
| HTTP | `httpx.AsyncClient`, timeout 5 s |

**Endpointy Pi-hole v6:**

- `GET /api/stats/summary` — total / blocked / percent / clients
- `GET /api/dns/blocking` — enabled + timer
- `GET /api/history` — kubełki 10 min / 24 h (**odstępstwo od speki v5** `overTimeData10mins`)
- `POST /api/dns/blocking` — `{ "blocking": bool, "timer"?: seconds }`

**Metryki:** TODAY, BLOCKED, % BLOCK, CLIENTS (opcjonalnie), BLOCK (status ON / OFF Nm).  
**layout:** `hero`.  
**chart:** TOTAL (muted) + BLOCKED (accent).  
**status karty:** `ok` jeśli blocking enabled, inaczej `warning`.  
**akcje:**

| action_id | efekt |
|-----------|--------|
| `block_off_5` | blocking=false, timer=300 |
| `block_off_15` | blocking=false, timer=900 |
| `block_on` | blocking=true |

Wszystkie z `group: "block"`.

### 8.2 `wireguard` — `backend/collectors/wireguard.py`

| | |
|--|--|
| id / label / icon | `wireguard` / `VPN` / `lock` |
| refresh | 10 s |
| settings | `peer_names: { pubkey: friendly }` |
| komenda | `sudo -n /usr/bin/wg show all dump` (**identyczna** z sudoers) |

Parsuje dump tab-separated (linie interfejsu 5 pól, peer 9 pól).  
**Metryki (tylko liczby — statusy peerów były ucinane na 7"):** LIVE, PEERS, TUNNELS.  
**chart:** DOWN / UP w KiB/s (różnica cumulative rx/tx między pollami).  
**status:** `ok` jeśli ≥1 interfejs, inaczej `warning`. Nieaktywni peerzy **nie** obniżają statusu.  
Handshake „active” < 180 s (stała `HANDSHAKE_ACTIVE_S`) — używane wewnętrznie do LIVE.

### 8.3 `system` — `backend/collectors/system.py`

| | |
|--|--|
| id / label / icon | `system` / `SYSTEM PI` / `cpu` |
| refresh | 5 s |
| źródła | `/proc/stat`, `/proc/meminfo`, `/sys/class/thermal/thermal_zone0/temp`, `/proc/loadavg`, `/proc/uptime` |
| settings | nieużywane (pusty dict OK) |

**Metryki:** CPU %, RAM % (względem MemAvailable), TEMP °C.  
**Progi warning:** TEMP ≥ 70°C, MEM ≥ 90%, CPU ≥ 95%.  
**chart:** CPU (accent), RAM (muted), TEMP (warn) — historia `deque` maxlen 36 (~3 min).  
**status karty:** warning jeśli którykolwiek próg.

CPU: różnica liczników między collectami; pierwszy raz sleep 0.25 s.

### 8.4 `smart` — `backend/collectors/smart.py`

| | |
|--|--|
| id / label / icon | `smart` / `SSD` / `hard-drive` |
| refresh | 60 s |
| settings | `device` (domyślnie `/dev/sda`), `mount` (domyślnie `/`) |
| komenda | `sudo -n /usr/sbin/smartctl -i -H -A -j <device>` |

**Metryki:** TEMP, FREE (`shutil.disk_usage(mount)`), HEALTH % (wear z atrybutów SMART ID 231/233/177/173/202/169).  
**chart:** tylko TEMP (gdy ≥2 próbki w historii).  
**status:** `error` jeśli SMART nie PASSED; `warning` jeśli temp ≥ 60°C, reallocated>0 (attr 5), lub health ≤ 20%.  
**sudoers:** ścieżka urządzenia w argv **musi** być literalnie taka jak w pliku sudoers.

### 8.5 `demo.py` (tylko `HUB_DEMO=1`)

Klasy: `DemoPihole`, `DemoWireguard`, `DemoSystem`, `DemoSmart` — te same `id` co produkcja.  
Lista: `DEMO_COLLECTORS` (kolejność: pihole, wireguard, system, smart, services).
DemoPihole: lokalny timer OFF 5/15 + akcje jak produkcja.

---

## 9. Frontend

Są **dwa** frontendy na tym samym API. Stary (`/`) zostaje, bo pozwala
porównać oba na sprzęcie; docelowy dla kiosku jest panel (`/panel/`).

### 9.0 Panel instrumentowy (`/panel/`) — podejście docelowe

**Dlaczego powstał.** Siatka kart z jednostkami `fr` negocjowała miejsce
przez CSS, więc wysokość wykresu wynikała z kombinacji klas
(`.card:not(.card--hero):not(.card--chart-focus) .chart { flex: 0 0 120px }`).
Każda nowa strona psuła poprzednie — w historii repo jest ciąg commitów,
które tylko naprawiają układ. Panel usuwa przyczynę, nie objawy.

**Trzy zasady:**

1. **Stałe strefy w pikselach.** 1024×600 dzieli się na: bar 52, mid 478
   (rail 96 | stage 770 | dock 156), nav 68. Każda strefa zna swój budżet,
   więc nie ma czego ściskać. Jedyne co się rozciąga to scena (jedna treść)
   i szyna (równy podział).
2. **Skala równomierna.** `scale(min(w/1024, h/600))` — jedna wartość, nie
   `scale(sx, sy)`. Na panelu 1024×600 wychodzi 1.0, piksel w piksel.
3. **Punktowe aktualizacje DOM.** Strona budowana raz; przy zmianie wartości
   wpisujemy tekst do węzłów `[data-k]`. Przebudowa tylko gdy zmieni się
   `shapeKey()` (inna strona / inny zestaw metryk).

**Strony biorą się z API.** Jedna strona = jeden collector, w kolejności
z `enabled_collectors`. Nowe źródło danych dostaje własną stronę i własny
kafel w nav **bez zmian w JS/CSS**.

**Reguły renderowania scenu** (decyduje POSTAĆ danych, nie id collectora):

| Warunek | Efekt |
|---------|-------|
| metryka `importance: "primary"` | wielka liczba (132 px) + jednostka |
| `num === null` (np. `"ON"`) | mniejszy stopień (`.big--text`, 78 px) |
| ≥ 5 metryk `type: "status"` | siatka lampek w scenie (systemd) |
| < 5 metryk `status` | płytka stanu obok liczby + sparkline w tle |
| brak detali i akcji | **dok znika**, scena poszerza się o jego 156 px |

Ostatnia reguła jest celowa: pusty dok to dokładnie ta „pustka”, która
psuła stary UI.

`panel.js` — funkcja `partition(card)` jest JEDNYM miejscem, które rozdziela
metryki na strefy. Dzięki temu ta sama wartość nie może trafić naraz na scenę
i do doku (w starym UI Pi-hole pokazywało się na dwóch stronach).

Transport: `EventSource("/api/stream")`, a przy ciszy dłuższej niż
`WATCHDOG_MS` przejście na polling `/api/state`. Historia wykresu: dociągana
per strona przez `/api/history/<id>`, odświeżana co `HISTORY_MS`.

`?cycle=1` (albo przycisk CYCLE) włącza auto-rotację stron co `CYCLE_MS`;
każdy dotyk wstrzymuje ją na `CYCLE_HOLD_MS`.

### 9.1 Dashboard kart (`/`) — poprzednie podejście

### Pliki

| Plik | Rola |
|------|------|
| `frontend/index.html` | shell, boot splash, topbar, page nav, views HUB/SVC/MEDIA, footer |
| `frontend/app.js` | scale, poll 5 s, pages+hash, render, charts SVG, actions, toast, boot |
| `frontend/style.css` | design system + layout kart (~2000 linii) |
| `frontend/fonts/*` | JB Nerd lokalnie |
| `frontend/assets/oh-emblem.png` (+ olive / outer-heaven warianty) | brand w topbarze |

### Model renderowania

1. `GET /api/dashboard` co `POLL_MS = 5000`.
2. `grid.innerHTML = collectors.map(renderCard).join("")` — **pełny re-render** (nie diff).
3. Podczas `actionBusy` poll jest pomijany.
4. Brak hardcodowanych sekcji per serwis w HTML — karty wyłącznie z API.
5. Specjalne ścieżki UI tylko gdy `layout === "hero"` (Pi-hole) oraz gdy
   `actions` mają `group: "block"`.

### Siatka

CSS `#dashboard-grid`: 3 kolumny × 2 rzędy (strona HUB).  
SVC: `#svc-grid` 4×2 z metryk `services`; MEDIA: subset `media: true` (Jellyfin/SMB).  
Nawigacja: `.page-nav` + `location.hash` (`#hub`/`#svc`/`#media`). Collector `services` **nie** jest kartą na HUB.
`.card--hero` spanuje pełną szerokość → typowy układ:

```
[======== Pi-hole hero ========]
[ VPN ] [ SYSTEM PI ] [ SSD ]
```

Kolejność kart = kolejność w `enabled_collectors` / `DEMO_COLLECTORS`.

### Kiosk scale 1024×600

- CSS: `.shell { width: 1024px; height: 600px; transform-origin: 0 0; }`
- JS: `shell.style.transform = scale(innerW/1024, innerH/600)` — **non-uniform**,
  pełne wypełnienie bez letterboxingu (lekkie rozciągnięcie względem 16:9 OK).
- Transform tylko wizualny — metryki/SVG liczą w px design size.
- Boot splash jest **wewnątrz** `.shell`, więc skaluje się razem.

### Boot splash (codec)

Sekwencja w `runBootSplash()`:

1. Od razu start poll dashboardu pod spodem.
2. ~900 ms: „LINK ESTABLISHED”.
3. ~1500 ms: fade (`is-done`).
4. ~1900 ms: remove z DOM.

### Statusy w UI

| API status | Kod na karcie | Badge topbar |
|------------|---------------|--------------|
| ok | OK | ONLINE |
| warning | WARN | CAUTION |
| error | ERR | ALERT (+ pulse tylko przy **wejściu** w error) |

Lewy pasek karty: `::before` kolorowany przez `data-status`.

### Wykresy

- Tylko `type: "line"`.
- Wide (hero): 520×160 viewBox; małe: 300×112.
- Role → klasy `.chart-line-accent` / `-muted` / `-warn`.
- Hero + warning → `chart-wrap--dim` (przygaszony wykres gdy Pi-hole paused).

### Akcje Pi-hole (UX)

- Segment 3 przycisków w `hero-rail`.
- Aktywny stan: ON vs OFF — API pokazuje „OFF 14M”, nie preset 5/15;
  frontend trzyma ostatni preset w `sessionStorage` kluczu `oh-pihole-off`
  (`"5"` / `"15"`).
- Toast po akcji; potem `refreshDashboard()`.

### Paleta (`:root` w `style.css`)

```
--bg #0b0b0a | --panel #121211 | --accent #8f9a63
--warn #b8953a | --error #a84a45 | --ok #7a8f55 | --muted #5a5850
--text #c8c4b8 | --text-hi #e8e4d8 | --text-dim #6e6a60
```

### Czego frontend **nie** robi (ważne dla LLM)

- Nie używa pola `icon` z API (brak mapy ICONS — mimo wzmianki w docstringu `base.py`).
- `renderUtilActions` / `renderToolActions` są stubami (`return ""`).
- Footer `mode` zawsze ustawiane na `"LIVE"` w JS (ignoruje ewentualne inne wartości).
- Brak WebSocket — tylko polling HTTP.

---

## 10. Deploy

### Pliki

| Plik | Cel |
|------|-----|
| `DEPLOY.md` | instrukcja krok po kroku |
| `deploy/outer-haven-hub.service` | systemd unit |
| `deploy/sudoers-outer-haven-hub` | NOPASSWD smartctl + wg |
| `deploy/Caddyfile.snippet` | przykład reverse proxy |

### systemd (skrót)

- `User=pi` / `Group=pi` (dostosuj).
- `WorkingDirectory=.../backend`
- `EnvironmentFile=-.../backend/.env`
- `Environment=HUB_CONFIG=.../config.yaml`
- `ExecStart=.../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8090`
- `Restart=on-failure`
- **Bez** `HUB_DEMO`.

### sudoers (krytyczne)

```
pi ALL=(root) NOPASSWD: /usr/sbin/smartctl -i -H -A -j /dev/sda
pi ALL=(root) NOPASSWD: /usr/bin/wg show all dump
```

- `sudo` porównuje argv **1:1**. Zmiana `device` w `config.yaml` **wymaga**
  tej samej zmiany w sudoers.
- Backend **nie** jest rootem; `NoNewPrivileges=false` bo potrzebuje sudo.

Instalacja:

```bash
sudo install -m 440 -o root -g root deploy/sudoers-outer-haven-hub /etc/sudoers.d/outer-haven-hub
sudo visudo -cf /etc/sudoers.d/outer-haven-hub
```

### Caddy

Backend tylko na loopback; Caddy wystawia LAN/WG:

```caddy
hub.lan {
    tls internal
    reverse_proxy 127.0.0.1:8090
}
```

Jeśli Caddy zajmuje 80/443, Pi-hole często na `:8080` → `base_url: "http://127.0.0.1:8080"`.

### Kiosk

Autologin → startx → Chromium:

```bash
chromium --kiosk --noerrdialogs --disable-infobars http://127.0.0.1:8090/
```

Bez sztywnego `--window-size` — FE skaluje do viewportu; czarne paski to sprawa X/rozdzielczości (patrz komentarze w `app.js` / `DEPLOY.md`).

### Clone na Pi (z DEPLOY.md)

```bash
git clone https://github.com/tenkejj/outer-haven-hub.git ~/outer-haven-hub
```

---

## 11. Przepływ danych (end-to-end)

```
[Źródła]
  Pi-hole HTTP API v6
  wg show (sudo)
  /proc /sys
  smartctl (sudo)
        │
        ▼
[Collector.collect / get_status / list_actions]
        │
        ▼
[CachedCollector]  cache + timeout 10s + izolacja błędów
        │
        ▼
[GET /api/dashboard]  asyncio.gather wszystkich runnerów
        │
        ▼
[frontend app.js]  poll 5s → renderCard → DOM
        │
[touch OFF/ON] ──► POST /api/collectors/pihole/actions/...
                        │
                        ▼
                 run_action → invalidate cache → następny poll świeży
```

---

## 12. Przykładowe JSON (kształty)

### Metryka number / percent / status

```json
{ "label": "TODAY", "value": "12.4k", "type": "number" }
{ "label": "% BLOCK", "value": 25.1, "type": "percent" }
{ "label": "BLOCK", "value": "OFF 14M", "type": "status", "state": "warning" }
```

### Pełna karta system (ok)

```json
{
  "id": "system",
  "label": "SYSTEM PI",
  "icon": "cpu",
  "status": "ok",
  "layout": "default",
  "metrics": [
    { "label": "CPU", "value": "34%", "type": "number", "state": "ok" },
    { "label": "RAM", "value": "42%", "type": "number", "state": "ok" },
    { "label": "TEMP", "value": "43°", "type": "number", "state": "ok" }
  ],
  "chart": {
    "type": "line",
    "series": [
      { "label": "CPU", "role": "accent", "points": [30, 34, 32] },
      { "label": "RAM", "role": "muted", "points": [40, 42, 41] },
      { "label": "TEMP", "role": "warn", "points": [42, 43, 43] }
    ]
  },
  "actions": [],
  "updated_at": 1720000000
}
```

---

## 13. Nieoczywiste decyzje (czytaj przed zmianami)

0. **Dwa frontendy, jedno API** — `/` (karty) i `/panel/` (panel instrumentowy). `/api/dashboard` obsługuje stary UI i musi zostać wstecznie zgodny; panel używa `/api/state` + `/api/history` + `/api/stream`. Warstwa semantyczna metryk jest tylko DODAWANA do karty, więc stary UI jej nie widzi.
1. **Ikona w kontrakcie, nie w UI** — `icon` jest w snapshot, ale `app.js` go nie rysuje. Albo dodaj ICONS, albo nie zakładaj, że ikony są widoczne.
2. **Historia Pi-hole = API v6 `/api/history`**, nie v5 z speki — świadomie.
3. **Brak psutil** — tylko Linux `/proc`/`/sys`; OK na Pi, słabo na Windows/macOS (demo i tak używa `HUB_DEMO`).
4. **sudo argv = sudoers 1:1** — najczęstsza pułapka przy zmianie dysku.
5. **Prywatne `_` klucze** — dla `get_status` / `list_actions`; nie wyciekają do FE.
6. **Footer zawsze LIVE** — nawet przy `HUB_DEMO=1`.
7. **Re-render całego grida** co 5 s — prostota na Pi; nie wprowadzaj ciężkiego VDOM bez potrzeby.
8. **Skala** — stary UI (`/`) używa `scale(sx, sy)` (niejednorodnej, rozciąga font); panel (`/panel/`) używa jednej `scale(s)`. Oba layouty „żyją” w 1024×600 — nie projektuj w `vh`/`%` viewportu jako źródła prawdy.
9. **Cache-bust** — `NoCacheStaticFiles` + `?v=` w HTML; po większych zmianach CSS podbij query.
10. **Akcje util/tool** — stuby FE; nowe grupy wymagają uzupełnienia rendererów **albo** użycia `group: "block"` tylko dla Pi-hole-like UX.
11. **Collector budowany przy imporcie** — nie hot-reload config bez restartu.
12. **Jeden httpx client** na PiholeCollector — keep-alive; SID w pamięci procesu.
13. **SMART returncode** — bity niskie `returncode & 0b11` traktowane jako błąd wywołania; inne bity smartctl mogą oznaczać warningi SMART (patrz man smartctl).
14. **KONTEKST.md vs ten plik** — `KONTEKST.md` jest skrótem; ten dokument jest kanonicznym briefem dla LLM.
15. **Speka poza repo** — zmiany architektoniczne komentuj w kodzie + ewentualnie tu; nie zakładaj, że agent przeczyta zewnętrzną SPECYFIKACJĘ.

---

## 14. Checklist: dodanie nowego collectora

1. Utwórz `backend/collectors/<name>.py` z klasą `XCollector(Collector)`.
2. Zaimplementuj `collect`, `get_status`; opcjonalnie `list_actions` / `run_action`.
3. Dodaj `if __name__ == "__main__": run_standalone(XCollector())`.
4. Import + wpis w `ALL_COLLECTOR_CLASSES` w `registry.py`.
5. Wpis w `config.yaml` (`enabled_collectors` + `collectors.<id>`).
6. Jeśli potrzebujesz sudo — **dopisz wąską linię** w `deploy/sudoers-outer-haven-hub` i zaktualizuj `DEPLOY.md`.
7. **Nie** zmieniaj `main.py`, `app.js` ani `panel/panel.js` (chyba że rozszerzasz sam kontrakt / generyczny renderer). Panel sam dorobi stronę i kafel w nav dla nowego id.
7a. Opcjonalnie dodaj `primary_metric` / `vital_metrics` / `metric_ranges` — bez nich panel wybierze pierwszą metrykę liczbową jako wielką liczbę.
8. Przetestuj: izolacja `python -m collectors.<name>`, potem pełny hub bez demo.
9. Opcjonalnie: dodaj `DemoX` do `demo.py` + `DEMO_COLLECTORS` (to **wyjątek** od „tylko registry” — tylko dla lokalnego UI bez sprzętu).

---

## 15. Szybkie odniesienia do plików

| Temat | Plik |
|-------|------|
| Kontrakt karty | `backend/collectors/base.py` |
| Rejestr wtyczek | `backend/collectors/registry.py` |
| Agregator / API / cache | `backend/main.py` |
| Config | `config.yaml` |
| Sekrety (szablon) | `backend/.env.example` |
| UI logika (karty) | `frontend/app.js` |
| UI wygląd (karty) | `frontend/style.css` |
| UI panel (docelowy) | `frontend/panel/panel.js`, `frontend/panel/panel.css` |
| Reguły agentów | `.cursorrules` |
| Deploy | `DEPLOY.md`, `deploy/*` |
| Krótki kontekst | `KONTEKST.md` |
| Historia zmian | `CHANGELOG.md` |

---

*Wygenerowano jako brief dla LLM na podstawie stanu kodu w repo. Przy większych zmianach architektury aktualizuj ten plik.*
