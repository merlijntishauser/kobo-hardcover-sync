// The widget (docs/plans/2026-10-26-mac-app-server-books-and-covers-design.md,
// step 5): the delivery pile of Covers, smaller, on the desktop and in
// Notification Center. Small: the book being read, its cover and its
// gauge. Medium: that book and the tip. It shows the shelf the app last
// kept (Shelf.swift) and asks nothing itself; the app has it drawn again
// when the books change. A click opens Covers at that book.

import SwiftUI
import WidgetKit

private let fonts: Void = registerTitleFont(in: Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/fonts"))

struct ShelfEntry: TimelineEntry {
    let date: Date
    let shelf: Shelf?
}

struct ShelfProvider: TimelineProvider {
    func placeholder(in context: Context) -> ShelfEntry { ShelfEntry(date: .now, shelf: nil) }

    func getSnapshot(in context: Context, completion: @escaping (ShelfEntry) -> Void) {
        completion(ShelfEntry(date: .now, shelf: readShelf()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ShelfEntry>) -> Void) {
        completion(Timeline(entries: [ShelfEntry(date: .now, shelf: readShelf())], policy: .never))
    }
}

/// Where a click on a book goes: the app, on Covers, at that book.
func opening(_ book: Shelf.Book) -> URL {
    URL(string: "kobo-hardcover-sync://book/" + (book.id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""))!
}

struct ShelfView: View {
    let entry: ShelfEntry
    @Environment(\.widgetFamily) private var family

    init(entry: ShelfEntry) {
        _ = fonts
        self.entry = entry
    }

    var body: some View {
        Group {
            if let shelf = entry.shelf, let book = shelf.reading ?? shelf.tip?.book {
                if family == .systemMedium {
                    HStack(alignment: .top, spacing: 14) {
                        if let reading = shelf.reading { Link(destination: opening(reading)) { readingSide(reading) } }
                        if shelf.reading != nil && shelf.tip != nil { Pencil.rule.frame(width: 1) }
                        if let tip = shelf.tip { Link(destination: opening(tip.book)) { tipSide(tip) } }
                    }
                } else {
                    small(book, tip: shelf.reading == nil ? shelf.tip?.text : nil).widgetURL(opening(book))
                }
            } else {
                Text(entry.shelf?.empty == true ? "No books yet. Plug in your Kobo." : "Open Kobo Hardcover Sync to see your books here.")
                    .font(.callout).foregroundStyle(Pencil.graphite)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
        .containerBackground(Pencil.ground, for: .widget)
    }

    /// Small: the cover large, the title under it, the gauge and how far; or, with nothing being read, the tip's question.
    private func small(_ book: Shelf.Book, tip: String?) -> some View {
        GeometryReader { box in
            VStack(alignment: .leading, spacing: 6) {
                lying(book, width: max(40, (box.size.height - 42) / 1.5))
                Text(book.title).font(titleFont(13)).lineLimit(1)
                if let tip {
                    HStack(spacing: 4) {
                        Mark(state: "warn", size: 14)
                        Text(tip).font(.caption).foregroundStyle(Pencil.graphite).lineLimit(1)
                    }
                } else {
                    HStack(spacing: 6) {
                        Gauge(percent: book.percent, finished: book.finished)
                        Text(book.finished ? "Read" : "\(book.percent)%").font(.caption.monospacedDigit()).foregroundStyle(Pencil.graphite)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private func readingSide(_ book: Shelf.Book) -> some View {
        HStack(alignment: .top, spacing: 10) {
            lying(book, width: 60)
            VStack(alignment: .leading, spacing: 4) {
                Text(book.title).font(titleFont(15)).lineLimit(3)
                Text(book.author).font(.caption).foregroundStyle(Pencil.graphite).lineLimit(1)
                Gauge(percent: book.percent, finished: book.finished).padding(.vertical, 2)
                Text(book.facts.first ?? "").font(.caption.monospacedDigit()).foregroundStyle(Pencil.graphite).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func tipSide(_ tip: Shelf.Tip) -> some View {
        HStack(alignment: .top, spacing: 10) {
            lying(tip.book, width: 60)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top, spacing: 4) {
                    Mark(state: "warn", size: 14)
                    Text(tip.text).font(.caption).lineLimit(3)
                }
                Text(tip.book.title).font(titleFont(13)).lineLimit(2)
                Text(tip.book.author).font(.caption).foregroundStyle(Pencil.graphite).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// A cover lying on the ground, as on the pile.
    private func lying(_ book: Shelf.Book, width: CGFloat) -> some View {
        WidgetCover(path: book.cover.isEmpty ? "" : shelfFolder()?.appendingPathComponent(book.cover).path ?? "", width: width)
            .background(Pencil.sheet)
            .shadow(color: .black.opacity(0.28), radius: 1, y: 1)
            .shadow(color: .black.opacity(0.1), radius: 4, y: 3)
    }
}

/// A cover in the widget, in full colour also where macOS tints widgets (the
/// desktop's tinted widget style, or a window in front of it), which would
/// otherwise draw the picture as a flat grey block.
struct WidgetCover: View {
    let path: String
    let width: CGFloat

    var body: some View {
        if let image = NSImage(contentsOfFile: path) {
            picture(Image(nsImage: image))
                .aspectRatio(contentMode: .fill)
                .frame(width: width, height: width * 1.5)
                .clipShape(RoundedRectangle(cornerRadius: 2))
                .accessibilityHidden(true)
        } else {
            Cover(path: "", width: width)  // the crossed box
        }
    }

    @ViewBuilder private func picture(_ image: Image) -> some View {
        if #available(macOS 15, *) {
            image.resizable().widgetAccentedRenderingMode(.fullColor)
        } else {
            image.resizable()
        }
    }
}

struct ShelfWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "shelf", provider: ShelfProvider()) { entry in
            ShelfView(entry: entry)
        }
        .configurationDisplayName("Reading now")
        .description("The book you are reading, and a tip from your own shelf.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct ShelfWidgets: WidgetBundle {
    var body: some Widget { ShelfWidget() }
}
