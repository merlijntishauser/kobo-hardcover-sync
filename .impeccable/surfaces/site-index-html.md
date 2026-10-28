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
Galley Proof world as DESIGN.md has it, the independent-project sentence, no
testimonials or numbers that do not exist, WCAG 2.2 AA, works without JavaScript,
loads nothing from outside the site (fonts are the project's own files).

## Direction contract

THESIS: The page is built on the one object the visitor owns: a Kobo's e-ink
screen at reading scale, showing a real sample book's reading line as the Kobo
keeps it; from that line one continuous red stroke runs into the proof margin,
where the mark says what Hardcover will be told. The mechanism is shown before a
word of claim. It refuses the headline-over-a-screenshot opener and the split
hero with copy on one side.

OWN-WORLD: Galley stock ground, Proof Sheet and Margin Tint surfaces, Proof Ink
and Graphite words, the two pencils (red: what a sync sends and the one filled
button; blue: the reader's choice or a question), Tick Green for up to date.
Schibsted Grotesk 800 for headings, 400/600 for everything else; Source Serif 4
600 for book titles only. Square-cut 2 to 4px corners, 1px rules, the 3px double
rule at the margin. The Kobo drawn from the icon's own device drawing (dark body,
the e-ink in the icon's own EINK_TOP/EINK_BOTTOM, art.py: a Clara's warm
grey paper, not the page's Margin Tint; its greys darkened to 4.5:1). The
site's own type scale, a page read once from a chair: 1rem body and lede,
a fluid h1 to 2.1rem and h2 to 2.1rem, 1.1rem name in the head, 11px on
the device's running head and facts. Light and dark share every role.

STORY: Sees their own device with a book on it, reads the mark beside it,
understands in one glance that the Kobo's reading goes to Hardcover and that the
page shows before it sends. Downloads the Mac app. Scrolls to the two printed
lights of the page, the Mac app's window, the four steps from plug-in to shelf,
what it does not do, the other tools, the independent sentence.

FIRST VIEWPORT: Two fifths left: the Kobo at 18rem (288px) wide on a desk, its
screen the last page of Middlemarch (running head, the Finale's opening lines,
the line gauge full, "100%, finished 21 Sep"); under the device the headline in
two short lines at 2.1rem ("Your Kobo knows what you read. Now Hardcover does
too."), the red Download for Mac button with the live version under it in small
type and the brew and uv commands beside it. Three fifths right: the proof margin
behind its double rule, four sample books with their marks: Next sync (struck
"Currently reading, 88%", caret "Read, 21 Sep 2026"), Up to date (Moby-Dick 37%),
Needs you (De avonden), Not syncing (Bleak House, history switched off). One red
stroke from the end of the gauge into the first mark, there without JavaScript
(a path for the desk layout, stretched with it), measured and drawn once on load
with JavaScript (1.2s, ease-out), static under reduced motion. Below 1024px the
Kobo and the margin stack, the button stays within the first screen on a 390 by
844 phone and at 1280 by 800.

FORM: The e-ink page, structure 7 of 7 on my ordered list, dealt to lead by
concept seed 795e9dc3 (surface scope, persuade). Raised by the declined hand: the
two lights as two pulls (silkscreen loft), one continuous stroke (neon circuit),
the change visible before it happens (algorave), the step strip that scales and
never wraps (drum machine), sections as blocks with deep gaps (cloud quarry).
Code-led: no image generation in this harness.

FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.

## Unresolved

- The Mac app's window picture: the snapshot render was not fit for a public
  page; the app is shown by its icon and words, and the page says a picture
  follows. The owner is asked for real screenshots of their window.
- GitHub Pages is not switched on for the repository; the owner decides when.
