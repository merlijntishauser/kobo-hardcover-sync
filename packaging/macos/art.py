"""Draws the Mac app's pictures as SVG, in the page's Galley Proof (DESIGN.md):

- AppIcon.icon: the app's icon from macOS 26 on, for Icon Composer and actool. The
  system draws the outline, the fill and the glass; the two layers are the slip and
  its marks.
- AppIcon.svg: the same icon drawn flat on Apple's grid, for macOS 13 to 15.
- VolumeIcon.svg: the disk image's icon, the slip lying in a galley tray.
- dmg-background.svg: the disk image's window, 640 by 400 points.

    python3 packaging/macos/art.py

writes them beside itself, and the PNGs made from them are kept beside them too: the
icons with rsvg-convert, the window in a browser, which has the page's font
(docs/macos-app.md, "The pictures").
"""

import math
import pathlib
import re

HERE = pathlib.Path(__file__).parent
FONT = "../../src/kobo_hardcover_sync/web/static/fonts/SchibstedGrotesk-latin.woff2"

# DESIGN.md's colours, light.
SHEET, MARGIN, INK, GRAPHITE, FAINT = "#fbfbf8", "#f2f4ef", "#17191c", "#4a4f57", "#5f656e"
RULE, SOFT, EDGE, GROUND = "#cdd1cb", "#e3e6e0", "#80868e", "#edefea"
BLUE, RED, GREEN = "#1c5e8b", "#c0212b", "#2c6a39"
COVERS = ("#2f4653", "#b07a2a", "#5d6f45")  # book cloth: slate, ochre, olive

# The slip is a galley of the list of books, on the 1024 canvas: a row per book with its
# cover, title, author and line gauge, and the proof margin behind its double rule, holding
# the row's mark. It starts at y 150 and runs on past the bottom.
SX, SW, MX = 196, 632, 640  # the slip's left edge, its width, the margin's left edge
ROWS = (150, 420, 690)


def shadow(name, dy, blur, opacity, colour="#000"):
    return (
        f'<filter id="{name}" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="{dy}"'
        f' stdDeviation="{blur}" flood-color="{colour}" flood-opacity="{opacity}"/></filter>'
    )


def gauge(x, y, w, read):
    ticks = "".join(f'<rect x="{x + w * i / 10 - 2:.1f}" y="{y - 12}" width="4" height="12" fill="{EDGE}"/>' for i in range(11))
    return (
        f'<rect x="{x}" y="{y - 2}" width="{w}" height="4" fill="{EDGE}"/>{ticks}'
        f'<rect x="{x}" y="{y - 14}" width="{w * read:.1f}" height="14" fill="{INK}"/>'
    )


def book(y, title, author, read, cover, lift):
    x = SX + 172
    return (
        f'<rect x="{SX + 48}" y="{y}" width="96" height="144" rx="4" fill="{cover}"{lift}/>'
        f'<rect x="{SX + 48}" y="{y}" width="10" height="144" fill="#000" opacity="0.16"/>'  # the spine
        f'<rect x="{x}" y="{y + 8}" width="{title}" height="34" rx="3" fill="{INK}"/>'
        f'<rect x="{x}" y="{y + 62}" width="{author}" height="20" rx="3" fill="{GRAPHITE}"/>' + gauge(x, y + 130, 240, read)
    )


def slip(lifted=True):
    """The sheet and its books. Covers lie on it with a shadow, except in the Icon Composer
    layer, where filters are not drawn."""
    lift = ' filter="url(#book)"' if lifted else ""
    top, h = ROWS[0], 950
    sheet = (
        f'<rect x="{SX}" y="{top}" width="{SW}" height="{h}" fill="{SHEET}"/>'
        f'<rect x="{MX}" y="{top}" width="{SX + SW - MX}" height="{h}" fill="{MARGIN}"/>'
        f'<rect x="{MX - 16}" y="{top}" width="5" height="{h}" fill="{RULE}"/>'
        f'<rect x="{MX - 6}" y="{top}" width="5" height="{h}" fill="{RULE}"/>'
    )
    lines = "".join(f'<rect x="{SX}" y="{y - 2}" width="{SW}" height="4" fill="{SOFT}"/>' for y in ROWS[1:])
    books = (
        book(ROWS[0] + 66, 230, 150, 0.62, COVERS[0], lift)
        + book(ROWS[1] + 66, 190, 120, 1.0, COVERS[1], lift)
        + book(ROWS[2] + 66, 240, 170, 0.3, COVERS[2], lift)
    )
    return sheet + lines + books


def marks():
    """The margin's marks, as in the legend: the red caret (the next sync changes this),
    the tick (up to date) and the dashed caret (nothing to send yet)."""
    stroke = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    y = ROWS[0] + 70
    caret = f'<path d="M{MX + 30} {y + 128} L{MX + 94} {y + 14} L{MX + 158} {y + 128}" {stroke} stroke="{RED}" stroke-width="34"/>'
    y = ROWS[1] + 96
    tick = f'<path d="M{MX + 44} {y + 40} L{MX + 82} {y + 78} L{MX + 150} {y + 4}" {stroke} stroke="{GREEN}" stroke-width="26"/>'
    y = ROWS[2] + 88
    dashed = (
        f'<path d="M{MX + 44} {y + 84} L{MX + 94} {y} L{MX + 144} {y + 84}" {stroke} stroke="{FAINT}"'
        ' stroke-width="14" stroke-dasharray="26 22"/>'
    )
    return caret + tick + dashed


def svg(body, defs="", size=1024):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f"<defs>{defs}</defs>{body}</svg>\n"
    )


def squircle(x, y, s, n=5.0, steps=256):
    """Apple's icon outline, near enough: a superellipse filling the square at x, y."""
    r = s / 2
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, d = math.cos(t), math.sin(t)
        pts.append((x + r + r * math.copysign(abs(c) ** (2 / n), c), y + r + r * math.copysign(abs(d) ** (2 / n), d)))
    return "M" + " L".join(f"{a:.2f} {b:.2f}" for a, b in pts) + " Z"


def icon_composer():
    """The .icon bundle: the slip below, its marks above in glass, on the non-repro blue."""
    folder = HERE / "AppIcon.icon"
    (folder / "Assets").mkdir(parents=True, exist_ok=True)
    (folder / "Assets" / "slip.svg").write_text(svg(slip(lifted=False)))
    (folder / "Assets" / "marks.svg").write_text(svg(marks()))
    (folder / "icon.json").write_text(
        """{
  "fill" : {
    "solid" : "srgb:0.76471,0.88627,0.93725,1.00000"
  },
  "groups" : [
    {
      "layers" : [
        {
          "glass" : true,
          "image-name" : "marks.svg",
          "name" : "marks"
        }
      ],
      "name" : "marks",
      "shadow" : {
        "kind" : "layer-color",
        "opacity" : 0.5
      },
      "specular" : true
    },
    {
      "layers" : [
        {
          "glass" : false,
          "image-name" : "slip.svg",
          "name" : "slip"
        }
      ],
      "name" : "slip",
      "shadow" : {
        "kind" : "neutral",
        "opacity" : 0.5
      },
      "specular" : false
    }
  ],
  "supported-platforms" : {
    "squares" : [
      "macOS"
    ]
  }
}
"""
    )


def flat_icon():
    """For macOS 13 to 15: the outline is drawn here, an 824 square with 100 around it."""
    shape = squircle(100, 100, 824)
    defs = (
        f'<clipPath id="tile"><path d="{shape}"/></clipPath>'
        + shadow("book", 3, 4, 0.25)
        + shadow("lift", 10, 10, 0.28)
        + shadow("slip", 6, 12, 0.30, "#14222b")
        + '<linearGradient id="rail" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cfe9f4"/>'
        '<stop offset="1" stop-color="#b6d9e8"/></linearGradient>'
    )
    body = (
        f'<g filter="url(#lift)"><path d="{shape}" fill="url(#rail)"/></g>'
        f'<g clip-path="url(#tile)"><g transform="translate(100 100) scale({824 / 1024})">'
        f'<g filter="url(#slip)">{slip()}</g>{marks()}</g></g>'
    )
    return svg(body, defs)


def volume_icon():
    """The slip lying in a galley tray: the shallow steel tray set type is kept in, walled on
    three sides and open at the right."""
    defs = (
        shadow("book", 3, 4, 0.25)
        + shadow("drop", 16, 16, 0.32)
        + shadow("lie", 8, 10, 0.38, "#14222b")
        + '<linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b3b9bf"/>'
        '<stop offset="1" stop-color="#cfd4d8"/></linearGradient>'
        '<linearGradient id="rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9aa1a8"/>'
        '<stop offset="1" stop-color="#6b727a"/></linearGradient>'
        f'<clipPath id="two"><rect x="{SX}" y="{ROWS[0]}" width="{SW}" height="540"/></clipPath>'
    )
    body = (
        '<g filter="url(#drop)">'
        '<path d="M116 330 h792 v420 h-792 z" fill="#4f565e"/>'  # the front edge: the tray's depth
        '<path d="M116 316 h792 v420 h-792 z" fill="url(#rim)"/>'  # the walls, from above
        '<path d="M142 340 h766 v372 h-766 z" fill="url(#floor)"/>'  # the floor, open at the right
        '<path d="M142 340 h766 v18 h-766 z" fill="#8c939a"/>'  # the back wall's inner face, in shade
        '<path d="M142 340 h16 v372 h-16 z" fill="#959ca3"/>'  # the left wall's
        "</g>"
        f'<g transform="translate(176 296) rotate(-6) scale(0.66)"><g filter="url(#lie)" clip-path="url(#two)">'
        f"{slip()}{marks()}</g></g>"
    )
    return svg(body, defs)


def move_mark():
    """The proofreader's mark that moves a thing: a loop round it, drawn as a hand would,
    a little uneven and left open, and a line from it to where it goes. Round the app at
    170, 218 (with its name under it), to Applications at 470, 200."""
    cx, cy, rx, ry = 170, 218, 94, 116
    pts = []
    for i in range(0, 309, 7):  # from below the right, round the bottom, the left and the top
        t = math.radians(28 + i)
        wobble = 1 + 0.018 * math.sin(2 * t + 0.9) + 0.008 * math.sin(5 * t)
        pts.append((cx + rx * wobble * math.cos(t), cy + ry * wobble * math.sin(t)))
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(1, len(pts)):  # through every point, smoothly (Catmull-Rom as cubic Béziers)
        a, b = pts[i - 1], pts[i]
        z, c = pts[max(i - 2, 0)], pts[min(i + 1, len(pts) - 1)]
        d += (
            f" C{a[0] + (b[0] - z[0]) / 6:.1f} {a[1] + (b[1] - z[1]) / 6:.1f}"
            f" {b[0] - (c[0] - a[0]) / 6:.1f} {b[1] - (c[1] - a[1]) / 6:.1f} {b[0]:.1f} {b[1]:.1f}"
        )
    ex, ey = pts[-1]
    d += f" C{ex + 22:.1f} {ey + 36:.1f} 318 200 392 200"
    return (
        f'<g fill="none" stroke="{BLUE}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{d}"/><path d="M378 189 L394 200 L377 210"/></g>'
    )


def window(icon):
    """The disk's window: the app icon printed in non-repro blue, the blue a camera does not
    see, so that it stays behind Finder's icons and names; one sentence; the move mark."""
    icon = re.sub(
        r"<svg [^>]*>", '<svg x="80" y="-6" width="480" height="480" viewBox="0 0 1024 1024" filter="url(#nonrepro)">', icon, count=1
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400" width="640" height="400">
<defs>
<style>
@font-face {{ font-family: "Schibsted Grotesk"; src: url("{FONT}") format("woff2"); font-weight: 400 900; }}
text {{ font-family: "Schibsted Grotesk"; }}
</style>
<filter id="nonrepro" color-interpolation-filters="sRGB">
<feColorMatrix type="saturate" values="0"/>
<feComponentTransfer>
<feFuncR type="table" tableValues="0.70 0.962"/><feFuncG type="table" tableValues="0.835 0.977"/><feFuncB type="table" tableValues="0.885 0.983"/>
</feComponentTransfer>
</filter>
</defs>
<rect width="640" height="400" fill="{GROUND}"/>
{icon}<text x="320" y="54" text-anchor="middle" font-size="19" font-weight="750" letter-spacing="-0.25" fill="{INK}">Drag Kobo Hardcover Sync onto Applications.</text>
{move_mark()}
<text x="320" y="380" text-anchor="middle" font-size="11.5" fill="{GRAPHITE}">Independent: not affiliated with Rakuten Kobo or Hardcover.</text>
</svg>
"""


def mark(d, colour, width):
    return f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def small_icon(size):
    """The flat icon at 16 and 32 pixels, drawn on their own pixel grid rather than shrunk:
    fewer books, no type, and the red caret as large as the margin allows."""
    if size == 32:
        tile, slip_, rule, books = (
            squircle(3, 3, 26, steps=128),
            (6, 8, 20),
            18,
            [(10, COVERS[0], 5, 3), (20, COVERS[1], 4, 3), (30, COVERS[2], 5, 3)],
        )
        caret, tick = mark("M20 15 L22.5 10.5 L25 15", RED, 1.6), mark("M20.3 22.3 L21.8 23.8 L24.6 20.4", GREEN, 1.4)
        type_ = "".join(
            f'<rect x="12" y="{y}" width="{w}" height="2" fill="{INK}"/><rect x="12" y="{y + 3}" width="3" height="1" fill="{GRAPHITE}"/>'
            for y, _, w, _ in books
        )
        soft = f'<rect x="6" y="18" width="20" height="1" fill="{SOFT}"/><rect x="6" y="28" width="20" height="1" fill="{SOFT}"/>'
    else:
        tile, slip_, rule, books = squircle(1, 1, 14, steps=96), (3, 5, 10), 7, [(6, COVERS[0], 0, 2), (12, COVERS[1], 0, 2)]
        caret, tick = mark("M8.8 10.2 L10.5 6.6 L12.2 10.2", RED, 1.3), mark("M8.9 14 L10 15.1 L12.3 12.6", GREEN, 1.1)
        type_ = ""
        soft = f'<rect x="3" y="11" width="10" height="0.75" fill="{SOFT}"/>'
    x, y, w = slip_
    covers = "".join(
        f'<rect x="{x + 2 - (size == 16)}" y="{top}" width="{cw}" height="{cw * 5 // 3 + (size == 16)}" fill="{c}"/>'
        for top, c, _, cw in books
    )
    defs = (
        f'<clipPath id="tile"><path d="{tile}"/></clipPath>'
        '<linearGradient id="rail" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cfe9f4"/>'
        '<stop offset="1" stop-color="#b3d7e7"/></linearGradient>'
    )
    body = (
        f'<path d="{tile}" fill="url(#rail)"/><g clip-path="url(#tile)">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{size}" fill="{SHEET}"/>'
        f'<rect x="{rule + 1}" y="{y}" width="{x + w - rule - 1}" height="{size}" fill="{MARGIN}"/>'
        f'<rect x="{rule}" y="{y}" width="1" height="{size}" fill="{RULE}"/>'
        f"{soft}{covers}{type_}{caret}{tick}</g>"
    )
    return svg(body, defs, size)


def small_volume(size):
    """The disk's icon at 16 and 32 pixels: the tray as a plain shape, the slip standing
    up out of it, square to the grid, with one or two books and the red caret."""
    if size == 32:
        tray = (2, 13, 28, 13, 2)  # x, y, width, height, wall
        slip_, rule, books = (9, 5, 16, 19), 18, [(7, COVERS[0]), (15, COVERS[1])]
        marks_ = mark("M19.8 12.4 L21.8 8.6 L23.8 12.4", RED, 1.5) + mark("M19.9 18.4 L21.1 19.6 L23.5 16.8", GREEN, 1.3)
        type_ = "".join(f'<rect x="15" y="{top}" width="2" height="2" fill="{INK}"/>' for top, _ in books)
        cover = 3, 5
    else:
        tray = (1, 7, 14, 6, 1)
        slip_, rule, books = (4, 2, 9, 9), 8, [(3, COVERS[0])]
        marks_ = mark("M9.3 7.4 L10.8 4.4 L12.3 7.4", RED, 1.2)
        type_ = ""
        cover = 2, 4
    tx, ty, tw, th, wall = tray
    x, y, w, h = slip_
    body = (
        f'<rect x="{tx}" y="{ty + 1}" width="{tw}" height="{th}" rx="1" fill="#4f565e"/>'  # the front edge
        f'<rect x="{tx}" y="{ty}" width="{tw}" height="{th}" rx="1" fill="#7c838b"/>'  # the walls
        f'<rect x="{tx + wall}" y="{ty + wall}" width="{tw - wall}" height="{th - 2 * wall}" fill="#c4c9ce"/>'  # the floor
        f'<rect x="{x}" y="{y + 1}" width="{w}" height="{h}" fill="#000" opacity="0.18"/>'  # the slip's shadow
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{SHEET}"/>'
        f'<rect x="{rule + 1}" y="{y}" width="{x + w - rule - 1}" height="{h}" fill="{MARGIN}"/>'
        f'<rect x="{rule}" y="{y}" width="1" height="{h}" fill="{RULE}"/>'
        + "".join(f'<rect x="{x + 1 + (size == 32)}" y="{top}" width="{cover[0]}" height="{cover[1]}" fill="{c}"/>' for top, c in books)
        + type_
        + marks_
    )
    return svg(body, size=size)


if __name__ == "__main__":
    icon_composer()
    flat = flat_icon()
    (HERE / "AppIcon.svg").write_text(flat)
    (HERE / "VolumeIcon.svg").write_text(volume_icon())
    (HERE / "dmg-background.svg").write_text(window(flat))
    for size in (16, 32):
        (HERE / f"AppIcon-{size}.svg").write_text(small_icon(size))
        (HERE / f"VolumeIcon-{size}.svg").write_text(small_volume(size))
