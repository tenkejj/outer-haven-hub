# WRT54GL → Raspberry Pi 4 → WireGuard → Oracle VPS
## Projekt izolowanej sieci P2P / legalnego torrentingu

**Status:** odłożone do czasu fizycznego dostępu do WRT54GL  
**Data dokumentu:** 11 sierpnia 2026

---

## 1. Cel projektu

Celem jest dodanie do istniejącej sieci domowej osobnego segmentu przeznaczonego dla legalnego P2P.

Docelowo:

- WRT54GL tworzy osobną sieć P2P.
- Urządzenia w tej sieci nie powinny mieć swobodnego dostępu do głównej LAN.
- Raspberry Pi 4 działa jako gateway dla ruchu P2P.
- Ruch P2P jest kierowany przez istniejący tunel WireGuard do Oracle VPS.
- VPS jest publicznym punktem wyjścia tego ruchu.
- Kill switch ma uniemożliwiać wyjście P2P zwykłą trasą T-Mobile, gdy WireGuard nie działa.
- Opcjonalne BitTorrent Protocol Encryption stanowi dodatkową warstwę na poziomie aplikacji.
- Istniejące usługi Pi mają pozostać nienaruszone poza koniecznymi zmianami routing/firewall.

To jest projekt dla **legalnego P2P**.

---

# 2. Aktualny setup Raspberry Pi 4

Host:

```text
mother-base
```

Użytkownik:

```text
tenkej
```

Pi 4 ma około 4 GB RAM.

Ostatni odczyt pamięci:

```text
Mem:  3.7Gi
used: 692Mi
free: 2.1Gi
available: 3.0Gi

Swap: 2.0Gi
used: 0B
```

---

# 3. Aktualne dyski

Ostatnie `lsblk`:

```text
NAME     SIZE FSTYPE MOUNTPOINTS    MODEL

loop0      2G swap

sda    465.8G                       WDC WDS500G2B0A
├─sda1   512M vfat   /boot/firmware
└─sda2 465.3G ext4   /

sdb      7.5G                       USB Disk
├─sdb1   7.5G ext4   /mnt/backup
└─sdb2    32M vfat

zram0      2G zram   [SWAP]
```

Główny SSD:

```text
/dev/sda
WDC WDS500G2B0A
~500 GB
```

System:

```text
/dev/sda2
ext4
/
```

Boot:

```text
/dev/sda1
vfat
/boot/firmware
```

Dodatkowy nośnik backup:

```text
/dev/sdb1
/mnt/backup
```

---

# 4. Aktualne wykorzystanie SSD

Ostatnie `df -hT`:

```text
/dev/sda2      ext4      459G   5.6G   435G   2% /
```

Czyli około:

**435 GB wolnego miejsca.**

Na `/srv` obecnie nie ma jeszcze katalogu mediów:

```text
/srv
├── .
└── ..
```

Planowany magazyn:

```text
/srv/media
```

z możliwą strukturą:

```text
/srv/media/
├── Filmy/
├── Seriale/
└── Zdjecia/
```

Nie planujemy przepartycjonowania SSD tylko dla tego celu.

---

# 5. Aktualnie działające usługi

Ostatnie:

```bash
systemctl list-units --type=service --state=running --no-pager
```

wykazało 21 usług:

```text
avahi-daemon.service
bluetooth.service
caddy.service
cron.service
dbus.service
getty@tty1.service
NetworkManager.service
outer-haven-hub.service
pihole-FTL.service
polkit.service
serial-getty@ttyS0.service
smartmontools.service
ssh.service
systemd-journald.service
systemd-logind.service
systemd-timesyncd.service
systemd-udevd.service
unbound.service
upower.service
user@1000.service
wpa_supplicant.service
```

Najważniejsze:

### Pi-hole FTL
DNS dla domu.

### Unbound
Rekurencyjny resolver DNS, obecnie nasłuchujący lokalnie na porcie 5335.

### WireGuard
Istniejący VPN do Oracle VPS.

### Caddy
Reverse proxy / HTTPS.

### Outer Haven Hub
Dashboard/agregator działający jako:

```text
outer-haven-hub.service
```

### Avahi
mDNS/DNS-SD, użyteczne dla lokalnego wykrywania usług, w tym potencjalnie urządzeń multimedialnych.

### SSH
Administracja Raspberry Pi.

---

# 6. Aktualne porty

Ostatnie `sudo ss -tulpn` pokazało m.in.:

```text
UDP 127.0.0.1:5335   unbound
UDP 0.0.0.0:5353     avahi-daemon
UDP 0.0.0.0:53       pihole-FTL
UDP 0.0.0.0:67       pihole-FTL
UDP 0.0.0.0:123      pihole-FTL

TCP 0.0.0.0:22       sshd
TCP 0.0.0.0:53       pihole-FTL
TCP 127.0.0.1:5335   unbound
TCP 0.0.0.0:8080     pihole-FTL
TCP 127.0.0.1:8090   uvicorn
TCP 127.0.0.1:2019   caddy
TCP 0.0.0.0:80       caddy
TCP 0.0.0.0:443      caddy
```

Przed zmianami należy ponownie sprawdzić stan systemu.

---

# 7. Użytkownicy systemowi

Ostatnie:

```bash
getent passwd | cut -d: -f1
```

pokazało:

```text
root
daemon
bin
sys
sync
games
man
lp
mail
news
uucp
proxy
www-data
backup
list
irc
_apt
nobody
systemd-network
dhcpcd
systemd-timesync
messagebus
sshd
dnsmasq
avahi
polkitd
tenkej
pihole
unbound
caddy
usbmux
```

---

# 8. Obecna topologia

Użytkownik ma Internet przez router T-Mobile.

Istnieje CGNAT.

Raspberry Pi działa obecnie w głównej sieci domowej.

Istnieje również Oracle VPS, do którego Pi ma już skonfigurowany WireGuard.

Schemat obecny:

```text
Internet
   |
CGNAT
   |
T-Mobile
   |
Główna LAN
   |
Raspberry Pi 4
```

---

# 9. Obecny WireGuard

WireGuard już działa na Pi.

Istniejący tunel ma zostać wykorzystany jako transport dla wydzielonego ruchu P2P.

Docelowo:

```text
Raspberry Pi
     |
     | WireGuard
     | 🔒
     v
Oracle VPS
     |
     v
Internet
```

Przed wdrożeniem trzeba zebrać aktualne informacje o interfejsie i routingu.

Bezpieczne diagnostycznie polecenie:

```bash
sudo wg show
```

Nie należy przesyłać:

- PrivateKey,
- haseł,
- tokenów,
- kluczy API,
- prywatnych certyfikatów.

---

# 10. Rola WRT54GL

WRT54GL ma pełnić przede wszystkim rolę:

**osobnego routera/firewalla dla sieci P2P.**

Nie ma zastępować:

- Pi-hole,
- Unbound,
- Raspberry Pi,
- WireGuard,
- Oracle VPS.

Jego zadanie:

```text
Główna LAN
     |
     |
  WRT54GL
     |
     v
P2P LAN
```

Dzięki temu możemy odseparować urządzenia P2P od reszty domu.

---

# 11. Proponowana adresacja

To są wartości robocze — zostaną potwierdzone dopiero po podłączeniu WRT.

```text
Główna LAN:
192.168.1.0/24

Raspberry Pi:
192.168.1.50

WRT WAN:
192.168.1.2

P2P LAN:
192.168.50.0/24

WRT LAN:
192.168.50.1

Przykładowy klient P2P:
192.168.50.10
```

Nie należy wpisywać tych adresów w ciemno przed sprawdzeniem aktualnej sieci.

---

# 12. Docelowa topologia

```text
                         INTERNET
                            |
                         CGNAT
                            |
                       T-Mobile
                            |
              +-------------+-------------+
              |                           |
          GŁÓWNA LAN                  WRT54GL
              |                           |
              |                       P2P LAN
              |                    192.168.50.0/24
              |                           |
              |                     P2P client
              |                           |
              |                           v
              |                    Raspberry Pi 4
              |                      192.168.1.50
              |                           |
              |                       WireGuard
              |                         🔒
              |                           |
              |                           v
              |                      Oracle VPS
              |                           |
              |                          NAT
              |                           |
              +---------------------------+
                                          |
                                       Internet
                                          |
                                         Peer
```

---

# 13. Jak będzie przepływał pakiet

Przykładowy klient P2P:

```text
192.168.50.10
```

wysyła ruch do swojej bramy:

```text
192.168.50.1
```

czyli WRT.

WRT kieruje ruch do Raspberry Pi.

Pi przekazuje go przez WireGuard:

```text
P2P client
    |
    v
WRT54GL
    |
    v
Raspberry Pi
    |
    v
wg0
    |
    v
Oracle VPS
    |
    v
Internet
```

---

# 14. WRT nie musi obsługiwać WireGuarda

To ważne architektonicznie.

WRT może wykonywać:

- DHCP,
- routing,
- firewall,
- izolację P2P LAN.

Raspberry Pi wykonuje:

- routing,
- forwarding,
- WireGuard,
- ewentualny NAT/ruleset wymagany przez projekt.

VPS wykonuje:

- zakończenie WireGuard,
- forwarding,
- NAT na wyjściu do Internetu.

---

# 15. Kill switch

To krytyczna część projektu.

Chcemy:

```text
P2P LAN
   |
   v
Raspberry Pi
   |
   +---- wg0 ----> VPS ----> Internet   ✅
   |
   +---- zwykły WAN ------------X       ❌
```

Gdy WireGuard działa:

```text
P2P -> VPN -> VPS -> Internet
```

Gdy WireGuard padnie:

```text
P2P -> Internet
       BLOCKED
```

Nie chcemy fallbacku przez zwykłe połączenie T-Mobile.

Kill switch należy skonfigurować dopiero po poprawnym uruchomieniu routingu i dokładnie przetestować.

---

# 16. BitTorrent Protocol Encryption

W kliencie P2P można dodatkowo włączyć szyfrowanie protokołu BitTorrent, jeśli dany klient je obsługuje.

Logicznie:

```text
          BitTorrent
             🔐
              |
          WireGuard
             🔒
              |
             VPS
```

To są dwie różne warstwy.

WireGuard:

- chroni tunel Pi ↔ VPS.

BitTorrent Protocol Encryption:

- dotyczy komunikacji na poziomie protokołu P2P.

Nie należy traktować żadnej z tych funkcji jako gwarancji pełnej anonimowości.

---

# 17. Co widzi T-Mobile?

T-Mobile może obserwować m.in.:

- połączenie z VPS,
- czas połączeń,
- ilość przesyłanych danych,
- metadane sieciowe.

Treść ruchu znajdującego się wewnątrz tunelu WireGuard jest szyfrowana.

---

# 18. Co widzi Oracle VPS?

WireGuard kończy się na VPS.

Dlatego nie należy zakładać:

> „Oracle nic nie widzi.”

Dokładniej:

```text
Pi
 |
 | 🔒 WireGuard
 v
VPS
 |
 | 🔓 zakończenie WireGuard
 v
Internet
```

Operator VPS może widzieć ruch na VPS, jego metadane oraz ruch wychodzący.

Jeżeli na poziomie BitTorrent jest dodatkowe szyfrowanie, stanowi ono kolejną warstwę.

---

# 19. Co widzi peer P2P?

Przy poprawnym routingu przez VPS peer powinien widzieć jako publiczny adres źródłowy:

```text
publiczne IP Oracle VPS
```

a nie bezpośrednio publiczny adres domowego połączenia.

To jest główny cel użycia VPS jako punktu wyjścia.

---

# 20. Segmentacja sieci

Główna LAN:

```text
192.168.1.0/24

telefon
laptop
TV
Raspberry Pi
inne urządzenia
```

P2P LAN:

```text
192.168.50.0/24

klient P2P
```

Docelowo firewall powinien ograniczyć możliwość inicjowania połączeń:

```text
P2P LAN -> Główna LAN
```

Pozwalamy tylko na wymagane wyjątki.

Nie zakładamy automatycznie, że P2P LAN ma mieć pełny dostęp do urządzeń domowych.

---

# 21. Obciążenie Raspberry Pi

Routing i NAT są dla Pi 4 relatywnie lekkie.

WireGuard jest znacznie bardziej istotny pod względem CPU.

Ważne są:

- przepustowość,
- liczba jednoczesnych połączeń,
- liczba pakietów,
- reguły firewalla,
- obciążenie pozostałych usług.

Orientacyjnie:

```text
routing             -> niskie
NAT/firewall        -> niskie
DNS                 -> niskie
WireGuard           -> zależne od transferu
dużo połączeń P2P   -> średnie
transkodowanie      -> wysokie
```

Podczas testów monitorujemy:

```bash
uptime
htop
free -h
sudo wg show
ip -s link
```

Nie przyjmujemy konkretnego limitu przepustowości bez pomiaru na rzeczywistym sprzęcie.

---

# 22. Media / SSD

Obecny SSD ma około:

```text
435 GB wolnego
```

Plan:

```text
/srv/media
```

Przykładowo:

```text
/srv/media/
├── Filmy/
├── Seriale/
└── Zdjecia/
```

Nie ma potrzeby przepartycjonowania SSD tylko po to, żeby utworzyć magazyn.

Ważna uwaga architektoniczna:

Wspólna partycja nie daje twardej izolacji przestrzeni między systemem i mediami. Jeśli media zapełnią filesystem, mogą wystąpić problemy z usługami systemowymi.

Przed wdrożeniem mediów trzeba więc ustalić odpowiedni mechanizm limitowania przestrzeni, np. osobny filesystem/partycję, loopback image albo inne ograniczenie, zależnie od finalnego projektu.

Nie zakładamy, że `ext4 reserved blocks` daje pełną izolację dla dowolnych usług — szczególnie gdy usługi mogą działać z uprawnieniami root.

---

# 23. Panasonic TX-40CS520E

Telewizor jest starszym modelem Full HD.

Docelowy profil biblioteki powinien preferować:

### Video

```text
H.264 / AVC
1080p
```

### Audio

Preferowane:

```text
AAC
MP3
```

### Kontener

Preferowany:

```text
MP4
```

MKV może być używany, ale trzeba sprawdzić konkretną kombinację kontenera, kodeka i ścieżki audio na telewizorze.

Należy unikać jako podstawowego profilu:

```text
4K
HEVC / H.265
AV1
DTS
```

jeżeli celem jest bezpośrednie odtwarzanie.

---

# 24. Jellyfin + DLNA

Planowany serwer mediów:

```text
SSD
 |
 +-- /srv/media
       |
       +-- Filmy
       +-- Seriale
       +-- Zdjecia
```

Jellyfin może zapewnić:

- bibliotekę,
- metadane,
- organizację treści,
- obsługę DLNA,
- możliwość dostosowania odtwarzania.

Dla Raspberry Pi 4 priorytetem powinien być:

**Direct Play zamiast transkodowania.**

Telewizor powinien dostawać pliki w formatach, które potrafi odtworzyć natywnie.

---

# 25. Avahi

Avahi jest obecnie uruchomione:

```text
avahi-daemon.service
```

Avahi implementuje mDNS/DNS-SD.

Jest to mechanizm lokalnego wykrywania usług.

W kontekście mediów może być przydatny dla lokalnego discovery, ale:

**Avahi ≠ DLNA.**

DLNA/UPnP i mDNS to różne mechanizmy.

---

# 26. Bezpieczeństwo przesyłania konfiguracji

Do diagnostyki można przekazywać wyniki typu:

```bash
lsblk
df -hT
free -h
systemctl list-units --type=service --state=running --no-pager
ss -tulpn
getent passwd | cut -d: -f1
ip addr
ip route
sudo wg show
```

Przed wysłaniem należy usuwać/anonimizować:

```text
PrivateKey
hasła
API keys
tokeny
SSH private keys
prywatne certyfikaty
sekrety z .env
session cookies
inne credentials
```

Najbezpieczniej nie przesyłać całego `/etc` jako archiwum bez wcześniejszego przejrzenia.

---

# 27. Plan wdrożenia po otrzymaniu WRT54GL

## Etap 0 — backup i diagnostyka

- backup działającej konfiguracji,
- sprawdzenie WireGuard,
- sprawdzenie routingu,
- sprawdzenie firewalli,
- sprawdzenie interfejsów,
- upewnienie się, że SSH pozostaje dostępne.

## Etap 1 — WRT

- identyfikacja rewizji WRT54GL,
- identyfikacja firmware,
- konfiguracja WAN,
- konfiguracja P2P LAN,
- DHCP,
- firewall,
- izolacja od głównej LAN.

## Etap 2 — routing

- WRT → Pi,
- IP forwarding na Pi,
- test komunikacji,
- test DNS,
- test dostępu bez VPN.

## Etap 3 — WireGuard

- skierowanie P2P przez `wg0`,
- test publicznego IP,
- test DNS,
- test routingu,
- test przepustowości.

## Etap 4 — kill switch

- blokada zwykłej ścieżki WAN,
- test WireGuard ON,
- test WireGuard OFF,
- potwierdzenie braku fallbacku.

## Etap 5 — klient P2P

- instalacja/konfiguracja klienta,
- związanie ruchu z właściwym interfejsem, jeśli klient to umożliwia,
- ustawienie limitów,
- protocol encryption,
- test legalnego P2P.

## Etap 6 — monitoring

```bash
htop
free -h
uptime
sudo wg show
ip -s link
```

---

# 28. Zasada bezpieczeństwa projektu

Nie przebudowywać całego działającego Pi naraz.

Kolejność:

```text
BACKUP
  ↓
DIAGNOSTYKA
  ↓
WRT
  ↓
P2P LAN
  ↓
ROUTING
  ↓
WIREGUARD
  ↓
KILL SWITCH
  ↓
TESTY
  ↓
KLIENT P2P
```

Każdy etap musi działać przed przejściem do następnego.

---

# 29. Czego jeszcze nie ustalamy

Do czasu fizycznego dostępu do WRT54GL nie zakładamy:

- dokładnej rewizji WRT,
- firmware,
- dokładnego sposobu połączenia WAN,
- finalnej adresacji,
- finalnego routingu,
- reguł firewall,
- dokładnej konfiguracji WireGuard,
- możliwości firmware WRT,
- sposobu NAT na VPS.

Najpierw zbierzemy fakty.

---

# 30. Docelowa architektura w jednym diagramie

```text
                         INTERNET
                            |
                         CGNAT
                            |
                       T-Mobile
                            |
              +-------------+-------------+
              |                           |
          GŁÓWNA LAN                  WRT54GL
              |                           |
              |                       P2P LAN
              |                    192.168.50.0/24
              |                           |
              |                      P2P client
              |                           |
              |                           v
              |                    Raspberry Pi 4
              |                           |
              |                      IP forwarding
              |                           |
              |                       WireGuard
              |                           🔒
              |                           |
              |                           v
              |                      Oracle VPS
              |                           |
              |                           NAT
              |                           |
              +---------------------------+
                                          |
                                       INTERNET
                                          |
                                         Peer
```

---

# 31. Krótkie podsumowanie

**WRT54GL:** osobna sieć P2P + firewall + DHCP.

**Raspberry Pi:** gateway dla P2P + istniejący WireGuard + obecne usługi.

**WireGuard:** szyfrowany tunel Pi → Oracle VPS.

**Oracle VPS:** publiczny punkt wyjścia ruchu.

**Kill switch:** brak wyjścia P2P przez zwykły WAN przy awarii VPN.

**BitTorrent encryption:** dodatkowa warstwa na poziomie protokołu P2P, nie zamiennik VPN.

**Główna LAN:** pozostaje niezależna od P2P.

**SSD 500 GB:** pozostaje na Pi; około 435 GB było wolne podczas ostatniego pomiaru.

**Media:** docelowo `/srv/media`, z Jellyfin/DLNA i profilem dostosowanym do Panasonic TX-40CS520E.

**Najważniejsza zasada:** najpierw backup i diagnostyka, potem WRT i routing, a dopiero na końcu P2P.

---

## Punkt wznowienia projektu

Gdy WRT54GL będzie fizycznie dostępny:

1. Podaj model/revizję i wersję firmware.
2. Podeślij zdjęcia portów/oznaczeń, jeśli potrzebne.
3. Nie resetuj go jeszcze, jeśli może zawierać istotną konfigurację.
4. Z Pi zbierzemy aktualny `ip addr`, `ip route`, `sudo wg show` oraz konfigurację firewalla bez sekretów.
5. Następnie zaprojektujemy dokładny routing WRT → Pi → WireGuard → VPS.

**Nie wykonujemy jeszcze żadnych zmian w produkcyjnej konfiguracji Pi.**
