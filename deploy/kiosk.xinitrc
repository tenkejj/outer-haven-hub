#!/bin/sh
# Outer Haven Hub — kiosk X session (~/.xinitrc na mother-base).
#
# Install:
#   cp deploy/kiosk.xinitrc ~/.xinitrc && chmod +x ~/.xinitrc
# Autologin tty1 → startx: patrz deploy/kiosk.profile-snippet + DEPLOY.md §4.
#
# Zasady (wypracowane na produkcji):
#   - URL root `/` — NIE `/panel/` (stary instrument-panel → JSON 404)
#   - BEZ --window-size / --window-position (czarne paski przy 1600x900 na 1080p)
#   - Preferuj 1920x1080 gdy EDID je oferuje (unika letterboxa)
#   - ?theme=hud — jawny motyw kiosku (telefon dostaje Wall z auto-detect)

xset s 600 600
xset +dpms
xset dpms 600 600 600

OUT=$(xrandr | awk '/ connected/{print $1; exit}')
if [ -n "$OUT" ]; then
  if xrandr | grep -q "1920x1080"; then
    xrandr --output "$OUT" --mode 1920x1080 --rate 60 --primary
  else
    xrandr --output "$OUT" --auto
  fi
fi

exec chromium --noerrdialogs --disable-infobars --kiosk --start-fullscreen \
  --force-device-scale-factor=1 \
  --incognito \
  "http://127.0.0.1:8090/?theme=hud"
