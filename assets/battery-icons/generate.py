#!/usr/bin/env python3
"""Generate macOS-pill battery symbolic icons matching the top-bar glyph
(extensions/macos-top-panel@local.dev/lib/batteryCanvas.js). One per 10%
level, plain + charging, so GNOME's login/lock-screen Quick Settings battery
looks the same as the menu bar's. Symbolic = single colour (the shell
recolours currentColor); the menu bar's yellow/red/green fill can't carry to
a themeable icon, so the greeter battery just follows the shell's own
low-battery colouring.

Run from anywhere; writes *.svg next to this file.
"""
import os

# 16x16 canvas; pill authored to the same proportions as batteryCanvas.js
# (22x13 glyph: 20-wide body + 2-wide nub, 1.3 outline, 2.3 corner, 2 inset).
W, H = 16, 16
BODY_W, BODY_H = 12.4, 8.0          # scaled ~0.62 from 20x13
NUB_W, NUB_H = 1.2, 3.4
OUTLINE = 0.9
CORNER = 1.6
INSET = 1.15
X0 = 0.6
Y0 = (H - BODY_H) / 2

HEADER = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'


def rr(x, y, w, h, r):
    r = round(min(r, w / 2, h / 2), 3)
    n = lambda v: round(v, 3)
    return (f'M{n(x + r)},{n(y)} h{n(w - 2 * r)} a{r},{r} 0 0 1 {r},{r} v{n(h - 2 * r)} '
            f'a{r},{r} 0 0 1 {-r},{r} h{n(-(w - 2 * r))} a{r},{r} 0 0 1 {-r},{-r} '
            f'v{n(-(h - 2 * r))} a{r},{r} 0 0 1 {r},{-r} z')


def bolt(cx, cy, s):
    pts = [(0.5, -3.6), (-2.1, 0.5), (-0.25, 0.5), (-0.75, 3.6), (2.1, -0.65), (0.15, -0.65)]
    d = f'M{cx + pts[0][0] * s},{cy + pts[0][1] * s} '
    d += ' '.join(f'L{cx + px * s},{cy + py * s}' for px, py in pts[1:])
    return d + ' Z'


def make(level, charging=False, charged=False):
    parts = [HEADER, '<g fill="#363636">']
    # outline (stroke via two rounded rects: outer filled minus inner hole -> even-odd)
    parts.append(
        f'<path fill-rule="evenodd" opacity="0.55" d="'
        f'{rr(X0, Y0, BODY_W, BODY_H, CORNER)} '
        f'{rr(X0 + OUTLINE, Y0 + OUTLINE, BODY_W - 2 * OUTLINE, BODY_H - 2 * OUTLINE, max(CORNER - OUTLINE, 0.4))}"/>')
    # terminal nub
    parts.append(f'<rect opacity="0.55" x="{X0 + BODY_W - 0.1}" y="{(H - NUB_H) / 2}" '
                 f'width="{NUB_W}" height="{NUB_H}" rx="0.5"/>')
    # fill bar
    inner_x = X0 + INSET
    inner_y = Y0 + INSET
    inner_w = BODY_W - 2 * INSET
    inner_h = BODY_H - 2 * INSET
    fill_w = round(inner_w * max(0, min(100, level)) / 100, 2)
    if fill_w > 0.3:
        parts.append(f'<rect x="{round(inner_x, 3)}" y="{round(inner_y, 3)}" '
                     f'width="{fill_w}" height="{round(inner_h, 3)}" '
                     f'rx="{round(min(0.6, fill_w / 2, inner_h / 2), 3)}"/>')
    # charging bolt on top
    if charging or charged:
        parts.append(f'<path fill="#363636" d="{bolt(X0 + BODY_W / 2 - 0.3, H / 2, 0.62)}"/>')
    parts.append('</g></svg>')
    return '\n'.join(parts)


HERE = os.path.dirname(os.path.abspath(__file__))
levels = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
written = []
for lv in levels:
    for suffix, kw in (('', {}), ('-charging', {'charging': True})):
        name = f'battery-level-{lv}{suffix}-symbolic.svg'
        open(os.path.join(HERE, name), 'w').write(make(lv, **kw))
        written.append(name)
# charged (full + still plugged) and the "plugged-in" alias GNOME also probes
for name in ('battery-level-100-charged-symbolic.svg', 'battery-full-charged-symbolic.svg'):
    open(os.path.join(HERE, name), 'w').write(make(100, charged=True))
    written.append(name)
for lv in levels:
    src = f'battery-level-{lv}-charging-symbolic.svg'
    dst = f'battery-level-{lv}-plugged-in-symbolic.svg'
    open(os.path.join(HERE, dst), 'w').write(open(os.path.join(HERE, src)).read())
    written.append(dst)
print(f'wrote {len(written)} icons to {HERE}')
