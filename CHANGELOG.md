# Changelog — Outer Haven Hub

## 2026-08-19 — panel instrumentowy + warstwa semantyczna metryk

Nowe podejście do UI. Siatka kart okazała się źródłem powtarzających się
awarii układu: wysokość wykresu wynikała z kombinacji klas CSS, więc każda
nowa strona psuła poprzednie. Panel dzieli ekran na **stałe strefy w px**.

- Frontend `frontend/panel/` (`/panel/`) — rail 96 | scena 770 | dok 156,
  nav 68 px; jedna strona = jeden collector, jedna wielka liczba na stronę
- Sparkline jako **tło scenu**, nie widget w ramce — nie ma czego ścisnąć
- Skala **równomierna** (`scale(s)`, nie `scale(sx, sy)`) — koniec z
  rozciąganiem fontu i nierównymi włoskami
- Punktowe aktualizacje DOM zamiast `innerHTML` całej siatki co 5 s
- Kontrakt: metryki dostają `importance` / `rail` / `num` / `unit` / `range`
  — collector opisuje ZNACZENIE, nie wygląd (patrz `collectors/base.py`)
- API: `GET /api/state` (bez historii), `GET /api/history/<id>` (na żądanie),
  `GET /api/stream` (SSE, z fallbackiem na polling po stronie panelu)
- Stary UI (`/`) i `GET /api/dashboard` **bez zmian** — da się porównać oba

## 2026-08-12 — strony HUB / SVC / MEDIA + collector services

- UI: segment `HUB | SVC | MEDIA` (hash `#hub`/`#svc`/`#media`), ten sam shell kiosku
- Collector `services`: `systemctl is-active` dla curated jednostek (Jellyfin, Samba, …)
- SVC = siatka wszystkich jednostek; MEDIA = Jellyfin + SMB + note/URL z config
- Demo: `DemoServices` w `HUB_DEMO=1`

## 2026-08-08 — cyberpunk HUD + wykresy wszędzie

- Font: JetBrains Mono Nerd Font lokalnie (`frontend/fonts/`), większa typografia
- Wykresy: Pi-hole 24h, System CPU/RAM, WireGuard rx/tx KiB/s, SMART temp
- Mocniejszy terminal/cyberpunk chrome (`0x`, scanlines SVG) — nadal bez glowów

## 2026-08-08 — akcje dotykowe + UI MGS/NieR

- Kontrakt akcji: `list_actions` / `run_action` + `POST /api/collectors/.../actions/...`
- Pi-hole: OFF 5M / OFF 15M / ON (API v6 `POST /api/dns/blocking` + timer)
- UI: flat HUD (MGS/NieR), bez gradientów i glowów; duże cele dotykowe
- Demo: akcje Pi-hole działają lokalnie w `HUB_DEMO=1`

## 2026-08-07 — szkielet + collectory + frontend

- Kontrakt wtyczek: `collectors/base.py`, rejestr + `config.yaml`
- Collectory startowe: `system`, `pihole` (API v6 + sesja SID), `smart`, `wireguard`
- Agregator FastAPI: równoległe zbieranie, cache per źródło, izolacja błędów (Faza 4)
- Tryb deweloperski `HUB_DEMO=1` ze sztucznymi danymi
- Frontend: dynamiczne karty, kiosk 1024×600, mini-wykres line
- Deploy: jednostka systemd, sudoers (smartctl/wg), przykład bloku Caddy
