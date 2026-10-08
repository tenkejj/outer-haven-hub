#!/bin/sh
# Kiosk Outer Haven Hub — wgraj jako ~/.xinitrc na Pi.
#
# WAŻNE: NIE wymuszaj 1920×1080, jeśli matryca ma inną natywną rozdzielczość.
# Zrzut z monituorka pokazał 1024×768 — przy --window-size=1920,1080 Chromium
# rysował za duże okno, a ekran pokazywał tylko wycinek („zoomed / clipped").
#
# Panel instrumentowy: http://127.0.0.1:8090/panel/
# Stary dashboard kart:  http://127.0.0.1:8090/

# Wygaszanie po 10 min bezczynności
xset s 600 600
xset +dpms
xset dpms 600 600 600

# Natywny tryb wyjścia HDMI (pierwszy podłączony). Bez sztywnego --mode.
OUT=$(xrandr | awk '/ connected/{print $1; exit}')
if [ -n "$OUT" ]; then
  xrandr --output "$OUT" --auto
fi

# Rozmiar okna = bieżąca rozdzielczość X (nie zgadujemy 1920×1080).
GEO=$(xrandr | awk -v o="$OUT" '$1==o && / connected/{
  for (i=1;i<=NF;i++) if ($i ~ /^[0-9]+x[0-9]+/) { print $i; exit }
}')
# Fallback: preferred mode z linii z *
if [ -z "$GEO" ]; then
  GEO=$(xrandr | awk '/\*/{print $1; exit}')
fi
W=${GEO%x*}
H=${GEO#*x}
[ -z "$W" ] && W=1024
[ -z "$H" ] && H=768

exec chromium --noerrdialogs --disable-infobars --kiosk --start-fullscreen \
  --window-position=0,0 --window-size="${W},${H}" \
  --force-device-scale-factor=1 \
  --incognito http://127.0.0.1:8090/panel/
