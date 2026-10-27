// The paper both the window and the widget are drawn on (DESIGN.md): the
// page's colours, its marks, the title type, the line gauge and a cover.

import AppKit
import CoreText
import ImageIO
import SwiftUI

// ---------- the page's colours, light and dark ----------
func tone(_ light: Int, _ dark: Int) -> Color {
    Color(
        NSColor(name: nil) { look in
            let hex = look.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            return NSColor(
                srgbRed: CGFloat(hex >> 16 & 0xff) / 255, green: CGFloat(hex >> 8 & 0xff) / 255, blue: CGFloat(hex & 0xff) / 255, alpha: 1)
        })
}

enum Pencil {
    static let red = tone(0xc0212b, 0xff8077)  // what a sync sends
    static let fill = tone(0xc0212b, 0xc0212b)  // Sync now: white words need the darker red in dark mode too
    static let blue = tone(0x1c5e8b, 0x86c5ea)  // the reader's choice, or a question for them
    static let green = tone(0x2c6a39, 0x86cf95)
    static let greenWash = tone(0xe1f0e2, 0x18301e)  // behind a message that something worked
    static let flag = tone(0x17191c, 0xe7e9e4)
    static let onFlag = tone(0xfbfbf8, 0x171a1e)
    static let ink = tone(0x17191c, 0xe7e9e4)
    static let graphite = tone(0x4a4f57, 0xaeb4bb)  // what was found, facts, labels
    static let faint = tone(0x5f656e, 0x959ca4)
    static let edge = tone(0x80868e, 0x6e757e)
    static let ground = tone(0xedefea, 0x0f1114)  // galley stock: under the covers, under the overview's sheets
    static let sheet = tone(0xfbfbf8, 0x171a1e)  // proof sheet: a slip, a cover's ground
    static let margin = tone(0xf4f5f1, 0x1b1f24)  // the proof margin: Hardcover's side
    static let rule = tone(0xcdd1cb, 0x30353c)
    static let ruleSoft = tone(0xe3e6e0, 0x24282e)  // between rows
    static let rail = tone(0xc3e2ef, 0x123040)  // non-repro blue: your Kobo
    static let railInk = tone(0x14222b, 0xe3f1f7)
    static let railGraphite = tone(0x2f4653, 0xa9c6d4)
}

// ---------- the marks ----------
/// One of the page's marks, drawn in the strokes of web/marks.py (a 20 by
/// 20 box, stroke 1.9). A state of the tool's answers picks it: a check, a
/// step or a sync ("ok", "note", "warn", "fail") or a book ("next", "wait",
/// "err", "none", "stet").
struct Mark: View {
    let state: String
    var size: CGFloat = 18
    var dash = Pencil.faint  // the dash and the dashed caret; on the rail, Rail Graphite

    var body: some View {
        OnSelection { selected in
            if state == "stet" {  // the word itself: kept as Hardcover has it
                Text("stet").font(.system(size: size * 0.7, weight: .heavy)).italic().foregroundStyle(selected ? onSelection : Pencil.blue)
                    .frame(minWidth: size, minHeight: size).accessibilityLabel("Kept as on Hardcover")
            } else {
                drawn(selected)
            }
        }
    }

    /// On a selected row every stroke is the selection's white, and the ink square's cross its blue.
    private func drawn(_ selected: Bool) -> some View {
        Canvas { context, box in
            func pencil(_ color: Color) -> Color { selected ? onSelection : color }
            let s = box.width / 20
            func at(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: x * s, y: y * s) }
            func stroke(_ path: Path, _ color: Color, _ width: CGFloat = 1.9, dash: [CGFloat] = []) {
                context.stroke(
                    path, with: .color(color),
                    style: StrokeStyle(lineWidth: width * s, lineCap: .round, lineJoin: .round, dash: dash.map { $0 * s }))
            }
            let caret = Path { p in
                p.move(to: at(4, 15.5))
                p.addLine(to: at(10, 5))
                p.addLine(to: at(16, 15.5))
            }
            switch kind {
            case "ok":
                stroke(Path { p in
                    p.move(to: at(4, 10.5))
                    p.addLine(to: at(8, 15))
                    p.addLine(to: at(16.5, 5))
                }, pencil(Pencil.green))
            case "next":
                stroke(caret, pencil(Pencil.red))
            case "wait":
                stroke(caret, pencil(dash), dash: [2.2, 2.6])
            case "warn":
                stroke(Path(ellipseIn: CGRect(x: 2.4 * s, y: 2.4 * s, width: 15.2 * s, height: 15.2 * s)), pencil(Pencil.blue), 1.7)
                stroke(Path { p in  // the hook of the query: the arc of marks.py, then its curve down
                    p.move(to: at(7.9, 8.1))
                    p.addArc(center: at(10.1, 8.1), radius: 2.2 * s, startAngle: .degrees(180), endAngle: .degrees(60), clockwise: false)
                    p.addCurve(to: at(10, 11.7), control1: at(10.4, 10.5), control2: at(10, 10.9))
                }, pencil(Pencil.blue), 1.7)
                context.fill(Path(ellipseIn: CGRect(x: 9.4 * s, y: 13.5 * s, width: 1.2 * s, height: 1.2 * s)), with: .color(pencil(Pencil.blue)))
            case "err":
                context.fill(Path(roundedRect: CGRect(x: 2.5 * s, y: 2.5 * s, width: 15 * s, height: 15 * s), cornerRadius: 1.5 * s), with: .color(pencil(Pencil.flag)))
                stroke(Path { p in
                    p.move(to: at(7, 7))
                    p.addLine(to: at(13, 13))
                    p.move(to: at(13, 7))
                    p.addLine(to: at(7, 13))
                }, selected ? Color(nsColor: .selectedContentBackgroundColor) : Pencil.onFlag, 1.8)
            default:
                stroke(Path { p in
                    p.move(to: at(5, 10))
                    p.addLine(to: at(15, 10))
                }, pencil(dash))
            }
        }
        .frame(width: size, height: size)
        .accessibilityElement()
        .accessibilityLabel(said)
    }

    /// The tool's states in the page's marks: a problem is the ink square, what needs the reader the query, a note the dash.
    private var kind: String {
        switch state {
        case "fail": return "err"
        case "warn": return "warn"
        case "note": return "none"
        default: return state
        }
    }

    private var said: String {
        switch kind {
        case "ok": return "In order"
        case "next": return "Changes at the next sync"
        case "wait": return "Waiting"
        case "warn": return "Needs you"
        case "err": return "Problem"
        default: return "Note"
        }
    }
}

/// Source Serif 4 for book titles: the page's own font, in the tool's package inside the app
/// (the widget carries a copy).
/// The page has it as two subsets under one name, and the latin-ext one holds no lowercase
/// letters; registered side by side, macOS took that one and set the rest in the system font.
/// So a title is the latin subset, with latin-ext behind it for the letters only it has.
private var titleFaces: (latin: CTFontDescriptor, ext: CTFontDescriptor?)?

func registerTitleFont(in fonts: URL) {
    func face(_ file: String) -> CTFontDescriptor? {
        (CTFontManagerCreateFontDescriptorsFromURL(fonts.appendingPathComponent(file) as CFURL) as? [CTFontDescriptor])?.first
    }
    guard let latin = face("SourceSerif4-latin.woff2") else { return }
    titleFaces = (latin, face("SourceSerif4-latin-ext.woff2"))
}

/// A book title: Source Serif 4 at this weight, sized optically as on the page; else the serif macOS has.
func titleFont(_ size: CGFloat, _ weight: Font.Weight = .semibold) -> Font {
    guard let faces = titleFaces else { return .system(size: size, weight: weight, design: .serif) }
    let wght = weight == .regular ? 400 : weight == .medium ? 500 : weight == .bold ? 700 : weight == .heavy ? 800 : 600
    let axes: [Int: CGFloat] = [0x7767_6874: CGFloat(wght), 0x6F70_737A: min(max(size, 8), 60)]  // "wght", "opsz"
    func at(_ face: CTFontDescriptor) -> CTFontDescriptor {
        CTFontDescriptorCreateCopyWithAttributes(face, [kCTFontVariationAttribute: axes] as CFDictionary)
    }
    var attributes: [CFString: Any] = [kCTFontVariationAttribute: axes]
    if let ext = faces.ext { attributes[kCTFontCascadeListAttribute] = [at(ext)] }
    return Font(CTFontCreateWithFontDescriptor(CTFontDescriptorCreateCopyWithAttributes(faces.latin, attributes as CFDictionary), size, nil))
}

/// The page's line gauge: a rule with a tick every tenth, the part read in ink.
struct Gauge: View {
    let percent: Int
    let finished: Bool

    var body: some View {
        OnSelection { selected in gauge(selected) }
            .frame(maxWidth: 160)
            .frame(height: 6)
            .accessibilityElement()
            .accessibilityLabel(finished ? "Finished" : "\(percent)%")
    }

    private func gauge(_ selected: Bool) -> some View {
        Canvas { context, box in
            let w = box.width
            var rule = Path()
            rule.move(to: CGPoint(x: 0, y: 4.5))
            rule.addLine(to: CGPoint(x: w, y: 4.5))
            for n in 0...10 {
                rule.move(to: CGPoint(x: (w - 1) * CGFloat(n) / 10 + 0.5, y: n == 10 ? 1 : 2.5))
                rule.addLine(to: CGPoint(x: (w - 1) * CGFloat(n) / 10 + 0.5, y: 4.5))
            }
            context.stroke(rule, with: .color(selected ? onSelection.opacity(0.6) : Pencil.edge), lineWidth: 1)
            let read = CGRect(x: 0, y: 3.5, width: w * CGFloat(finished ? 100 : percent) / 100, height: 2)
            context.fill(Path(read), with: .color(selected ? onSelection : finished ? Pencil.green : Pencil.ink))
        }
    }
}

// ---------- on a selected row ----------
/// The words and marks on a selected row of a list: white on the selection's blue.
let onSelection = Color(nsColor: .alternateSelectedControlTextColor)

/// Whether this is drawn on a selected row (the key window's, in its blue), where
/// the pencils' colours would sink: macOS 14 and later say; before, never.
struct OnSelection<Content: View>: View {
    @ViewBuilder let content: (Bool) -> Content

    var body: some View {
        if #available(macOS 14, *) { Prominence(content: content) } else { content(false) }
    }
}

@available(macOS 14, *)
private struct Prominence<Content: View>: View {
    let content: (Bool) -> Content
    @Environment(\.backgroundProminence) private var prominence

    var body: some View { content(prominence == .increased) }
}

/// Graphite for what was found, facts and labels; on a selected row the selection's quieter white.
func quiet(_ selected: Bool) -> AnyShapeStyle { selected ? AnyShapeStyle(.secondary) : AnyShapeStyle(Pencil.graphite) }

/// A pencil's colour; on a selected row the selection's white.
func pencil(_ color: Color, _ selected: Bool) -> AnyShapeStyle { selected ? AnyShapeStyle(onSelection) : AnyShapeStyle(color) }

/// A cover from the tool's cache, or the crossed box of a book without one.
/// The small ones (240 points wide, the run's) are all kept, as the run shows
/// them again and again; of the large ones (`book --large-cover`, some 9 MB
/// each when drawn) only the last few.
struct Cover: View {
    let path: String
    let width: CGFloat
    private static var cache: [String: NSImage] = [:]
    private static var large: [(path: String, image: NSImage)] = []  // the last used first
    private static let largeKept = 4

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
        if let n = large.firstIndex(where: { $0.path == path }) {
            let kept = large.remove(at: n)
            large.insert(kept, at: 0)
            return kept.image
        }
        guard let image = NSImage(contentsOfFile: path) else { return nil }
        if (image.representations.first?.pixelsWide ?? 0) > 600 { keep(path, image) } else { cache[path] = image }
        return image
    }

    /// A large cover, read and decoded away from the main thread, so that showing it does not wait on either.
    static func prepare(_ path: String) -> NSImage? {
        guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
            let image = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary)
        else { return nil }
        return NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height))
    }

    /// A large cover kept, on the main thread: the oldest goes when there are more than a few.
    static func keep(_ path: String, _ image: NSImage) {
        large.removeAll { $0.path == path }
        large.insert((path, image), at: 0)
        if large.count > largeKept { large.removeLast(large.count - largeKept) }
    }
}
