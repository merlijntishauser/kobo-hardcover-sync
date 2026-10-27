// Books, in local mode (docs/plans/2026-10-24-mac-app-native-books-design.md,
// steps 2 and 3): the page's list drawn here, from `books --json`.
// Searching, filtering and sorting happen in the app, on what the tool
// said; a change (Sync, State, a match, removal, Set all) goes through the
// tool (`book ID ...`, `books --sync ...`), which answers the book as it
// is then. What a sync does with a book is still decided in the tool.

import AppKit
import SwiftUI

/// The title font from the tool's package in the app (Paper.swift).
func registerTitleFont() {
    let lib = Bundle.main.resourceURL?.appendingPathComponent("python/lib")
    let python = (try? FileManager.default.contentsOfDirectory(atPath: lib?.path ?? ""))?.first { $0.hasPrefix("python3.") }
    guard let lib, let python else { return }
    registerTitleFont(in: lib.appendingPathComponent(python).appendingPathComponent("site-packages/kobo_hardcover_sync/web/static/fonts"))
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

    /// As the tool searches (SQL like): any case, but é is not e, so that Set all takes the books shown.
    private func found(_ book: BooksAnswer.Book) -> Bool {
        let q = search.trimmingCharacters(in: .whitespaces)
        return q.isEmpty || [book.title, book.author].contains { $0.range(of: q, options: .caseInsensitive) != nil }
    }

    /// A change to one book through the tool; `shown` draws it at once, until the tool's answer replaces it.
    func change(_ id: String, _ args: [String], shown: ((inout BooksAnswer.Book) -> Void)? = nil) {
        if isPreview && args.contains("--remove") {  // it would take the book off the real shelf
            problem = previewLeavesHardcover
            return
        }
        if let shown, let n = books?.books.firstIndex(where: { $0.id == id }) { shown(&books!.books[n]) }
        changing.insert(id)
        DispatchQueue.global(qos: .userInitiated).async {
            let found = answer(BookAnswer.self, ["book", id] + args + ["--json"])
            DispatchQueue.main.async {
                self.changing.remove(id)
                switch found {
                case .success(let changed):
                    if let n = self.books?.books.firstIndex(where: { $0.id == id }) { self.books?.books[n] = changed.book }
                    self.status?.books = changed.books
                    self.books?.tip = changed.tip
                case .failure(let why):
                    self.problem = said(why)
                    self.loadBooks()  // back to what the tool has
                }
            }
        }
    }

    /// Set all: Sync for every book the search and filter show, while that is still as many.
    func setAll(_ sync: String) {
        let args = ["books", "--sync", sync, "--filter", filter, "--search", search.trimmingCharacters(in: .whitespaces)]
        let expect = ["--expect", String(shownBooks.count), "--json"]
        DispatchQueue.global(qos: .userInitiated).async {
            let found = answer(BooksAnswer.self, args + expect)
            let now = answer(StatusAnswer.self, ["status", "--json"])
            DispatchQueue.main.async {
                switch found {
                case .success(let list): self.books = list
                case .failure(let why): self.problem = said(why)
                }
                if case .success(let status) = now { self.status = status }
            }
        }
    }

    /// A field of a book as a control changes it.
    func binding(_ id: String, _ field: WritableKeyPath<BooksAnswer.Book, String>, _ args: @escaping (String) -> [String]) -> Binding<String> {
        Binding(
            get: { self.books?.books.first { $0.id == id }?[keyPath: field] ?? "" },
            set: { new in self.change(id, args(new)) { $0[keyPath: field] = new } })
    }

    /// The State, keeping its date where a date belongs to it.
    func stateBinding(_ book: BooksAnswer.Book) -> Binding<String> {
        binding(book.id, \.state) { new in
            ["finished", "rereading"].contains(new) && !book.stateDate.isEmpty ? ["--state", new, "--date", book.stateDate] : ["--state", new]
        }
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
                    if let first = books.firstRun { FirstRun(model: model, first: first) }
                    if let tip = books.tip, let book = books.books.first(where: { $0.id == tip.id }) {
                        TipBand(model: model, tip: tip, book: book)
                    }
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
            Form {
                Section {
                    Row(state: "fail", what: "Books", found: broken)
                } footer: {
                    if model.status?.mode == "server" {  // an older server, or a proxy that does not let the app through: the page still has them
                        HStack {
                            Spacer()
                            Button("Open the page") { _ = tool(["open"]) }
                        }
                    }
                }
            }
            .formStyle(.grouped)
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
/// The tip: one book from your own shelf, a question for you, so the blue circled query.
/// Open shows it in Details; Not now puts it aside for a month and the tool gives the next.
struct TipBand: View {
    @ObservedObject var model: WindowModel
    let tip: BooksAnswer.Tip
    let book: BooksAnswer.Book

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Mark(state: "warn", size: 20)
            Cover(path: book.cover, width: 30)
            VStack(alignment: .leading, spacing: 2) {
                Text(book.title).font(titleFont(14)).lineLimit(1)
                Text(tip.text).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            Button("Open") { model.chosenBook = book.id }
            Button("Not now") { model.change(book.id, ["--not-now"]) }
                .disabled(model.changing.contains(book.id))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("A tip: \(book.title). \(tip.text)")
    }
}

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
        SetAll(model: model, syncs: words.syncs)
    }
}

/// Set all: Sync for every book in the list as it is shown, asked first.
struct SetAll: View {
    @ObservedObject var model: WindowModel
    let syncs: [[String]]
    @State private var asked: [String]?  // the Sync chosen, while the question is open

    var body: some View {
        let n = model.shownBooks.count
        Menu("Set all \(n)") {
            ForEach(syncs, id: \.self) { sync in Button("Sync: \(sync.last ?? "")") { asked = sync } }
        }
        .fixedSize()
        .disabled(n == 0)
        .confirmationDialog(
            "Set Sync to \(asked?.last ?? "") for \(n == 1 ? "1 book" : "\(n) books")?",
            isPresented: Binding(get: { asked != nil }, set: { if !$0 { asked = nil } })
        ) {
            Button("Set \(n == 1 ? "1 book" : "\(n) books")") {
                if let key = asked?.first { model.setAll(key) }
                asked = nil
            }
        } message: {
            Text("Every book in the list as it is shown now, also those further down.")
        }
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
                .width(min: 160, ideal: 200)
            TableColumn("Sync") { book in
                WordPicker(label: "Sync", options: words?.syncs ?? [], selection: model.binding(book.id, \.sync) { ["--sync", $0] })
            }
            .width(min: 64, ideal: 70, max: 100)
            TableColumn("State") { book in
                VStack(alignment: .leading, spacing: 1) {
                    WordPicker(label: "State", options: words?.states ?? [], selection: model.stateBinding(book))
                    if !book.stateDate.isEmpty { Text(book.stateDate).font(.caption).foregroundStyle(.secondary).padding(.leading, 4) }
                }
            }
            .width(min: 96, ideal: 110, max: 160)
            TableColumn("Hardcover status") { book in StatusCell(book: book) }
                .width(min: 140, ideal: 190)
        }
        .contextMenu(forSelectionType: String.self) { ids in
            if let id = ids.first { Button("Open on the Page") { openAt(id) } }
        }
    }
}

/// A row's choice of the page's words: a pop-up menu, small.
struct WordPicker: View {
    let label: String
    let options: [[String]]
    @Binding var selection: String

    var body: some View {
        Picker(label, selection: $selection) {
            ForEach(options, id: \.self) { option in Text(option.last ?? "").tag(option.first ?? "") }
        }
        .labelsHidden()
        .pickerStyle(.menu)
        .controlSize(.small)
        .fixedSize()
    }
}

/// The page, at this book: for what the app does not change.
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
                    .fixedSize(horizontal: false, vertical: true)
                if book.status.kind == "next" && book.status.text.contains(":") { Correction(book: book) }  // as the page: a change it can say
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

/// What the tool said when it changed nothing, without its name in front.
func said(_ why: NoAnswer) -> String {
    let text = why.said.split(separator: "\n").last.map(String.init) ?? why.said
    return text.hasPrefix("kobo-hardcover-sync: ") ? String(text.dropFirst("kobo-hardcover-sync: ".count)) : text
}

/// Everything known of one book, as the page's Details has it, with the changes the page makes.
struct DetailsPane: View {
    @ObservedObject var model: WindowModel
    let book: BooksAnswer.Book
    let words: BooksAnswer.Words
    @State private var looking = ""  // what to search Hardcover for
    @State private var removing = false

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
                    if model.changing.contains(book.id) { ProgressView().controlSize(.small) }
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
                Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
                    GridRow {
                        Text("Sync").foregroundStyle(.secondary)
                        WordPicker(label: "Sync", options: words.syncs, selection: model.binding(book.id, \.sync) { ["--sync", $0] })
                    }
                    GridRow {
                        Text("State").foregroundStyle(.secondary)
                        WordPicker(label: "State", options: words.states, selection: model.stateBinding(book))
                    }
                    if ["finished", "rereading"].contains(book.state) {
                        GridRow {
                            Text("Since").foregroundStyle(.secondary)
                            if let date = day(book.stateDate) {
                                DatePicker("Since", selection: Binding(get: { date }, set: { since($0) }), displayedComponents: .date)
                                    .labelsHidden().controlSize(.small).fixedSize()
                            } else {
                                Button("Add a date") { since(Date()) }.controlSize(.small)
                            }
                        }
                    }
                }
                .font(.callout)
                if needsMatch { match }
                pairs(words.sections.first ?? "", book.details.kobo.filter { !["Sync", "State"].contains($0.first ?? "") })
                pairs(words.sections.last ?? "", book.details.hardcover)
                HStack {
                    if let link = URL(string: book.details.link), !book.details.link.isEmpty {
                        Button("Open on Hardcover") { NSWorkspace.shared.open(link) }
                    }
                    Button("Open on the Page") { openAt(book.id) }
                }
                if book.details.onShelf {
                    Button("Remove from Hardcover…", role: .destructive) { removing = true }
                        .confirmationDialog("Remove “\(book.title)” from your Hardcover shelf?", isPresented: $removing) {
                            Button("Remove", role: .destructive) { model.change(book.id, ["--remove"]) }
                        } message: {
                            Text("It is taken off the shelf on Hardcover now, with its reading dates, and no longer synced.")
                        }
                }
            }
            .padding(16)
            .textSelection(.enabled)
            .disabled(model.changing.contains(book.id))
        }
        .onChange(of: book.id) { _ in looking = "" }
    }

    /// No match yet: the books it could be, and looking for others.
    private var needsMatch: Bool { book.details.link.isEmpty && (book.status.kind == "warn" || !book.details.candidates.isEmpty) }

    private var match: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Which book is it?").font(.headline)
            if book.details.candidates.isEmpty {
                Text("Hardcover found nothing for it. Look for it by another title.").font(.callout).foregroundStyle(.secondary)
            }
            ForEach(book.details.candidates, id: \.id) { c in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(c.title).font(titleFont(13, .regular))
                        if !c.author.isEmpty { Text(c.author).font(.caption).foregroundStyle(.secondary) }
                    }
                    Spacer(minLength: 6)
                    Button("Use") { model.change(book.id, ["--pick", String(c.id)]) }.controlSize(.small)
                }
            }
            HStack {
                TextField("Title or author", text: $looking).textFieldStyle(.roundedBorder).onSubmit(look)
                Button("Search Hardcover", action: look).disabled(looking.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .controlSize(.small)
        }
    }

    private func look() {
        let q = looking.trimmingCharacters(in: .whitespaces)
        if !q.isEmpty { model.change(book.id, ["--search", q]) }
    }

    private func day(_ text: String) -> Date? {
        let read = DateFormatter()
        read.dateFormat = "yyyy-MM-dd"
        read.locale = Locale(identifier: "en_US_POSIX")
        return text.isEmpty ? nil : read.date(from: text)
    }

    private func since(_ date: Date) {
        let write = DateFormatter()
        write.dateFormat = "yyyy-MM-dd"
        write.locale = Locale(identifier: "en_US_POSIX")
        let text = write.string(from: date)
        model.change(book.id, ["--state", book.state, "--date", text]) { $0.stateDate = text }
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
