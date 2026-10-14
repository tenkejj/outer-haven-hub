# Remote AI — szablony (PC + sieć WG)

Patrz pełny opis etapów: [`docs/REMOTE-AI.md`](../../docs/REMOTE-AI.md).

| Plik | Przeznaczenie |
|------|----------------|
| `phase0-diagnose.sh` | Bezpieczna diagnostyka IP/WG (Pi lub PC) |
| `llama-server.service` | systemd unit na PC |
| `llama-server.env.example` | ścieżka GGUF, port, `-ngl` |
| `hermes-webui.env.example` | hasło + host/port |
| `Caddyfile.remote-ai.snippet` | opcjonalny reverse proxy w sieci domowej/WG |

Instalacja unitów — **na PC**, nie na Pi:

```bash
# po dostosowaniu ścieżek:
sudo cp llama-server.service /etc/systemd/system/
sudo cp llama-server.env /etc/default/llama-server   # z .env.example
sudo systemctl daemon-reload
sudo systemctl enable --now llama-server
```
