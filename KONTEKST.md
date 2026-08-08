# Outer Haven Hub — kontekst projektu

**Status:** implementacja w toku (Fazy 1–4 w kodzie, Faza 5 = deploy na Pi)
**Ekran docelowy:** panel kiosk na `mother-base` (RPi 4); UI full-bleed (dawniej 1024×600)

## Po co to jest

Fizyczny dashboard infrastruktury domowej: Pi-hole, SMART dysku, WireGuard,
metryki systemowe Pi — jednym rzutem oka, bez przełączania paneli.

## Architektura (skrót)

- **Backend** (`backend/`): FastAPI na `127.0.0.1:8090`, agreguje wtyczki
  (collectors), izoluje błędy, cache’uje per `refresh_interval`.
- **Frontend** (`frontend/`): statyczny HTML/CSS/JS, karty generowane z
  `/api/dashboard` — zero sekcji wpisanych na sztywno.
- **Deploy** (`deploy/`): systemd + wąski sudoers + Caddy reverse proxy.

## Rozszerzalność

Nowy serwis = 1 plik collectora + linia w `registry.py` + linia w `config.yaml`.
Kontrakt: `backend/collectors/base.py`.

## Odchylenia od speki (jawne)

| Temat | Speka | Rzeczywistość | Dlaczego |
|---|---|---|---|
| Historia Pi-hole | `GET /api/stats/overTimeData10mins` (v5) | `GET /api/history` (v6) | Autentykacja SID = API v6; ten sam sens (kubełki 10 min / 24 h) |
| Metryki systemowe | `/proc` lub psutil | tylko `/proc`+`/sys` | jedna zależność mniej |
| Tryb demo | — | `HUB_DEMO=1` + `collectors/demo.py` | praca nad UI bez Pi |

## Decyzje (sekcja 10)

1. Akcje z ekranu — tak. Kontrakt: `list_actions` / `run_action` w collectorze;
   Pi-hole: OFF 5M / OFF 15M / ON.
2. Wykresy tak (Pi-hole 24h, same linie).
3. Alarmowe podświetlenie tak (`ok` / `warning` / `error`) — pasek/kod, bez glow.

## UI

MGS / NieR: flat HUD, mono, oliwkowy akcent, narożniki L.
Bez gradientów, bez jasnych glowów, bez „vibe-coded” kart.
