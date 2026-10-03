"""The page's status language, as proofreaders' marks (DESIGN.md).

A mark carries the colour, the words beside it stay plain:
ok    a tick              up to date
next  a caret             the next sync changes this
wait  a dashed caret      switched on, nothing to send yet
warn  a circled query     needs the reader (a match)
err   an ink square, X    failed
none  a dash              not syncing
stet  the word itself     kept as Hardcover has it
Every mark is decorative: the words next to it say the same thing."""

from __future__ import annotations

from .fmt import e

_SVG = (
    '<svg class="mk" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9"'
    ' stroke-linecap="round" stroke-linejoin="round">{}</svg>'
)
_CARET = '<path d="M4 15.5 10 5l6 10.5"/>'
SHAPES = {
    "ok": '<path d="M4 10.5l4 4.5L16.5 5"/>',
    "next": _CARET,
    "wait": '<path d="M4 15.5 10 5l6 10.5" stroke-dasharray="2.2 2.6"/>',
    "warn": '<circle cx="10" cy="10" r="7.6" stroke-width="1.7"/><path d="M7.9 8.1a2.2 2.2 0 1 1 3.3 1.9c-.8.5-1.2.9-1.2 1.7"'
    ' stroke-width="1.7"/><circle cx="10" cy="14.1" r=".6" fill="currentColor"/>',
    "err": '<rect x="2.5" y="2.5" width="15" height="15" rx="1.5" fill="currentColor" stroke="none"/>'
    '<path d="M7 7l6 6M13 7l-6 6" stroke-width="1.8" style="stroke: var(--on-flag)"/>',
    "none": '<path d="M5 10h10"/>',
}
# The small caret before an inserted value.
INSERT = (
    '<svg viewBox="0 0 10 10" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"'
    ' stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 8.5 5 2l3.5 6.5"/></svg>'
)
# The name's own mark: the caret a proofreader writes where something goes in.
BRAND = (
    '<svg viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.4"'
    f' stroke-linecap="round" stroke-linejoin="round">{_CARET}</svg>'
)


# Help: a circled query in the same stroke as the marks.
HELP = _SVG.format(SHAPES["warn"]).replace('class="mk"', 'class="ic"')


def mark(kind: str) -> str:
    if kind == "stet":
        return '<span class="mk stet" aria-hidden="true">stet</span>'
    return _SVG.format(SHAPES.get(kind, SHAPES["none"]))


def line(kind: str, text: str, inner: str = "") -> str:
    """One status line: the mark, then the words (plain text, escaped here),
    then any further markup (already escaped)."""
    return f'<div class="act {kind}">{mark(kind)}<span>{e(text)}</span>{inner}</div>'
