# Outer Haven — mapa homelaba (mother-base)

Kanoniczny opis **całego setupu domowego**: co działa dziś na Raspberry Pi 4,
jak jest wystawione na LAN, oraz planowany segment P2P (WRT54GL → Pi → WireGuard
→ Oracle VPS).

**Źródła**

| Źródło | Co wnosi |
|--------|----------|
| `wrt54gl_p2p_architektura.md` (11.08.2026) | inwentaryzacja Pi, dyski, porty, topologia T-Mobile/CGNAT, projekt P2P |
| repo `outer-haven-hub` + eksploatacja kiosku | Hub, DNS `hub.haven`, usługi w `config.yaml`, panel 7″ |
| ten dokument | jeden spójny obraz; bez sekretów |

Nazewnictwo (Outer Haven, mother-base) — inspiracja Metal Gear.

> **Sekrety poza gitem:** hasła Pi-hole App, klucze WireGuard, tokeny, certyfikaty.
> Do diagnostyki wolno wysyłać `lsblk`, `df`, `ss`, `wg show` **bez** PrivateKey.

**Status projektu P2P:** odłożony do fizycznego dostępu do WRT54GL.
**Nie zmieniać produkcyjnej konfiguracji Pi „na zapas”.**

---

## 1. Na jednym rzucie oka

| Warstwa | Stan |
|--------|------|
| Host | Raspberry Pi 4 · hostname **`mother-base`** · user **`tenkej`** · ~4 GB RAM |
| Internet | T-Mobile → **CGNAT** (brak publicznego IPv4 na domu) |
| Główna LAN | `192.168.1.0/24` |
| Pi w LAN | ostatnio w eksploatacji **`192.168.1.201`**; w planie P2P roboczo `192.168.1.50` — potwierdzić przed zmianami |
| DNS domu | **Pi-hole** (:53, admin :8080) → **Unbound** (`127.0.0.1:5335`) |
| HTTPS / proxy | **Caddy** :80/:443 → m.in. Hub na `127.0.0.1:8090`, nazwa **`hub.haven`** |
| VPN | **WireGuard** na Pi → **Oracle VPS** (istniejący tunel; też baza pod P2P) |
| Dashboard | **Outer Haven Hub** (`outer-haven-hub.service`) + kiosk 7″ **1600×900** |
| Magazyn | SSD ~500 GB (`/dev/sda`) + USB backup `/mnt/backup` |
| Media (plan) | `/srv/media` + Jellyfin/DLNA pod TV **Panasonic TX-40CS520E** |
| Remote AI (plan) | iPhone → WG → Oracle VPS → dom → **PC** (`llama-server` + Hermes/Hermex) — [`REMOTE-AI.md`](./REMOTE-AI.md) |
| P2P (plan) | osobna sieć na **WRT54GL** → Pi jako gateway → WG → VPS + kill switch |

```text
                         INTERNET
                            |
                         CGNAT
                            |
                       T-Mobile
                            |
              +-------------+-------------+
              |                           |
          GŁÓWNA LAN                  WRT54GL   ← plan (odłożone)
       192.168.1.0/24                     |
              |                       P2P LAN
              |                    192.168.50.0/24
              |                           |
         mother-base                 P2P client
         (Pi 4)                           |
              |                           v
              |                    Raspberry Pi
              |                    (gateway P2P)
              |                           |
              |                       WireGuard
              |                           |
              +---------------------------+
                                          |
                                     Oracle VPS
                                          |
                                       Internet
```

---

## 2. Sprzęt — mother-base

### 2.1 Host

| | |
|--|--|
| Hostname | `mother-base` |
| Użytkownik | `tenkej` (uid typowo 1000) |
| SoC | Raspberry Pi 4 |
| RAM | ~4 GB (ostatni odczyt: Mem 3.7 Gi, available ~3.0 Gi; Swap 2.0 Gi + zram) |
| Repo huba | `~/outer-haven-hub` (unit w repo bywa z szablonem `User=pi` — na Pi dopasować ścieżki) |

### 2.2 Dyski (ostatnie `lsblk`)

| Urządzenie | Rozmiar | FS | Mount | Model / rola |
|------------|---------|-----|-------|----------------|
| `sda` | 465.8 G | — | — | **WDC WDS500G2B0A** (SSD ~500 GB) |
| `sda1` | 512 M | vfat | `/boot/firmware` | boot |
| `sda2` | 465.3 G | ext4 | `/` | system + dane |
| `sdb` | 7.5 G | — | — | USB Disk |
| `sdb1` | 7.5 G | ext4 | `/mnt/backup` | backup |
| `sdb2` | 32 M | vfat | — | — |
| `zram0` / loop swap | 2 G | — | `[SWAP]` | swap |

Ostatnie `df -hT` na `/`:

```text
/dev/sda2  ext4  459G  5.6G  435G  2% /
```

Hub monitoruje SMART na **`/dev/sda`** (`config.yaml` + sudoers — argv 1:1).

### 2.3 Magazyn mediów (plan)

Dziś `/srv` puste. Docelowo **bez** przepartycjonowania SSD:

```text
/srv/media/
├── Filmy/
├── Seriale/
└── Zdjecia/
```

Uwaga: wspólna partycja z `/` nie izoluje miejsca — pełny dysk mediów może
uderzyć w usługi systemowe. Przed produkcyjnym wrzucaniem filmów ustalić limit
(osobny FS / loop / quota), nie polegać wyłącznie na reserved blocks ext4.

### 2.4 Kiosk

| | |
|--|--|
| Ekran | 7″ touchscreen, natywne **1600×900** (nie zgadywać 1920×1080) |
| Start | autologin → `startx` → `~/.xinitrc` / wzorzec `deploy/kiosk.xinitrc` |
| Browser | Chromium `--kiosk`, URL lokalny `http://127.0.0.1:8090/…` |
| UI | dashboard `/` oraz instrument panel `/panel/` (branch panelowy) |

---

## 3. Sieć — stan obecny

### 3.1 Topologia dziś

```text
Internet → CGNAT → T-Mobile → Główna LAN → Raspberry Pi 4 (mother-base)
```

Pi siedzi w **głównej** sieci domowej. Osobnego segmentu P2P jeszcze nie ma.

### 3.2 Adresacja

| Nazwa | Wartość | Uwaga |
|------|---------|--------|
| Główna LAN | `192.168.1.0/24` | wspólna dla telefonu, laptopa, TV, Pi |
| Pi (eksploatacja) | `192.168.1.201` | widziane przy admin Pi-hole / hub.haven |
| Pi (plan P2P, roboczo) | `192.168.1.50` | z dokumentu WRT — **nie wpisywać w ciemno** |
| Hostname | `mother-base` | URL-e usług |
| Hub po DNS | `https://hub.haven/` | Local DNS (Pi-hole) + Caddy |
| Hub loopback | `http://127.0.0.1:8090/` | FastAPI tylko localhost |

### 3.3 DNS

```text
klienci LAN → Pi-hole (:53) → Unbound (127.0.0.1:5335) → Internet
                 └─ Local DNS: hub.haven, mother-base, …
```

- **Pi-hole FTL** — DNS domu, DHCP helper (widać też :67/:123 w snapshotcie portów).
- **Unbound** — rekursja lokalnie na **5335** (nie na publicznym :53).
- Admin Pi-hole: typowo przez Caddy lub bezpośrednio **`:8080`**
  (`https://192.168.1.201/admin/` w eksploatacji).
- Gdy Caddy trzyma 80/443, w `config.yaml` huba często:
  `collectors.pihole.base_url: "http://127.0.0.1:8080"`.

### 3.4 Porty (ostatnie `ss -tulpn`)

| Bind | Usługa |
|------|--------|
| UDP/TCP `0.0.0.0:53` | pihole-FTL |
| UDP `0.0.0.0:67`, `:123` | pihole-FTL |
| UDP/TCP `127.0.0.1:5335` | unbound |
| UDP `0.0.0.0:5353` | avahi-daemon |
| TCP `0.0.0.0:22` | sshd |
| TCP `0.0.0.0:80`, `:443` | caddy |
| TCP `0.0.0.0:8080` | pihole-FTL (admin) |
| TCP `127.0.0.1:8090` | Outer Haven Hub (uvicorn) |
| TCP `127.0.0.1:2019` | caddy (admin API lokalnie) |

Przed większymi zmianami **ponowić** snapshot portów.

### 3.5 Caddy

Reverse proxy + HTTPS (`tls internal` dla nazw lokalnych). Backend huba **nie**
jest rootem i **nie** słucha na WAN — tylko loopback `:8090`.

Przykład w repo: `deploy/Caddyfile.snippet`. Produkcyjny Caddyfile na Pi może
mieć bloki `hub.haven`, Pi-hole, itd.

### 3.6 WireGuard (istniejący)

Na Pi jest już tunel **WireGuard → Oracle VPS**.

```text
Raspberry Pi ──🔒 wg──► Oracle VPS ──► Internet
```

- Hub czyta stan peerów przez `sudo wg show all dump` (wąski sudoers).
- Friendly names: `config.yaml` → `peer_names` (np. laptop / phone) — to osobna
  oś „kto jest w tunelu”, nie mylić z przyszłym routowaniem P2P.
- Diagnostyka OK: `sudo wg show`. **Nie** wysyłać PrivateKey.

Rola VPS dziś / w planie P2P: publiczny punkt wyjścia (dom jest za CGNAT T-Mobile).

---

## 4. Usługi na Pi

### 4.1 Snapshot „running” (dokument WRT, 11.08.2026)

21 jednostek w stanie running, m.in.:

`pihole-FTL`, `unbound`, `caddy`, `outer-haven-hub`, `ssh`, `NetworkManager`,
`avahi-daemon`, `bluetooth`, `cron`, `smartmontools`, `wpa_supplicant`, …

### 4.2 Usługi istotne / monitorowane w Hubie

Z `config.yaml` → `collectors.services.units` (+ stan z inwentaryzacji):

| Usługa | Unit | Dostęp / port | Rola | Uwagi |
|--------|------|---------------|------|--------|
| Pi-hole | `pihole-FTL.service` | :53, admin :8080 | DNS domu | krytyczna |
| Unbound | `unbound.service` | `127.0.0.1:5335` | resolver | krytyczna |
| Caddy | `caddy.service` | :80/:443 | TLS + proxy | krytyczna |
| Outer Haven Hub | `outer-haven-hub.service` | `127.0.0.1:8090` | dashboard / kiosk | krytyczna |
| SSH | `ssh.service` | :22 | admin | krytyczna |
| NetworkManager | `NetworkManager.service` | — | sieć hosta | |
| Avahi | `avahi-daemon.service` | :5353 mDNS | discovery | `critical: false`; **≠ DLNA** |
| SMARTD | `smartmontools.service` | — | dysk | hub i tak woła `smartctl` |
| Jellyfin | `jellyfin.service` | `http://mother-base:8096` | media | w config hub; biblioteka pod `/srv/media` |
| Samba / Files | `smbd.service` (+ nmbd, wsdd2, winbind) | `smb://mother-base` | pliki | w config hub |
| Minecraft | `minecraft.service` | `:25565` | gra | `critical: false` — OFF = standby |

Nextcloud: wpis w `enabled_collectors` zakomentowany — na później.

### 4.3 Użytkownicy systemowi (skrót)

Obok kont standardowych: `tenkej`, `pihole`, `unbound`, `caddy`, `dnsmasq`, `avahi`, …

---

## 5. Outer Haven Hub

| | |
|--|--|
| Stack | Python 3 + FastAPI + uvicorn · vanilla HTML/CSS/JS |
| Bind | **tylko** `127.0.0.1:8090` |
| Config | `config.yaml` + `backend/.env` (`PIHOLE_APP_PASSWORD`) |
| Deploy | systemd + `deploy/sudoers-outer-haven-hub` + Caddy |
| UI | MGS / Mother Base — oliwkowy akcent, bez glow / fioletu / emoji |
| Collectory | `pihole`, `wireguard`, `system`, `smart`, `services` |

**URL-e**

| Cel | Adres |
|-----|--------|
| Hub (LAN) | `https://hub.haven/` |
| Panel kiosk | `https://hub.haven/panel/` |
| Hub lokalnie | `http://127.0.0.1:8090/` |
| Pi-hole admin | `https://192.168.1.201/admin/` (lub przez Caddy) |
| Jellyfin | `http://mother-base:8096` |
| Samba | `smb://mother-base` |

Sudoers (argv = config 1:1):

```text
… NOPASSWD: /usr/sbin/smartctl -i -H -A -j /dev/sda
… NOPASSWD: /usr/bin/wg show all dump
```

Szczegóły kontraktu collectorów: `LLM-CONTEXT.md`, `KONTEKST.md`, `DEPLOY.md`.

---

## 6. Media i TV (plan)

### 6.1 Jellyfin + DLNA

```text
SSD (/)
 └── /srv/media/{Filmy,Seriale,Zdjecia}
           │
           └── Jellyfin → biblioteka / metadane / DLNA
```

Na Pi 4 priorytet: **Direct Play**, nie transkodowanie.

Avahi pomaga w lokalnym discovery, ale **nie zastępuje DLNA**.

### 6.2 Profil pod Panasonic TX-40CS520E

Starszy Full HD — docelowa biblioteka:

| | Preferowane | Unikać jako baza |
|--|-------------|------------------|
| Video | H.264 / AVC, 1080p | 4K, HEVC, AV1 |
| Audio | AAC, MP3 | DTS (jako główny) |
| Kontener | MP4 | MKV tylko po teście na TV |

---

## 7. Projekt P2P — WRT54GL → Pi → WG → Oracle VPS

> Cel: **osobny segment legalnego P2P**, izolowany od głównej LAN, z wyjściem
> wyłącznie przez WireGuard na VPS. Status: **czekamy na fizyczny WRT54GL**.

Pełna nota źródłowa: [`wrt54gl_p2p_architektura.md`](./wrt54gl_p2p_architektura.md).

### 7.1 Role

| Element | Rola | Nie robi |
|---------|------|----------|
| **WRT54GL** | osobny router/firewall P2P: DHCP, izolacja LAN | nie zastępuje Pi-hole / Unbound / WG / VPS |
| **Raspberry Pi** | gateway P2P: forwarding, WG, reguły | nie jest klientem torrent „zamiast” izolacji |
| **WireGuard** | szyfrowany tunel Pi ↔ VPS | nie jest szyfrowaniem BitTorrent |
| **Oracle VPS** | koniec tunelu, NAT, publiczne IP wyjścia | nie „niewidzialność” — VPS widzi ruch po dekapsulacji |
| **Kill switch** | gdy WG padnie → P2P **bez** fallbacku na T-Mobile | włączać dopiero po działającym routingu |

### 7.2 Adresacja robocza (do potwierdzenia po podłączeniu WRT)

```text
Główna LAN:     192.168.1.0/24
  Raspberry Pi: 192.168.1.50     (roboczo; dziś często .201)
  WRT WAN:      192.168.1.2

P2P LAN:        192.168.50.0/24
  WRT LAN:      192.168.50.1
  klient P2P:   192.168.50.10
```

### 7.3 Przepływ pakietu (docelowo)

```text
P2P client (192.168.50.10)
    → WRT54GL (192.168.50.1)
    → Raspberry Pi (gateway)
    → wg0
    → Oracle VPS (NAT)
    → Internet / peer
```

Peer powinien widzieć **publiczne IP VPS**, nie adres za CGNAT T-Mobile.

WRT **nie musi** obsługiwać WireGuarda — tylko izolację i routing do Pi.

### 7.4 Kill switch

```text
P2P → wg0 → VPS → Internet     ✅
P2P → zwykły WAN (T-Mobile)    ❌ zablokowane
```

Testować osobno: WG ON / WG OFF. Bez fallbacku.

### 7.5 BitTorrent Protocol Encryption

Opcjonalna warstwa **aplikacyjna** (klient P2P). To **nie** zamiennik WireGuard:

```text
BitTorrent 🔐  →  WireGuard 🔒  →  VPS  →  Internet
```

T-Mobile widzi połączenie z VPS i metadane; treść w tunelu WG jest szyfrowana.
VPS po dekapsulacji widzi ruch wychodzący. Nie obiecywać „pełnej anonimowości”.

### 7.6 Segmentacja

```text
Główna LAN 192.168.1.0/24     telefon, laptop, TV, Pi, …
P2P LAN    192.168.50.0/24     tylko klient(y) P2P
```

Firewall: ograniczyć `P2P LAN → Główna LAN` (tylko świadome wyjątki).

### 7.7 Obciążenie Pi

| Składnik | Orientacyjnie |
|----------|----------------|
| routing / NAT / DNS | niskie |
| WireGuard | zależy od transferu |
| dużo połączeń P2P | średnie |
| transkodowanie Jellyfin | wysokie — unikać |

Monitoring przy testach: `uptime`, `htop`, `free -h`, `sudo wg show`, `ip -s link`.

### 7.8 Plan wdrożenia (po dostaniu WRT)

```text
BACKUP → DIAGNOSTYKA → WRT → P2P LAN → ROUTING → WIREGUARD → KILL SWITCH → TESTY → KLIENT P2P
```

| Etap | Co |
|------|-----|
| 0 | backup config, `wg`, routing, firewall, SSH zostaje |
| 1 | WRT: rev/firmware, WAN, P2P LAN, DHCP, izolacja |
| 2 | WRT→Pi, IP forwarding, test bez VPN |
| 3 | P2P przez `wg0`, test publicznego IP / DNS / throughput |
| 4 | kill switch ON/OFF |
| 5 | klient P2P + protocol encryption + limity |
| 6 | monitoring |

**Punkt wznowienia:** gdy WRT będzie fizycznie dostępny — model/revizja/firmware,
zdjęcia portów jeśli trzeba; **nie resetować** na ślepo; z Pi zebrać
`ip addr`, `ip route`, `sudo wg show`, firewall **bez sekretów**.

Do czasu WRT **nie** ustalamy finalnej adresacji, reguł, firmware ani NAT na VPS.

---

## 8. Operacje

### Update Huba

```bash
cd ~/outer-haven-hub
git fetch origin && git checkout <branch> && git pull --ff-only
sudo systemctl restart outer-haven-hub
# Ctrl+Shift+R / restart kiosku
```

### Healthcheck

```bash
systemctl is-active outer-haven-hub caddy pihole-FTL unbound
curl -s -o /dev/null -w "hub %{http_code}\n" http://127.0.0.1:8090/
free -h; df -hT /; sudo wg show
```

### Demo UI bez Pi

```bash
cd backend && HUB_DEMO=1 uvicorn main:app --host 127.0.0.1 --port 8090
```

### Bezpieczna diagnostyka (OK do wklejenia po ocenzurowaniu)

```bash
lsblk
df -hT
free -h
systemctl list-units --type=service --state=running --no-pager
ss -tulpn
ip addr
ip route
sudo wg show          # bez PrivateKey w outputcie do czatu
```

**Nie** wysyłać: PrivateKey, haseł, `.env`, tokenów, całych `/etc` w archiwum.

---

## 9. Mapa zależności

```text
[klienci głównej LAN]
        │
        ├─ DNS ──► Pi-hole :53 ──► Unbound :5335 ──► Internet
        │              └─ hub.haven / mother-base
        │
        ├─ HTTPS ─► Caddy :443 ──► Hub :8090
        │                      └─► Pi-hole admin :8080
        │
        ├─ (plan) media ─► Jellyfin :8096 ← /srv/media
        └─ (plan) pliki ─► Samba

[segment P2P — plan]
  klient → WRT54GL → Pi (forward + kill switch) → wg0 → Oracle VPS → peer

[Hub]
  httpx→Pi-hole · sudo wg · /proc·/sys · sudo smartctl · systemctl
```

---

## 10. Pliki referencyjne

| Ścieżka | Treść |
|---------|--------|
| [`docs/HOMELAB.md`](./HOMELAB.md) | ten dokument (mapa całości) |
| [`docs/REMOTE-AI.md`](./REMOTE-AI.md) | iPhone → VPS → Qwen + Hermes (etapy wdrożenia) |
| [`docs/wrt54gl_p2p_architektura.md`](./wrt54gl_p2p_architektura.md) | nota źródłowa P2P / inwentaryzacja |
| [`deploy/remote-ai/`](../deploy/remote-ai/) | szablony llama-server / Hermes / diagnostyka |
| `config.yaml` | collectory, SMART device, peer_names, unit’y |
| `backend/.env` | sekrety (nie w gicie) |
| `DEPLOY.md` | instalacja huba na Pi |
| `LLM-CONTEXT.md` | kontrakt API / collectorów dla LLM |
| `deploy/*` | systemd, sudoers, Caddy snippet, kiosk xinitrc |

---

## 11. Changelog dokumentu

| Data | Zmiana |
|------|--------|
| 2026-10-14 | Pierwsza mapa z repo + eksploatacji kiosku |
| 2026-10-14 | Scalenie z `wrt54gl_p2p_architektura.md`: dyski, porty, T-Mobile/CGNAT, Oracle VPS, plan P2P/WRT, media/TV, plan wdrożenia |
