// What the tool answers (`status --json`, `doctor --json`, `books --json`,
// `book --json`, `history --json`, `settings --json`, `update --json`,
// `token --json`, `sync --steps`), as the app reads it. The samples in
// packaging/macos/samples have the same shape: tests/test_app_answers.py
// holds the tool to them, CheckSamples.swift holds these types to them.
//
// Foundation only, so that CI can compile it without the app.

import Foundation

/// The schema this app reads; the tool raises it when a field changes meaning.
let schema = 1

struct Sync: Codable, Equatable, Identifiable {
    let at: String  // ISO 8601, with the offset
    let trigger: String  // "mount", "app", "hand", or "" before there was a history
    let ok: Bool
    let title: String
    let message: String

    var id: String { at + trigger + title }
    var date: Date? { ISO8601DateFormatter().date(from: at) }
}

struct StatusAnswer: Codable {
    let schema: Int
    let version: String
    let mode: String  // "server", "local", or "" before setup
    let server: String
    let folder: String
    let kobo: String?  // where it is mounted, when one is plugged in
    let lastSync: Sync?
    let syncing: String?  // what started the sync that runs now in another process ("mount", "app", "hand"); "" when none
    var books: Books?  // local mode, once a Kobo was read: the books are on this Mac

    /// The books in counts, for the overview's arrows.
    struct Books: Codable {
        let total: Int
        let on: Int  // switched on
        let next: Int  // what the next sync changes on Hardcover (or, in a dry run, would)
        let needsMatch: Int
        let live: Bool
        let user: String  // the Hardcover account, "" before connecting
        let collection: String  // the collection on the Kobo, "" for none
    }
}

struct Check: Codable, Equatable, Identifiable {
    let group: String
    let what: String
    let state: String  // "ok", "note", "warn", "fail"
    let found: String
    let todo: String

    var id: String { group + what }
}

struct DoctorAnswer: Codable {
    let schema: Int
    let version: String
    let summary: String
    let problems: Int
    let checks: [Check]
}

/// `books --json`: every book with its row and its Details, in the page's
/// words; searching, filtering and sorting happen in the app.
struct BooksAnswer: Codable {
    struct Book: Codable, Identifiable {
        let id: String
        let title: String
        let author: String
        let cover: String  // the cached thumbnail, "" while there is none
        let new: Bool  // first opened after this tool first saw the Kobo: the Auto tag
        let percent: Int
        let finished: Bool
        let opened: Bool  // ever opened on the Kobo (not its last read date: the Kobo sets that on unopened books too)
        let facts: [String]  // "37%", "last read 2 Oct 2026", "4 h read"
        let lastRead: String
        var sync: String  // "auto", "on", "off"; var: shown at once while the tool changes it
        let syncs: Bool
        var state: String
        var stateDate: String
        let status: Status
        let correction: [String]  // kept, struck, inserted; [] when the next sync changes nothing on the shelf
        let edition: String
        let stet: Bool  // the edition was chosen on Hardcover: kept as it is
        let filters: [String]
        let details: Details
    }

    struct Status: Codable {
        let kind: String  // a mark: "ok", "next", "wait", "warn", "err", "none"
        let text: String
    }

    struct Details: Codable {
        struct Candidate: Codable {
            let id: Int  // the book on Hardcover
            let title: String
            let author: String
        }

        let kobo: [[String]]  // label, value
        let hardcover: [[String]]
        let link: String
        let candidates: [Candidate]
        let onShelf: Bool
    }

    /// Getting started (start.py): the four steps from a new reader to a live
    /// shelf, the same as above the page's books; nil once live with books.
    struct Start: Codable {
        struct Step: Codable, Identifiable {
            let key: String  // "connect", "kobo", "books", "live"
            let n: Int
            let title: String
            let text: String
            let state: String  // "done", "now" (the first not done), "later"
            let action: String  // "connect", "server_page", "show_books", "go_live", or ""

            var id: String { key }
        }

        let title: String
        let on: Int  // switched on so far
        let tally: String  // "switched on so far."
        let canGoLive: Bool  // connected: Go live can be chosen
        let steps: [Step]
    }

    /// Once live, the books switched on that wait for you (start.py); nil when none do.
    struct NeedsYou: Codable {
        let n: Int
        let match: Int  // without a Hardcover match: the filter Needs a match
        let failed: Int  // not sent at the last sync
        let text: String
    }

    /// One book from your own shelf, as a question (tip.py); nil when no rule finds one.
    struct Tip: Codable {
        let id: String
        let rule: String  // "left_off", "wanted", "never_opened"
        let text: String
    }

    struct Sort: Codable {
        let key: String
        let label: String
        let order: [Int]  // places in books
    }

    struct Words: Codable {
        struct Group: Codable {
            let group: String
            let keys: [[String]]  // key, label
        }

        let filters: [Group]
        let sections: [String]  // Details: on the Kobo, on Hardcover
        let syncs: [[String]]
        let states: [[String]]
        let legend: [[String]]  // mark, what it means
    }

    let schema: Int
    let live: Bool
    let user: String
    var start: Start?  // nil once live; nil also from a server before 0.18.0
    var needsYou: NeedsYou?
    var tip: Tip?
    var books: [Book]
    let sorts: [Sort]
    let words: Words
}

/// `book ID ... --json`: the book after a change, and the counts the overview shows.
struct BookAnswer: Codable {
    let schema: Int
    let book: BooksAnswer.Book
    let books: StatusAnswer.Books
    let tip: BooksAnswer.Tip?  // a change can make another book the tip
    let start: BooksAnswer.Start?  // and move Getting started on
    let needsYou: BooksAnswer.NeedsYou?
    let large: String?  // with --large-cover: the cover large, "" when there is none
}

struct HistoryAnswer: Codable {
    let schema: Int
    let syncs: [Sync]
}

struct SettingsAnswer: Codable {
    struct Values: Codable {
        let ejectAfterSync: Bool
        let verboseLog: Bool
        let allowUntestedKobo: Bool
        let checkForUpdates: Bool
        let exportTo: String
        let webhookUrl: String
    }

    let schema: Int
    let mode: String
    let server: String
    let uploadTokenHash: String
    let hardcoverConnected: Bool
    let hardcoverUser: String
    let live: Bool  // local mode: sending to Hardcover, not a dry run
    let settings: Values
}

struct UpdateAnswer: Codable {
    let schema: Int
    let version: String
    let latest: String  // "" when GitHub never said
    let newer: Bool
    let link: String
    let problem: String  // GitHub did not answer this time
}

/// One line of `sync --steps`: a step as it finishes, or, last, the outcome.
struct StepLine: Codable {
    struct Done: Codable {
        /// A book the sync marked Read on Hardcover: a notification of its own, with its cover.
        struct Finished: Codable {
            let title: String
            let cover: String  // its file, "" without one
        }

        let ok: Bool
        let title: String
        let message: String
        var finished: [Finished]? = nil  // nil from a tool before 0.15.0
    }

    let schema: Int
    let step: String?
    let state: String?
    let text: String?
    let done: Done?
}

/// One line of `token --json`: where to approve (with a code to compare,
/// in the device flow), or, last, how it ended.
struct TokenLine: Codable {
    struct Done: Codable {
        let ok: Bool
        let user: String
        let message: String
    }

    let schema: Int
    let open: String?
    let code: String?
    let done: Done?
}

enum AnswerError: Error {
    case otherSchema(Int)
}

/// An answer of the tool, or nil with why not. A line that is not JSON (a
/// warning on stderr) is not an answer.
func decode<T: Codable>(_ type: T.Type, _ text: String) -> Result<T, Error> {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    do {
        let data = Data(text.utf8)
        let found = try decoder.decode(SchemaOnly.self, from: data).schema
        guard found == schema else { return .failure(AnswerError.otherSchema(found)) }
        return .success(try decoder.decode(T.self, from: data))
    } catch {
        return .failure(error)
    }
}

private struct SchemaOnly: Codable {
    let schema: Int
}
