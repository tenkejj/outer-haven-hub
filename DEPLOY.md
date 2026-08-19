# Deploy (Raspberry Pi)

Backend on `127.0.0.1:8090`. Do **not** set `HUB_DEMO` in production.

## 1. Clone + venv

```bash
git clone https://github.com/tenkejj/outer-haven-hub.git ~/outer-haven-hub
cd ~/outer-haven-hub/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# set PIHOLE_APP_PASSWORD=...
```

Edit `config.yaml` (Pi-hole `base_url`, SMART `device`/`mount`, WireGuard `peer_names`).

## 2. Sudoers + systemd

Adjust `User=` / paths for your account (defaults assume `pi` → `/home/pi/outer-haven-hub`):

```bash
# deploy/sudoers-outer-haven-hub — then:
sudo install -m 440 -o root -g root deploy/sudoers-outer-haven-hub /etc/sudoers.d/outer-haven-hub
sudo visudo -cf /etc/sudoers.d/outer-haven-hub

# deploy/outer-haven-hub.service — User=, WorkingDirectory=, EnvironmentFile=, HUB_CONFIG, ExecStart
sudo cp deploy/outer-haven-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now outer-haven-hub
```

## 3. Caddy (optional LAN / WG)

```caddy
your-hostname.example {
    tls internal
    reverse_proxy 127.0.0.1:8090
}
```

## 4. Kiosk

Autologin → `startx` → Chromium full-screen, e.g.:

```bash
chromium --kiosk --noerrdialogs --disable-infobars http://127.0.0.1:8090/panel/
```

No fixed `--window-size`; use the display resolution.

Two UIs are served:

| URL | UI |
|-----|-----|
| `http://127.0.0.1:8090/` | card dashboard (tabs + grid) |
| `http://127.0.0.1:8090/panel/` | instrument panel (recommended for the 7" screen) |
| `http://127.0.0.1:8090/panel/?cycle=1` | panel that rotates pages on its own |

The panel is laid out for a native **1024×600** panel and scales uniformly,
so it is sharpest when X runs at that resolution. Check with `xrandr`; if the
display reports something else, the panel still fits (letterboxed) but the
design canvas in `frontend/panel/panel.js` (`DESIGN_W` / `DESIGN_H`) is the
place to change if you want it native.
