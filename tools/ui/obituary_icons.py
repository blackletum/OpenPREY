#!/usr/bin/env python3
# Copyright (C) 2026 DarkMatter Productions. GPL-3.0-or-later.
"""The multiplayer obituary feed's icons, drawn as compact silhouettes.

    python tools/ui/obituary_icons.py            write the icons and their materials
    python tools/ui/obituary_icons.py --check    exit 1 if any icon or the material file is stale
    python tools/ui/obituary_icons.py --preview out.png
                                                 a contact sheet of every icon, for review

The graphical obituary feed (guis/obituaries.gui, src/ui/ObituaryWindow.h)
draws each death as "killer [icon] victim" on a line 15 units high, the icon
13 units high. Prey's weapon-bar icons (textures/interface/icons/*) are
detailed line drawings meant for 50x28 units; at the feed's size they blur
into noise, and they are retail art. These are openPR06's own: each weapon
reduced to a solid side view that reads at 13 units, muzzle toward the
victim (right), every one on the same 2:1 frame and centre line so they
share a weight in the feed.

- Weapons (256x128): wrench, spirit bow, Hunter rifle, crawler, auto cannon,
  acid sprayer, rocket launcher, leech gun.
- Glyphs (128x128): skull (suicide, death without a killer), telefrag (a
  bursting portal), generic (a kill by anything else).
- Badges (64x64), drawn on the icon's top-trailing corner: scope (the
  rifle's scoped shot), mine (a crawler left as a trap), grenade (the auto
  cannon's and the acid sprayer's alternate fire), plasma, bolt and sun (the
  leech gun's modes), skull (a suicide with a weapon).

Each icon is white with a dark keyline 1/32 of its height wide, so the feed
tints the white with HUD ink (the material is `colored`) while the keyline
keeps it separate from a bright scene and a badge separate from its weapon.
Every shape is drawn at SS times its size and box-filtered down; nothing is
random, so --check compares exactly.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXTURES = ROOT / "content" / "basepr" / "pak1" / "guis" / "assets" / "hud" / "obits"
MATERIALS = ROOT / "content" / "basepr" / "pak0" / "materials" / "openpr06_obituaries.mtr"
MATERIAL_PREFIX = "guis/assets/hud/obits"

SS = 4                      # supersampling
KEYLINE = 1.0 / 32.0        # the dark keyline, as a fraction of the icon's height
KEYLINE_ALPHA = 0.85


# ------------------------------------------------------------------ geometry

def ellipse_pts(cx, cy, rx, ry, n=72, a0=0.0, a1=360.0):
    pts = []
    for i in range(n + 1):
        t = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def rounded_pts(x0, y0, x1, y1, r, n=8):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = []
    for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            t = math.radians(start + 90 * i / n)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def bezier(p0, p1, p2, p3, n=24):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return pts


def stroke_pts(path, w0, w1=None):
    """A closed outline around a polyline whose width runs from w0 to w1."""
    w1 = w0 if w1 is None else w1
    n = len(path)
    left, right = [], []
    for i, (x, y) in enumerate(path):
        ax, ay = path[max(0, i - 1)]
        bx, by = path[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        half = (w0 + (w1 - w0) * i / max(1, n - 1)) / 2
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))
    return left + right[::-1]


class Icon:
    """A coverage mask built from added and cut polygons, in final texels."""

    def __init__(self, w, h):
        from PIL import Image, ImageDraw
        self.w, self.h = w, h
        self.image = Image.new("L", (w * SS, h * SS), 0)
        self.draw = ImageDraw.Draw(self.image)

    def _poly(self, pts, value):
        self.draw.polygon([(x * SS, y * SS) for x, y in pts], fill=value)

    def add(self, pts):
        self._poly(pts, 255)

    def cut(self, pts):
        self._poly(pts, 0)

    # conveniences
    def ellipse(self, cx, cy, rx, ry, cut=False):
        (self.cut if cut else self.add)(ellipse_pts(cx, cy, rx, ry))

    def rect(self, x0, y0, x1, y1, r=0.0, cut=False):
        (self.cut if cut else self.add)(rounded_pts(x0, y0, x1, y1, r))

    def stroke(self, path, w0, w1=None, caps=True, cut=False):
        (self.cut if cut else self.add)(stroke_pts(path, w0, w1))
        if caps:
            w1 = w0 if w1 is None else w1
            self.ellipse(path[0][0], path[0][1], w0 / 2, w0 / 2, cut)
            self.ellipse(path[-1][0], path[-1][1], w1 / 2, w1 / 2, cut)

    def ring(self, cx, cy, ro, ri):
        self.ellipse(cx, cy, ro, ro)
        self.ellipse(cx, cy, ri, ri, cut=True)

    def finish(self):
        """White shape, dark keyline outside it, box-filtered to final size."""
        import numpy as np
        from PIL import Image
        fill = np.asarray(self.image, dtype=np.uint8) > 127
        radius = max(1, round(KEYLINE * self.h * SS))
        grown = fill.copy()
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > radius * radius:
                    continue
                shifted = np.zeros_like(fill)
                ys = slice(max(0, dy), fill.shape[0] + min(0, dy))
                yd = slice(max(0, -dy), fill.shape[0] + min(0, -dy))
                xs = slice(max(0, dx), fill.shape[1] + min(0, dx))
                xd = slice(max(0, -dx), fill.shape[1] + min(0, -dx))
                shifted[ys, xs] = fill[yd, xd]
                grown |= shifted
        f = fill.astype(np.float64)
        g = grown.astype(np.float64)
        # box filter SSxSS down to the final texels
        def down(a):
            return a.reshape(self.h, SS, self.w, SS).mean(axis=(1, 3))
        cf, cg = down(f), down(g)
        alpha = np.maximum(cf, cg * KEYLINE_ALPHA)
        lum = np.where(alpha > 0, cf / np.maximum(alpha, 1e-6), 0.0)
        lum = np.clip(lum, 0.0, 1.0)
        rgba = np.zeros((self.h, self.w, 4), dtype=np.uint8)
        v = np.round(lum * 255).astype(np.uint8)
        rgba[..., 0] = v
        rgba[..., 1] = v
        rgba[..., 2] = v
        rgba[..., 3] = np.round(np.clip(alpha, 0, 1) * 255).astype(np.uint8)
        return Image.fromarray(rgba)


def mirrored(path, axis):
    return [(2 * axis - x, y) for x, y in path]


# ------------------------------------------------------------------ weapons (256x128, muzzle right)

def wrench(c: Icon):
    # Handle: long, slightly tapering, with a hanging hole at its end.
    c.add([(14, 64), (168, 60), (168, 88), (14, 86)])
    c.ellipse(16, 75, 11, 11)
    c.ellipse(20, 75, 5, 4.5, cut=True)
    # Head: the hook jaw over the movable jaw, toothed, open toward the victim.
    c.add([(156, 56), (176, 44), (204, 36), (236, 31), (248, 36), (248, 47), (216, 51),
           (210, 56), (210, 66), (240, 66), (248, 72), (246, 84), (230, 91), (196, 93), (164, 92), (156, 86)])
    for x in range(218, 246, 7):
        c.cut([(x, 51.5), (x + 3.5, 48), (x + 7, 51.5)])
        c.cut([(x, 65.5), (x + 3.5, 69), (x + 7, 65.5)])
    # The adjusting nut under the head, knurled.
    c.rect(176, 92, 210, 104, 3)
    for x in range(182, 208, 6):
        c.rect(x, 94, x + 2, 102, cut=True)


def bow(c: Icon):
    # The limb: a recurve standing at the leading side, thick at the grip.
    upper = bezier((52, 12), (28, 22), (22, 44), (32, 64), 28)
    lower = bezier((32, 64), (22, 84), (28, 106), (52, 116), 28)
    c.stroke(upper, 8, 16, caps=False)
    c.stroke(lower, 16, 8, caps=False)
    c.ellipse(32, 64, 8, 8)
    c.stroke([(50, 12), (60, 8), (66, 13)], 8, 6)
    c.stroke([(50, 116), (60, 120), (66, 115)], 8, 6)
    c.rect(20, 50, 42, 78, 5)
    # The string drawn back to the nock.
    c.stroke([(62, 12), (96, 64)], 4.5)
    c.stroke([(96, 64), (62, 116)], 4.5)
    # The arrow, nocked, its head at the victim.
    c.add([(94, 59.5), (222, 59.5), (222, 68.5), (94, 68.5)])
    c.add([(214, 46), (252, 64), (214, 82), (224, 64)])
    c.add([(94, 64), (110, 44), (126, 44), (112, 64)])
    c.add([(94, 64), (110, 84), (126, 84), (112, 64)])


def rifle(c: Icon):
    # The hooked stock curling down at the back.
    c.stroke(bezier((70, 62), (40, 60), (22, 70), (20, 96), 24), 14, 9, caps=False)
    c.stroke(bezier((20, 96), (19, 106), (24, 112), (32, 110), 10), 9, 5)
    # Receiver and fore-end.
    c.rect(56, 50, 172, 78, 7)
    # The long barrel with its muzzle block and an under-rail.
    c.rect(166, 57, 240, 67, 2)
    c.rect(232, 52, 250, 72, 3)
    c.rect(150, 74, 228, 81, 3)
    # Scope on two mounts, its objective toward the victim.
    c.rect(92, 31, 150, 45, 7)
    c.ellipse(152, 38, 6, 9)
    c.rect(102, 43, 110, 52)
    c.rect(132, 43, 140, 52)
    # Grip.
    c.add([(96, 76), (114, 76), (108, 104), (92, 104)])
    # Vents along the receiver.
    for x in (70, 78, 86):
        c.rect(x, 56, x + 3, 70, 1.5, cut=True)


def crawler(c: Icon):
    # Prey's living grenade: a segmented body on four bent legs.
    for side in (1, -1):
        def m(path):
            return path if side == 1 else mirrored(path, 128)
        c.stroke(m(bezier((104, 62), (84, 38), (60, 36), (50, 54), 16)), 15, 12, caps=True)
        c.stroke(m(bezier((50, 54), (42, 70), (38, 88), (34, 108), 16)), 12, 7, caps=True)
        c.stroke(m(bezier((112, 72), (98, 64), (86, 72), (82, 84), 12)), 13, 10, caps=True)
        c.stroke(m(bezier((82, 84), (78, 94), (77, 102), (76, 110), 12)), 10, 6, caps=True)
    c.ellipse(128, 62, 34, 19)
    c.rect(121, 34, 135, 50, 4)
    c.ellipse(128, 32, 10, 9)
    for x in (113, 141):
        c.rect(x - 1.5, 46, x + 1.5, 78, 1.5, cut=True)


def autocannon(c: Icon):
    # A heavy body with a ridge of spines, twin barrels to the front.
    c.rect(38, 42, 182, 94, 15)
    for x0, peak, x1 in ((64, (78, 20), 90), (92, (108, 16), 120), (122, (136, 24), 146)):
        c.add([(x0, 46), peak, (x1, 46)])
    c.rect(170, 46, 244, 67, 6)
    c.rect(170, 70, 244, 91, 6)
    c.rect(234, 43, 250, 70, 4)
    c.rect(234, 67, 250, 94, 4)
    c.rect(166, 67, 250, 70, cut=True)
    c.ellipse(243, 56.5, 3, 5, cut=True)
    c.ellipse(243, 80.5, 3, 5, cut=True)
    # Ribs and grip.
    for x in (146, 155):
        c.rect(x, 50, x + 3, 86, 1.5, cut=True)
    c.add([(62, 92), (82, 92), (76, 114), (56, 114)])
    c.ellipse(40, 68, 12, 22)


def acidsprayer(c: Icon):
    # The pocked tank, a flared nozzle, and the hose-hook at the back.
    c.rect(70, 38, 192, 86, 22)
    for x in (92, 110, 128, 146, 164):
        for y in (52, 70):
            c.ellipse(x + (9 if y == 70 else 0), y, 3.2, 3.2, cut=True)
    c.add([(188, 51), (228, 56), (244, 49), (250, 52), (250, 72), (244, 75), (228, 68), (188, 73)])
    c.stroke(bezier((74, 62), (44, 60), (24, 74), (26, 100), 24), 13, 9, caps=False)
    c.stroke(bezier((26, 100), (27, 110), (34, 114), (42, 111), 10), 9, 5)
    c.add([(112, 84), (130, 84), (124, 108), (108, 108)])


def rocketlauncher(c: Icon):
    # A fat organic tube with a drum under it and a flared maw.
    c.rect(28, 38, 226, 82, 20)
    c.add([(218, 36), (248, 26), (250, 94), (218, 84)])
    c.ellipse(244, 60, 4, 17, cut=True)
    c.ellipse(108, 88, 27, 21)
    c.ellipse(108, 88, 17, 12, cut=True)
    c.ellipse(108, 88, 9, 6)
    c.add([(150, 80), (168, 80), (162, 108), (146, 108)])
    c.ellipse(30, 60, 14, 25)
    for x in (182, 192, 202):
        c.rect(x, 44, x + 3, 76, 1.5, cut=True)


def leechgun(c: Icon):
    # Three canisters over the body, a clawed muzzle, and the arm at the back.
    c.rect(58, 52, 208, 90, 10)
    for x in (82, 114, 146):
        c.rect(x, 20, x + 24, 56, 6)
        c.rect(x, 29, x + 24, 32, cut=True)
    c.add([(204, 57), (240, 63), (250, 71), (240, 79), (204, 85)])
    c.add([(206, 52), (248, 56), (210, 61)])
    c.add([(206, 90), (248, 86), (210, 81)])
    c.stroke(bezier((62, 72), (36, 72), (20, 84), (22, 104), 24), 13, 9, caps=False)
    c.stroke(bezier((22, 104), (23, 112), (30, 116), (38, 113), 10), 9, 5)
    c.add([(108, 88), (126, 88), (120, 112), (104, 112)])


# ------------------------------------------------------------------ glyphs (128x128)

def skull_shape(c: Icon, s: float = 1.0):
    def p(x, y):
        return (64 + (x - 64) * s, 64 + (y - 64) * s)

    def e(cx, cy, rx, ry, cut=False):
        x, y = p(cx, cy)
        c.ellipse(x, y, rx * s, ry * s, cut)

    def r(x0, y0, x1, y1, rad, cut=False):
        a, b = p(x0, y0)
        cc, d = p(x1, y1)
        c.rect(a, b, cc, d, rad * s, cut)

    e(64, 54, 42, 40)
    r(38, 70, 90, 112, 11)
    e(46, 60, 12, 13, cut=True)
    e(82, 60, 12, 13, cut=True)
    c.cut([p(64, 74), p(57, 88), p(71, 88)])
    for x in (51, 62.5, 74):
        r(x, 96, x + 3.5, 114, 1.5, cut=True)
    e(28, 84, 7, 10, cut=True)
    e(100, 84, 7, 10, cut=True)


def skull(c: Icon):
    skull_shape(c)


def telefrag(c: Icon):
    # A portal standing open, shattering what it arrived on: an upright oval
    # ring with shards thrown from both sides.
    c.ellipse(64, 64, 30, 50)
    c.ellipse(64, 64, 19, 39, cut=True)
    c.ellipse(64, 64, 9, 20)
    for side in (1, -1):
        for a, length in ((-38, 26), (0, 30), (38, 26)):
            t = math.radians(a)
            bx = 64 + side * 34
            by = 64 + math.sin(t) * 40
            dx, dy = side * math.cos(t), math.sin(t)
            nx, ny = -dy, dx
            c.add([(bx + nx * 5, by + ny * 5), (bx + dx * length, by + dy * length), (bx - nx * 5, by - ny * 5)])


def generic(c: Icon):
    # An impact: a kill by something with no icon of its own.
    pts = []
    for i in range(20):
        a = math.radians(i * 18 - 90)
        r = 60 if i % 2 == 0 else (30 if i % 4 == 1 else 36)
        pts.append((64 + math.cos(a) * r, 64 + math.sin(a) * r))
    c.add(pts)
    c.ellipse(64, 64, 13, 13, cut=True)


# ------------------------------------------------------------------ badges (64x64)

def scope(c: Icon):
    c.ring(32, 32, 24, 17)
    for a in (0, 90, 180, 270):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        c.stroke([(32 + ca * 8, 32 + sa * 8), (32 + ca * 29, 32 + sa * 29)], 5.5, caps=False)
    c.ellipse(32, 32, 3.5, 3.5)


def mine(c: Icon):
    c.ellipse(32, 34, 10, 10)
    for side in (0, 180):
        for ro, ri in ((19, 14.5), (28, 23.5)):
            pts = ellipse_pts(32, 34, ro, ro, 24, side - 42, side + 42)
            pts += ellipse_pts(32, 34, ri, ri, 24, side + 42, side - 42)
            c.add(pts)


def grenade(c: Icon):
    c.ellipse(30, 38, 19, 21)
    c.rect(22, 10, 38, 20, 2)
    c.stroke([(38, 13), (50, 20), (52, 34)], 5.5)
    c.rect(18, 36, 42, 39, cut=True)


def plasma(c: Icon):
    c.ring(32, 32, 27, 21)
    c.ellipse(32, 32, 14, 14)


def bolt(c: Icon):
    c.add([(38, 3), (14, 35), (29, 35), (22, 61), (50, 24), (35, 24), (44, 3)])


def sun(c: Icon):
    c.ellipse(32, 32, 12, 12)
    for i in range(8):
        a = math.radians(i * 45)
        side = math.radians(13)
        c.add([(32 + math.cos(a - side) * 16, 32 + math.sin(a - side) * 16),
               (32 + math.cos(a) * 30, 32 + math.sin(a) * 30),
               (32 + math.cos(a + side) * 16, 32 + math.sin(a + side) * 16)])


# name: (draw, width, height); the badge skull is the glyph's drawing at half size
ICONS = {
    "wrench": (wrench, 256, 128),
    "bow": (bow, 256, 128),
    "rifle": (rifle, 256, 128),
    "crawler": (crawler, 256, 128),
    "autocannon": (autocannon, 256, 128),
    "acidsprayer": (acidsprayer, 256, 128),
    "rocketlauncher": (rocketlauncher, 256, 128),
    "leechgun": (leechgun, 256, 128),
    "skull": (skull, 128, 128),
    "telefrag": (telefrag, 128, 128),
    "generic": (generic, 128, 128),
    "scope": (scope, 64, 64),
    "mine": (mine, 64, 64),
    "grenade": (grenade, 64, 64),
    "plasma": (plasma, 64, 64),
    "bolt": (bolt, 64, 64),
    "sun": (sun, 64, 64),
    "skull_badge": (None, 64, 64),
}


def textures() -> dict[str, object]:
    result = {}
    for name, (draw, w, h) in ICONS.items():
        if name == "skull_badge":
            # The skull drawn on a 128 frame at half size, then cut to 64.
            canvas = Icon(128, 128)
            skull_shape(canvas, 0.5)
            canvas.image = canvas.image.crop((32 * SS, 32 * SS, 96 * SS, 96 * SS))
            canvas.w, canvas.h = 64, 64
        else:
            canvas = Icon(w, h)
            draw(canvas)
        result[f"{name}.tga"] = canvas.finish()
    return result


def material_text() -> str:
    lines = [
        "// The multiplayer obituary feed's icons (guis/obituaries.gui, src/ui/ObituaryWindow.h),",
        "// written by tools/ui/obituary_icons.py; idMultiplayerGame::PushObituary picks them.",
        "// White silhouettes on a dark keyline, tinted by the feed through `colored`.",
        "",
    ]
    for name in ICONS:
        lines += [
            f"{MATERIAL_PREFIX}/{name} {{",
            "\tnoshadows",
            "\tsort gui",
            "\t{",
            "\t\tblend blend",
            f"\t\tmap {MATERIAL_PREFIX}/{name}.tga",
            "\t\tclamp",
            "\t\tnopicmip",
            "\t\thighquality",
            "\t\tcolored",
            "\t}",
            "}",
            "",
        ]
    return "\n".join(lines)


def preview(path: Path, icons: dict) -> None:
    """A contact sheet: each icon large on the feed's well, then at feed size on a line."""
    from PIL import Image, ImageDraw
    ink = (160, 178, 202)
    well = (28, 36, 45)
    cell_w, cell_h = 272, 150
    cols = 4
    items = list(icons.items())
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (14, 18, 22, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (name, image) in enumerate(items):
        x, y = (i % cols) * cell_w, (i // cols) * cell_h
        draw.rectangle((x + 4, y + 4, x + cell_w - 4, y + cell_h - 18), fill=well + (255,))
        tinted = Image.new("RGBA", image.size, ink + (255,))
        r, g, b, a = image.split()
        tint = Image.merge("RGBA", (
            r.point(lambda v: v * ink[0] // 255), g.point(lambda v: v * ink[1] // 255),
            b.point(lambda v: v * ink[2] // 255), a))
        scale = min(1.0, 120 / image.size[1])
        big = tint.resize((int(image.size[0] * scale), int(image.size[1] * scale)), Image.LANCZOS)
        sheet.alpha_composite(big, (x + 8, y + 8))
        # at feed size: 13 units high at 1080p is about 29 pixels
        small_h = 29
        small = tint.resize((max(1, image.size[0] * small_h // image.size[1]), small_h), Image.LANCZOS)
        sheet.alpha_composite(small, (x + cell_w - small.size[0] - 10, y + cell_h - 18 - small_h - 6))
        draw.text((x + 6, y + cell_h - 16), name, fill=(200, 210, 220, 255))
    sheet.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if any icon or the material file is stale")
    parser.add_argument("--preview", type=Path, help="write a contact sheet of the icons to this PNG and nothing else")
    args = parser.parse_args()
    from PIL import Image, ImageChops
    icons = textures()
    if args.preview:
        preview(args.preview, icons)
        return 0
    stale = 0
    for name, image in icons.items():
        path = TEXTURES / name
        if args.check:
            if not path.exists():
                print(f"missing: {path.relative_to(ROOT).as_posix()}")
                stale += 1
                continue
            with Image.open(path) as current:
                current = current.convert("RGBA")
                if current.size != image.size or ImageChops.difference(current, image).getbbox():
                    print(f"stale: {path.relative_to(ROOT).as_posix()}")
                    stale += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    text = material_text()
    if args.check:
        if not MATERIALS.exists() or MATERIALS.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            print(f"stale: {MATERIALS.relative_to(ROOT).as_posix()}")
            stale += 1
    else:
        MATERIALS.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {MATERIALS.relative_to(ROOT).as_posix()}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
