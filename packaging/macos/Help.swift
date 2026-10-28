// The app's guide (Help, ⌘?): what each pane is for, the marks, the keys and
// what to do when something is wrong, on the overview's paper. Written for the
// reader, not the developer: docs/macos-app.md is how the app is built.

import AppKit
import SwiftUI

/// A line of the guide: a paragraph, a word explained, a mark explained, or a key.
enum HelpLine: Hashable {
    case say(String)
    case term(String, String)
    case mark(String, String, String)  // the tool's state, its name, what it means
    case key(String, String)

    var words: String {
        switch self {
        case .say(let a): return a
        case .term(let a, let b), .key(let a, let b): return a + " " + b
        case .mark(_, let a, let b): return a + " " + b
        }
    }
}

struct HelpTopic: Identifiable {
    let id: String  // its title
    let symbol: String
    let lines: [HelpLine]
}

let helpTopics: [HelpTopic] = [
    HelpTopic(id: "How it works", symbol: "book.closed", lines: [
        .say("\(name) reads your reading from your Kobo and keeps Hardcover in step with it: which books you are reading, how far you are, and what you finished when."),
        .say("Plug in the Kobo and it syncs by itself, whether this window is open or not. A notification says what it did."),
        .term("Dry run", "Until you go live, nothing is sent: Books shows what would be. Go live in Settings, Sync, when that looks right. With a server, you go live on the server's page."),
        .term("Matches", "A book it cannot place on Hardcover by ISBN, or by title and author together, waits for you to choose. It never guesses."),
        .term("Your Kobo", "Nothing on it is changed, except a collection of the books that sync, and only if you give that collection a name."),
    ]),
    HelpTopic(id: Pane.overview.rawValue, symbol: Pane.overview.symbol, lines: [
        .say("The overview draws the way a sync goes: from your Kobo, through this Mac and your server if you use one, to Hardcover. Each link has its mark, and the arrows carry the books."),
        .say("Click a link for its checks: what each found, and what to do about it. The first link that needs you opens by itself."),
        .term("Sync Now", "Runs a sync now, without waiting for the Kobo to be plugged in (⌘R)."),
        .term("Check Again", "Runs the checks again, after you fixed something (⇧⌘R)."),
    ]),
    HelpTopic(id: Pane.books.rawValue, symbol: Pane.books.symbol, lines: [
        .say("Every book the Kobo has seen opened, with what goes to Hardcover. Search finds a title or author; Show picks one filter at a time; Sort puts them in order."),
        .term("Sync: On", "This book goes to Hardcover."),
        .term("Sync: Off", "It does not. Books that were on the Kobo before \(name) started begin as Off, so you can pick yours."),
        .term("Sync: Auto", "A book you open on this Kobo from now on syncs by itself; switch it Off if it is not yours."),
        .term("State: Follow Kobo", "Hardcover gets what the Kobo says: reading with progress, or finished."),
        .term("State: Finished", "Counts as read on that date, even if the Kobo shows a few percent because you opened it again."),
        .term("State: Re-reading", "A new read-through of a book you finished before."),
        .term("Want to read, Did not finish", "Hardcover keeps that status, and nothing is sent until you set Follow Kobo again. A status you set on Hardcover shows up here as the matching State."),
        .term("Details", "Select a book for what the Kobo and Hardcover each have, its dates and edition, and its match. A book without one lists the books it could be, and lets you look for others."),
        .term("The tip", "Above the list, one book of yours with a question about it."),
    ]),
    HelpTopic(id: "The marks", symbol: "checkmark.circle", lines: [
        .say("The Hardcover status is marked the way a proofreader marks a page: what the next sync changes, and what it leaves alone. The overview and History use the same marks."),
        .mark("next", "Red caret", "The next sync sends this. What Hardcover has now is struck through; what it gets follows the caret. In a dry run, the caret shows what would be sent."),
        .mark("wait", "Dashed caret", "The book is switched on but unread, so there is nothing to send yet."),
        .mark("ok", "Tick", "Up to date on Hardcover; on the overview, in order."),
        .mark("stet", "stet", "Kept as it is on Hardcover: an edition you chose there wins over the one \(name) would pick. Stet is Latin for “let it stand”."),
        .mark("warn", "Circled question mark", "Needs you: a book without a match, or a check with something to do."),
        .mark("fail", "Black square", "A problem: the last sync failed for this book, or a check failed. Details, or the check, says why."),
        .mark("note", "Dash", "Not syncing, or a note."),
    ]),
    HelpTopic(id: Pane.covers.rawValue, symbol: Pane.covers.symbol, lines: [
        .say("Your books as covers, in three rows that drift by: in front the books you read in the last year, behind them the rest you read, at the back the ones never opened. Show picks the same filters as Books."),
        .term("Point at a cover", "It lifts, with its title and status under it. Click it to open the book."),
        .term("The trackpad", "Two fingers move the rows; they drift again a few seconds later."),
        .term("A cover large", "Space, or a click on the cover in a book, shows it over the window. Its corner button, or F, puts it on black over the whole screen. A click or a key puts it back."),
    ]),
    HelpTopic(id: Pane.history.rawValue, symbol: Pane.history.symbol, lines: [
        .say("The last syncs on this Mac, newest first: when, what started it, and what it said. The last hundred are kept, without book titles."),
        .term("Show the Log", "Opens agent.log in Console: what each sync did, in counts and messages."),
    ]),
    HelpTopic(id: "Keys", symbol: "keyboard", lines: [
        .key("⌘R", "Sync now"),
        .key("⇧⌘R", "Check again"),
        .key("⌘1 to ⌘4", "Overview, Books, Covers, History"),
        .key("⌃⌘S", "Show or hide the sidebar"),
        .key("⌃⌘F", "Full screen"),
        .key("⌘,", "Settings"),
        .key("⌘?", "This guide"),
        .key("← → ↑ ↓", "Covers: pick a cover, along a row and between rows"),
        .key("Return", "Covers: open the book"),
        .key("Space", "Covers: the cover large, and back"),
        .key("F", "A cover large: over the whole screen"),
        .key("Escape", "Close a book, or put a cover back"),
    ]),
    HelpTopic(id: "When something is wrong", symbol: "lifebuoy", lines: [
        .say("Start with the overview. A link with the question mark or the black square opens its checks, and each says what to do."),
        .term("Nothing happens when the Kobo is plugged in", "Tap Connect on the Kobo. If the Kobo's check says macOS does not let the app read it, do what the check says, then plug it in again."),
        .term("The Kobo's database is in use", "Close Calibre, the Kobo desktop app or anything else that reads the Kobo, and plug it in again."),
        .term("Nothing new", "The Kobo is as it was at the last sync. Read a page, and plug it in again."),
        .term("Needs a Hardcover match", "Open the book's Details and choose the right book, or look for it there."),
        .term("Hardcover could not be reached", "Nothing is lost: the next sync carries on."),
        .term("Hardcover no longer accepts the connection", "It was ended on Hardcover, or went unused for six months. Connect again in Settings, Sync."),
        .term("Something it did not expect", "A bug. Show the Log has the details; please report it, with what the overview's checks say."),
        .say("The log holds counts and messages, never book titles or tokens."),
    ]),
    HelpTopic(id: "Updates", symbol: "arrow.down.circle", lines: [
        .say("At most once a day, after a sync, the app asks GitHub for the latest version. When one is out, the overview says so; Check for Updates… in the app menu asks at once."),
        .term("Install and Restart", "Downloads the new version, installs it only when it is signed and notarised as this one is, puts it in this one's place and starts it."),
        .term("Look for a newer version", "In Settings, App: off, and the app never asks."),
    ]),
]

struct HelpView: View {
    @State private var chosen: String? = helpTopics.first?.id
    @State private var search = ""

    private var shown: [HelpTopic] {
        let q = search.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return helpTopics }
        return helpTopics.filter { topic in
            topic.id.localizedCaseInsensitiveContains(q) || topic.lines.contains { $0.words.localizedCaseInsensitiveContains(q) }
        }
    }

    var body: some View {
        NavigationSplitView {
            List(shown, selection: $chosen) { topic in
                Label(topic.id, systemImage: topic.symbol).tag(topic.id)
            }
            .navigationSplitViewColumnWidth(min: 180, ideal: 200)
        } detail: {
            if let topic = shown.first(where: { $0.id == chosen }) ?? shown.first {
                HelpPage(topic: topic, search: search)
            } else {
                Galley { Text("Nothing in the guide says “\(search)”.").foregroundStyle(Pencil.graphite) }
            }
        }
        .searchable(text: $search, placement: .sidebar, prompt: "Search the guide")
        .frame(minWidth: 680, minHeight: 440)
    }
}

/// A topic on a proof sheet; while searching, only its lines that say the words.
struct HelpPage: View {
    let topic: HelpTopic
    let search: String

    var body: some View {
        let q = search.trimmingCharacters(in: .whitespaces)
        let lines = q.isEmpty || topic.id.localizedCaseInsensitiveContains(q) ? topic.lines : topic.lines.filter { $0.words.localizedCaseInsensitiveContains(q) }
        Galley {
            SheetHead(topic.id)
            ProofSheet {
                ForEach(Array(lines.enumerated()), id: \.offset) { n, line in
                    if n > 0 { SoftRule() }
                    HelpLineView(line: line).onSheet()
                }
            }
        }
    }
}

struct HelpLineView: View {
    let line: HelpLine

    var body: some View {
        switch line {
        case .say(let text):
            Text(text).foregroundStyle(Pencil.ink).lineSpacing(2).fixedSize(horizontal: false, vertical: true)
        case .term(let term, let text):
            VStack(alignment: .leading, spacing: 2) {
                Text(term).fontWeight(.medium).foregroundStyle(Pencil.ink)
                Text(text).foregroundStyle(Pencil.graphite).lineSpacing(2).fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .combine)
        case .mark(let state, let term, let text):
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Mark(state: state).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 4 }.accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(term).fontWeight(.medium).foregroundStyle(Pencil.ink)
                    Text(text).foregroundStyle(Pencil.graphite).lineSpacing(2).fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)
        case .key(let keys, let text):
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(keys).font(.body.monospacedDigit().weight(.medium)).foregroundStyle(Pencil.ink)
                    .frame(width: 96, alignment: .leading)
                Text(text).foregroundStyle(Pencil.graphite).fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .combine)
        }
    }
}
