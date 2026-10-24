// Books, in local mode (docs/plans/2026-10-24-mac-app-native-books-design.md,
// step 2): the page's list drawn here, from `books --json`. Searching,
// filtering and sorting happen in the app, on what the tool said; what a
// sync does with a book is still decided in the tool. A change opens the
// page at the book, until changing books comes here too.

import AppKit
import CoreText
import SwiftUI

/// Source Serif 4 for book titles: the page's own font, in the tool's package inside the app.
func registerTitleFont() {
    let lib = Bundle.main.resourceURL?.appendingPathComponent("python/lib")
    let python = (try? FileManager.default.contentsOfDirectory(atPath: lib?.path ?? ""))?.first { $0.hasPrefix("python3.") }
    guard let lib, let python else { return }
    let fonts = lib.appendingPathComponent(python).appendingPathComponent("site-packages/kobo_hardcover_sync/web/static/fonts")
    for file in ["SourceSerif4-latin.woff2", "SourceSerif4-latin-ext.woff2"] {
        CTFontManagerRegisterFontsForURL(fonts.appendingPathComponent(file) as CFURL, .process, nil)
    }
}

/// A book title: Source Serif 4, else the serif macOS has.
func titleFont(_ size: CGFloat, _ weight: Font.Weight = .semibold) -> Font {
    NSFontManager.shared.availableMembers(ofFontFamily: "Source Serif 4") != nil
        ? .custom("Source Serif 4", size: size).weight(weight) : .system(size: size, weight: weight, design: .serif)
}

extension WindowModel {
    /// The books of the list as chosen: the search, then the filter, in the sort's order.
    var shownBooks: [BooksAnswer.Book] {
        guard let answer = books else { return [] }
        let order = answer.sorts.first { $0.key == sort }?.order ?? Array(answer.books.indices)
        return order.compactMap { answer.books.indices.contains($0) ? answer.books[$0] : nil }
            .filter { found($0) && $0.filters.contains(filter) }
    }

    /// How many books each filter holds, with the search as it is.
    var filterCounts: [String: Int] {
        var out: [String: Int] = [:]
        for book in books?.books ?? [] where found(book) {
            for f in book.filters { out[f, default: 0] += 1 }
        }
        return out
    }

    private func found(_ book: BooksAnswer.Book) -> Bool {
        let q = search.trimmingCharacters(in: .whitespaces)
        return q.isEmpty || [book.title, book.author].contains { $0.range(of: q, options: [.caseInsensitive, .diacriticInsensitive]) != nil }
    }

    func word(_ list: [[String]]?, _ key: String) -> String {
        list?.first { $0.first == key }?.last ?? key
    }
}

struct BooksPane: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        if let books = model.books {
            HStack(spacing: 0) {
                VStack(spacing: 0) {
                    BooksBar(model: model, words: books.words)
                    Divider()
                    if books.books.isEmpty {
                        Spacer()
                        Text("No books yet: nothing was read from a Kobo so far. Plug it in.").foregroundStyle(.secondary)
                        Spacer()
                    } else {
                        BooksTable(model: model)
                    }
                }
                .frame(minWidth: 440, maxWidth: .infinity)
                if let id = model.chosenBook, let book = books.books.first(where: { $0.id == id }) {
                    Divider()
                    DetailsPane(model: model, book: book, words: books.words).frame(width: 300)
                }
            }
        } else if let broken = model.booksBroken {
            Form { Section { Row(state: "fail", what: "Books", found: broken) } }.formStyle(.grouped)
        } else {
            VStack {
                Spacer()
                ProgressView().controlSize(.small)
                Spacer()
            }
            .frame(maxWidth: .infinity)
        }
    }
}

/// Search, the page's filters and its sort, then the legend of the marks.
struct BooksBar: View {
    @ObservedObject var model: WindowModel
    let words: BooksAnswer.Words

    var body: some View {
        let counts = model.filterCounts
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {  // on one line, or the search above the choices
                HStack(spacing: 10) {
                    search.frame(minWidth: 160, maxWidth: 260)
                    choices(counts)
                    Spacer(minLength: 0)
                }
                VStack(alignment: .leading, spacing: 8) {
                    search
                    HStack(spacing: 10) { choices(counts) }
                }
            }
            Legend(legend: words.legend)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var search: some View {
        TextField("Search title or author", text: $model.search).textFieldStyle(.roundedBorder)
    }

    @ViewBuilder private func choices(_ counts: [String: Int]) -> some View {
        Picker("Show", selection: $model.filter) {
            ForEach(words.filters, id: \.group) { group in
                Section(group.group) {
                    ForEach(group.keys, id: \.self) { key in
                        Text("\(key.last ?? "") (\(counts[key.first ?? ""] ?? 0))").tag(key.first ?? "")
                    }
                }
            }
        }
        .fixedSize()
        Picker("Sort", selection: $model.sort) {
            ForEach(model.books?.sorts ?? [], id: \.key) { sort in Text(sort.label).tag(sort.key) }
        }
        .fixedSize()
    }
}

/// Every mark the list can hold, with what it means (the page's Legend Rule).
struct Legend: View {
    let legend: [[String]]

    var body: some View {
        Flow(spacing: 14, lineSpacing: 4) {
            ForEach(legend, id: \.self) { item in
                HStack(spacing: 4) {
                    Mark(state: item.first ?? "", size: 14)
                    Text(item.last ?? "")
                }
                .fixedSize()
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .accessibilityElement(children: .combine)
    }
}

/// Items side by side, on as many lines as the width needs.
struct Flow: Layout {
    var spacing: CGFloat
    var lineSpacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let rows = lines(subviews, width)
        let height = rows.reduce(0) { $0 + $1.height } + lineSpacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width ?? rows.map(\.width).max() ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in lines(subviews, bounds.width) {
            var x = bounds.minX
            for n in row.items {
                let size = subviews[n].sizeThatFits(.unspecified)
                subviews[n].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: .unspecified)
                x += size.width + spacing
            }
            y += row.height + lineSpacing
        }
    }

    private func lines(_ subviews: Subviews, _ width: CGFloat) -> [(items: [Int], width: CGFloat, height: CGFloat)] {
        var out: [(items: [Int], width: CGFloat, height: CGFloat)] = []
        for (n, view) in subviews.enumerated() {
            let size = view.sizeThatFits(.unspecified)
            if let last = out.last, last.width + spacing + size.width <= width {
                out[out.count - 1] = (last.items + [n], last.width + spacing + size.width, max(last.height, size.height))
            } else {
                out.append(([n], size.width, size.height))
            }
        }
        return out
    }
}

struct BooksTable: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        let words = model.books?.words
        Table(model.shownBooks, selection: $model.chosenBook) {
            TableColumn("Book") { book in BookCell(book: book) }
                .width(min: 180, ideal: 260)
            TableColumn("Sync") { book in
                Text(model.word(words?.syncs, book.sync)).foregroundStyle(book.syncs ? .primary : .secondary)
            }
            .width(min: 44, ideal: 64, max: 90)
            TableColumn("State") { book in
                VStack(alignment: .leading, spacing: 1) {
                    Text(model.word(words?.states, book.state))
                    if !book.stateDate.isEmpty { Text(book.stateDate).font(.caption).foregroundStyle(.secondary) }
                }
            }
            .width(min: 70, ideal: 96, max: 150)
            TableColumn("Hardcover status") { book in StatusCell(book: book) }
                .width(min: 150, ideal: 220)
        }
        .contextMenu(forSelectionType: String.self) { ids in
            if let id = ids.first { Button("Change on the Page") { openAt(id) } }
        } primaryAction: { ids in
            if let id = ids.first { openAt(id) }
        }
    }
}

/// The page, at this book: where it is changed until the app can.
func openAt(_ id: String) {
    DispatchQueue.global(qos: .userInitiated).async { _ = tool(["open", "--book", id]) }
}

struct BookCell: View {
    let book: BooksAnswer.Book

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Cover(path: book.cover, width: 32)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(book.title).font(titleFont(14)).lineLimit(2)
                    if book.new {
                        Text("New").font(.caption2.weight(.semibold)).foregroundStyle(Pencil.blue)
                            .padding(.horizontal, 4).overlay(RoundedRectangle(cornerRadius: 3).stroke(Pencil.blue, lineWidth: 0.75))
                    }
                }
                Text(book.author).font(.callout).foregroundStyle(.secondary).lineLimit(1)
                Gauge(percent: book.percent, finished: book.finished)
                Text(book.facts.joined(separator: " · ")).font(.caption.monospacedDigit()).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

/// The page's line gauge: a rule with a tick every tenth, the part read in ink.
struct Gauge: View {
    let percent: Int
    let finished: Bool

    var body: some View {
        Canvas { context, box in
            let w = box.width
            var rule = Path()
            rule.move(to: CGPoint(x: 0, y: 4.5))
            rule.addLine(to: CGPoint(x: w, y: 4.5))
            for n in 0...10 {
                rule.move(to: CGPoint(x: (w - 1) * CGFloat(n) / 10 + 0.5, y: n == 10 ? 1 : 2.5))
                rule.addLine(to: CGPoint(x: (w - 1) * CGFloat(n) / 10 + 0.5, y: 4.5))
            }
            context.stroke(rule, with: .color(Pencil.edge), lineWidth: 1)
            let read = CGRect(x: 0, y: 3.5, width: w * CGFloat(finished ? 100 : percent) / 100, height: 2)
            context.fill(Path(read), with: .color(finished ? Pencil.green : .primary))
        }
        .frame(maxWidth: 160)
        .frame(height: 6)
        .accessibilityLabel(finished ? "Finished" : "\(percent)%")
    }
}

/// A cover from the tool's cache, or the crossed box of a book without one.
struct Cover: View {
    let path: String
    let width: CGFloat
    private static var cache: [String: NSImage] = [:]

    var body: some View {
        Group {
            if let image = Self.image(path) {
                Image(nsImage: image).resizable().aspectRatio(contentMode: .fill)
            } else {
                Canvas { context, box in
                    var cross = Path(CGRect(origin: .zero, size: box).insetBy(dx: 0.5, dy: 0.5))
                    cross.move(to: .zero)
                    cross.addLine(to: CGPoint(x: box.width, y: box.height))
                    cross.move(to: CGPoint(x: box.width, y: 0))
                    cross.addLine(to: CGPoint(x: 0, y: box.height))
                    context.stroke(cross, with: .color(Pencil.edge), lineWidth: 1)
                }
            }
        }
        .frame(width: width, height: width * 1.5)
        .clipShape(RoundedRectangle(cornerRadius: 2))
        .accessibilityHidden(true)
    }

    private static func image(_ path: String) -> NSImage? {
        guard !path.isEmpty else { return nil }
        if let kept = cache[path] { return kept }
        let image = NSImage(contentsOfFile: path)
        cache[path] = image
        return image
    }
}

/// The Hardcover status: its mark and words; for a change, the old value
/// struck in red and the new one after a caret; then the edition.
struct StatusCell: View {
    let book: BooksAnswer.Book

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Mark(state: book.status.kind, size: 16).padding(.top, 1)
            VStack(alignment: .leading, spacing: 2) {
                Text(headline).font(.callout.weight(book.status.kind == "next" ? .semibold : .regular))
                    .foregroundStyle(book.status.kind == "next" ? Pencil.red : book.status.kind == "none" ? .secondary : .primary)
                if book.status.kind == "next" { Correction(book: book) }
                if !book.edition.isEmpty {
                    HStack(spacing: 4) {
                        if book.stet { Mark(state: "stet", size: 14) }
                        Text(book.edition).lineLimit(1)
                    }
                    .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([book.status.text, book.edition].filter { !$0.isEmpty }.joined(separator: ". "))
    }

    /// "Next sync", not "Next sync: …": the correction says the rest.
    private var headline: String {
        book.status.kind == "next" ? String(book.status.text.split(separator: ":", maxSplits: 1).first ?? "") : book.status.text
    }
}

struct Correction: View {
    let book: BooksAnswer.Book

    var body: some View {
        let rest = book.status.text.split(separator: ":", maxSplits: 1).dropFirst().first.map { $0.trimmingCharacters(in: .whitespaces) } ?? ""
        let (kept, was, now) = book.correction.count == 3 ? (book.correction[0], book.correction[1], book.correction[2]) : ("", "", rest)
        HStack(spacing: 4) {
            if !kept.isEmpty { Text(kept) }
            if !was.isEmpty { Text(was).strikethrough(color: Pencil.red).foregroundStyle(.secondary) }
            Mark(state: "next", size: 10)
            Text(now).foregroundStyle(Pencil.red)
        }
        .font(.callout)
        .lineLimit(1)
    }
}

/// Everything known of one book, as the page's Details has it; changing it opens the page.
struct DetailsPane: View {
    @ObservedObject var model: WindowModel
    let book: BooksAnswer.Book
    let words: BooksAnswer.Words

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 12) {
                    Cover(path: book.cover, width: 56)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(book.title).font(titleFont(18)).fixedSize(horizontal: false, vertical: true)
                        Text(book.author).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Button {
                        model.chosenBook = nil
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .buttonStyle(.borderless)
                    .keyboardShortcut(.cancelAction)
                    .accessibilityLabel("Close Details")
                }
                StatusCell(book: book)
                pairs(words.sections.first ?? "", book.details.kobo)
                pairs(words.sections.last ?? "", book.details.hardcover)
                if !book.details.candidates.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Could be").font(.headline)
                        ForEach(Array(book.details.candidates.enumerated()), id: \.offset) { _, c in
                            Text("\(c.title), \(c.author)").font(.callout)
                        }
                    }
                }
                HStack {
                    Button("Change on the Page") { openAt(book.id) }
                    if let link = URL(string: book.details.link), !book.details.link.isEmpty {
                        Button("Open on Hardcover") { NSWorkspace.shared.open(link) }
                    }
                }
            }
            .padding(16)
            .textSelection(.enabled)
        }
    }

    @ViewBuilder private func pairs(_ title: String, _ pairs: [[String]]) -> some View {
        if !pairs.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.headline)
                ForEach(pairs, id: \.self) { pair in
                    HStack(alignment: .firstTextBaseline) {
                        Text(pair.first ?? "").foregroundStyle(.secondary).frame(width: 96, alignment: .leading)
                        Text(pair.last ?? "").fixedSize(horizontal: false, vertical: true)
                    }
                    .font(.callout)
                }
            }
        }
    }
}
