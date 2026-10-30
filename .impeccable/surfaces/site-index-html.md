---
version: 1
slug: "site-index-html"
primary_target: "site/index.html"
related_targets: []
---

# The promotional site (site/index.html, GitHub Pages)

Mode: Persuade. One static page at merlijntishauser.github.io/kobo-hardcover-sync,
deployed from `site/` on `main` by a Pages workflow. Visitor: a Kobo reader who
heard of the tool (Reddit, the Hardcover community, a search). They should leave
believing it works with their Kobo as it is, Kobo-store books included, and that
it stays on their own machine. Lead action: download the Mac app, the version and
file read live from the latest GitHub release, with a plain link to the releases
page without JavaScript; Homebrew and pip as the second way. Proof: real
screenshots of the Books page (light and dark, desk and phone) and the Mac app,
rendered from the code with a made-up shelf, labelled as such. Constraints: the
independent-project sentence, no testimonials or numbers that do not exist, WCAG
2.2 AA, works without JavaScript, loads nothing from outside the site (fonts and
photographs are the site's own files; the photographs are Unsplash's, under the
Unsplash License, listed in THIRD-PARTY-NOTICES.md). Redesign of 2026-10-30,
asked for by the owner: vibrant colour, gradients, photographs of people reading.

## Direction contract

THESIS: The site tells the made-up shelf the way readers already tell their
year: as the share cards of a year in review, each card one fact the Kobo keeps
and what Hardcover will be told about it, the strike and the write-in on the
card itself. The mechanism is shown as the cards before a word of claim. It
refuses the headline-over-a-screenshot opener and the split hero with copy on
one side and a device on the other.

OWN-WORLD: Four gradient cards, each one hue family in three or four
saturated stops with the dark end where the words are, owning the first
viewport in both lights: plum to coral (#5b2a86 to #ff6b6b), teal to lime
(#0b5c57 to #c6f26b), deep blue to sky (#1e3a8a to #38bdf8, no violet
anywhere), and a slate card (#3a3952 to #1b1a2a). The ground is white by day
(#fbfbfd) and near-black at night (#0d0c14); the gradient cards are the same
in both, a share graphic does not change with the room. The one exception is
the download card: ink by day and white at night, so that the action card is
the strongest thing on the ground in each light (an ink card on the night
ground would dissolve). White words on the dark gradients; a heading that
crosses the lime end is ink. The caret and the strike on a card are the
card's pale red (#ffd1cf); the tick and the dash in the lists are the card's
words colour.
Figures at Schibsted Grotesk 800, 9rem on a card, -0.06em; headings 800;
everything else 400 and 600; Source Serif 4 600 for book titles only. 18px
corners on cards and 12px on the one button, the share card's own rounding; no
hairline rules, cards separate by colour. Photographs are cards too:
full-bleed, a gradient scrim at the foot for the words, starting higher where
a figure or a heading sits on it.

STORY: Sees four cards and reads them as one story: the Kobo's count, a Kobo
being read in a park, "Currently reading, 88%" struck through and "Read, 21 Sep
2026" written in, and the download. Understands in one glance that what the
Kobo knows goes to Hardcover, and that the page shows it before sending it.
Downloads the Mac app. Scrolls to the page's two lights as cards, the Mac app's
window, the four steps as four gradient cards, what it leaves alone, the other
tools, the independent sentence, the close.

FIRST VIEWPORT: The head: the name with its caret, the page's places, GitHub.
A row of four cards, 1360 wide at 1440, each about 325 by 440: the plum card with
"34" at 9rem and "books on the Kobo, read from its own database over the cable";
the photograph (a Kobo read on a park chair, Perfecto Capucine) with
"Middlemarch, 100%, finished 21 Sep" on its scrim; the teal card with the strike
and the write-in, "Read, 21 Sep 2026" at 3.4rem; the download card, ink by day
and white at night, the app icon at its head, Download for Mac as the one
filled button with the live version under it and brew and uv as code. Under
the row, the headline in two or three lines at 4.4rem on the left and the lede
on the right, with "a made-up shelf"
in small type. Below 1100px the cards go two by two; below 720px one column,
and the order becomes headline, download card, then the rest, so that the
action is within the first screen on a 390 by 844 phone. Signature interaction:
the cards rise into place once on load, 60ms apart on the expo ease-out, and on
the teal card the strike draws across and the new value writes in, the
product's own motion; static under reduced motion. Nothing else moves.

FORM: The year-in-review poster, structure 1 of 7 on my ordered list, my own
pick chosen by the owner over the dealt rainbow shelf, seed:9fd62655229622b4
(direction scope, persuade). Code-led: no image generation in this harness.

FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.

## Unresolved

- Photographs chosen by the owner on Unsplash: the park Kobo (Perfecto
  Capucine, 2gllPE42ouU) is the hero; the teal book (Sincerely Media,
  HFeG2vERmWo), the bed (Paige Cody, ypdO5AlNMgs) and the bench (Leon Seibert,
  hQzBAtJoJQo) go lower down. The fifth they named (Lala Azizli, 87lrs0EaNZo)
  shows a Kindle, not a Kobo, and is left out.
- The Mac app's pictures are the owner's own screenshots of 0.19.0, in both
  themes, as before.
