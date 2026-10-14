# Remote AI — iPhone → VPS → dom → Qwen + Hermes

Planowana droga: czat z lokalnym modelem i sterowanie agentem Hermesa
z iPhone’a na uczelni, bez wystawiania API na publiczny internet.

**Status:** Etap 0–1 OK + hermes-webui na foxhound (`192.168.1.104:8787`, health OK). Dalej: Caddy na Pi → Hermex.
**Nie ruszamy routingu P2P / WRT** — to osobny projekt (`docs/wrt54gl_p2p_architektura.md`).

Szablony: [`deploy/remote-ai/`](../deploy/remote-ai/).

### Stan z diagnostyki (2026-10-14)

| Host | Rola | IP |
|------|------|-----|
| **sumit** (Oracle VPS) | hub WG | `wg0` **`10.10.0.1/24`**, `:51820`, public `130.61.160.71` |
| **mother-base** (Pi) | peer + Caddy | LAN `192.168.1.201`, WG **`10.10.0.2`** |
| **iPhone** | peer | WG **`10.10.0.3`** — dostęp do Pi **potwierdzony** |
| **foxhound** (PC) | silnik AI | LAN **`192.168.1.104`**, bez WG |

**Trasa (działa do Pi; AI jeszcze lokalnie na PC):**

```text
iPhone 10.10.0.3
  → sumit 10.10.0.1
  → mother-base 10.10.0.2  (Caddy / hub)
  → foxhound 192.168.1.104:8787  hermes-webui  (Hermex)
       └── lokalnie 127.0.0.1:8080  llama-server (Qwen3.5-9B Q5) ← tylko Hermes
```

### Kanoniczna komenda llama-server (foxhound)

```bash
/home/tenkej/llama.cpp/build/bin/llama-server \
  -m ~/Models/Qwen3.5-9B/Qwen3.5-9B-Q5_K_M.gguf \
  --alias qwen3.5-9b-q5 \
  -ngl 20 \
  -c 65536 \
  -np 1 \
  -b 512 \
  -ub 128 \
  -fa on \
  -ctk q8_0 \
  -ctv q8_0 \
  --no-kv-offload \
  --reasoning off \
  --reasoning-budget 0 \
  --host 127.0.0.1 \
  --port 8080
```

`llama-server` zostaje na **localhost** (backend Hermesa). Z iPhone’a nie łączymy
się prosto do :8080 — tylko do **hermes-webui** przez Caddy na Pi.

---

## 1. Cel

| Element | Rola |
|--------|------|
| **iPhone** | klient: WireGuard + przeglądarka (czat) + aplikacja **Hermex** (agent) |
| **Oracle VPS** | osiągalny punkt wejścia (dom za CGNAT T-Mobile) |
| **mother-base (Pi 4)** | infrastruktura / ewentualny hop w tunelu WG — **bez** modelu |
| **PC** (Ryzen 5 3600, 16 GB, RTX 3060 Ti) | `llama-server` (Qwen) + Hermes Agent + `hermes-webui` |

Dwa niezależne serwisy na tej samej prywatnej sieci WG:

1. **Czat** — UI → API `llama-server` (OpenAI-compatible).
2. **Hermes** — `hermes-webui` (:8787) ← aplikacja Hermex na iPhonie.

Awaria czatu ≠ awaria agenta. Restart modelu ≠ restart Pi-hole / Caddy.

---

## 2. Droga ruchu (docelowa)

```text
iPhone (uczelnia)
    │  WireGuard (własny klucz)
    v
Oracle VPS
    │  istniejący tunel WG → dom
    v
sieć domowa  (Pi i/lub PC w AllowedIPs / routingu)
    │
    ├── PC :8080  llama-server   → czat Qwen (GGUF na GPU)
    └── PC :8787  hermes-webui   → Hermex (agent + narzędzia)
```

To jest **plan**. Konkretna trasa zależy od tego, czy dziś VPS peeruje z Pi,
z PC, czy z obu, oraz czy LAN `192.168.1.0/24` jest w `AllowedIPs`.

### Co się dzieje przy pytaniu

1. Otwierasz prywatny URL czatu na iPhonie (tylko w sieci WG).
2. Ruch idzie zaszyfrowanym tunelem do domu.
3. UI woła `llama-server` na PC.
4. **Qwen ~9B** (GGUF, llama.cpp) generuje na RTX 3060 Ti.
5. Odpowiedź wraca tą samą drogą.

Model **nie** działa na iPhonie ani na Pi.

### Bezpieczeństwo (twarde reguły)

- `llama-server` i `hermes-webui` **nie** na publicznym `0.0.0.0` bez hasła / bez WG.
- Preferowane: bind `127.0.0.1` + dostęp tylko przez interfejs WG / reverse proxy w sieci WG.
- Hasło `HERMES_WEBUI_PASSWORD` obowiązkowe przed wystawieniem poza localhost.
- VPS jest w ścieżce IP — widzi metadane; treść w tunelu WG jest szyfrowana między peerami WG. Nie wystawiaj HTTP bez TLS poza zaufaną siecią WG.

---

## 3. Mapa etapów

| Etap | Gdzie | Wynik | Ryzyko |
|------|-------|-------|--------|
| **0** | Pi + VPS + PC | znamy topologię WG i IP | tylko odczyt |
| **1** | WG | iPhone sięga PC po IP WG/LAN | małe (AllowedIPs) |
| **2** | PC | `llama-server` lokalnie + test z LAN | brak zmian na Pi |
| **3** | PC | prosty czat (Open WebUI lub UI llama.cpp) przez WG | małe |
| **4** | PC | Hermes Agent + hermes-webui + Hermex | małe |
| **5** | PC | systemd / autostart, sleep inhibit, monitoring | małe |

Każdy etap musi przejść test zanim ruszysz następny.

---

## 4. Etap 0 — diagnostyka (teraz)

Skrypt: `deploy/remote-ai/phase0-diagnose.sh` (uruchom na Pi i na PC).

### 0a. Na mother-base (Pi)

```bash
hostname
ip -4 addr
ip route
sudo wg show
# Zanonimizuj PrivateKey / pełne klucze przed wklejeniem komukolwiek.
```

Szukamy: nazwa interfejsu `wg*`, IP WG Pi, peer VPS, `allowed ips`.

### 0b. Na Oracle VPS

```bash
sudo wg show
ip -4 addr
ip route
```

Szukamy: czy VPS ma peer tylko do Pi, czy też do PC / iPhone; czy routuje `192.168.1.0/24`.

### 0c. Na PC (Omarchy / Linux)

```bash
hostname
ip -4 addr
ip route
# jeśli PC ma własny WG:
sudo wg show 2>/dev/null || true
ping -c2 192.168.1.201   # Pi — dostosuj IP
```

### Decyzja po Etapie 0

Wybierz jedną ścieżkę (preferencja od najprostszej):

| Opcja | Opis |
|-------|------|
| **A** | PC jest peerem WG VPS (jak telefon) — iPhone ↔ VPS ↔ PC |
| **B** | Tylko Pi jest peerem VPS; VPS/Pi routują LAN do PC (`192.168.1.x`) |
| **C** | PC za Tailscale (Hermex to lubi) — **osobna** sieć; ten projekt celuje w Twój istniejący Oracle WG |

Wklej wyniki Etapu 0 (bez sekretów) — wtedy dopisujemy dokładne `AllowedIPs` / DNS.

---

## 5. Etap 1 — zasięg iPhone → PC

Cel: z iPhone’a (WG włączony) otwierasz `http://<IP-PC>:8080/health` lub ping.

1. PC nie może być uśpiony (wyłącz suspend przy zasilaniu / `systemctl mask sleep.target` ostrożnie — albo „inhibit” tylko gdy serwer działa).
2. Firewall PC: pozwól na porty **tylko** z sieci WG / LAN, nie z całego internetu.
3. Jeśli używasz opcji B: na Pi `IP forwarding` + trasa do PC już może istnieć dla innych usług — **nie** mieszaj z regułami P2P kill-switch.

Test sukcesu: Safari na iPhonie ładuje health check z PC.

---

## 6. Etap 2 — llama-server na PC

### Model (Twój sprzęt)

| | Rekomendacja |
|--|----------------|
| Daily | **~8–9B Q5_K_M** (Qwen), `-ngl 99`, całe na 3060 Ti 8 GB |
| Plik | GGUF w katalogu np. `~/models/qwen-*.gguf` |

### Instalacja llama.cpp (skrót)

```bash
# przykład — dostosuj do swojego setupu (build z CUDA)
cd ~
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
# zbuduj z CUDA wg oficjalnego README, potem:
./build/bin/llama-server --help
```

### Uruchomienie testowe (tylko localhost)

```bash
./build/bin/llama-server \
  -m ~/models/TWOJ-QWEN-9B-Q5_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  -ngl 99 -c 8192
```

Test:

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/v1/models
```

Szablon unit: `deploy/remote-ai/llama-server.service` + `llama-server.env.example`.

Gdy Etap 1 działa, możesz zbindować na IP interfejsu WG **albo** zostawić `127.0.0.1`
i wystawić przez Caddy tylko w sieci WG (bezpieczniej).

---

## 7. Etap 3 — prywatny czat

Opcje (wybierz jedną):

| UI | Plus | Minus |
|----|------|-------|
| Wbudowany UI llama-server | zero zależności | prostszy |
| **Open WebUI** | wygląda jak ChatGPT, historie | osobny kontener/proces |
| Minimalny HTML w Hubie | spójne z Outer Haven | trzeba dopisać |

Wspólne: UI woła OpenAI-compatible API:

`POST http://<pc>:8080/v1/chat/completions`

Dostęp **tylko** przez WG (iPhone w tunelu). Bez publicznego port-forward na T-Mobile.

---

## 8. Etap 4 — Hermes + Hermex

Hermex (App Store) mówi do **hermes-webui**, nie do wbudowanego dashboardu Hermesa.

### Na PC (foxhound)

Hermes Agent (CLI) ≠ **hermes-webui** (to, czego potrzebuje Hermex).
Jeśli `~/hermes-webui` nie istnieje — zainstaluj UI osobno:

```bash
# opcjonalnie: gdzie jest agent
command -v hermes; ls -d ~/.hermes ~/hermes* 2>/dev/null

git clone https://github.com/nesquena/hermes-webui.git ~/hermes-webui
cd ~/hermes-webui
python3 bootstrap.py
```

Hasło **przed** wystawieniem poza localhost:

```bash
export HERMES_WEBUI_PASSWORD='zmien-na-dlugie-haslo'
./start.sh
# albo: ./ctl.sh start
curl -s http://127.0.0.1:8787/health
```

Domyślnie: `127.0.0.1:8787`.

### Dostęp z iPhone (u Ciebie: WireGuard, nie Tailscale)

Zamiast `tailscale serve`:

1. Upewnij się, że iPhone osiąga PC:8787 w sieci WG (Etap 1).
2. Albo reverse proxy (Caddy na PC lub na Pi) z TLS w sieci lokalnej/WG na hostname typu `hermes.haven` / `hermes.wg`.
3. W Hermex: Server URL = ten HTTPS/HTTP + hasło z `HERMES_WEBUI_PASSWORD`.
4. Test Connection → `/health`.

**Nie** używaj Cloudflare Tunnel, jeśli chcesz trzymać wszystko w fortecy WG
(CF to publiczny hostname — wtedy hasło jest obowiązkowe i akceptujesz edge CF).

Skonfiguruj Hermesa tak, by jako backend LLM używał lokalnego `llama-server`
(`http://127.0.0.1:8080/v1/...`), nie chmury — wtedy agent i czat dzielą ten sam Qwen na GPU.

### Czy Hermes działa po odłożeniu telefonu?

Tak, jeśli proces na PC żyje (hermes-webui + zadanie). Hermex to sterowanie,
nie runtime. To **nie** jest zdalny pulpit Omarchy — do GUI potrzeba osobnego
mechanizmu (nie w zakresie tego dokumentu).

---

## 9. Etap 5 — twardość na co dzień

Na PC:

- systemd user/system dla `llama-server` i hermes-webui,
- wyłącz autosuspend gdy serwisy aktywne,
- opcjonalnie mały health w Outer Haven Hub (collector „remote-ai” — później),
- backup GGUF / konfiguracji Hermesa.

Na iPhonie:

- profil WireGuard always-on (opcjonalnie) albo ręcznie przed nauką,
- Hermex + zakładka czatu.

---

## 10. Co robimy w tym repo vs na maszynach

| W repo `outer-haven-hub` | Na Twoich maszynach (Ty wklejasz) |
|--------------------------|-----------------------------------|
| Ten dokument + szablony unit/env/Caddy | Etap 0: `wg show` / IP |
| Skrypt diagnostyczny | Etap 2–4: instalacja na PC |
| Link z `docs/HOMELAB.md` | Klucze WG, hasła, GGUF |

Z tej sesji Cloud Agent **nie** ma SSH do VPS/Pi/PC — wdrażanie idzie
komendami, które dostajesz poniżej i w `deploy/remote-ai/`.

---

## 11. Następny krok

PC = **foxhound / 192.168.1.104** — zapisane.

### Jeszcze Etap 0: VPS

```bash
hostname
ip -4 addr
sudo wg show
```

Szukamy: IP VPS w `10.10.0.0/24` (pewnie `.1`), lista peerów (Pi `.2`, iPhone `?`).

### Równolegle — Etap 2 na foxhound (nie czeka na VPS)

Gdy masz GGUF Qwen ~9B Q5:

```bash
# przykładowy test — dostosuj ścieżki do swojego builda llama.cpp
./llama-server -m ~/models/qwen-*.gguf --host 127.0.0.1 --port 8080 -ngl 99 -c 8192
# w drugim terminalu:
curl -s http://127.0.0.1:8080/health
```

Potem otwarcie tylko na LAN (dla proxy z Pi), nie na świat:

```bash
# dopiero gdy localhost działa — bind na LAN PC:
./llama-server -m ~/models/qwen-*.gguf --host 192.168.1.104 --port 8080 -ngl 99 -c 8192
# z Pi:
curl -s http://192.168.1.104:8080/health
```

---

## 12. Szybka ściągawka portów (PC)

| Port | Serwis | Bind na start |
|------|--------|----------------|
| foxhound `:8080` | llama-server | `127.0.0.1` — tylko Hermes na PC |
| foxhound `:8787` | hermes-webui | LAN `192.168.1.104` + hasło → Caddy na Pi |
| Pi `:8080` | Pi-hole admin | inna maszyna — brak kolizji z foxhound |

---

## Changelog

| Data | Zmiana |
|------|--------|
| 2026-10-14 | Start: architektura iPhone→VPS→dom→Qwen/Hermes, etapy 0–5, szablony deploy |
