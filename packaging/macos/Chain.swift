// The overview (docs/plans/2026-10-24-mac-app-native-books-design.md): the
// sync drawn as the path it takes, Kobo → This Mac → (Server) → Hardcover,
// each link with its mark, and the page's marks drawn as the page draws
// them (web/marks.py), in the page's colours (DESIGN.md).

import AppKit
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
    static let flag = tone(0x17191c, 0xe7e9e4)
    static let onFlag = tone(0xfbfbf8, 0x171a1e)
    static let faint = tone(0x5f656e, 0x959ca4)
    static let edge = tone(0x80868e, 0x6e757e)
    static let ground = tone(0xedefea, 0x0f1114)  // galley stock: under the covers
    static let sheet = tone(0xfbfbf8, 0x171a1e)  // proof sheet: a slip, a cover's ground
    static let rule = tone(0xcdd1cb, 0x30353c)
}

// ---------- the marks ----------
/// One of the page's marks, drawn in the strokes of web/marks.py (a 20 by
/// 20 box, stroke 1.9). A state of the tool's answers picks it: a check, a
/// step or a sync ("ok", "note", "warn", "fail") or a book ("next", "wait",
/// "err", "none", "stet").
struct Mark: View {
    let state: String
    var size: CGFloat = 18

    var body: some View {
        if state == "stet" {  // the word itself: kept as Hardcover has it
            Text("stet").font(.system(size: size * 0.7, weight: .heavy)).italic().foregroundStyle(Pencil.blue)
                .frame(minWidth: size, minHeight: size).accessibilityLabel("Kept as on Hardcover")
        } else {
            drawn
        }
    }

    private var drawn: some View {
        Canvas { context, box in
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
                }, Pencil.green)
            case "next":
                stroke(caret, Pencil.red)
            case "wait":
                stroke(caret, Pencil.faint, dash: [2.2, 2.6])
            case "warn":
                stroke(Path(ellipseIn: CGRect(x: 2.4 * s, y: 2.4 * s, width: 15.2 * s, height: 15.2 * s)), Pencil.blue, 1.7)
                stroke(Path { p in  // the hook of the query: the arc of marks.py, then its curve down
                    p.move(to: at(7.9, 8.1))
                    p.addArc(center: at(10.1, 8.1), radius: 2.2 * s, startAngle: .degrees(180), endAngle: .degrees(60), clockwise: false)
                    p.addCurve(to: at(10, 11.7), control1: at(10.4, 10.5), control2: at(10, 10.9))
                }, Pencil.blue, 1.7)
                context.fill(Path(ellipseIn: CGRect(x: 9.4 * s, y: 13.5 * s, width: 1.2 * s, height: 1.2 * s)), with: .color(Pencil.blue))
            case "err":
                context.fill(Path(roundedRect: CGRect(x: 2.5 * s, y: 2.5 * s, width: 15 * s, height: 15 * s), cornerRadius: 1.5 * s), with: .color(Pencil.flag))
                stroke(Path { p in
                    p.move(to: at(7, 7))
                    p.addLine(to: at(13, 13))
                    p.move(to: at(13, 7))
                    p.addLine(to: at(7, 13))
                }, Pencil.onFlag, 1.8)
            default:
                stroke(Path { p in
                    p.move(to: at(5, 10))
                    p.addLine(to: at(15, 10))
                }, Pencil.faint)
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

// ---------- the chain ----------
/// A link of the chain: a part the sync passes through, with the checks of `doctor` about it.
struct ChainLink: Identifiable {
    let id: String  // "Kobo", "This Mac", "Server", "Hardcover"
    let checks: [Check]
    let line: String  // how it is, in a few words, when nothing is wrong with it

    /// The worst of its checks, else what its own check says: a Kobo not
    /// plugged in, or Hardcover not connected yet, is the dash, never a warning.
    var state: String {
        if checks.contains(where: { $0.state == "fail" }) { return "fail" }
        if checks.contains(where: { $0.state == "warn" }) { return "warn" }
        if checks.first(where: { $0.what == own })?.state == "note" { return "note" }
        return checks.isEmpty ? "note" : "ok"
    }

    /// The check that says whether the link itself is there.
    private var own: String {
        switch id {
        case "This Mac": return "Trigger"
        default: return id  // "Kobo", "Server", "Hardcover"
        }
    }

    /// What is wrong, else how it is.
    var said: String {
        checks.first { $0.state == "fail" }.map(\.found) ?? checks.first { $0.state == "warn" }.map(\.found) ?? line
    }
}

/// Where a step of `sync --steps` happens on the chain.
func linkOf(step: String) -> String {
    switch step {
    case "Kobo", "Collection": return "Kobo"
    case "Upload": return "Server"
    case "Hardcover", "Matches": return "Hardcover"
    default: return "This Mac"
    }
}

extension WindowModel {
    /// The links in the order a sync takes them, from doctor's groups: the
    /// Server check is a link of its own, the notifications belong to this Mac.
    var links: [ChainLink] {
        let checks = (self.checks ?? []) + [notificationsCheck]
        let status = self.status
        let books = status?.books
        let server = status?.mode == "server"
        var out = [
            ChainLink(
                id: "Kobo", checks: checks.filter { $0.group == "Your Kobo" },
                line: status?.kobo != nil ? "Plugged in" : status?.lastSync?.date.map { "Last seen \(spoken($0).lowercased())" } ?? "Not plugged in"),
            ChainLink(
                id: "This Mac", checks: checks.filter { ($0.group == "This computer" || $0.group == "Also") && $0.what != "Server" },
                line: "Syncs when the Kobo is plugged in"),
        ]
        if server {
            out.append(
                ChainLink(id: "Server", checks: checks.filter { $0.what == "Server" }, line: URL(string: status?.server ?? "")?.host ?? ""))
        }
        let hardcover: String
        if server {
            hardcover = "Checked on the server"
        } else if let books, !books.user.isEmpty {
            hardcover = books.live ? "Live · @\(books.user)" : "Dry run · @\(books.user)"
        } else {
            hardcover = "Not connected yet"
        }
        out.append(ChainLink(id: "Hardcover", checks: checks.filter { $0.group == "Hardcover" }, line: hardcover))
        return out
    }

    /// The notifications as a check of this Mac: what only macOS knows.
    var notificationsCheck: Check {
        let (state, found): (String, String)
        switch notifications {
        case .denied: (state, found) = ("warn", "Off: a sync started by plugging in the Kobo does not say what it did.")
        case .notDetermined: (state, found) = ("note", "Not allowed yet: they say what a sync did.")
        default:
            (state, found) =
                previews == .never
                ? ("note", "On, but they show only the app's name: Show previews is Never in macOS's settings.")
                : ("ok", "On: each sync says what it did.")
        }
        return Check(group: "This computer", what: "Notifications", state: state, found: found, todo: "")
    }

    /// The links a sync now running has passed, with how it went there.
    var passed: [String: String] {
        var out: [String: String] = [:]
        for step in steps {
            let link = linkOf(step: step.step ?? "")
            let state = step.state ?? "note"
            if out[link] != "fail" && (out[link] != "warn" || state == "fail") { out[link] = state }
        }
        if out["Kobo"] != nil && out["This Mac"] == nil { out["This Mac"] = "ok" }  // the Mac read it
        return out
    }
}

struct ChainView: View {
    @ObservedObject var model: WindowModel
    @Binding var open: String?

    var body: some View {
        let links = model.links
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: 0) {
                ForEach(Array(links.enumerated()), id: \.element.id) { n, link in
                    if n > 0 { ArrowView(above: above(n, links), below: below(n, links), working: working(n, links)).frame(minWidth: 70, maxWidth: 130) }
                    linkView(link).frame(width: 118)
                }
            }
            VStack(alignment: .leading, spacing: 4) {  // a narrow window: the chain from top to bottom
                ForEach(links) { link in linkView(link) }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
    }

    private func linkView(_ link: ChainLink) -> some View {
        let syncing = model.syncing || !model.elsewhere.isEmpty || model.outcome != nil
        let state = syncing ? model.passed[link.id] ?? link.state : link.state
        return LinkView(link: link, state: state, checking: model.checks == nil, chosen: open == link.id) {
            open = open == link.id ? "" : link.id
        }
    }

    /// The counts the arrows carry, in local mode, where the books are on this Mac.
    private func above(_ n: Int, _ links: [ChainLink]) -> String {
        guard let books = model.status?.books else { return "" }
        switch links[n].id {
        case "This Mac": return "\(books.total) \(books.total == 1 ? "book" : "books")"
        case "Hardcover":
            if books.next == 0 { return books.on == 0 ? "None switched on" : "Nothing to send" }
            return books.live ? "\(books.next) to send" : "\(books.next) would be sent"
        default: return ""
        }
    }

    private func below(_ n: Int, _ links: [ChainLink]) -> String {
        guard links[n].id == "This Mac", let books = model.status?.books, !books.collection.isEmpty else { return "" }
        return "← \(books.on) in \(books.collection)"
    }

    /// The arrow a sync now running is working on: after the last link it passed.
    private func working(_ n: Int, _ links: [ChainLink]) -> Bool {
        guard model.outcome == nil else { return false }
        if !model.elsewhere.isEmpty && !model.syncing { return n == 1 }  // started by the Kobo: no steps come here
        guard model.syncing else { return false }
        let passed = model.passed
        let reached = links.prefix { passed[$0.id] != nil }.count
        return n == max(reached, 1)
    }
}

struct LinkView: View {
    let link: ChainLink
    let state: String
    let checking: Bool
    let chosen: Bool
    let choose: () -> Void

    var body: some View {
        Button(action: choose) {
            VStack(spacing: 5) {
                Group {
                    if checking && link.id != "Kobo" && link.checks.count <= 1 {
                        ProgressView().controlSize(.small)
                    } else {
                        Mark(state: state, size: 24)
                    }
                }
                .frame(height: 26)
                Text(link.id).font(.headline)
                Text(link.said).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).lineLimit(3)
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 6)
            .frame(maxWidth: .infinity)
            .background(RoundedRectangle(cornerRadius: 8).fill(chosen ? Color.primary.opacity(0.07) : .clear))
            .contentShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityHint(chosen ? "Hides its checks" : "Shows its checks")
    }
}

/// The way from one link to the next, with the books it carries; while a
/// sync works on it, the page's red line gauge sweeps along it.
struct ArrowView: View {
    let above: String
    let below: String
    let working: Bool
    @Environment(\.accessibilityReduceMotion) private var still
    @State private var sweep = false

    var body: some View {
        VStack(spacing: 3) {
            Text(above).font(.caption.monospacedDigit()).foregroundStyle(.secondary).lineLimit(2).multilineTextAlignment(.center)
                .frame(minHeight: 16, alignment: .bottom)
            GeometryReader { box in
                let w = box.size.width
                ZStack(alignment: .leading) {
                    Path { p in
                        p.move(to: CGPoint(x: 0, y: 5))
                        p.addLine(to: CGPoint(x: w - 1, y: 5))
                        p.move(to: CGPoint(x: w - 7, y: 1))
                        p.addLine(to: CGPoint(x: w - 1, y: 5))
                        p.addLine(to: CGPoint(x: w - 7, y: 9))
                    }
                    .stroke(Pencil.edge, style: StrokeStyle(lineWidth: 1, lineCap: .round, lineJoin: .round))
                    if working {
                        Rectangle().fill(Pencil.red).frame(width: still ? w - 8 : w / 3, height: 2)
                            .offset(x: still ? 0 : (sweep ? w * 2 / 3 - 8 : 0), y: 0)
                            .onAppear {
                                guard !still else { return }
                                withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { sweep = true }
                            }
                            .onDisappear { sweep = false }
                    }
                }
            }
            .frame(height: 10)
            Text(below).font(.caption.monospacedDigit()).foregroundStyle(.secondary).lineLimit(2).multilineTextAlignment(.center)
        }
        .padding(.horizontal, 6)
        .padding(.top, 14)
        .accessibilityElement(children: .combine)
        .accessibilityLabel([above, below, working ? "Syncing" : ""].filter { !$0.isEmpty }.joined(separator: ", "))
    }
}
