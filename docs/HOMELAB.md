# Outer Haven — mapa homelaba (mother-base)

Dokument opisuje **cały setup infrastruktury domowej** wokół hosta `mother-base`,
nie tylko aplikację dashboardu. Źródła: repo `outer-haven-hub`, `config.yaml`,
deploy, oraz stan znany z eksploatacji na Pi (LAN, kiosk, DNS).

Nazewnictwo (Outer Haven, mother-base) — inspiracja Metal Gear.

> **Uwaga:** sekrety (hasła Pi-hole App, klucze WireGuard) **nie** należą do tego
> pliku. Trzymaj je w `backend/.env` / konfiguracji WG poza gitem.

---

## 1. Na jednym rzucie oka

| Warstwa | Co to jest |
|--------|------------|
| Host | Raspberry Pi 4 — hostname **`mother-base`** |
| Rola | DNS (Pi-hole + Unbound), VPN (WireGuard), media (Jellyfin), pliki (Samba), dashboard kiosk (Outer Haven Hub), opcjonalnie Minecraft |
| Sieć LAN | typowo `192.168.1.0/24`; Pi widziane jako **`192.168.1.201`** |
| Nazwy lokalne | `mother-base`, **`hub.haven`** (lokalny DNS przez Pi-hole) |
| Wejście z LAN / WG | **Caddy** (TLS) → reverse proxy na usługi na loopback / lokalnych portach |
| Ekran | 7″ touchscreen kiosk, natywna matryca **1600×900**, Chromium full-screen |
| Kod dashboardu | https://github.com/tenkejj/outer-haven-hub → `~/outer-haven-hub` na Pi |

```
                         Internet
                             │
                   [ router / brama LAN ]
                             │
                    192.168.1.0/24  (LAN)
                             │
         ┌───────────────────┼────────────────────┐
         │                   │                    │
   laptop / phone       mother-base          inne urządzenia
   (klienci WG)         192.168.1.201
                             │
                             ├── eth0
                             ├── Pi-hole + Unbound   (DNS domu)
                             ├── WireGuard          (VPN do domu)
                             ├── Caddy              (TLS + proxy)
                             ├── Jellyfin :8096
                             ├── Samba (smbd/…)
                             ├── Minecraft :25565   (opcjonalnie, często OFF)
                             ├── Outer Haven Hub    127.0.0.1:8090
                             └── kiosk Chromium → /panel/ lub /
```

---

## 2. Sprzęt — mother-base

| Element | Stan / założenie |
|--------|-------------------|
| SoC | Raspberry Pi 4 |
| Hostname | `mother-base` |
| Konto (eksploatacja) | `tenkej` (repo w `~/outer-haven-hub`; unit systemd w repo bywa z szablonem `User=pi` — na żywej maszynie ścieżki/konto trzeba dopasować) |
| Dysk | SSD widziany jako **`/dev/sda`**, montowany na `/` — monitorowany SMART (`smartctl`) |
| Sieć | Ethernet **`eth0`** (metryki NET IN/OUT w hubie) |
| Wyświetlacz | panel dotykowy 7″, **1600×900** (nie zgadywać 1920×1080) |
| Kiosk | X11 (`startx` / `~/.xinitrc`) → Chromium `--kiosk` na `http://127.0.0.1:8090/…` |

---

## 3. Sieć i DNS

### 3.1 Adresacja

| Nazwa | Wartość | Skąd |
|------|---------|------|
| LAN IP Pi | `192.168.1.201` | dostęp administracyjny (m.in. panel Pi-hole po IP) |
| Hostname | `mother-base` | system + URL-e usług (`http://mother-base:8096`, `smb://mother-base`) |
| Hub w przeglądarce | `https://hub.haven/` | lokalna strefa / wpis DNS w Pi-hole + Caddy |
| Hub loopback | `http://127.0.0.1:8090/` | backend FastAPI (tylko localhost) |

### 3.2 Ścieżka DNS w domu

1. Klienci LAN mają DNS → **Pi-hole** (na mother-base).
2. Pi-hole filtruje reklamy / listy.
3. Rekursja / resolver w tle: **Unbound** (`unbound.service`).
4. Lokalne nazwy (`hub.haven`, ewentualnie inne `*.haven`) — Local DNS / wpisy w Pi-hole.

Typowy dostęp admin Pi-hole z LAN: `https://192.168.1.201/admin/`
(gdy Caddy/proxy tak wystawia; dokładny port zależy od Caddyfile na Pi).

### 3.3 Caddy

- Słucha 80/443 (albo wg Caddyfile).
- Backend huba **nie** jest wystawiony na świat — tylko `127.0.0.1:8090`.
- Przykład bloku w repo: `deploy/Caddyfile.snippet` (`tls internal` + `reverse_proxy`).
- Na Pi używane hostname’y w stylu **`hub.haven`** (nie przykładowe `hub.lan` z snippetu).

Jeśli Caddy zajmuje 80/443, API Pi-hole często jest na **`:8080`** —
wtedy w `config.yaml`: `collectors.pihole.base_url: "http://127.0.0.1:8080"`.

### 3.4 WireGuard

- Interfejsy `wg*` na mother-base.
- Hub czyta stan przez `sudo wg show all dump` (wąski sudoers).
- Friendly names peerów: `config.yaml` → `collectors.wireguard.peer_names`
  (mapa public key → np. `laptop` / `phone`).
- Peerzy spoza domu łączą się do usług po VPN (hub, media, pliki — zależnie od `AllowedIPs`).

### 3.5 Router / WRT54GL (P2P)

W kolejce / załączniku użytkownika jest osobny opis:

`wrt54gl_p2p_architektura.md`

Ten plik opisuje warstwę routera (Linksys WRT54GL) i architekturę P2P względem
reszuty sieci. **Treść należy wkleić / zmerge’ować do sekcji poniżej**, gdy plik
będzie dostępny w workspace — tu zostawione miejsce na kanoniczny opis z tego źródła.

```
TODO — treść z wrt54gl_p2p_architektura.md:
- rola WRT54GL w LAN (brama / AP / osobny segment?)
- adresacja, VLAN / DMZ jeśli są
- reguły firewall / port forwarding pod P2P
- jak mother-base łączy się z tym routerem
```

---

## 4. Usługi na mother-base

Lista zgodna z `config.yaml` → `collectors.services.units` (to, co hub monitoruje).

### 4.1 Krytyczna infrastruktura

| Usługa | Jednostka systemd | Port / URL | Rola |
|--------|-------------------|------------|------|
| Pi-hole | `pihole-FTL.service` | admin WWW / DNS :53 | filtrowanie DNS, Local DNS |
| Unbound | `unbound.service` | resolver | rekursja DNS za Pi-hole |
| Caddy | `caddy.service` | 80/443 | TLS + reverse proxy |
| Outer Haven Hub | `outer-haven-hub.service` | `127.0.0.1:8090` | agregator + UI kiosku |
| SSH | `ssh.service` | :22 | administracja |
| NetworkManager | `NetworkManager.service` | — | sieć hosta |
| WireGuard | (interfejsy wg, niekoniecznie jedna unitka w liście hub) | UDP WG | zdalny dostęp |

### 4.2 Media i pliki

| Usługa | Jednostka | Dostęp | Uwagi |
|--------|-----------|--------|--------|
| Jellyfin | `jellyfin.service` | `http://mother-base:8096` | media server |
| Samba | `smbd.service` | `smb://mother-base` | udziały plików („Files”) |
| NMBD | `nmbd.service` | NetBIOS | odkrywanie w LAN Windows |
| WSDD | `wsdd2.service` | WS-Discovery | widoczność w Eksploratorze |
| Winbind | `winbind.service` | — | `critical: false` |

### 4.3 Gry (opcjonalne)

| Usługa | Jednostka | Port | Uwagi |
|--------|-----------|------|--------|
| Minecraft | `minecraft.service` | `mother-base:25565` | `critical: false` — OFF to normalny standby, nie awaria huba |

### 4.4 Wsparcie / tło

| Usługa | Jednostka | Uwagi |
|--------|-----------|--------|
| Avahi | `avahi-daemon.service` | mDNS; `critical: false` |
| Bluetooth | `bluetooth.service` | `critical: false` |
| Cron | `cron.service` | `critical: false` |
| SMARTD | `smartmontools.service` | monitoring dysku; hub i tak woła `smartctl` osobno |

### 4.5 Planowane / wyłączone w configu

- **Nextcloud** — wpis w `enabled_collectors` zakomentowany (`# - nextcloud`), collector dopiero do dodania.

---

## 5. Outer Haven Hub (dashboard)

### 5.1 Stack

| Warstwa | Technologia |
|--------|-------------|
| Backend | Python 3 + FastAPI + uvicorn, **tylko** `127.0.0.1:8090` |
| Frontend | vanilla HTML/CSS/JS (bez React/Vue) |
| Config | `config.yaml` + sekrety w `backend/.env` |
| Deploy | systemd + wąski sudoers (`smartctl`, `wg`) + Caddy |

### 5.2 Co zbiera (collectory)

| id | Źródło | Sens na ekranie |
|----|--------|-----------------|
| `pihole` | API v6 (SID + App Password) | % blokad, klienci, historia 24h, akcje OFF 5M / 15M / ON |
| `wireguard` | `wg show all dump` | LIVE peerzy, ruch, lista peerów |
| `system` | `/proc`, `/sys` | CPU, RAM, TEMP, sieć |
| `smart` | `smartctl` na `/dev/sda` | zdrowie SSD, temperatura, wolne miejsce |
| `services` | `systemctl is-active` | Jellyfin, Files, Minecraft, Caddy, Pi-hole, Hub, SSH, … |

### 5.3 UI — dwa powierzchnie

| URL | Rola |
|-----|------|
| `http://127.0.0.1:8090/` lub `https://hub.haven/` | klasyczny dashboard (zakładki HUB / DNS / NET / DISK / SYS / SVC / MEDIA — zależnie od brancha) |
| `…/panel/` | instrument panel pod kiosk 7″ (DNS / VPN / HOST / DISK / APPS) — branch panelowy |

Kiosk na Pi powinien celować w ten URL, który faktycznie ma otwarty Chromium
(w `deploy/kiosk.xinitrc` na branchu panelowym: `/panel/`).

### 5.4 Estetyka

MGS / Mother Base: flat HUD, mono, akcent oliwkowy `#8f9a63`, narożniki L,
duże cele dotykowe. Bez gradientów, glow, fioletu, glassmorphism, emoji.

### 5.5 Sudoers (krytyczne)

```
# deploy/sudoers-outer-haven-hub — argv musi być 1:1 z config.yaml
… NOPASSWD: /usr/sbin/smartctl -i -H -A -j /dev/sda
… NOPASSWD: /usr/bin/wg show all dump
```

Zmiana dysku w `config.yaml` **wymaga** tej samej zmiany w sudoers.

---

## 6. Kiosk (ekran na mother-base)

1. Autologin użytkownika graficznego → `startx`.
2. `~/.xinitrc` (wzorzec: `deploy/kiosk.xinitrc`):
   - `xrandr --auto` — natywny tryb matrycy,
   - parsowanie czystego `W×H` (np. `1600x900`) **bez** sufiksu `+0+0`,
   - Chromium `--kiosk --window-size=${W},${H}` → hub.
3. Skalowanie UI: design canvas (panel 1024×600 lub shell dashboardu) dopasowany do viewportu;
   na panelu instrumentowym używane jest CSS `zoom` (nie `transform: scale`),
   żeby trafienia dotykowe na Chromium/Pi były zsynchronizowane z obrazem.
4. DPMS / screensaver — krótkie timeouty w xinitrc (oszczędność matrycy).

---

## 7. Dostęp — ściągawka URL

| Cel | Adres |
|-----|--------|
| Hub (LAN, po DNS) | `https://hub.haven/` |
| Hub panel kiosk | `https://hub.haven/panel/` |
| Hub lokalnie na Pi | `http://127.0.0.1:8090/` |
| Pi-hole admin (IP) | `https://192.168.1.201/admin/` |
| Jellyfin | `http://mother-base:8096` |
| Samba | `smb://mother-base` |
| Minecraft | `mother-base:25565` (gdy unit aktywny) |
| SSH | `ssh tenkej@mother-base` lub `@192.168.1.201` |

Z WireGuard — te same hostname’y / IP w tunelu, o ile routing/`AllowedIPs` na to pozwala.

---

## 8. Pliki i sekrety (gdzie co żyje)

| Ścieżka | Zawartość |
|---------|-----------|
| `~/outer-haven-hub/` | clone repo na Pi |
| `config.yaml` | włączone collectory, device SMART, peer_names WG, lista unitów |
| `backend/.env` | `PIHOLE_APP_PASSWORD=…` (App Password z Pi-hole, nie hasło UI) |
| `/etc/systemd/system/outer-haven-hub.service` | unit huba |
| `/etc/sudoers.d/outer-haven-hub` | smartctl + wg |
| Caddyfile (systemowy) | bloki `hub.haven`, Pi-hole, itd. |
| `~/.xinitrc` | start kiosku |
| Konfiguracja WG | poza tym repo (klucze / `wg0.conf`) |
| `wrt54gl_p2p_architektura.md` | architektura routera / P2P (osobny dokument użytkownika) |

Dev na laptopie: lokalny clone (np. `/home/tenkej/dev/outerhaven`) + `HUB_DEMO=1`.

---

## 9. Operacje codzienne

### Update huba na Pi

```bash
cd ~/outer-haven-hub
git fetch origin
git checkout <branch>
git pull --ff-only
sudo systemctl restart outer-haven-hub
# twarde odświeżenie Chromium na kiosku / Ctrl+Shift+R w przeglądarce
```

### Szybki healthcheck

```bash
systemctl is-active outer-haven-hub caddy pihole-FTL unbound jellyfin smbd
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8090/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8090/panel/
systemctl is-active minecraft.service || true
```

### Demo bez Pi (dev)

```bash
cd backend
HUB_DEMO=1 uvicorn main:app --host 127.0.0.1 --port 8090
```

---

## 10. Mapa zależności (logiczna)

```
[klienci LAN / WG]
        │
        ├─ DNS ──────► Pi-hole ──► Unbound ──► Internet
        │                 │
        │                 └─ Local DNS: hub.haven, mother-base, …
        │
        ├─ HTTPS ────► Caddy ──► Outer Haven Hub (:8090)
        │                    └─► Pi-hole admin (np. :8080)
        │
        ├─ media ────► Jellyfin (:8096)
        ├─ pliki ────► Samba (smbd + nmbd/wsdd)
        └─ gra ──────► Minecraft (:25565)   [opcjonalnie]

[Hub backend]
        ├─ httpx → Pi-hole API
        ├─ sudo wg → WireGuard
        ├─ /proc,/sys → System
        ├─ sudo smartctl → SSD
        └─ systemctl → Services
```

---

## 11. Co jest poza zakresem tego dokumentu

- Pełna treść `SPECYFIKACJA-outer-haven-hub.md` (żyje poza repo na mother-base).
- Szczegóły firmware / reguł **WRT54GL** — uzupełnij z `wrt54gl_p2p_architektura.md`.
- Hasła, prywatne klucze WG, App Password Pi-hole.
- Dokładny Caddyfile produkcyjny (może odbiegać od snippetu w repo).

---

## 12. Changelog dokumentu

| Data | Zmiana |
|------|--------|
| 2026-10-14 | Pierwsza wersja mapy homelaba na podstawie repo + eksploatacji mother-base; sekcja WRT54GL jako TODO pod plik użytkownika |
