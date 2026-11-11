# Deploy (Raspberry Pi / mother-base)

Backend on `127.0.0.1:8090`. Do **not** set `HUB_DEMO` in production.

Hostname Caddy (produkcja): `hub.haven` → https://hub.haven/

## Update (już zainstalowane)

Po merge do `master`:

```bash
cd ~/outer-haven-hub
cp config.yaml ~/oh-config.yaml.bak   # lokalne peer keys / ścieżki
git fetch origin
git checkout master
git pull origin master
cp ~/oh-config.yaml.bak config.yaml
sudo systemctl restart outer-haven-hub
```

Sprawdzenie:

```bash
systemctl status outer-haven-hub --no-pager
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8090/
curl -sS http://127.0.0.1:8090/api/dashboard | head -c 200; echo
```

Kiosk Chromium trzyma stary CSS — hard-reload albo `pkill Xorg` (autologin odpali startx od nowa).

## Motywy (HUD / Wall / Deck)

| Kontekst | Domyślnie | URL |
|----------|-----------|-----|
| Kiosk (monitor, `~/.xinitrc`) | **HUD** | `http://127.0.0.1:8090/?theme=hud` |
| Telefon (wąski / touch) | **Wall** | auto, albo `https://hub.haven/?theme=wall` |
| Ręcznie | cycle przyciskiem HUD | `?theme=deck` |

Priorytet: `?theme=` → `localStorage` → auto (touch/wąski = wall, inaczej hud).

## Podgląd z telefonu

Ten sam hub przez Caddy (LIVE, bez `HUB_DEMO`):

1. Wi‑Fi domowe albo WireGuard.
2. https://hub.haven/ (root `/`, **nie** `/panel/`).
3. Hard-reload po deployu.

## 1. Clone + venv (pierwszy raz)

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

Adjust `User=` / paths (defaults assume `pi` → `/home/pi/outer-haven-hub`; na mother-base często `tenkej`):

```bash
sudo install -m 440 -o root -g root deploy/sudoers-outer-haven-hub /etc/sudoers.d/outer-haven-hub
sudo visudo -cf /etc/sudoers.d/outer-haven-hub

sudo cp deploy/outer-haven-hub.service /etc/systemd/system/
# popraw User=, ścieżki, EnvironmentFile=, HUB_CONFIG
sudo systemctl daemon-reload
sudo systemctl enable --now outer-haven-hub
```

## 3. Caddy (LAN / WG)

```caddy
hub.haven {
    tls internal
    reverse_proxy 127.0.0.1:8090
}
```

## 4. Kiosk (X + Chromium)

Wzorce w repo:

- `deploy/kiosk.xinitrc` → `~/.xinitrc`
- `deploy/kiosk.profile-snippet` → dopisz do `~/.bash_profile`
- autologin: `/etc/systemd/system/getty@tty1.service.d/autologin.conf`

```bash
cp ~/outer-haven-hub/deploy/kiosk.xinitrc ~/.xinitrc
chmod +x ~/.xinitrc
# dopisz fragment z deploy/kiosk.profile-snippet do ~/.bash_profile
```

**Zakaz na produkcji (już rozpracowane):**

- `--window-size=1600,900` → czarne paski na 1080p
- `http://127.0.0.1:8090/panel/` → stary panel / JSON 404

Po zmianie xinitrc: `pkill Xorg` albo `sudo reboot`.

Szybki check:

```bash
DISPLAY=:0 XAUTHORITY=$(ls /tmp/serverauth.* 2>/dev/null | head -1) xrandr | grep '\*'
ps aux | grep -E '[c]hromium.*8090'
# oczekuj: 1920x1080* oraz URL ...8090/?theme=hud  (bez window-size, bez /panel/)
```

## 5. HDMI „No Signal” (Pi 4 + monitor)

Typowe przyczyny: zły port HDMI, brak hotplug, DPMS, albo X nie wystartował.

### Diagnostyka

```bash
vcgencmd display_power 1
ls /sys/class/drm/
cat /sys/class/drm/card*-HDMI-A-*/status 2>/dev/null
ps aux | grep -E 'Xorg|chromium' | grep -v grep
DISPLAY=:0 XAUTHORITY=$(ls /tmp/serverauth.* 2>/dev/null | head -1) xrandr --query
```

HDMI-A-1 `connected` + X z trybem `*` = Pi wysyła obraz; „No Signal” → wejście monitora / kabel.

### Force hotplug

Bookworm: `/boot/firmware/config.txt`:

```
hdmi_force_hotplug=1
```

`sudo reboot`. Port: **HDMI0** (bliżej USB-C).
