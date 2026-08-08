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
chromium --kiosk --noerrdialogs --disable-infobars http://127.0.0.1:8090/
```

No fixed `--window-size`; use the display resolution.
