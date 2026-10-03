---
name: Kobo Hardcover Sync
description: A galley proof of your Hardcover shelf, with what the next sync changes marked in the margin, by day and at night.
colors:
  ground: "#edefea"
  sheet: "#fbfbf8"
  margin: "#f4f5f1"
  ink: "#17191c"
  graphite: "#4a4f57"
  faint: "#5f656e"
  rule: "#cdd1cb"
  rule-soft: "#e3e6e0"
  edge: "#80868e"
  rail: "#c3e2ef"
  rail-ink: "#14222b"
  rail-graphite: "#2f4653"
  blue: "#1c5e8b"
  blue-wash: "#ddeff7"
  red: "#c0212b"
  red-wash: "#f9e3e1"
  green: "#2c6a39"
  green-wash: "#e1f0e2"
  flag: "#17191c"
  on-flag: "#fbfbf8"
  on-fill: "#ffffff"
  ground-dark: "#0f1114"
  sheet-dark: "#171a1e"
  margin-dark: "#1b1f24"
  ink-dark: "#e7e9e4"
  graphite-dark: "#aeb4bb"
  faint-dark: "#959ca4"
  rule-dark: "#30353c"
  rule-soft-dark: "#24282e"
  edge-dark: "#6e757e"
  rail-dark: "#123040"
  rail-ink-dark: "#e3f1f7"
  rail-graphite-dark: "#a9c6d4"
  blue-dark: "#86c5ea"
  blue-wash-dark: "#173444"
  red-dark: "#ff8077"
  red-wash-dark: "#3b1f1f"
  green-dark: "#86cf95"
  green-wash-dark: "#18301e"
  flag-dark: "#e7e9e4"
  on-flag-dark: "#0f1114"
  on-fill-dark: "#0f1114"
typography:
  display:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1.45rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "2.1rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.035em"
  dialog-title:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1.375rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  card-heading:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1.25rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  book-title:
    fontFamily: "'Source Serif 4', Georgia, 'Times New Roman', serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  book-title-details:
    fontFamily: "'Source Serif 4', Georgia, 'Times New Roman', serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
  control:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
  mark:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 650
  label:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.78rem"
    fontWeight: 650
  small:
    fontFamily: "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    fontFeature: "\"tnum\""
  sign-in-code:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "min(1.375rem, 7vw)"
    fontWeight: 600
    letterSpacing: "0.12em"
    fontFeature: "\"tnum\""
rounded:
  sheet: "2px"
  inner: "3px"
  ctl: "4px"
  step: "50%"
spacing:
  control-gap: "0.5rem"
  card-gap: "0.75rem"
  cell: "1rem 0.9rem"
  toolbar: "0.95rem 1.1rem"
  card: "1.2rem 1.35rem 1.35rem"
  column-gap: "2rem"
  rail-w: "17.25rem"
components:
  button:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.9rem"
    height: "2.375rem"
  button-touch:
    rounded: "{rounded.ctl}"
    height: "2.75rem"
  button-primary:
    backgroundColor: "{colors.red}"
    textColor: "{colors.on-fill}"
    typography: "{typography.control}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.9rem"
    height: "2.375rem"
  button-solid:
    backgroundColor: "{colors.flag}"
    textColor: "{colors.on-flag}"
    typography: "{typography.control}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.9rem"
    height: "2.375rem"
  button-danger:
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    padding: "0.4rem 0.15rem"
    height: "2.375rem"
  details-link:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
    padding: "0.15rem 0.65rem"
    height: "2rem"
  chip:
    textColor: "{colors.graphite}"
    rounded: "{rounded.ctl}"
    padding: "0.2rem 0.6rem"
    height: "2rem"
  chip-hover:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.ink}"
  chip-current:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.on-fill}"
  field:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 0.7rem"
    height: "2.375rem"
  select:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
    padding: "0.4rem 2rem 0.4rem 0.7rem"
    height: "2.375rem"
  theme-switch-pressed:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.on-fill}"
    rounded: "{rounded.inner}"
    padding: "0.2rem 0.7rem"
    height: "2rem"
  tag:
    textColor: "{colors.blue}"
    rounded: "{rounded.inner}"
    padding: "0 0.3rem"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.sheet}"
  card:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.sheet}"
    padding: "1.2rem 1.35rem 1.35rem"
  proof-margin:
    backgroundColor: "{colors.margin}"
    textColor: "{colors.ink}"
    padding: "1rem 0.9rem"
  rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-ink}"
    padding: "1.75rem 1.4rem 1rem"
    width: "17.25rem"
  nav-item:
    textColor: "{colors.rail-ink}"
    rounded: "{rounded.ctl}"
    padding: "0 0.75rem"
    height: "2.6rem"
  nav-item-current:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
  sign-in-code:
    backgroundColor: "{colors.margin}"
    textColor: "{colors.ink}"
    typography: "{typography.sign-in-code}"
    rounded: "{rounded.ctl}"
    padding: "0.2rem 0.7rem"
---

# Design System: Kobo Hardcover Sync

## Overview

**Creative North Star: "The Galley Proof"**

The list of books is a galley proof of your Hardcover shelf. Each book is
a line set on the sheet, and the Hardcover column is the proof margin:
what the next sync will change is marked there in proofreaders' marks, on
the row itself. The old value is struck through in red, the new value is
written in after a caret. A reader who looks at the page sees, per book,
what Hardcover will be told and why.

The world is a print shop's, made of paper, pencil and rule. A cool grey
galley stock for the page; a near-white sheet for the list; a pale
non-repro blue rail that is "your Kobo" (the name, the navigation, and on
Books what the Kobo and Hardcover last did, with the button that sends).
Two pencils do the marking: red for what a sync sends, blue for what the
reader chose or is asked. Everything else is ink and graphite. The page is
dense where a proof is dense, in the list, and only the book titles are
set in a book face.

It turns down the usual look for this kind of tool: a neutral list with
coloured status dots and badges. A mark is drawn beside plain words, never
pinned on as a badge. There are no pill shapes and no photographs; book
covers are the only pictures, and the tool fetches them itself.

**Key Characteristics:**
- The Hardcover column is a proof margin: a tinted column behind a double hairline rule, holding one status line per book.
- Seven marks, all in the legend above the list: red caret, dashed caret, tick, *stet*, circled query, ink square with a cross, dash.
- Two pencils with one job each: red for what a sync sends, blue for the reader's own choice or a question for them.
- Two typefaces with one job each: Source Serif 4 for book titles, Schibsted Grotesk for everything else.
- Square-cut: 2px to 4px corners, no pills.
- Light and dark share every role; WCAG 2.2 AA in both.
- One authored motion: the strike draws, the new value writes in.

## Colors

Galley stock, ink and graphite, with a non-repro blue rail and two
pencils, in a light and a dark version that share every role. Dark
applies when the system asks for it, unless the reader chose light, or
when the reader chose dark; both blocks hold the same values. The
browser's `theme-color` is the rail colour in each theme.

### Primary
- **Red Pencil** (`red`): what the next sync sends and the fill that sends
  it. The caret and first line of a *Next sync* mark, the strike through
  the old value, the inserted new value, and the *Sync now* and *Go live*
  buttons. Its wash (`red-wash`) is the text selection; the text caret in a
  field is red.

### Secondary
- **Blue Pencil** (`blue`): the reader's own choice, or a question for
  them. The chosen filter chip, the pressed theme switch below 1024px, the
  *stet* mark, the circled query and its first line, the count on *Needs a
  match*, links, the focus ring and native form accents.
  **Blue Wash** (`blue-wash`) is behind a hovered chip or theme button, and
  briefly behind the row you come back to after an action.

### Tertiary
- **Tick Green** (`green`): up to date. The tick and the first line of *Up
  to date on Hardcover*, a passing check, the ticks in the rail. **Green
  Wash** (`green-wash`) is behind a message that something worked.
- **Flag Ink** (`flag`, with `on-flag`): failed, and the ink fill. A filled
  square with a cross cut out; *Last sync failed* reversed out of an ink
  box; the border of a message that something went wrong. Also the fill of
  every filled button that does not send.

### Neutral
- **Galley Stock** (`ground`): the page.
- **Proof Sheet** (`sheet`): the list, cards, dialogs, fields and buttons.
- **Margin Tint** (`margin`): the proof margin and its head, the sign-in code, a token shown once.
- **Proof Ink** (`ink`): words; the read part of the line gauge.
- **Graphite** (`graphite`): authors, facts, labels, table heads, the edition line, select chevrons.
- **Faint Graphite** (`faint`): placeholders, the dashed caret and the dash in the list and legend, the gauge of a book that does not sync. The lightest grey a word or mark may have.
- **Field Edge** (`edge`): the edge of every field, select and button, the gauge's ticks, the crossed box of a missing cover.
- **Rule** (`rule`) and **Soft Rule** (`rule-soft`): the sheet's border and the double rules; lines between rows and sections.
- **Non-repro Blue** (`rail`, with `rail-ink` and `rail-graphite`): the rail on a desk, the band and the bottom navigation below 1024px. In the rail the dash of "books syncing" is Rail Graphite and the ticks are Tick Green.

### Named Rules
**The Two Pencils Rule.** Red fills only *Sync now* and *Go live*, and
marks only what a sync sends. Every other filled button is an ink fill
(*Start using Kobo Hardcover Sync*, *Connect to Hardcover*, *I have approved it*, *Use*, a
confirmation, *Check and save*). Blue is only for the reader's own choice
or a question for them; a label that states a fact (*New*, *Admin*) is
grey. A removing action is ink, never red.

**The Legend Rule.** Every mark the margin can hold is in the legend above
the list, drawn and coloured the same, with the words of the page's
strings: *Next sync changes this*, *Nothing to send yet*, *Up to date*,
*Kept as on Hardcover*, *Needs you*, *Failed*, *Not syncing*. Help explains
each one under *Hardcover status*. A new mark is not used until it is in
both.

**The Two Lights Rule.** Every colour has a light and a dark value with
the same role. A colour that exists in one theme only is a mistake. In
dark the red and blue are lighter and fills carry dark words
(`on-fill-dark`).

**The Legible Rule.** Words stand at 4.5:1 or more on whatever they are
on, the edge of a field and every mark at 3:1 (WCAG 2.2 AA), in both
themes. `tests/test_design_tokens.py` checks the pairs from `kobo.css`.

## Typography

**Display Font:** Schibsted Grotesk (with -apple-system, Segoe UI, sans-serif)
**Body Font:** Schibsted Grotesk
**Book titles:** Source Serif 4 (with Georgia, Times New Roman)
**Label/Mono Font:** the system monospace, for the sign-in code, tokens and short technical values

**Character:** Schibsted Grotesk is a newspaper grotesque, firm at 800 for
the few headings and plain at 13px in a dense row. Source Serif 4 sets the
books as the books they are, with optical sizing on. Both are served by
the tool itself from its own static files, under the SIL Open Font
Licence.

### Hierarchy
- **Display** (800, 1.45rem from 1024px, 1.25rem below, 1.05, -0.025em): the name, once, with the caret mark before it.
- **Headline** (800, 2.1rem from 1024px, 1.6rem below, 1.05, -0.035em): a page's title (*Books*, *Settings*, *Admin*). A page outside the frame uses 1.75rem.
- **Dialog title** (800, 1.375rem, -0.02em): the title of Help; 1.25rem at 520px and below. Help's section headings are 1.0625rem at 750.
- **Card heading** (800, 1.25rem, 1.2, -0.02em): the heading of a card. A small heading inside a card or Details is 0.8125rem at 700 in graphite.
- **Book title** (Source Serif 4, 600, 1.0625rem, 1.25): a book in the list. 1.375rem at the top of Details; also the caption in the cover lightbox.
- **Body** (400, 0.9375rem, 1.5): everything else, and the corrected value in the margin. Running text is kept to 62ch to 64ch.
- **Control** (600, 0.875rem): buttons; fields and selects at 0.875rem and 400; authors and the Hardcover cell at 0.875rem.
- **Mark** (650, 0.8125rem): the first line of a mark in the margin, in the mark's colour.
- **Label** (650, 0.78rem): table heads and filter group names. Sentence case, never capitals.
- **Small** (400, 0.8125rem): facts under a gauge, the legend (0.75rem below 1024px), hints, the edition line, the foot.
- **Sign-in code** (system monospace, 600, min(1.375rem, 7vw), 0.12em): set large because the reader compares it by eye with what Hardcover shows. Other code is the monospace at 0.8125rem.

### Named Rules
**The Book Face Rule.** Source Serif 4 is for book titles and nothing
else: in the list, at the top of Details, under a large cover. The name,
headings, buttons and every fact are Schibsted Grotesk.

**The Figures Rule.** Tabular figures go only where numbers stand in
columns or are compared: the facts under a gauge (`.meta`), the counts on
chips, the count on the Filter button, and code. Never on the root or on
running text: in Schibsted Grotesk `tabular-nums` widens full stops and
commas too. `tests/test_design_tokens.py` holds this.

## Layout

One frame on every page: a rail and a main column. Phone first.

**Below 1024px** it is one column. The rail is a band at the top (padding
0.9rem 1rem 1rem): the name with its own Help button (`.bandhelp`), on
Books the two status lines and *Refresh* beside a wider *Sync now*. The
navigation is a bar fixed at the bottom, three equal targets of at least
3.25rem, icon over word. The filters fold behind one *Filter* button that
names the chosen one and its count (with JavaScript; without it they stay
open). Each book is a card: cover and title across; *Sync* and *State*
side by side under their names; then the margin strip, set off by the
double rule, holding the mark. Cards are 0.75rem apart; the page gutter
is 0.75rem. Other tables (Admin) stack as a name beside its value. The
foot (who is signed in, the theme switch) follows the list.

**Below 720px** (a phone) the first book and its mark come on the first
screen, at 390 by 844: the page's line under its title and the band's
"N of M books syncing" step aside (the legend and the *Filter* count say
the same), and *Filter* and *Sort* share one row, the sort's label kept for
a screen reader only.

**From 720px to 1023px** (a tablet) two book cards sit side by side, and
the rail's status lines go into three columns with the two buttons under
them, to the right.

**From 1024px** (a desk) the rail is 17.25rem down the left, with the page
2rem beside it, everything in one window height. The rail holds the name
and one line about the tool, the navigation as a list, on Books the status
and the buttons (*Sync now* above *Refresh*), and at its foot who is signed
in, the theme switch, Help, and the sentence that says the project is
independent of Rakuten Kobo and Hardcover (on a phone that sentence is in
Help). The page holds the title, one line of meta
and the legend, then one sheet: search and sort, the three filter groups
as chips with *Set all N shown to* at the end, and the table. The list
scrolls inside its sheet under a sticky table head; settings and admin
scroll their column of cards. Cards are capped at 46rem (Admin uses the
full width); the page is capped at 92rem.

**At 520px and below** a term and its value in Details stack with a
narrower term column (6.75rem instead of 8.5rem), Help's list of terms goes
to one column, and filter group names go above their chips.

The table has fixed columns: the book takes what is left, *Sync* 7.5rem,
*State* 10.75rem, *Hardcover status* 34%. Cells are padded 1rem 0.9rem
(1.1rem on the left edge from 1024px); the toolbar 0.95rem 1.1rem. Controls
are 2.375rem tall and sit 0.5rem apart. What takes keyboard focus is
scrolled clear of the bottom bar on a phone and the table head on a desk.

**The Finger Rule.** Below 1024px fields, selects, buttons and *Details*
are 2.75rem (44px), and the theme switch 2.5rem. Under a coarse pointer,
at any width, everything you operate is 2.75rem, chips and the theme
switch included.

## Elevation & Depth

Flat paper. The sheet and cards lie on the page with a 1px rule and, in
light only, a faint fall of shadow; in dark there is none and nothing is
lost. Below 1024px the list's sheet dissolves and the book cards have no
shadow. Real depth is kept for things physically on top: a cover, a
dialog.

### Shadow Vocabulary
- **Lift, light only** (`box-shadow: 0 1px 0 #cdd1cb, 0 18px 40px -28px rgba(23, 25, 28, 0.38)`): under the sheet and cards. `none` in dark.
- **Cover** (`box-shadow: 0 1px 2px rgba(0, 0, 0, 0.28), 0 3px 8px rgba(0, 0, 0, 0.1)`): a book cover lying on the sheet.
- **Dialog** (`box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35)`): Help and Details, over `rgba(10, 12, 14, 0.6)`. The cover lightbox uses `0 24px 64px rgba(0, 0, 0, 0.55)` over `rgba(10, 12, 14, 0.88)`.
- **Current page** (`box-shadow: 0 1px 0 var(--rule)`): the current item in the desk navigation.

### Named Rules
**The Flat Paper Rule.** Surfaces are told apart by tone and a rule. A
shadow is never needed to read the page; the dark theme proves it.

## Shapes

Square-cut, like paper and type, with one exception: the step numbers of
the first run sit in circles, as a proofreader rings a number. The sheet, cards and dialogs are 2px;
small inner parts (a tag, a theme-switch button, a cover's fore-edge) are
3px; buttons, fields, selects, chips, *Details* and navigation items are
4px. Covers are 1px at the spine and 3px at the fore-edge, the one 1px
corner there is, kept because a book's spine is square. The focus ring
has 2px corners.

Lines carry the structure. Borders are 1px. The one heavy line is a 3px
double rule, the proofreader's hairline pair: down the left of the margin
column on a desk, across the top of a book card's margin strip below
1024px, and under the title bar of Help.

**The No Pills Rule.** No pill-shaped buttons, chips, tags or switches.
The largest corner on anything you operate is 4px.

## Components

Controls are drawn, not decorated: a 1px Field Edge, ink words, and the
two pencils only where they mean something.

### Buttons
- **Shape:** 4px, 2.375rem tall (2.75rem below 1024px and under a finger), 0.4rem 0.9rem, 600 at 0.875rem.
- **Default:** Proof Sheet with a Field Edge border and ink words; hover turns the border ink.
- **Primary (red fill):** *Sync now* and *Go live* only. Hover brightens it slightly (`brightness(1.07)`). *Sync now* says what it is about to send on a second, smaller line: "sends 3 marked changes" (live) or "would send 3 marked changes" (dry run), the number of books carrying the red mark, kept current as rows change; with none, the line is left out.
- **Solid (ink fill):** Flag Ink with `on-flag` words, for a choice that changes nothing on Hardcover yet.
- **Danger (removing):** no box, ink words underlined (thicker on hover): *Remove from Hardcover*, *Remove*, *Disconnect*, *Remove the token*.
- **Disabled:** 45% opacity, greyscale, no hover (*Go live* without a connection).
- **Help:** a square button with a drawn circled query in the marks' stroke (`marks.HELP`); in the band below 1024px it is transparent with a rail-ink edge, on a desk it sits at the foot of the rail.
- **Focus:** a 2px Blue Pencil outline, 2px off the control, on everything.

### Chips
- **Style:** no border, graphite words with the count in ink at 650; 2rem tall, 4px, 0.2rem 0.6rem.
- **State:** hover washes it in Blue Wash; the current one is filled Blue Pencil with `on-fill` words. One choice at a time, in three named groups (*Reading progress*, *On this Kobo*, *Hardcover status*). The count of *Needs a match* is blue.
- **Below 1024px:** the groups fold behind one *Filter* button: a funnel, *Filter: All*, the count and a chevron.

### Cards / Containers
- **Corner Style:** 2px.
- **Background:** Proof Sheet on Galley Stock. The book list is one sheet; Settings and Admin are a column of cards (two side by side where there is room for 20rem each).
- **Shadow Strategy:** the light-only lift (see Elevation & Depth).
- **Border:** 1px Rule.
- **Internal Padding:** 1.2rem 1.35rem 1.35rem; a section inside a card starts with a Soft Rule and a small graphite heading.

### Inputs / Fields
- **Style:** Proof Sheet, 1px Field Edge, 4px, 2.375rem tall, 0.875rem; placeholder in Faint Graphite. Every select has the same small drawn chevron in graphite.
- **Hover / Focus:** hover turns the edge ink; focus is the 2px blue outline. The text caret is red.
- **In a row:** *Sync* and *State* are plain selects as wide as their column; in a row that does not sync their words are graphite. Without JavaScript each gets a *Set* button.
- **Messages:** success on Green Wash; a failure on Proof Sheet with a 1px Flag Ink border.

### Navigation
- **Desk:** a list in the rail, icon and word at 600, 2.6rem tall. The current page is a Proof Sheet box in ink with a hairline under it; hover is a half-sheet wash.
- **Below 1024px:** a bar fixed at the bottom in Non-repro Blue, three equal targets, icon over word at 0.78rem, in Rail Graphite; the current one is Rail Ink on a 30% sheet wash.
- **Theme switch:** a 4px segmented control, *Light*, *Auto*, *Dark*. In the rail the pressed one is a Proof Sheet box; below 1024px, on the page, it is filled Blue Pencil.

### The status line (signature)
One language for status everywhere, built from the marks: a two-column
grid, a 1.6rem column for the mark and the words beside it, so a detail
line sits under the words and not under the mark. The mark carries the
colour; the words stay in ink. The same line says what the Kobo and
Hardcover last did in the rail (ticks in Tick Green, the dash in Rail
Graphite), whether Settings is live or a dry run, and what each check
found.

### The proof margin (signature)
The Hardcover column, tinted Margin Tint behind a 3px double rule, its
head tinted too. Each book has one status line there: the first line in
the mark's colour at 650, then the correction, then the edition line in
graphite, then one small *Details* button (2rem, 4px).

- **Red caret:** *Next sync*. Under it the correction: the old value in graphite struck through in red, then the new value in red at 650 after a small caret.
- **Dashed caret** (Faint Graphite): switched on, unread, nothing to send yet.
- **Tick** (Tick Green): up to date on Hardcover.
- **Circled query** (Blue Pencil): needs a Hardcover match.
- **Ink square with a cross:** the last sync failed; the words reversed out of an ink box.
- **Dash** (Faint Graphite): not syncing; the words in graphite.
- **stet** (blue italic, 800): on the edition line, before the edition, when the edition was chosen on Hardcover and is kept as it is.

### The line gauge (signature)
Under the author: a printer's line gauge, at most 16rem long. A 1px Field
Edge base with a tick every tenth and one at the end; the part read is a
4px bar of ink. In a row that does not sync the bar is Faint Graphite.
Beneath it, one line of small facts in graphite: the percentage, when it
was last read, how long.

### Covers
A cover is 48px by 72px in the list and 60px by 90px in Details, with the
cover shadow; it opens large in a lightbox. A book without a cover is the
crossed box a proof leaves where a picture goes: Proof Sheet, a 1px Field
Edge and two hairline diagonals.

### Labels: *New* and *Admin*
A small label states a fact: *New* after the title of a book new on this
Kobo, *Admin* beside a reader who is one (Settings, the Admin page).
0.75rem at 700, Pencil Grey words in a 1px outline of the same grey, 3px
corners; not a pill. It is grey because it is neither the reader's choice
nor a question for them, so it takes neither pencil.

### The first run
While the reader is in dry run and has books, the top of the Books sheet
says what to do with a Kobo full of books read before: a heading (*Pick the
books that are yours*, 1.25rem at 800), one paragraph held to 62ch, and the
count of books switched on so far (1.75rem at 800, ink, tabular, kept
current as rows change) with "Nothing is sent while this is a dry run".
Beside it on a wide desk (from 1100px), under it otherwise, three numbered
steps: *Connect to Hardcover* (a green tick when done, else a link to
Settings), *Pick your books* (the current step: its number filled blue,
its name blue, because it is the reader's), *Go live*. Numbers sit in
1.6rem circles with a Field Edge ring, the one round shape on the page.
A double rule closes it off from the toolbar; on a phone it is a card of
its own above the search. Going live is the last step, so going live
removes it. While it shows, the line under *Books* is left out: it would
say the same.

### Sign-in steps
A numbered list held to 64ch. The code is the sign-in code style on
Margin Tint with a Field Edge border, 4px, selected whole with one click
and never broken across lines. Pasting a token instead sits behind a
disclosure whose chevron turns in 0.2s.

### Dialogs
Help and Details are native dialogs, 2px, on a dimmed page, on a phone as
on a desk: the page had them before this design and keeps them, so a book
opens over the list and closing it returns to the same place (without
JavaScript, Details is its own page). Details shows the next sync with the
same struck and inserted correction as the row. Help is
reading matter: the title and *Close* stay put above a double rule while
the text scrolls, and the words and marks from the page stand in their own
11rem column.

### Motion
One authored moment. When the list loads, and whenever a row is redrawn,
the strike draws across the old value (0.5s) and the new value writes in
from the left (0.6s, 0.2s later), both on an expo ease-out
(`cubic-bezier(0.16, 1, 0.3, 1)`), each row 70ms after the one above (up
to the thirteenth). Two small functional motions remain: coming back to a
row washes it Blue Wash for 1.8s, and a large cover fades and grows in for
0.18s. Under `prefers-reduced-motion` all of them are off; the row you
came back to keeps a steady wash.

## Do's and Don'ts

### Do:
- **Do** put what a sync will do with a book in its proof margin, as one status line with one of the seven marks.
- **Do** strike the old value in red and write the new value after a red caret when the next sync changes something.
- **Do** fill red only *Sync now* and *Go live*; give every other filled button the ink fill.
- **Do** keep blue for the reader's own choice or a question for them.
- **Do** add any new mark to the legend and to Help's *Hardcover status*, drawn and coloured the same, before it appears in a row.
- **Do** set book titles in Source Serif 4 at 600 and everything else in Schibsted Grotesk.
- **Do** put `tabular-nums` only on numbers that stand in columns or are compared: the facts, chip counts, the Filter count, code.
- **Do** use 2px for sheets, cards and dialogs, 4px for what you operate, and the 3px double rule where the margin begins.
- **Do** make every control 2.75rem below 1024px and under a finger.
- **Do** give every new colour a light and a dark value with the same role, and check it: 4.5:1 for words, 3:1 for field edges and marks.
- **Do** make every action work without JavaScript, and stop every motion under `prefers-reduced-motion`.
- **Do** draw a missing cover as the crossed box.

### Don't:
- **Don't** show status as coloured dots or badges on a neutral list; the mark is drawn beside plain words.
- **Don't** use red for decoration, for a warning, or for a button that removes something; a removing action is ink, underlined.
- **Don't** use pill shapes, for buttons, chips, tags or switches.
- **Don't** set `tabular-nums` on the root or on running text.
- **Don't** set anything but a book title in Source Serif 4.
- **Don't** rely on a shadow to separate surfaces; the dark theme has none.
- **Don't** set labels in capitals or track them out.
- **Don't** add a second authored motion; the strike and the write-in are the one.
- **Don't** load a font, a script, a style or a picture from elsewhere; the tool serves everything, the two fonts and the book covers included.
