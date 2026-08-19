# Outer Haven Hub

Dashboard / kiosk for a Raspberry Pi home lab: Pi-hole, WireGuard, system metrics, and SSD SMART status on one screen.

Naming (`mother-base`, Outer Haven) is heavily inspired by Metal Gear.

**Stack:** Python 3 + FastAPI backend; vanilla HTML/CSS/JS frontend. Listens on `127.0.0.1` only.
![Outer Haven Hub dashboard](docs/dashboard.png)

## Local demo

Synthetic data; no Pi or live services required:

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
HUB_DEMO=1 uvicorn main:app --host 127.0.0.1 --port 8090
```

Open: http://127.0.0.1:8090/

## Two front ends

| URL | UI |
|-----|-----|
| `/` | Card dashboard — tabbed grid of cards, one card per source |
| `/panel/` | **Instrument panel** — one page per source, one big number each |

The panel is built for the 7" 1024×600 touchscreen: fixed pixel zones
(rail / stage / dock / nav) instead of a card grid, so nothing can squash
or leave gaps. It scales **uniformly**, so on the panel's native resolution
it renders pixel-for-pixel. Add `?cycle=1` to rotate pages automatically.

Both read the same collectors; the panel uses the lighter `/api/state`
plus `/api/stream` (SSE) and pulls chart history only for the page on screen.

## Deploy

Production setup on a Raspberry Pi: [DEPLOY.md](DEPLOY.md).
