// The overview (docs/plans/2026-10-24-mac-app-native-books-design.md): the
// sync drawn as the path it takes, Kobo → This Mac → (Server) → Hardcover,
// each link with its mark, and the page's marks drawn as the page draws
// them (web/marks.py), in the page's colours (DESIGN.md).

import AppKit
import SwiftUI

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
        // Who, and live or a dry run: from the status in local mode, from the books answer (the server's) in server mode.
        let who: (live: Bool, user: String)? = books.map { ($0.live, $0.user) } ?? self.books.map { ($0.live, $0.user) }
        let hardcover: String
        if let who, !who.user.isEmpty {
            hardcover = who.live ? "Live · @\(who.user)" : "Dry run · @\(who.user)"
        } else if who == nil && server {
            hardcover = "Checked on the server"  // the server's books not answered yet
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
                    if n > 0 {
                        ArrowView(above: above(n, links), below: below(n, links), working: working(n, links), sends: sends(n, links))
                            .frame(minWidth: 70, maxWidth: 130)
                    }
                    linkView(link).frame(width: 118)
                }
            }
            VStack(alignment: .leading, spacing: 4) {  // a narrow window: the chain from top to bottom
                ForEach(links) { link in linkView(link) }
            }
        }
        .frame(maxWidth: .infinity)
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

    /// Live, with books to send: the count on the way to Hardcover is what the next sync sends.
    private func sends(_ n: Int, _ links: [ChainLink]) -> Bool {
        guard let books = model.status?.books else { return false }
        return links[n].id == "Hardcover" && books.live && books.next > 0
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

/// A link of the chain on the overview's proof sheet. Your Kobo is the
/// page's non-repro blue rail, Hardcover its proof margin behind the double
/// rule; This Mac and the server are on the sheet itself. What it says is in
/// the colour of its mark when it needs you: blue for a question, ink for a failure.
struct LinkView: View {
    let link: ChainLink
    let state: String
    let checking: Bool
    let chosen: Bool
    let choose: () -> Void

    private var kobo: Bool { link.id == "Kobo" }
    private var name: Color { kobo ? Pencil.railInk : Pencil.ink }
    private var line: Color {
        switch state {
        case "warn": return Pencil.blue
        case "fail": return name
        default: return kobo ? Pencil.railGraphite : Pencil.graphite
        }
    }

    var body: some View {
        Button(action: choose) {
            VStack(spacing: 5) {
                Group {
                    if checking && link.id != "Kobo" && link.checks.count <= 1 {
                        ProgressView().controlSize(.small)
                    } else {
                        Mark(state: state, size: 24, dash: kobo ? Pencil.railGraphite : Pencil.faint)
                    }
                }
                .frame(height: 26)
                Text(link.id).font(.headline).foregroundStyle(name)
                Text(link.said).font(.caption.weight(state == "fail" ? .semibold : .regular)).foregroundStyle(line)
                    .multilineTextAlignment(.center).lineLimit(3)
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity)
            .background { slip }
            .overlay(alignment: .bottom) {  // the open link: a rule under it, as the page marks where you are
                if chosen { Rectangle().fill(name).frame(height: 2).padding(.horizontal, 18).padding(.bottom, 3) }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(chosen ? .isSelected : [])
        .accessibilityHint(chosen ? "Hides its checks" : "Shows its checks")
    }

    @ViewBuilder private var slip: some View {
        if kobo {
            RoundedRectangle(cornerRadius: 3).fill(Pencil.rail)
        } else if link.id == "Hardcover" {
            HStack(spacing: 1) {  // the proofreader's double rule, down the margin's left
                Pencil.rule.frame(width: 1)
                Pencil.rule.frame(width: 1)
                Pencil.margin
            }
        }
    }
}

/// The way from one link to the next, with the books it carries; while a
/// sync works on it, the page's red line gauge sweeps along it.
struct ArrowView: View {
    let above: String
    let below: String
    let working: Bool
    var sends = false  // what it carries goes to Hardcover at the next sync: in red, with the caret
    @Environment(\.accessibilityReduceMotion) private var still
    @State private var sweep = false

    var body: some View {
        VStack(spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                if sends { Mark(state: "next", size: 12).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 2 } }
                Text(above).font(.caption.monospacedDigit().weight(sends ? .semibold : .regular))
                    .foregroundStyle(sends ? Pencil.red : Pencil.graphite).lineLimit(2).multilineTextAlignment(.center)
            }
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
            Text(below).font(.caption.monospacedDigit()).foregroundStyle(Pencil.graphite).lineLimit(2).multilineTextAlignment(.center)
        }
        .padding(.horizontal, 6)
        .padding(.top, 14)
        .accessibilityElement(children: .combine)
        .accessibilityLabel([above, below, working ? "Syncing" : ""].filter { !$0.isEmpty }.joined(separator: ", "))
    }
}
