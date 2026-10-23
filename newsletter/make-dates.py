#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draws the three turnaround date cards for the weekly email as one PNG.

   An email cannot run a formula once it has been sent, so the dates are drawn
   here instead, every morning, and the email points at the picture by its
   fixed web address. Whoever opens the email sees that day's dates.

   Run by .github/workflows/newsletter-dates.yml shortly before the nightly
   site publish, which copies media/ to the live site.

   Usage:  python3 newsletter/make-dates.py [YYYY-MM-DD] [output-folder]
   Date defaults to today in Las Vegas; folder defaults to media/.
   Needs Pillow. Fonts are in newsletter/fonts (Montserrat, Open Sans, both
   SIL Open Font License). Icons are media/nl-icon-*.png.
"""
import os, sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

HERE  = os.path.dirname(os.path.abspath(__file__))
REPO  = os.path.dirname(HERE)
MEDIA = os.path.join(REPO, 'media')
FONTS = os.path.join(HERE, 'fonts')
NAME  = 'nl-turnaround-dates.png'

# Fastest first. Same tiers as the calculator: 5, 7 and 10 business days.
TIERS = [('Super Rush', 5, 'bolt'), ('Rush', 7, 'chevrons'), ('Standard', 10, 'calendar')]

# ---------------------------------------------------------------- dates
# Same rule as the newsletter build: weekends and major holidays do not count.
def _nth(y, m, wd, n):
    d = date(y, m, 1); d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)
def _last(y, m, wd):
    d = (date(y, m + 1, 1) - timedelta(days=1)) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - wd) % 7)
def holidays(y):
    thx = _nth(y, 11, 3, 4)
    return {date(y,1,1), _last(y,5,0), date(y,7,4), _nth(y,9,0,1),
            thx, thx + timedelta(days=1), date(y,12,24), date(y,12,25), date(y,12,31)}

def ready_by(start, business_days):
    hol = holidays(start.year) | holidays(start.year + 1)
    d, n = start, 0
    while n < business_days:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in hol:
            n += 1
    return d

# ---------------------------------------------------------------- drawing
S = 4                          # draw at 4x, then shrink to 2x for a crisp result
W, H = 320, 114                # logical size in px; the email shows it at 320 wide
INK, INK3, CARD = (26, 35, 48, 255), (123, 134, 150, 255), (244, 245, 248, 255)

def font(file, px, axes):
    f = ImageFont.truetype(os.path.join(FONTS, file), int(px * S))
    f.set_variation_by_axes(axes)
    return f
MONT = lambda px, w=700: font('Montserrat-VF.ttf', px, [w])
OPEN = lambda px, w=400: font('OpenSans-VF.ttf', px, [w, 100])

def text_w(f, s, track=0):
    return f.getlength(s) + track * S * len(s)

def draw_text(d, x, y, s, f, fill, track=0):
    """Baseline-anchored text with optional letter spacing (px)."""
    if not track:
        d.text((x * S, y * S), s, font=f, fill=fill, anchor='ls'); return
    cx = x * S
    for ch in s:
        d.text((cx, y * S), ch, font=f, fill=fill, anchor='ls')
        cx += f.getlength(ch) + track * S

def render(today, out_dir):
    img = Image.new('RGBA', (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    gap, cw, ch = 8, (W - 16) / 3, 84
    for i, (label, days, icon) in enumerate(TIERS):
        x0 = i * (cw + gap)
        d.rounded_rectangle([x0 * S, 0, (x0 + cw) * S, ch * S], radius=12 * S, fill=CARD)
        mid = x0 + cw / 2
        # title
        f = MONT(11, 700); t = label.upper()
        draw_text(d, mid - text_w(f, t, 0.3) / 2 / S, 24, t, f, INK, 0.3)
        # "N Business Days"
        f = OPEN(10, 400); t = '%d Business Days' % days
        draw_text(d, mid - text_w(f, t) / 2 / S, 40, t, f, INK3)
        # icon + date
        f = MONT(15, 700); t = ready_by(today, days).strftime('%b %-d')
        row_w = 14 + 5 + text_w(f, t) / S
        rx = mid - row_w / 2
        ic = Image.open(os.path.join(MEDIA, 'nl-icon-%s.png' % icon)).convert('RGBA').resize((14 * S, 14 * S), Image.LANCZOS)
        img.alpha_composite(ic, (int(rx * S), int(56 * S)))
        draw_text(d, rx + 19, 68, t, f, INK)
    # footnote: "Dates based on <bold date>. Business days only."
    f1, f2, base = OPEN(11.5, 400), OPEN(11.5, 700), 107
    x = 0
    for s, f, c in (('Dates based on ', f1, INK3), (today.strftime('%a, %b %-d, %Y'), f2, INK),
                    ('. Business days only.', f1, INK3)):
        draw_text(d, x, base, s, f, c); x += text_w(f, s) / S
    img = img.resize((W * 2, H * 2), Image.LANCZOS)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, NAME)
    img.save(out, optimize=True)
    return out

if __name__ == '__main__':
    today = (date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1
             else datetime.now(ZoneInfo('America/Los_Angeles')).date())
    out_dir = sys.argv[2] if len(sys.argv) > 2 else MEDIA
    out = render(today, out_dir)
    print('wrote %s (%.1f KB) for %s: %s' % (out, os.path.getsize(out) / 1024, today,
          ', '.join('%s %s' % (l, ready_by(today, n).strftime('%b %-d')) for l, n, _ in TIERS)))
