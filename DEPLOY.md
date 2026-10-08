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

Autologin on `tty1` → `startx` → Chromium. Example profile:

```bash
# ~/.bash_profile — start X only on the local console
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  startx
fi
```

Install the ready `.xinitrc` (native resolution, `/panel/` URL):

```bash
cp deploy/kiosk.xinitrc ~/.xinitrc
chmod +x ~/.xinitrc
```

**Do not hard-code `1920×1080`** unless that is the panel's native mode.
Forcing a larger mode / `--window-size` than the physical matrix makes
Chromium paint off-screen; the monitor then shows a cropped, “zoomed” slice.
Check with `DISPLAY=:0 xrandr` and `scrot` (framebuffer size = truth).

Two UIs are served:

| URL | UI |
|-----|-----|
| `http://127.0.0.1:8090/` | card dashboard (tabs + grid) |
| `http://127.0.0.1:8090/panel/` | instrument panel (recommended for kiosk) |
| `http://127.0.0.1:8090/panel/?cycle=1` | panel that rotates pages on its own |

The panel canvas is **1024×600** and scales **uniformly** to fit the window
(letterboxed on taller screens such as 1024×768). It also caps the viewport
against `screen.width/height`, so a bad `--window-size` no longer blows up
the layout.

### SSE and restarts

The panel subscribes to `GET /api/stream`. Uvicorn waits for open connections
during shutdown, so an unbounded stream would stall `systemctl restart`. Two
guards handle this and both are already in the repo:

- `STREAM_MAX_S` in `backend/main.py` ends each stream after ~45 s (the
  browser reconnects on its own).
- `--timeout-graceful-shutdown 3` in `deploy/outer-haven-hub.service`.

If you copied the unit file before this change, re-copy it:

```bash
sudo cp deploy/outer-haven-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart outer-haven-hub
```
