#!/usr/bin/env bash
# Etap 0 — diagnostyka sieci / WireGuard (bez sekretów w stdout).
# Uruchom na mother-base (Pi) i na PC. Na VPS: te same komendy ręcznie.
#
#   chmod +x phase0-diagnose.sh
#   ./phase0-diagnose.sh
#
# Przed wysłaniem komukolwiek: sprawdź, czy nie ma PrivateKey / PresharedKey.

set -euo pipefail

redact_keys() {
  # Ukryj typowe linie sekretów WG, gdyby trafiły do outputu.
  sed -E \
    -e 's/(PrivateKey[[:space:]]*=[[:space:]]*).*/\1[REDACTED]/' \
    -e 's/(PresharedKey[[:space:]]*=[[:space:]]*).*/\1[REDACTED]/' \
    -e 's#(-----BEGIN .*PRIVATE KEY-----).*#\1 [REDACTED]#'
}

echo "=== host ==="
hostname
date -Is
echo

echo "=== uname ==="
uname -a
echo

echo "=== ipv4 addresses ==="
ip -4 addr show | redact_keys
echo

echo "=== routes ==="
ip route
echo

echo "=== listening (selected) ==="
if command -v ss >/dev/null 2>&1; then
  ss -tulpn 2>/dev/null | egrep '(:22|:80|:443|:8080|:8081|:8090|:8787|:5335|:53\s)' || true
else
  echo "(ss not found)"
fi
echo

echo "=== wireguard (sudo) ==="
if command -v wg >/dev/null 2>&1; then
  if sudo -n wg show 2>/dev/null | redact_keys; then
    :
  else
    sudo wg show 2>/dev/null | redact_keys || echo "(brak uprawnień do wg show — uruchom: sudo ./phase0-diagnose.sh)"
  fi
else
  echo "(wg not installed)"
fi
echo

echo "=== done ==="
echo "Wyślij ten output (już z redakcją PrivateKey). Dopisz ręcznie:"
echo "  - czy ten host to Pi / PC / VPS"
echo "  - IP LAN PC (jeśli znane)"
echo "  - czy iPhone jest pearem tego samego WG co VPS"
