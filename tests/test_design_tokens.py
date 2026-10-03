"""The colours the page is built from, held to WCAG 2.2 AA (the bar in
PRODUCT.md): words at 4.5:1, the edge of a field and every mark at 3:1.
Read from the stylesheet, so a changed token is checked without a browser."""

import pathlib
import re

CSS = (pathlib.Path(__file__).resolve().parents[1] / "src" / "kobo_hardcover_sync" / "web" / "static" / "kobo.css").read_text()


def tokens(block: str) -> dict:
    return dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", block))


DAY = tokens(CSS[CSS.index(":root {") : CSS.index("@media (prefers-color-scheme: dark)")])
NIGHT_AUTO = tokens(CSS[CSS.index("@media (prefers-color-scheme: dark)") : CSS.index(':root[data-theme="dark"]')])
NIGHT_CHOSEN = tokens(CSS[CSS.index(':root[data-theme="dark"]') : CSS.index("* { box-sizing")])
GROUNDS = ("sheet", "margin", "ground")  # the sheet, the Hardcover column's tint, the page


def luminance(colour: str) -> float:
    r, g, b = (int(colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return sum(
        w * (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for w, c in zip((0.2126, 0.7152, 0.0722), (r, g, b), strict=True)
    )


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_night_colours_are_the_same_whether_the_system_or_the_reader_chose_them():
    assert NIGHT_AUTO == NIGHT_CHOSEN and len(NIGHT_AUTO) > 15  # written out twice in the stylesheet: this keeps them one
    assert set(NIGHT_AUTO) == set(DAY) - {"serif", "sans", "mono", "r-sheet", "r-ctl", "rail-w"}  # every colour has a day and a night value


def test_words_can_be_read_on_every_surface_they_stand_on():
    for name, theme in (("day", DAY), ("night", NIGHT_AUTO)):
        for word in ("ink", "graphite", "faint", "blue", "red", "green"):
            for ground in GROUNDS:
                assert contrast(theme[word], theme[ground]) >= 4.5, (
                    f"{name}: --{word} on --{ground} is {contrast(theme[word], theme[ground]):.2f}"
                )
        for word in ("rail-ink", "rail-graphite"):  # the rail: the name, the navigation, the sync status
            assert contrast(theme[word], theme["rail"]) >= 4.5, f"{name}: --{word} on the rail"
        # The words on a filled control: red for what sends (Sync now, Go live), blue for a choice, ink for the rest.
        assert contrast(theme["on-fill"], theme["red"]) >= 4.5, name
        assert contrast(theme["on-fill"], theme["blue"]) >= 4.5, name
        assert contrast(theme["on-flag"], theme["flag"]) >= 4.5, name
    assert "button.primary { background: var(--red)" in CSS and '.chip[aria-current="true"] { background: var(--blue)' in CSS


def test_edges_and_marks_can_be_seen():
    for name, theme in (("day", DAY), ("night", NIGHT_AUTO)):
        for ground in GROUNDS:
            assert contrast(theme["edge"], theme[ground]) >= 3, f"{name}: the edge of a field on --{ground}"
            for mark in ("red", "green", "blue", "faint", "flag"):  # the marks, the line gauge's fill, the focus ring
                assert contrast(theme[mark], theme[ground]) >= 3, f"{name}: --{mark} as a mark on --{ground}"
        for mark in ("green", "rail-graphite"):  # the marks in the rail's sync status
            assert contrast(theme[mark], theme["rail"]) >= 3, f"{name}: --{mark} as a mark on the rail"
    assert re.search(r"input\[type=\"search\"\][^{]*\{[^}]*border: 1px solid var\(--edge\)", CSS)  # fields carry that edge
    assert "::placeholder { color: var(--faint); }" in CSS


def test_figures_are_tabular_only_where_numbers_stand():
    # On the whole page, Schibsted Grotesk's tabular figures widen full stops,
    # commas and colons too: "hardcover . app". Only number-bearing parts get them.
    body = CSS[CSS.index("body {") : CSS.index("}", CSS.index("body {"))]
    assert "tabular-nums" not in body and "tabular-nums" not in CSS[CSS.index(":root {") : CSS.index("* { box-sizing")]
    assert re.search(r"\.meta, \.chip b,[^{]*\{ font-variant-numeric: tabular-nums; \}", CSS)
