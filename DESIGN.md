---
name: Kobo Hardcover Sync
description: A reader's own log of what a Kobo read and what Hardcover was told, calm by day and at night.
colors:
  bg: "#f0f4ff"
  surface: "#ffffff"
  surface-2: "#f6f8fd"
  ink: "#1e293b"
  muted: "#475569"
  faint: "#5f6f86"
  line: "#d3dbe8"
  line-soft: "#e6ebf4"
  edge: "#7b8ba2"
  accent: "#0891b2"
  accent-fill: "#0e7490"
  accent-ink: "#0e7490"
  accent-soft: "#e0f2fe"
  on-accent: "#ffffff"
  ok: "#15803d"
  ok-soft: "#dcfce7"
  warn: "#b45309"
  warn-soft: "#fef3c7"
  err: "#be123c"
  track: "#dbe4f3"
  bg-dark: "#0f172a"
  surface-dark: "#131c31"
  surface-2-dark: "#0c1424"
  ink-dark: "#e2e8f0"
  muted-dark: "#94a3b8"
  faint-dark: "#8291a8"
  line-dark: "#2a3a55"
  line-soft-dark: "#1e2a40"
  edge-dark: "#64748b"
  accent-dark: "#22d3ee"
  accent-fill-dark: "#22d3ee"
  accent-ink-dark: "#67e8f9"
  accent-soft-dark: "rgba(34, 211, 238, 0.12)"
  on-accent-dark: "#0b1220"
  ok-dark: "#34d399"
  ok-soft-dark: "rgba(52, 211, 153, 0.14)"
  warn-dark: "#fbbf24"
  warn-soft-dark: "rgba(251, 191, 36, 0.14)"
  err-dark: "#fb7185"
  track-dark: "#223049"
typography:
  display:
    fontFamily: "Literata, Georgia, 'Times New Roman', serif"
    fontSize: "clamp(1.55rem, 8vw, 2.1rem)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Literata, Georgia, 'Times New Roman', serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Literata, Georgia, 'Times New Roman', serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Sora, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Sora, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.55
  display-sidebar:
    fontFamily: "Literata, Georgia, 'Times New Roman', serif"
    fontSize: "1.62rem"
    fontWeight: 600
    lineHeight: 1.1
  dialog-title:
    fontFamily: "Literata, Georgia, 'Times New Roman', serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
  card-heading:
    fontFamily: "Literata, Georgia, 'Times New Roman', serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.25
  secondary:
    fontFamily: "Sora, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
  caption:
    fontFamily: "Sora, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  line: "2px"
  cover: "3px"
  focus: "4px"
  ctl: "9px"
  panel: "16px"
  pill: "999px"
spacing:
  control-gap: "0.5rem"
  row: "0.85rem"
  panel: "1rem"
  card: "1.25rem"
  frame: "1.5rem"
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.9rem"
    height: "2.25rem"
  button-primary:
    backgroundColor: "{colors.accent-fill}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.9rem"
    height: "2.25rem"
  button-danger:
    textColor: "{colors.err}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.9rem 0.4rem 0"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.65rem"
    height: "2.25rem"
  row-select:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 1.9rem 0.4rem 0.65rem"
  chip:
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.65rem"
  chip-hover:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-ink}"
  chip-current:
    backgroundColor: "{colors.accent-fill}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.pill}"
  tag:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.pill}"
    padding: "0.1rem 0.5rem"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "1.15rem 1.25rem 1.3rem"
  nav-item:
    textColor: "{colors.muted}"
    rounded: "{rounded.ctl}"
    padding: "0.5rem 0.7rem"
  nav-item-current:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
---

# Design System: Kobo Hardcover Sync

## Overview

**Creative North Star: "The Reading Log"**

A reader's own ledger. Each book is a line: its title set like a title, a
thin rule that shows how far you are, when you last read it, and what
Hardcover was or will be told. The page is the notebook that holds those
lines, and everything else on it (the filters, the switches, the settings)
is the margin. The mood is calm, plain and bookish: unhurried, a little
domestic, with the book titles carrying the character and the interface
staying out of the way.

It is dense where a log is dense, in the list, and roomy where someone
reads, in the help dialog and on the settings cards. It has two lights, a
day theme and a night theme, each with its own photograph of a real Kobo:
on linen by day, at dusk by night. The photograph sits once, at the top of
the sidebar, and dissolves into the page.

Three looks were considered and turned down, and stay turned down: a
dashboard of tiles and big numbers, a photograph across the full width
above the list, and filters in the sidebar like mail folders. The list of
books is the page; nothing is allowed to push it down or stand in front
of it.

**Key Characteristics:**
- One frame for every page: a sidebar that is "your Kobo", a sheet that is "your books".
- Two typefaces with one job each: Literata for anything that is a title, Sora for the interface.
- One accent, Reading-light Cyan, spent on where you are in a book and on what you chose.
- Readable by the numbers: WCAG 2.2 AA for words, edges and marks, in both lights.
- Status is a dot and plain words, the same everywhere.
- Controls are quiet until pointed at; one filled button per page.
- Surfaces are told apart by tone and a hairline, not by shadow.

## Colors

A cool, paper-and-slate palette with a single cyan, in a day and a night
version that share every role.

### Primary
- **Reading-light Cyan** (#0891b2 by day, #22d3ee at night): the glow of an
  e-reader's front light. It draws the reading line under a title, marks
  the edge of a row that syncs, and is the focus ring.
- **Reading-light Deep** (#0e7490 by day; at night the bright cyan itself):
  the fill of the chosen filter and the one primary button. By day white
  words stand on it; at night the fill is bright and the words on it are
  dark (#0b1220).
- **Reading-light Ink** (#0e7490 by day, #67e8f9 at night): the same hue
  for words: links, the current item in the phone's navigation, the
  Details button.
- **Reading-light Wash** (#e0f2fe by day, a 12% tint at night): behind a
  hovered filter, the pressed theme switch, the *New* tag, and the row you
  just came back to.

### Secondary
- **Shelf Green** (#15803d by day, #34d399 at night): done and well. The
  reading line of a finished book, the dot of "Up to date on Hardcover",
  the wash behind a success message (#dcfce7).

### Tertiary
- **Bookplate Amber** (#b45309 by day, #fbbf24 at night): needs you. The
  dot of "Needs a Hardcover match" and the count on that filter.
- **Margin Red** (#be123c by day, #fb7185 at night): went wrong, or takes
  something away. The dot of a failed sync, the border of an error
  message, the text of a removing button.

### Neutral
- **Morning Paper** (#f0f4ff) and **Night Desk** (#0f172a): the page.
- **Sheet White** (#ffffff) and **Slate Sheet** (#131c31): panels, the
  list, dialogs, controls.
- **Ruled Tint** (#f6f8fd, night #0c1424): the table head, the quiet
  selects in a row, the space a photograph loads into.
- **Log Ink** (#1e293b, night #e2e8f0): text.
- **Pencil Grey** (#475569, night #94a3b8): second-line text, labels,
  authors, hints.
- **Faint Pencil** (#5f6f86, night #8291a8): placeholders, filter group
  names, the small labels on a phone's book cards, the dot of "not
  syncing". The lightest grey a word may have.
- **Field Edge** (#7b8ba2, night #64748b): the border of a field you type
  in or choose from, so the field can be found without its words.
- **Rule** (#d3dbe8, night #2a3a55) and **Soft Rule** (#e6ebf4, night
  #1e2a40): borders around panels and controls; lines between rows.
- **Track** (#dbe4f3, night #223049): the unread part of a reading line,
  and the tile of a book without a cover.

### Named Rules
**The One Light Rule.** There is one accent. Cyan means "your place" or
"your choice" and nothing else; green, amber and red appear only as
status, never as decoration.

**The Dot Rule.** Colour carries status only through an 8px dot; the words
beside it stay in ink. No coloured text for status, no coloured row
backgrounds, no badges.

**The Two Lights Rule.** Every colour has a day and a night value with the
same role. A colour that exists in one theme only is a mistake.

**The Legible Rule.** Words stand at 4.5:1 or more on whatever they are
on, the edge of a field and every mark at 3:1 (WCAG 2.2 AA). The bright
cyan cannot carry white words by day, which is why fills are Reading-light
Deep. `tests/test_design_tokens.py` checks the pairs.

## Typography

**Display Font:** Literata (with Georgia, Times New Roman)
**Body Font:** Sora (with the system sans-serif)
**Label/Mono Font:** the system monospace, for tokens and hashes only

**Character:** Literata was made for reading ebooks, so the titles on the
page look the way they do on the device. Sora is a plain, slightly wide
sans that stays legible at 13px in a dense row. Both are served by the
tool itself.

### Hierarchy
- **Display** (600, clamp(1.55rem, 8vw, 2.1rem), 1.1, -0.02em): the name,
  once, set on the photograph. In the sidebar it is 1.62rem, the size at
  which the three words fit on one line.
- **Headline** (600, 1.75rem, 1.2, -0.01em): a page's title (Settings,
  Admin).
- **Dialog title** (600, 1.5rem, 1.2): the title of the help dialog.
- **Card heading** (600, 1.25rem, 1.25): the heading of a card, a section
  of the help dialog, the book's title at the top of Details. One size for
  all three.
- **Title** (600, 1.0625rem, 1.3): a book in the list; a reader's name in
  Admin.
- **Body** (400, 0.9375rem, 1.55): everything else. Running text is kept
  to 62ch to 64ch.
- **Secondary** (400, 0.875rem): second lines, authors, controls, the
  sidebar's status.
- **Label** (600, 0.8125rem): table heads, field labels, the small
  headings inside a card. Sentence case, never capitals. The same size at
  400 for hints and the small facts under a reading line.
- **Caption** (400, 0.75rem): filter group names, the phone's navigation,
  the names above a phone card's switches. The smallest size there is.

### Named Rules
**The Title Rule.** Literata is for things that are titles: the name, page
and card headings, book titles. Anything you operate or read as a fact is
Sora. A serif button or a sans book title is wrong.

**The Figures Rule.** Numbers are tabular everywhere, so percentages and
dates line up down the list.

## Layout

One frame for every page.

From 1024px it is two columns inside one window height: a sidebar of
17.5rem that holds the photograph with the name on it, the navigation,
what the Kobo and Hardcover last did (with *Sync now*), and at the bottom
who is signed in, the theme switch and help; beside it the sheet, which
takes the rest up to 96rem. The page itself does not scroll; the list
scrolls inside its sheet under a table head that stays put. Settings and
Admin put their cards where the sheet is; Settings is capped at 46rem for
reading, Admin uses the full width for its table.

Below 1024px it is one column, phone first: the photograph is the top of
the page, the navigation is a bar fixed at the bottom under the thumb, the
filters fold behind one line that names the chosen one, and each book is a
card: cover and title across, the two switches side by side under their
names, then what Hardcover gets. From 720px a tablet shows two cards per
row. At 520px and below, the help dialog and term lists go to one column.

The list is a table with fixed columns: the book takes what is left, Sync
7.25rem, State 10.5rem, Hardcover status 29%. Rows are padded 0.85rem;
panels 1rem to 1.25rem; controls sit 0.5rem apart;
the frame's gutter is 1.5rem. Controls are 2.25rem tall, 2.5rem below
1024px, and 2.75rem (44px) under a finger, whatever the width. What takes
keyboard focus is scrolled clear of the two bars that stay put: the
navigation at the bottom of a phone, the table's head on a desk. With text
at twice its size, rows of controls wrap; nothing scrolls sideways.

**The List First Rule.** Nothing sits above the list that is taller than
the toolbar. A new element earns a place in the sidebar, in a row, or in
the Details dialog, not between the reader and their books.

## Elevation & Depth

Layered by tone. Surfaces are told apart by colour and a 1px rule: the
page, the sheet on it, the tinted table head, the quiet selects. The day
theme adds a very soft shadow under panels as atmosphere; the night theme
has none, and nothing is lost. A shadow is never needed to understand the
page.

### Shadow Vocabulary
- **Panel, day only** (`0 1px 2px rgba(15, 23, 42, 0.04), 0 12px 32px rgba(15, 23, 42, 0.07)`): under the sheet, cards and the status panel on a phone. `none` at night.
- **Cover** (`0 1px 2px rgba(15, 23, 42, 0.2), 0 4px 10px rgba(15, 23, 42, 0.12)`): a book cover is an object lying on the sheet; it is the one thing with a real shadow in both themes.
- **Dialog** (`0 24px 64px rgba(0, 0, 0, 0.35)`): Help and Details, over a dimmed page (`rgba(8, 13, 26, 0.6)`).

### Named Rules
**The Tone Rule.** If two surfaces need telling apart, change the tone or
draw a rule. Reach for a shadow only for something that is physically on
top: a cover, a dialog.

## Shapes

Three radii, each with one meaning. Panels, the things that hold content,
are 16px. Controls, the things you operate, are 9px. Pills (999px) are
only for a choice from a set: filter chips, the theme switch, the *New*
tag. Covers keep the 3px of a book's corner; the focus ring has 4px, the
ends of the reading line 2px. Borders are 1px in Rule; the
one heavier line is the 3px of Reading-light Cyan down the left edge of a
row that syncs. The reading line is 4px tall with 2px ends. The
photograph is cropped by its panel and fades into the page colour rather
than ending at an edge.

## Components

Controls are quiet until pointed at. In a list of thirty books, thirty
framed boxes would be louder than the books.

### Buttons
- **Shape:** softly squared (9px), 2.25rem tall, 2.5rem on a phone.
- **Default:** Sheet White with a Rule border and ink text (0.4rem 0.9rem, 500 weight).
- **Primary:** filled Reading-light Deep with the on-accent text, 600 weight. One per page: *Sync now*, *Check and save*.
- **Hover / Focus:** the border turns cyan; the primary brightens slightly. Focus is a 2px cyan outline, 2px off the control.
- **Removing:** Margin Red text with no box and no left padding, underlined on hover. It sits beside the safe action, never in its place.
- **Disabled:** half opacity, no hover.

### Chips
- **Style:** text in Pencil Grey with its count in ink; no border, pill-shaped (0.25rem 0.65rem).
- **State:** hover washes it in Reading-light Wash; the chosen one is filled Reading-light Deep. One choice at a time, in named groups (*Reading progress*, *On this Kobo*, *Hardcover status*). A count that wants attention is amber.

### Cards / Containers
- **Corner Style:** 16px.
- **Background:** Sheet White on the page colour; the list is one sheet, Settings and Admin are a column of cards.
- **Shadow Strategy:** see Elevation: a soft shadow by day, none at night.
- **Border:** 1px Rule.
- **Internal Padding:** 1.15rem 1.25rem 1.3rem for a card; the sheet's toolbar 0.85rem 1rem. Sections inside a card are parted by a Soft Rule and a small label heading.

### Inputs / Fields
- **Style:** Sheet White, 1px Field Edge, 9px, 2.25rem tall; placeholder in Faint Pencil. Every select has the same drawn chevron in Pencil Grey.
- **In a row:** selects lose their border and sit on Ruled Tint; the border comes back on hover and focus. Their chevron and their words identify them. Without JavaScript each gets a *Set* button.
- **Focus:** the 2px cyan outline; hover darkens the border to Pencil Grey.
- **Error:** shown as a message, not on the field: a panel-coloured box with a Margin Red border, the reason in Pencil Grey beneath. Success is a Shelf Green wash.

### Navigation
- **Desk:** a list in the sidebar, icon and word, Pencil Grey; the current page is a Sheet White box with a Rule border, ink text and a cyan icon.
- **Phone:** a fixed bar at the bottom, icon over word at 0.75rem; the current page in Reading-light Ink.

### The reading line (signature)
Under every title: a 4px line, at most 26rem long, cyan for as far as the
book has been read on a Track ground; green and full when the book is
finished. Beneath it one row of small facts in Pencil Grey: the
percentage, when it was last read, how long. In a row whose sync is off
the line and the title fade. This is the one loud element of the page.

### The status line (signature)
One language for status everywhere: an 8px dot and plain words. Cyan dot:
the next sync will do this. Green: up to date. Amber: needs you. Red:
failed. Grey with grey words: not syncing. A second line in Pencil Grey
names the match; one small *Details* button follows. The sidebar uses the
same line for what the Kobo and Hardcover last did.

### Dialogs
Help and Details are native dialogs, 16px, on a dimmed page. Help is
reading matter: the title and *Close* stay while the text scrolls,
sections are parted by a Soft Rule, and words from the page stand in
their own column. Details opens with the cover and title and ends with
the actions, parted by a rule. A cover opens large in a lightbox, with a
0.18s fade and grow. Coming back to a row after an action washes it cyan
for 1.8s. Both motions stop when reduced motion is asked for.

## Do's and Don'ts

### Do:
- **Do** set every title in Literata at 600 and everything you operate in Sora.
- **Do** give every new colour a day and a night value with the same role.
- **Do** show status as an 8px dot and plain words in ink.
- **Do** keep one filled button per page; everything else is a bordered or borderless control.
- **Do** use 16px for what holds content, 9px for what you operate, and a pill only for a choice from a set.
- **Do** put a new fact about a book in its row's small grey line or in Details, and a new fact about the installation in the sidebar.
- **Do** make every motion stop under `prefers-reduced-motion`, and every action work without JavaScript.
- **Do** fill with Reading-light Deep and draw with Reading-light Cyan; check any new pair of colours against 4.5:1 for words and 3:1 for edges and marks.

### Don't:
- **Don't** build a dashboard of tiles and big numbers. The list of books is the page.
- **Don't** put a photograph across the full width above the list; the photograph lives once, in the sidebar.
- **Don't** move the filters into the sidebar like mail folders.
- **Don't** colour status text, tint whole rows, or add badges; the dot carries the colour.
- **Don't** set words in a grey lighter than Faint Pencil, or white words on the bright cyan.
- **Don't** use cyan for decoration. If it is not your place in a book or your choice, it is not cyan.
- **Don't** rely on a shadow to separate surfaces; the night theme has none.
- **Don't** set labels in capitals or track them out.
- **Don't** load a font, a script, a style or a picture from elsewhere; the tool serves everything, book covers included.
