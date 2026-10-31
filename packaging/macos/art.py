"""Draws the Mac app's pictures as SVG (docs/macos-app.md, "The pictures"):

- AppIcon.icon: the app's icon from macOS 26 on, for Icon Composer and actool. The
  system draws the outline, the fill (a blue-to-navy gradient) and the glass; the two
  layers are the e-reader and the sync mark on its screen, drawn flat: macOS lights them.
- AppIcon.svg: the same icon drawn on Apple's grid with its own light, for macOS 13 to 15.
- VolumeIcon.svg: the disk image's icon, the e-reader in its sleeve.
- dmg-background.svg: the disk image's window, 640 by 400 points.

    python3 packaging/macos/art.py

writes them beside itself, and the PNGs made from them are kept beside them too: the
icons with rsvg-convert, the window in a browser, which has the page's font.

The icon: the Kobo itself, a page of text on its e-ink screen and under it, in the blue
pencil, the two-way sync: what the Kobo read goes to the shelf, what changed on the shelf
comes back. One device, one mark; the red stays for what a sync sends, in the window.
"""

import math
import pathlib
import re

HERE = pathlib.Path(__file__).parent
FONT = "../../src/lastread/web/static/fonts/SchibstedGrotesk-latin.woff2"

# DESIGN.md's colours, light.
INK, GRAPHITE, GROUND = "#17191c", "#4a4f57", "#edefea"
BLUE = "#1c5e8b"
# The icon's own: the tile from the rail's blue down to navy, the device's body, e-ink.
TILE_TOP, TILE_BOTTOM = "#2a5c84", "#10212f"
BODY, BODY_TOP, BODY_BOTTOM = "#3a4049", "#4a515b", "#2b3038"
EINK, EINK_TOP, EINK_BOTTOM = "#ece9df", "#f0ede3", "#e3dfd2"
TEXT = "#6b7079"  # the page's lines, as e-ink prints them
SLEEVE_TOP, SLEEVE_BOTTOM = "#46606f", "#1c2a33"

# The device on the 1024 canvas, which is the tile itself (flat_icon scales it onto
# Apple's grid): its body, its screen, the lines of the page and the two arrows.
DEVICE = (200, 52, 624, 920, 70)  # x, y, width, height, corner
SCREEN = (256, 124, 512, 696, 16)
LINES = ((214, 710), (282, 710), (350, 710), (418, 572))  # y, right end; all from x 314
ARROWS = (596, 712)  # the one that goes, the one that comes back


def shadow(name, dy, blur, opacity, colour="#000"):
    return (
        f'<filter id="{name}" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="{dy}"'
        f' stdDeviation="{blur}" flood-color="{colour}" flood-opacity="{opacity}"/></filter>'
    )


def gradient(name, top, bottom):
    return (
        f'<linearGradient id="{name}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
        f'<stop offset="1" stop-color="{bottom}"/></linearGradient>'
    )


def rounded(box, fill, extra=""):
    x, y, w, h, r = box
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{extra}/>'


def mark(d, colour, width):
    return f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def reader(lit=True, lines=LINES, screen=SCREEN):
    """The e-reader: its body, its e-ink screen and the lines of the page on it. Lit: with
    the gradients and the hairline edge of the flat icon; flat for an Icon Composer layer,
    which macOS lights itself."""
    body = rounded(DEVICE, "url(#body)" if lit else BODY)
    edge = rounded(DEVICE, "none", ' stroke="#fff" stroke-opacity="0.08" stroke-width="7"') if lit else ""
    page = rounded(screen, "url(#eink)" if lit else EINK)
    text = mark("".join(f"M314 {y}H{right}" for y, right in lines), TEXT, 20)
    return body + edge + page + text


def sync(arrows=ARROWS, x=(338, 686), head=60, width=48):
    """The two-way sync on the page, in the blue pencil: an arrow that goes, one that comes back."""
    go, back = arrows
    left, right = x
    d = (
        f"M{left} {go}H{right}M{right - head} {go - head}L{right} {go}L{right - head} {go + head}"
        f"M{right} {back}H{left}M{left + head} {back - head}L{left} {back}L{left + head} {back + head}"
    )
    return mark(d, BLUE, width)


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


def srgb(hex_colour):
    """A colour as Icon Composer writes it."""
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return f"srgb:{r:.5f},{g:.5f},{b:.5f},1.00000"


def icon_composer():
    """The .icon bundle: the fill a gradient from the rail's blue down to navy, the
    e-reader below, the sync mark above it in glass."""
    folder = HERE / "AppIcon.icon"
    (folder / "Assets").mkdir(parents=True, exist_ok=True)
    (folder / "Assets" / "reader.svg").write_text(svg(reader(lit=False)))
    (folder / "Assets" / "sync.svg").write_text(svg(sync()))
    (folder / "icon.json").write_text(
        f"""{{
  "fill" : {{
    "linear-gradient" : [
      "{srgb(TILE_BOTTOM)}",
      "{srgb(TILE_TOP)}"
    ],
    "orientation" : {{
      "start" : {{
        "x" : 0.5,
        "y" : 1
      }},
      "stop" : {{
        "x" : 0.5,
        "y" : 0
      }}
    }}
  }},
  "groups" : [
    {{
      "layers" : [
        {{
          "glass" : true,
          "image-name" : "sync.svg",
          "name" : "sync"
        }}
      ],
      "name" : "sync",
      "shadow" : {{
        "kind" : "layer-color",
        "opacity" : 0.5
      }},
      "specular" : true
    }},
    {{
      "layers" : [
        {{
          "glass" : false,
          "image-name" : "reader.svg",
          "name" : "reader"
        }}
      ],
      "name" : "reader",
      "shadow" : {{
        "kind" : "neutral",
        "opacity" : 0.5
      }},
      "specular" : false
    }}
  ],
  "supported-platforms" : {{
    "squares" : [
      "macOS"
    ]
  }}
}}
"""
    )


def flat_icon():
    """For macOS 13 to 15: the outline is drawn here, an 824 square with 100 around it,
    lit from above as macOS lights its icons."""
    shape = squircle(100, 100, 824)
    defs = (
        f'<clipPath id="tile"><path d="{shape}"/></clipPath>'
        + shadow("lift", 10, 10, 0.28)
        + shadow("device", 14, 16, 0.45, "#06111a")
        + gradient("ground", TILE_TOP, TILE_BOTTOM)
        + gradient("body", BODY_TOP, BODY_BOTTOM)
        + gradient("eink", EINK_TOP, EINK_BOTTOM)
    )
    body = (
        f'<g filter="url(#lift)"><path d="{shape}" fill="url(#ground)"/></g>'
        f'<g clip-path="url(#tile)"><g transform="translate(100 100) scale({824 / 1024})">'
        f'<g filter="url(#device)">{reader()}</g>{sync()}</g></g>'
    )
    return svg(body, defs)


def volume_icon():
    """The e-reader in its sleeve: the device standing half out of a slate cloth pouch,
    so the disk and the app tell apart on the desktop. The page shows two lines and the
    sync mark above the sleeve's edge."""
    defs = (
        shadow("drop", 16, 16, 0.32)
        + shadow("stand", 10, 12, 0.40, "#06111a")
        + gradient("body", BODY_TOP, BODY_BOTTOM)
        + gradient("eink", EINK_TOP, EINK_BOTTOM)
        + gradient("sleeve", SLEEVE_TOP, SLEEVE_BOTTOM)
    )
    lines = ((200, 710), (266, 572))
    body = (
        f'<g transform="translate(0 -12)"><g filter="url(#stand)">{reader(lines=lines)}</g>{sync(arrows=(340, 436), width=44)}</g>'
        '<g filter="url(#drop)">'
        '<rect x="150" y="492" width="724" height="500" rx="48" fill="url(#sleeve)"/>'  # the pouch
        '<rect x="150" y="492" width="724" height="34" rx="17" fill="#5a7383"/>'  # its hem, catching the light
        "</g>"
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
<feFuncR type="table" tableValues="0.78 0.962"/><feFuncG type="table" tableValues="0.875 0.977"/><feFuncB type="table" tableValues="0.91 0.983"/>
</feComponentTransfer>
</filter>
</defs>
<rect width="640" height="400" fill="{GROUND}"/>
{icon}<text x="320" y="54" text-anchor="middle" font-size="19" font-weight="750" letter-spacing="-0.25" fill="{INK}">Drag Lastread onto Applications.</text>
{move_mark()}
<text x="320" y="380" text-anchor="middle" font-size="11.5" fill="{GRAPHITE}">Independent: not affiliated with Rakuten Kobo or Hardcover.</text>
</svg>
"""


def small_icon(size):
    """The flat icon at 16 and 32 pixels, drawn on their own pixel grid rather than shrunk:
    the device, its screen, two or three lines and the two arrows as whole pixels."""
    if size == 32:
        tile = squircle(3, 3, 26, steps=128)
        body, screen = (8, 5, 16, 23, 3), (10, 7, 12, 17, 1)
        lines = "".join(f'<rect x="12" y="{y}" width="{w}" height="1" fill="{TEXT}"/>' for y, w in ((9, 8), (11, 8), (13, 6)))
        arrows = mark("M13 17.5H19M17.5 16L19 17.5L17.5 19", BLUE, 1.2) + mark("M19 21.5H13M14.5 20L13 21.5L14.5 23", BLUE, 1.2)
    else:
        tile = squircle(1, 1, 14, steps=96)
        body, screen = (4, 2, 8, 12, 1.5), (5, 3, 6, 9, 0.5)
        lines = "".join(f'<rect x="6" y="{y}" width="{w}" height="1" fill="{TEXT}"/>' for y, w in ((4, 4), (6, 3)))
        arrows = mark("M6 8.5H10M9 7.5L10 8.5", BLUE, 1) + mark("M10 10.5H6M7 11.5L6 10.5", BLUE, 1)
    defs = f'<clipPath id="tile"><path d="{tile}"/></clipPath>' + gradient("ground", TILE_TOP, TILE_BOTTOM)
    return svg(
        f'<path d="{tile}" fill="url(#ground)"/><g clip-path="url(#tile)">{rounded(body, BODY)}{rounded(screen, EINK)}{lines}{arrows}</g>',
        defs,
        size,
    )


def small_volume(size):
    """The disk's icon at 16 and 32 pixels: the device standing out of its sleeve, square
    to the grid, with a line or two and the arrow that goes."""
    if size == 32:
        body, screen, sleeve = (9, 2, 14, 20, 2), (11, 4, 10, 12, 1), (4, 14, 24, 16, 2)
        lines = f'<rect x="13" y="6" width="6" height="1" fill="{TEXT}"/><rect x="13" y="8" width="5" height="1" fill="{TEXT}"/>'
        arrows = mark("M13 11.5H19M17.5 10L19 11.5L17.5 13", BLUE, 1.2)
    else:
        body, screen, sleeve = (5, 1, 6, 10, 1), (6, 2, 4, 5, 0.5), (2, 8, 12, 7, 1)
        lines = f'<rect x="7" y="3" width="2" height="1" fill="{TEXT}"/>'
        arrows = mark("M7 5.5H9", BLUE, 1)
    defs = gradient("sleeve", SLEEVE_TOP, SLEEVE_BOTTOM)
    x, y, w, h, r = sleeve
    return svg(
        rounded(body, BODY)
        + rounded(screen, EINK)
        + lines
        + arrows
        + f'<rect x="{x}" y="{y + 1}" width="{w}" height="{h}" rx="{r}" fill="#000" opacity="0.25"/>'  # the sleeve's shadow on the device
        + rounded(sleeve, "url(#sleeve)"),
        defs,
        size,
    )


if __name__ == "__main__":
    icon_composer()
    flat = flat_icon()
    (HERE / "AppIcon.svg").write_text(flat)
    (HERE / "VolumeIcon.svg").write_text(volume_icon())
    (HERE / "dmg-background.svg").write_text(window(flat))
    for size in (16, 32):
        (HERE / f"AppIcon-{size}.svg").write_text(small_icon(size))
        (HERE / f"VolumeIcon-{size}.svg").write_text(small_volume(size))
