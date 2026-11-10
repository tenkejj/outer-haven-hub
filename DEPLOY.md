# Deploy (Raspberry Pi)

Backend on `127.0.0.1:8090`. Do **not** set `HUB_DEMO` in production.

## Update (już zainstalowane)

Po merge do `master` — na Pi:

```bash
cd ~/outer-haven-hub    # dostosuj path jeśli inny
git fetch origin
git checkout master
git pull origin master
sudo systemctl restart outer-haven-hub
```

Sprawdzenie:

```bash
systemctl status outer-haven-hub --no-pager
curl -sS http://127.0.0.1:8090/api/dashboard | head -c 200
```

Kiosk Chromium czasem trzyma stary CSS mimo `Cache-Control: no-cache` — hard-reload
albo restart kiosku po `systemctl restart`.

## Podgląd z telefonu (ten sam hub co na monitorze)

Nie potrzebujesz osobnego dema. Caddy wystawia backend na LAN / WireGuard;
telefon otwiera **ten sam** UI z prawdziwymi danymi.

1. Telefon w Wi‑Fi domowym **albo** podłączony do WireGuard.
2. Otwórz root huba, np. `https://hub.lan/` (Twój hostname z Caddy).
3. **Nie** `/panel/` — to stary URL instrument-panel; teraz redirectuje na `/`,
   ale na starszym deployu dawał `{"detail":"Not Found"}`.
4. Hard-reload po deployu.

Canvas 1024×600 skaluje się do viewportu telefonu (ten sam shell co kiosk).

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

## 3. Caddy (LAN / WG — wymagane do podglądu z telefonu)

```caddy
hub.lan {
    tls internal
    reverse_proxy 127.0.0.1:8090
}
```

Bez tego bloku hub działa tylko na `127.0.0.1:8090` (kiosk na Pi). Telefon
nie zobaczy nic, dopóki reverse proxy (i DNS / `dns.hosts` / WG) nie wskazuje
na ten host.

## 4. Kiosk

Autologin → `startx` → Chromium full-screen, e.g.:

```bash
chromium --kiosk --noerrdialogs --disable-infobars http://127.0.0.1:8090/
```

No fixed `--window-size`; use the display resolution.
