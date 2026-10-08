#!/bin/sh
# Kiosk Outer Haven Hub — wgraj jako ~/.xinitrc na Pi.
#
# Panel: http://127.0.0.1:8090/panel/
#
# Rozdzielczość: xrandr --auto (natywny / preferred mode).
# NIE zgaduj 1920×1080. NIE bierz surowego "1600x900+0+0" do --window-size
# (Chromium dostawał H="900+0+0" i odpadał na małe okno → panel w rogu).

xset s 600 600
xset +dpms
xset dpms 600 600 600

OUT=$(xrandr | awk '/ connected/{print $1; exit}')
if [ -n "$OUT" ]; then
  xrandr --output "$OUT" --auto
fi

# Tylko czyste "1600x900" — bez "+0+0" z linii "connected".
MODE=$(xrandr | awk '/\*/{print $1; exit}')
if [ -z "$MODE" ]; then
  MODE=$(xrandr | awk -v o="$OUT" '
    $1 == o && / connected/ {
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^[0-9]+x[0-9]+/) {
          split($i, a, /[+* ]/);
          print a[1];
          exit
        }
      }
    }')
fi

W=$(echo "$MODE" | cut -dx -f1)
H=$(echo "$MODE" | cut -dx -f2)
# Sanity: tylko cyfry
W=$(echo "$W" | tr -cd '0-9')
H=$(echo "$H" | tr -cd '0-9')
[ -z "$W" ] && W=1600
[ -z "$H" ] && H=900

exec chromium --noerrdialogs --disable-infobars --kiosk --start-fullscreen \
  --window-position=0,0 --window-size="${W},${H}" \
  --force-device-scale-factor=1 \
  --incognito http://127.0.0.1:8090/panel/
