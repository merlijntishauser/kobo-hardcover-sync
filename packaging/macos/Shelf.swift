// The widget's shelf (docs/plans/2026-10-26-mac-app-server-books-and-covers-design.md,
// step 5): the book being read and the tip, as the app last saw them, with
// their covers. The widget is sandboxed and cannot read the tool's folder,
// so the app leaves them in the app group's folder, which both may use.
// The group is the one the signature names (sign.sh): an app signed ad hoc
// has none, and keeps no shelf.

import Foundation
import Security
import WidgetKit

struct Shelf: Codable, Equatable {
    struct Book: Codable, Equatable {
        let id: String
        let title: String
        let author: String
        let percent: Int
        let finished: Bool
        let facts: [String]
        let cover: String  // a file in the shelf's folder, "" for none
    }

    struct Tip: Codable, Equatable {
        let book: Book
        let text: String
    }

    var reading: Book?
    var tip: Tip?
    var empty = false  // set up, and no book read from a Kobo yet
}

/// The book being read: the most recently read that is started and not finished.
func readingNow(_ books: [BooksAnswer.Book]) -> BooksAnswer.Book? {
    books.filter { !$0.finished && $0.percent > 0 }.max { $0.lastRead < $1.lastRead }
}

/// The app group's folder, when this app or widget is signed with one.
func shelfFolder() -> URL? {
    guard let task = SecTaskCreateFromSelf(nil),
        let groups = SecTaskCopyValueForEntitlement(task, "com.apple.security.application-groups" as CFString, nil) as? [String],
        let group = groups.first
    else { return nil }
    return FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group)
}

/// What the widget shows; nil before the app kept a shelf.
func readShelf() -> Shelf? {
    guard let folder = shelfFolder(), let data = try? Data(contentsOf: folder.appendingPathComponent("shelf.json")) else { return nil }
    return try? JSONDecoder().decode(Shelf.self, from: data)
}

/// The shelf as these books have it, for the widget; only when it changed.
func keepShelf(_ books: [BooksAnswer.Book], tip: BooksAnswer.Tip?) {
    guard let folder = shelfFolder() else { return }
    try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    // A cover keeps the name of the tool's cached file, so the widget never shows one under another's name.
    func kept(_ book: BooksAnswer.Book) -> Shelf.Book {
        let file = book.cover.isEmpty ? "" : "cover-" + URL(fileURLWithPath: book.cover).lastPathComponent
        let to = folder.appendingPathComponent(file)
        let there = !file.isEmpty
            && (FileManager.default.fileExists(atPath: to.path)
                || (try? FileManager.default.copyItem(at: URL(fileURLWithPath: book.cover), to: to)) != nil)
        return Shelf.Book(
            id: book.id, title: book.title, author: book.author, percent: book.percent, finished: book.finished, facts: book.facts,
            cover: there ? file : "")
    }
    var shelf = Shelf(empty: books.isEmpty)
    shelf.reading = readingNow(books).map(kept)
    if let tip, let book = books.first(where: { $0.id == tip.id }) {
        shelf.tip = Shelf.Tip(book: kept(book), text: tip.text)
    }
    let used = Set(["shelf.json", shelf.reading?.cover ?? "", shelf.tip?.book.cover ?? ""])
    for file in (try? FileManager.default.contentsOfDirectory(atPath: folder.path)) ?? [] where file.hasPrefix("cover-") && !used.contains(file) {
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(file))
    }
    guard shelf != readShelf(), let data = try? JSONEncoder().encode(shelf) else { return }
    try? data.write(to: folder.appendingPathComponent("shelf.json"), options: .atomic)
    WidgetCenter.shared.reloadAllTimelines()
}

/// No shelf any more: the app was removed from this Mac.
func forgetShelf() {
    guard let folder = shelfFolder() else { return }
    for file in (try? FileManager.default.contentsOfDirectory(atPath: folder.path)) ?? [] where file == "shelf.json" || file.hasPrefix("cover-") {
        try? FileManager.default.removeItem(at: folder.appendingPathComponent(file))
    }
    WidgetCenter.shared.reloadAllTimelines()
}
