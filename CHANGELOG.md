# Changelog — Outer Haven Hub

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
