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
asked for by the owner: vibrant colour, gradients, photographs of people reading;
reworked on 2026-10-31 after its critique (22/32): the real row as the hero.

## Direction contract

THESIS: The site's proof is the tool's own proof: one row of the Books page
at full size, drawn in the page's own markup with the proof mark on it, the
old value struck through in red and the new one written in after a caret,
under the claim and beside the download. The mechanism is shown as the
product shows it, before a word of explanation. The year-in-review cards
follow as the story, three of them, demoted from the opener they were on
2026-10-30 after the critique of that day read the cards as a borrowed
genre and the page's own list as the thing worth showing. It refuses the
headline-over-a-screenshot opener (the row is markup, not a picture) and
the split hero with copy on one side and a device on the other.

OWN-WORLD: The ground is white by day (#fbfbfd) and near-black at night
(#0d0c14). The sheet is the tool's row and carries the tool's own colours,
scoped to it (`--sh-*`: sheet, margin tint, rule, edge, red, green, blue,
in both lights), a 1px rule and 18px corners; it is the one place the
site's palette and the tool's meet. Three gradient cards tell the story,
each one hue family in three or four saturated stops with the dark end
where the words are: plum to coral (#5b2a86 to #ff6b6b), teal to lime
(#0b5c57 to #c6f26b), deep blue to sky (#1e3a8a to #38bdf8, no violet
anywhere), and a slate card (#3a3952 to #1b1a2a) lower down. The cards
are the same in both lights. The download card is ink by day and white at
night, so that the action card is the strongest thing on the ground in
each light. White words on every gradient, the *What it does* heading
included; the strike and the caret on a card are the card's pale red
(#ffd1cf); the row's are the tool's red.
Figures at Schibsted Grotesk 800, 6rem to 9rem on a card, -0.06em;
headings 800; everything else 400 and 600; Source Serif 4 600 for book
titles only (the row's title and the park card's). 18px corners on cards
and the sheet, 12px on the one button, 4px on the row's drawn controls as
in the tool; no hairline rules outside the sheet and the table. Photographs
are cards too: full-bleed, a gradient scrim at the foot for the words,
starting higher where a figure or a heading sits on it.

STORY: Reads the claim, sees the download beside it, and under both one
row of the page: Middlemarch finished on the Kobo, and in the Hardcover
column "Currently reading, 88%" struck through and "Read, finished 21 Sep
2026" written in, the Sync now button saying what it would send. Understands
in one glance that what the Kobo knows goes to Hardcover, and that the page
shows it first. Downloads the Mac app. Scrolls to the story in three cards
(the Kobo's count, a Kobo read in a park, the everyday correction), the
page's two lights, the Mac app's window, the four steps from the token to
the shelf, what it does and leaves alone, the other tools, the close.

FIRST VIEWPORT: The head: the name with its caret, the page's places,
GitHub. The claim in two columns at 1440: the headline (2.4rem to 3.8rem)
and the lede on the left, the download card on the right (the app icon,
Download for Mac as the one filled button, the live version line, brew and
uv as code). Under them the sheet, 1360 wide: a rail with the four marks'
legend and the red Sync now button ("sends 4 marked changes"), the head row
(Book, Sync, State, Hardcover status), the one row (cover, title, author,
the line gauge, the facts; the two drawn switches; the margin on its tint
behind a double rule with the caret, the correction, the edition line and
Details), and a caption saying the shelf is made up, the marks are the
page's own, and that it starts as a dry run. The three story cards begin at
the foot of the viewport. Below 900px the claim is one column; below 720px
the row stacks (book, the two switches side by side, the margin under
them) and the download card follows the lede, so that the button is within
the first screen on a 390 by 844 phone. Signature interaction: the download
card, the sheet and the three cards rise into place once on load, 60ms
apart on the expo ease-out, and in the row the strike draws across and the
new value writes in, the tool's own motion at the tool's own timing; the
teal card's correction stands still. Static under reduced motion. Nothing
else moves.

FORM: The real row as the hero, chosen by the owner on 2026-10-31 from the
critique's three questions, over keeping the poster or drawing the product
on cards; the poster (structure 1 of 7, seed:9fd62655229622b4, persuade)
stays as the story below it. Code-led: no image generation in this harness.

FINISH: unreviewed and undocumented is unfinished; this build ends with the
critique's findings resolved, DESIGN.md, and every shipping raster carrying
its provenance.

## Unresolved

- Photographs chosen by the owner on Unsplash: the park Kobo (Perfecto
  Capucine, 2gllPE42ouU) is the story's card; the teal book (Sincerely Media,
  HFeG2vERmWo), the bed (Paige Cody, ypdO5AlNMgs) and the bench (Leon Seibert,
  hQzBAtJoJQo) go lower down. The fifth they named (Lala Azizli, 87lrs0EaNZo)
  shows a Kindle, not a Kobo, and is left out.
- The Mac app's pictures are the owner's own screenshots of 0.19.0, in both
  themes, as before.
