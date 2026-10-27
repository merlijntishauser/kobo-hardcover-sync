// Covers (docs/plans/2026-10-26-mac-app-server-books-and-covers-design.md,
// step 3): the library as a press run. Three rows of covers drift left,
// the front one largest: books read in the last year, then every other
// book read, then at the back the books never opened. Under them, past a
// double rule, the delivery pile: the book being read and the tip. The
// covers are the only pictures; the rest is the page's paper, ink, rules
// and marks. The drift and the lift are this pane's own motion; under
// reduced motion the run stands still and moves only by hand.

import AppKit
import SwiftUI

/// The three rows of the run, back to front.
enum RunRow: Int, CaseIterable {
    case back, middle, front

    /// Cover heights in points at full size; a smaller window scales the run down.
    var height: CGFloat { [72, 108, 150][rawValue] }
    /// Points a second at full size: the front row moves one cover in about six seconds, the rows behind slower.
    var speed: CGFloat { [7, 11, 17][rawValue] }
}

/// Which row a book runs in.
func runRow(_ book: BooksAnswer.Book, since yearAgo: String) -> RunRow {
    if !book.opened { return .back }
    return book.lastRead >= yearAgo ? .front : .middle
}

/// From one cover to the next in a row. A row shorter than the window spreads out to fill it:
/// each book on the run once, and no stretch of bare ground.
func runStep(_ row: RunRow, count: Int, k: CGFloat, width: CGFloat) -> CGFloat {
    let w = row.height * k / 1.5
    return max(w + max(10, w * 0.22), (width + w) / CGFloat(max(count, 1)))
}

/// Where each row stands, advanced a frame at a time. A reference, not state:
/// the timeline redraws every frame, and a frame must not redraw again.
final class Drift {
    var offset: [CGFloat] = [0, 0, 0]
    var pace: [CGFloat] = [1, 1, 1]  // 1 drifting, 0 standing; eased between
    var byHandUntil = Date.distantPast  // a two-finger move holds the drift for a while
    private var last: Date?

    func step(to now: Date, standing: [Bool], speeds: [CGFloat]) {
        let dt = min(now.timeIntervalSince(last ?? now), 0.1)
        last = now
        for r in 0..<3 {
            let target: CGFloat = standing[r] || now < byHandUntil ? 0 : 1
            pace[r] += (target - pace[r]) * (1 - exp(-dt / 0.18))  // an exponential ease, as the page's expo out
            offset[r] += speeds[r] * pace[r] * CGFloat(dt)
        }
    }

    /// These rows have eased to a stop, and no move by hand still holds them.
    func stopped(_ rows: [RunRow], at now: Date) -> Bool {
        now >= byHandUntil && rows.allSatisfy { pace[$0.rawValue] < 0.002 }
    }
}

/// A cover on the run: which book, and where it stands on its row's strip.
/// The row moves as one; a cover keeps its place on the strip, so a frame
/// changes one offset per row, not one per cover.
struct Placed: Identifiable {
    let id: Int  // the place on the strip, counted from the row's start; the loop repeats the books along it
    let book: BooksAnswer.Book
    let frame: CGRect  // on the strip: the row's shift brings it into the window
}

struct CoversPane: View {
    @ObservedObject var model: WindowModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drift = Drift()
    @State private var lifted: (row: RunRow, id: String)?  // under the pointer, or the keyboard's
    @State private var keyed = false  // the keyboard is in the run: it stands
    @State private var visible = true
    @State private var byHand = 0  // redraws a standing run after a move by hand
    @State private var runFrame = CGRect.zero  // in the window, for the trackpad
    @State private var captionHeight: CGFloat = 96
    @AppStorage("CoversShow") private var show = "all"  // which books the run holds: one of the list's filters, kept apart from Books'
    @State private var watcher: Any?
    @FocusState private var focused: Bool
    @State private var settled = false  // the whole run stands and has eased to a stop: no frames until it moves

    var body: some View {
        if let books = model.books {
            GeometryReader { box in
                let runHeight = box.size.height * 0.62
                let rows = rows(books)
                let present = RunRow.allCases.filter { !rows[$0.rawValue].isEmpty }  // a row without books takes no room
                VStack(spacing: 0) {
                    run(books, rows: rows, present: present, size: CGSize(width: box.size.width, height: runHeight))
                    DoubleRule().padding(.horizontal, 20)
                        .overlay(alignment: .trailing) {  // on the rule, which breaks for it: a mark in the margin
                            Show(show: $show, books: books).padding(.horizontal, 8).background(Pencil.ground).padding(.trailing, 28)
                        }
                        .zIndex(1)
                    Pile(model: model, books: books, coverWidth: RunRow.front.height * scale(runHeight, present) / 1.5)
                        .frame(height: box.size.height - runHeight - 3)
                }
            }
            .background(Pencil.ground)
            .overlay {
                if let id = model.chosenBook, let book = books.books.first(where: { $0.id == id }) {
                    Spread(model: model, book: book, words: books.words)
                        .transition(.opacity.combined(with: .scale(scale: 0.96)))
                }
            }
            .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: model.chosenBook)
            .onAppear(perform: watch)
            .onDisappear(perform: unwatch)
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.didChangeOcclusionStateNotification)) { _ in
                visible = NSApp.occlusionState.contains(.visible)
            }
        } else if let broken = model.booksBroken {
            Form { Section { Row(state: "fail", what: "Covers", found: broken) } }.formStyle(.grouped)
        } else {
            VStack {
                Spacer()
                ProgressView().controlSize(.small)
                Spacer()
            }
            .frame(maxWidth: .infinity)
        }
    }

    // ---------- the run ----------

    /// The selection the run shows; a filter the tool no longer has is all books.
    private func selection(_ books: BooksAnswer) -> String {
        books.words.filters.contains { $0.keys.contains { $0.first == show } } ? show : "all"
    }

    private func rows(_ books: BooksAnswer) -> [[BooksAnswer.Book]] {
        let yearAgo = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-365 * 86400))
        let chosen = selection(books)
        var out: [[BooksAnswer.Book]] = [[], [], []]
        for book in books.books where book.filters.contains(chosen) { out[runRow(book, since: yearAgo).rawValue].append(book) }  // newest read first, as the tool lists them
        out[RunRow.back.rawValue].sort { $0.title.localizedCompare($1.title) == .orderedAscending }
        return out
    }

    /// The run's scale: the rows that have books, and their gaps, in the height there is; never above full size.
    private func scale(_ height: CGFloat, _ present: [RunRow]) -> CGFloat {
        let full = present.reduce(0) { $0 + $1.height } + CGFloat(present.count + 1) * 22
        return min(1, max(0.45, height / max(full, 1)))
    }

    @ViewBuilder private func run(_ books: BooksAnswer, rows: [[BooksAnswer.Book]], present: [RunRow], size: CGSize) -> some View {
        let k = scale(size.height, present)
        let standing = RunRow.allCases.map { row in keyed || lifted?.row == row || model.enlarged != nil || model.chosenBook != nil }
        let still = present.allSatisfy { standing[$0.rawValue] }  // nothing on the run drifts: under the spread, the large cover, the keyboard
        let paused = reduceMotion || !visible || present.isEmpty || (still && settled)
        TimelineView(.animation(minimumInterval: nil, paused: paused)) { time in
            let _ = paused ? () : drift.step(to: time.date, standing: standing, speeds: RunRow.allCases.map { $0.speed * k })
            let _ = paused || !still || !drift.stopped(present, at: time.date) ? () : DispatchQueue.main.async { settled = true }
            let _ = byHand
            let shift = drift.offset
            let placed = RunRow.allCases.map { place(rows[$0.rawValue], row: $0, present: present, k: k, size: size) }
            let shown = { (row: RunRow, item: Placed) in item.frame.offsetBy(dx: -shift[row.rawValue], dy: 0) }  // in the window
            ZStack(alignment: .topLeading) {
                ForEach(RunRow.allCases, id: \.self) { row in
                    ZStack(alignment: .topLeading) {
                        ForEach(placed[row.rawValue]) { item in
                            RunCover(
                                book: item.book, frame: item.frame, k: k, up: lifted?.row == row && lifted?.id == item.book.id,
                                reduceMotion: reduceMotion, open: { model.chosenBook = item.book.id }
                            )
                            .equatable()
                        }
                    }
                    .offset(x: -shift[row.rawValue])
                    .zIndex(lifted?.row == row ? 1 : 0)  // the lifted cover over the rest
                }
                if present.isEmpty && !books.books.isEmpty {
                    Text("No books in this selection.").foregroundStyle(.secondary)
                        .frame(width: size.width, height: size.height)
                }
                if let lifted, let item = placed[lifted.row.rawValue].first(where: { $0.book.id == lifted.id }) {
                    // Under the cover; where the run has no room under it (the front row), above the lifted cover.
                    let frame = shown(lifted.row, item)
                    let below = frame.maxY + 10
                    let top = frame.maxY - frame.height * (reduceMotion ? 1 : 1.12)
                    Caption(book: item.book)
                        .frame(width: 260, alignment: .leading)
                        .background(GeometryReader { g in
                            Color.clear.onAppear { captionHeight = g.size.height }.onChange(of: g.size.height) { captionHeight = $0 }
                        })
                        .offset(
                            x: min(max(8, frame.minX), size.width - 268),
                            y: below + captionHeight <= size.height ? below : max(4, top - 10 - captionHeight)
                        )
                        .zIndex(2)  // over the lifted cover, which stands over the rest
                        .allowsHitTesting(false)
                }
            }
            .frame(width: size.width, height: size.height, alignment: .topLeading)
            .contentShape(Rectangle())
            .onContinuousHover { phase in
                guard !keyed else { return }
                switch phase {
                case .active(let point):
                    let hit = RunRow.allCases.reversed().lazy.compactMap { row in
                        placed[row.rawValue].first { shown(row, $0).contains(point) }.map { (row, $0.book.id) }
                    }.first
                    if hit?.0 != lifted?.row || hit?.1 != lifted?.id { lifted = hit }
                case .ended:
                    lifted = nil
                }
            }
        }
        .frame(width: size.width, height: size.height)
        .clipped()
        .background(GeometryReader { g in Color.clear.onAppear { runFrame = g.frame(in: .global) }.onChange(of: g.size) { _ in runFrame = g.frame(in: .global) } })
        .focusable()
        .withoutFocusRing()  // the lifted cover shows where the keyboard is
        .focused($focused)
        .onMoveCommand { move($0, rows: rows, k: k, width: size.width) }
        .onAppear { bringUp(rows: rows, k: k, width: size.width) }
        .onChange(of: model.spotlit) { _ in bringUp(rows: rows, k: k, width: size.width) }
        .onChange(of: show) { _ in
            lifted = nil
            bringUp(rows: rows, k: k, width: size.width)  // a book from Spotlight or the widget, after showing all
        }
        .onChange(of: still) { stands in
            if !stands { settled = false }  // it drifts again; when it next stands, it eases to a stop first
        }
        .onExitCommand {
            if model.enlarged != nil { model.enlarged = nil } else { keyed = false; lifted = nil }
        }
        .background {  // Return opens, Space shows it large: the keys of the run
            Group {
                Button("") { if let id = lifted?.id { model.chosenBook = id } }.keyboardShortcut(.defaultAction)
                Button("") { toggleLarge(books) }.keyboardShortcut(" ", modifiers: [])
            }
            .opacity(0)
            .accessibilityHidden(true)
            .disabled(model.chosenBook != nil || model.enlarged != nil)  // the book is open: its own fields and keys
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Covers: read in the last year, then the rest read, then never opened")
    }

    /// The covers of a row that show now, at their places on its strip: the loop repeated along it.
    private func place(_ books: [BooksAnswer.Book], row: RunRow, present: [RunRow], k: CGFloat, size: CGSize) -> [Placed] {
        guard !books.isEmpty, let n = present.firstIndex(of: row) else { return [] }
        let h = row.height * k
        let w = h / 1.5
        let step = runStep(row, count: books.count, k: k, width: size.width)
        let gap = (size.height - present.reduce(0) { $0 + $1.height * k }) / CGFloat(present.count + 1)
        let y = gap * CGFloat(n + 1) + present.prefix(n).reduce(0) { $0 + $1.height * k }
        let shift = drift.offset[row.rawValue]
        var out: [Placed] = []
        var place = Int(((shift - w) / step).rounded(.down)) + 1  // the first whose right edge is in the window
        while CGFloat(place) * step - shift < size.width {
            let book = books[(place % books.count + books.count) % books.count]
            out.append(Placed(id: place, book: book, frame: CGRect(x: CGFloat(place) * step, y: y, width: w, height: h)))
            place += 1
        }
        return out
    }

    // ---------- by hand and by keyboard ----------

    /// Arrows move along a row and between rows; the run stands while the keyboard is in it.
    private func move(_ direction: MoveCommandDirection, rows: [[BooksAnswer.Book]], k: CGFloat, width: CGFloat) {
        let filled = RunRow.allCases.filter { !rows[$0.rawValue].isEmpty }
        guard let front = filled.last else { return }
        var row = lifted?.row ?? front
        var index = lifted.flatMap { l in rows[l.row.rawValue].firstIndex { $0.id == l.id } } ?? 0
        if lifted != nil {
            switch direction {
            case .left: index -= 1
            case .right: index += 1
            case .up: row = filled.last { $0.rawValue < row.rawValue } ?? row
            case .down: row = filled.first { $0.rawValue > row.rawValue } ?? row
            @unknown default: return
            }
        }
        let books = rows[row.rawValue]
        index = (index % books.count + books.count) % books.count
        keyed = true
        lifted = (row, books[index].id)
        drift.offset[row.rawValue] = CGFloat(index) * runStep(row, count: books.count, k: k, width: width) - width / 3  // a third in
        byHand += 1
    }

    /// A book chosen in Spotlight: lifted on its row, a third in, as the keyboard would have it.
    private func bringUp(rows: [[BooksAnswer.Book]], k: CGFloat, width: CGFloat) {
        guard let id = model.spotlit else { return }
        if show != "all" && !rows.joined().contains(where: { $0.id == id }) {
            show = "all"  // not in the selection: the run shows every book, then lifts it
            return
        }
        model.spotlit = nil
        for row in RunRow.allCases {
            guard let index = rows[row.rawValue].firstIndex(where: { $0.id == id }) else { continue }
            keyed = true
            lifted = (row, id)
            drift.offset[row.rawValue] = CGFloat(index) * runStep(row, count: rows[row.rawValue].count, k: k, width: width) - width / 3
            byHand += 1
            return
        }
    }

    private func toggleLarge(_ books: BooksAnswer) {
        if let id = lifted?.id { model.enlarged = books.books.first { $0.id == id } }
    }

    /// Two fingers on the trackpad move the run; it drifts again a few seconds after.
    private func watch() {
        focused = true
        model.chosenBook = nil  // Details chosen on Books does not open here as a sheet
        watcher = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
            guard let window = event.window, window.isKeyWindow, let content = window.contentView else { return event }
            let at = CGPoint(x: event.locationInWindow.x, y: content.bounds.height - event.locationInWindow.y)
            guard runFrame.contains(at) else { return event }
            let dx = abs(event.scrollingDeltaX) >= abs(event.scrollingDeltaY) ? event.scrollingDeltaX : event.scrollingDeltaY
            for row in RunRow.allCases { drift.offset[row.rawValue] -= dx * row.speed / RunRow.front.speed }
            drift.byHandUntil = Date().addingTimeInterval(3)
            byHand += 1
            return nil
        }
    }

    private func unwatch() {
        if let watcher { NSEvent.removeMonitor(watcher) }
        watcher = nil
        model.enlarged = nil  // it belongs to Covers
    }
}

/// A cover on the run, at its place on the strip. Equal to the last frame's
/// while the book, the place and the lift are: the run moves it without
/// drawing it again.
struct RunCover: View, Equatable {
    let book: BooksAnswer.Book
    let frame: CGRect
    let k: CGFloat
    let up: Bool
    let reduceMotion: Bool
    let open: () -> Void

    static func == (a: RunCover, b: RunCover) -> Bool {
        a.book.id == b.book.id && a.book.cover == b.book.cover && a.book.title == b.book.title && a.book.author == b.book.author
            && a.book.status.kind == b.book.status.kind && a.book.status.text == b.book.status.text
            && a.frame == b.frame && a.k == b.k && a.up == b.up && a.reduceMotion == b.reduceMotion
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            Cover(path: book.cover, width: frame.width)
                .background(Pencil.sheet)
                .shadow(color: .black.opacity(up ? 0.22 : 0.28), radius: up ? 6 : 1, y: up ? 6 : 1)
                .shadow(color: .black.opacity(0.1), radius: 4, y: 3)
            if book.status.kind == "next" {  // the one mark on the run: the next sync changes this book
                Mark(state: "next", size: max(12, 16 * k))
                    .background(Circle().fill(Pencil.sheet).padding(-1))
                    .offset(x: -5, y: 6)
            }
        }
        .scaleEffect(up && !reduceMotion ? 1.12 : 1, anchor: .bottom)
        .zIndex(up ? 1 : 0)
        .animation(.timingCurve(0.16, 1, 0.3, 1, duration: 0.25), value: up)
        .offset(x: frame.minX, y: frame.minY)
        .onTapGesture(perform: open)
        .accessibilityElement()
        .accessibilityLabel("\(book.title), \(book.author). \(book.status.text)")
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { open() }
    }
}

/// Which books the run holds: the list's own filters, with their counts.
struct Show: View {
    @Binding var show: String
    let books: BooksAnswer

    var body: some View {
        Picker("Show", selection: $show) {
            ForEach(books.words.filters, id: \.group) { group in
                Section(group.group) {
                    ForEach(group.keys, id: \.self) { key in
                        let n = books.books.filter { $0.filters.contains(key.first ?? "") }.count
                        Text("\(key.last ?? "") (\(n))").tag(key.first ?? "")
                    }
                }
            }
        }
        .fixedSize()
        .controlSize(.small)
    }
}

/// Under a lifted cover: its title, author, gauge and status line, on a slip of the sheet.
struct Caption: View {
    let book: BooksAnswer.Book

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(book.title).font(titleFont(15)).lineLimit(2).fixedSize(horizontal: false, vertical: true)
            Text(book.author).font(.callout).foregroundStyle(.secondary).lineLimit(1)
            Gauge(percent: book.percent, finished: book.finished).padding(.vertical, 2)
            HStack(alignment: .top, spacing: 5) {
                Mark(state: book.status.kind, size: 14).padding(.top, 1)
                Text(book.status.text).font(.caption).lineLimit(2)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 2).fill(Pencil.sheet))
        .overlay(RoundedRectangle(cornerRadius: 2).stroke(Pencil.rule, lineWidth: 1))
        .shadow(color: .black.opacity(0.18), radius: 10, y: 6)
    }
}

/// The proofreader's hairline pair, 3 points high: where the run ends and the pile begins.
struct DoubleRule: View {
    var body: some View {
        VStack(spacing: 1) {
            Rectangle().fill(Pencil.rule).frame(height: 1)
            Rectangle().fill(Pencil.rule).frame(height: 1)
        }
        .frame(height: 3)
        .accessibilityHidden(true)
    }
}

/// The delivery pile: the book being read, and the tip.
struct Pile: View {
    @ObservedObject var model: WindowModel
    let books: BooksAnswer
    let coverWidth: CGFloat  // as wide as the front row's covers

    private var reading: BooksAnswer.Book? { readingNow(books.books) }

    var body: some View {
        GeometryReader { box in
            let coverWidth = min(coverWidth, max(48, (box.size.height - 48) / 1.5))
            HStack(alignment: .top, spacing: 36) {
                if books.books.isEmpty {
                    Text("No books yet: nothing was read from a Kobo so far. Plug it in.").foregroundStyle(.secondary)
                } else {
                    if let book = reading {
                        HStack(alignment: .top, spacing: 16) {
                            lying(book, width: coverWidth)
                            VStack(alignment: .leading, spacing: 6) {
                                Text(book.title).font(titleFont(22)).lineLimit(3).fixedSize(horizontal: false, vertical: true)
                                Text(book.author).foregroundStyle(.secondary).lineLimit(1)
                                Gauge(percent: book.percent, finished: book.finished).padding(.vertical, 2)
                                Text(book.facts.joined(separator: " · ")).font(.callout.monospacedDigit()).foregroundStyle(.secondary).lineLimit(1)
                            }
                            .frame(maxWidth: 360, alignment: .leading)
                        }
                    }
                    if let tip = books.tip, let book = books.books.first(where: { $0.id == tip.id }) {
                        HStack(alignment: .top, spacing: 16) {
                            lying(book, width: coverWidth)
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(alignment: .top, spacing: 6) {
                                    Mark(state: "warn", size: 18)
                                    Text(tip.text).fixedSize(horizontal: false, vertical: true)
                                }
                                Text(book.title).font(titleFont(16)).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                                Text(book.author).font(.callout).foregroundStyle(.secondary).lineLimit(1)
                                HStack {
                                    Button("Open") { model.chosenBook = book.id }
                                    Button("Not now") { model.change(book.id, ["--not-now"]) }.disabled(model.changing.contains(book.id))
                                }
                                .padding(.top, 4)
                            }
                            .frame(maxWidth: 280, alignment: .leading)
                        }
                        .accessibilityElement(children: .contain)
                        .accessibilityLabel("A tip")
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 24)
            .padding(.top, 22)
        }
    }

    private func lying(_ book: BooksAnswer.Book, width: CGFloat) -> some View {
        Cover(path: book.cover, width: width)
            .background(Pencil.sheet)
            .shadow(color: .black.opacity(0.28), radius: 1, y: 1)
            .shadow(color: .black.opacity(0.1), radius: 4, y: 3)
            .onTapGesture { model.chosenBook = book.id }
    }
}

/// A click on a cover: the book over the pane, its cover as large as the height
/// allows in the left third, its Details and what can be done with it in the
/// rest. The thumbnail first, then the cover large once the tool has it.
struct Spread: View {
    @ObservedObject var model: WindowModel
    let book: BooksAnswer.Book
    let words: BooksAnswer.Words
    @State private var large: (id: String, path: String)?

    var body: some View {
        GeometryReader { box in
            HStack(spacing: 0) {
                Cover(path: large?.id == book.id ? large?.path ?? "" : book.cover, width: max(96, min(box.size.width / 3 - 56, (box.size.height - 64) / 1.5)))
                    .background(Pencil.sheet)
                    .shadow(color: .black.opacity(0.28), radius: 1, y: 1)
                    .shadow(color: .black.opacity(0.16), radius: 18, y: 12)
                    .onTapGesture { model.enlarged = book }
                    .accessibilityElement()
                    .accessibilityLabel("The cover of \(book.title)")
                    .accessibilityAddTraits(.isButton)
                    .accessibilityAction { model.enlarged = book }
                    .frame(width: box.size.width / 3, height: box.size.height)
                Pencil.rule.frame(width: 1).padding(.vertical, 32)
                DetailsPane(model: model, book: book, words: words, spread: true)
                    .frame(maxWidth: 620, maxHeight: .infinity, alignment: .topLeading)
                    .padding(.horizontal, 12)
                    .padding(.top, 16)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Pencil.ground)
        .onAppear(perform: fetch)
        .onChange(of: book.id) { _ in fetch() }
    }

    private func fetch() {
        let id = book.id
        model.largeCover(id) { large = (id, $0) }
    }
}

extension View {
    /// No focus ring (macOS 14 and later; before, macOS draws one).
    @ViewBuilder func withoutFocusRing() -> some View {
        if #available(macOS 14, *) { focusEffectDisabled() } else { self }
    }
}

/// The cover over the whole window, as large as it fits (Space on the run, or a
/// click on the cover in the spread); a click, Space or Escape puts it back.
struct Lightbox: View {
    @ObservedObject var model: WindowModel
    let book: BooksAnswer.Book
    @State private var large: (id: String, path: String)?

    var body: some View {
        GeometryReader { box in
            ZStack {
                Color(red: 10 / 255, green: 12 / 255, blue: 14 / 255).opacity(0.88)
                VStack(spacing: 14) {
                    Cover(path: large?.id == book.id ? large?.path ?? "" : book.cover, width: max(96, min(box.size.width - 96, (box.size.height - 104) / 1.5)))
                        .shadow(color: .black.opacity(0.55), radius: 32, y: 24)
                    Text(book.title).font(titleFont(22)).foregroundStyle(.white).lineLimit(1)
                }
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: close)
        .background {
            Group {
                Button("", action: close).keyboardShortcut(" ", modifiers: [])
                Button("", action: close).keyboardShortcut(.cancelAction)
            }
            .opacity(0)
            .accessibilityHidden(true)
        }
        .onAppear {
            let id = book.id
            model.largeCover(id) { large = (id, $0) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("The cover of \(book.title)")
        .accessibilityAddTraits(.isModal)
        .accessibilityAction(named: "Close", close)
        .transition(.opacity.combined(with: .scale(scale: 0.96)))
    }

    private func close() { model.enlarged = nil }
}
