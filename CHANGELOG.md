# Changelog — Outer Haven Hub

## 2026-11-11 — neon cyberpunk + HDMI no-signal

- Paleta fiolet / magenta / cyan, glowy, glitch brand, więcej animacji wykresów
- Jawne odstępstwo od oliwkowego MGS/NieR (`.cursorrules` + komentarz w CSS)
- DEPLOY §5: diagnostyka i fix HDMI „No Signal” na Pi 4

## 2026-11-11 — CRT cyberpunk HUD (produkcja)

- Fosforowa paleta, scanlines, CRT sweep, draw-in linii / rise słupków (steps)
- Blink statusów (badge / pasek karty), branding `0x*`, footer STREAM
- Redirect `GET|HEAD /panel` → `/` (stary JSON `{"detail":"Not Found"}`)
- DEPLOY: update na Pi + podgląd z telefonu przez Caddy

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
