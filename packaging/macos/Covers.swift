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
}

/// A cover on the run: which book, and where it is drawn now.
struct Placed: Identifiable {
    let id: String  // the book, and which pass of the loop
    let book: BooksAnswer.Book
    let frame: CGRect
}

struct CoversPane: View {
    @ObservedObject var model: WindowModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drift = Drift()
    @State private var lifted: (row: RunRow, id: String)?  // under the pointer, or the keyboard's
    @State private var keyed = false  // the keyboard is in the run: it stands
    @State private var large: BooksAnswer.Book?  // Space: the cover, large
    @State private var visible = true
    @State private var byHand = 0  // redraws a standing run after a move by hand
    @State private var runFrame = CGRect.zero  // in the window, for the trackpad
    @State private var captionHeight: CGFloat = 96
    @State private var watcher: Any?
    @FocusState private var focused: Bool

    var body: some View {
        if let books = model.books {
            GeometryReader { box in
                let runHeight = box.size.height * 0.62
                let present = RunRow.allCases.filter { row in rows(books)[row.rawValue].count > 0 }
                VStack(spacing: 0) {
                    run(books, size: CGSize(width: box.size.width, height: runHeight))
                    DoubleRule().padding(.horizontal, 20)
                    Pile(model: model, books: books, coverWidth: RunRow.front.height * scale(runHeight, present) / 1.5)
                        .frame(height: box.size.height - runHeight - 3)
                }
            }
            .background(Pencil.ground)
            .overlay { if let large { Lightbox(book: large) { withAnimation(reduceMotion ? nil : .easeOut(duration: 0.18)) { self.large = nil } } } }
            .sheet(isPresented: Binding(get: { model.chosenBook != nil }, set: { if !$0 { model.chosenBook = nil } })) {
                if let id = model.chosenBook, let book = books.books.first(where: { $0.id == id }) {
                    DetailsPane(model: model, book: book, words: books.words).frame(width: 380, height: 560)
                }
            }
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

    private func rows(_ books: BooksAnswer) -> [[BooksAnswer.Book]] {
        let yearAgo = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-365 * 86400))
        var out: [[BooksAnswer.Book]] = [[], [], []]
        for book in books.books { out[runRow(book, since: yearAgo).rawValue].append(book) }  // newest read first, as the tool lists them
        out[RunRow.back.rawValue].sort { $0.title.localizedCompare($1.title) == .orderedAscending }
        return out
    }

    /// The run's scale: the rows that have books, and their gaps, in the height there is; never above full size.
    private func scale(_ height: CGFloat, _ present: [RunRow]) -> CGFloat {
        let full = present.reduce(0) { $0 + $1.height } + CGFloat(present.count + 1) * 22
        return min(1, max(0.45, height / max(full, 1)))
    }

    @ViewBuilder private func run(_ books: BooksAnswer, size: CGSize) -> some View {
        let rows = rows(books)
        let present = RunRow.allCases.filter { !rows[$0.rawValue].isEmpty }  // a row without books takes no room
        let k = scale(size.height, present)
        let paused = reduceMotion || !visible || books.books.isEmpty
        TimelineView(.animation(minimumInterval: nil, paused: paused)) { time in
            let standing = RunRow.allCases.map { row in keyed || lifted?.row == row || large != nil || model.chosenBook != nil }
            let _ = paused ? () : drift.step(to: time.date, standing: standing, speeds: RunRow.allCases.map { $0.speed * k })
            let _ = byHand
            let placed = RunRow.allCases.map { place(rows[$0.rawValue], row: $0, present: present, k: k, size: size) }
            ZStack(alignment: .topLeading) {
                ForEach(RunRow.allCases, id: \.self) { row in
                    ForEach(placed[row.rawValue]) { item in
                        cover(item, row: row, k: k)
                    }
                }
                if let lifted, let item = placed[lifted.row.rawValue].first(where: { $0.book.id == lifted.id }) {
                    // Under the cover; where the run has no room under it (the front row), above the lifted cover.
                    let below = item.frame.maxY + 10
                    let top = item.frame.maxY - item.frame.height * (reduceMotion ? 1 : 1.12)
                    Caption(book: item.book)
                        .frame(width: 260, alignment: .leading)
                        .background(GeometryReader { g in
                            Color.clear.onAppear { captionHeight = g.size.height }.onChange(of: g.size.height) { captionHeight = $0 }
                        })
                        .offset(
                            x: min(max(8, item.frame.minX), size.width - 268),
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
                        placed[row.rawValue].first { $0.frame.contains(point) }.map { (row, $0.book.id) }
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
        .focused($focused)
        .onMoveCommand { move($0, rows: rows, k: k, width: size.width) }
        .onAppear { bringUp(rows: rows, k: k, width: size.width) }
        .onChange(of: model.spotlit) { _ in bringUp(rows: rows, k: k, width: size.width) }
        .onExitCommand {
            if large != nil { large = nil } else { keyed = false; lifted = nil }
        }
        .background {  // Return opens, Space shows it large: the keys of the run
            Group {
                Button("") { if let id = lifted?.id { model.chosenBook = id } }.keyboardShortcut(.defaultAction)
                Button("") { toggleLarge(books) }.keyboardShortcut(" ", modifiers: [])
            }
            .opacity(0)
            .accessibilityHidden(true)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Covers: read in the last year, then the rest read, then never opened")
    }

    /// The covers of a row where they are now: the loop repeated across the width, only what shows.
    private func place(_ books: [BooksAnswer.Book], row: RunRow, present: [RunRow], k: CGFloat, size: CGSize) -> [Placed] {
        guard !books.isEmpty, let n = present.firstIndex(of: row) else { return [] }
        let width = size.width
        let h = row.height * k
        let w = h / 1.5
        let step = runStep(row, count: books.count, k: k, width: width)
        let period = step * CGFloat(books.count)
        let gap = (size.height - present.reduce(0) { $0 + $1.height * k }) / CGFloat(present.count + 1)
        let y = gap * CGFloat(n + 1) + present.prefix(n).reduce(0) { $0 + $1.height * k }
        let shift = drift.offset[row.rawValue].truncatingRemainder(dividingBy: period)
        var out: [Placed] = []
        var pass = 0
        var start = -shift - (shift < 0 ? period : 0)
        while start < width {
            for (i, book) in books.enumerated() {
                let x = start + CGFloat(i) * step
                if x > -w && x < width { out.append(Placed(id: "\(book.id)#\(pass)", book: book, frame: CGRect(x: x, y: y, width: w, height: h))) }
            }
            start += period
            pass += 1
        }
        return out
    }

    private func cover(_ item: Placed, row: RunRow, k: CGFloat) -> some View {
        let up = lifted?.row == row && lifted?.id == item.book.id
        return ZStack(alignment: .bottomLeading) {
            Cover(path: item.book.cover, width: item.frame.width)
                .background(Pencil.sheet)
                .shadow(color: .black.opacity(up ? 0.22 : 0.28), radius: up ? 6 : 1, y: up ? 6 : 1)
                .shadow(color: .black.opacity(0.1), radius: 4, y: 3)
            if item.book.status.kind == "next" {  // the one mark on the run: the next sync changes this book
                Mark(state: "next", size: max(12, 16 * k))
                    .background(Circle().fill(Pencil.sheet).padding(-1))
                    .offset(x: -5, y: 6)
            }
        }
        .scaleEffect(up && !reduceMotion ? 1.12 : 1, anchor: .bottom)
        .zIndex(up ? 1 : 0)
        .animation(.timingCurve(0.16, 1, 0.3, 1, duration: 0.25), value: up)
        .offset(x: item.frame.minX, y: item.frame.minY)
        .onTapGesture { model.chosenBook = item.book.id }
        .accessibilityElement()
        .accessibilityLabel("\(item.book.title), \(item.book.author). \(item.book.status.text)")
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { model.chosenBook = item.book.id }
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
        withAnimation(reduceMotion ? nil : .timingCurve(0.16, 1, 0.3, 1, duration: 0.18)) {
            if large != nil {
                large = nil
            } else if let id = lifted?.id {
                large = books.books.first { $0.id == id }
            }
        }
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

/// Space: the cover large, over the run; a click or Space again puts it back.
struct Lightbox: View {
    let book: BooksAnswer.Book
    let close: () -> Void

    var body: some View {
        GeometryReader { box in
            ZStack {
                Color(red: 10 / 255, green: 12 / 255, blue: 14 / 255).opacity(0.88)
                VStack(spacing: 14) {
                    Cover(path: book.cover, width: min(box.size.width * 0.5, (box.size.height - 90) / 1.5, 360))
                        .shadow(color: .black.opacity(0.55), radius: 32, y: 24)
                    Text(book.title).font(titleFont(22)).foregroundStyle(.white)
                }
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: close)
        .transition(.opacity.combined(with: .scale(scale: 0.96)))
    }
}
