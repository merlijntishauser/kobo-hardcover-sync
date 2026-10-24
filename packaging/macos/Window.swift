// The app's window (docs/plans/2026-10-24-mac-app-native-books-design.md):
// one line that answers "is it ready", above a sidebar of Overview (the
// chain, Chain.swift), Books and History. Everything comes from the tool,
// as JSON (Model.swift); what only macOS knows (whether notifications are
// on) is added here.

import AppKit
import ServiceManagement
import SwiftUI
import UserNotifications

/// What the window shows. Filled on a background queue, published on the main one.
final class WindowModel: ObservableObject {
    @Published var status: StatusAnswer?
    @Published var checks: [Check]?  // nil while being checked
    @Published var summary = ""
    @Published var syncs: [Sync] = []
    @Published var broken: String?  // the tool did not answer: nothing else can be shown
    @Published var steps: [StepLine] = []
    @Published var outcome: StepLine.Done?
    @Published var syncing = false  // Sync now, in this window
    @Published var elsewhere = ""  // a sync this window did not start, while it runs: what started it
    @Published var notifications = UNAuthorizationStatus.notDetermined
    @Published var previews = UNShowPreviewsSetting.always
    @Published var newer: String?
    @Published var pane: Pane? = .overview

    let setUp: () -> Void
    private var foldSince: String?  // the newest sync in History when Sync now was clicked
    private var run = 0  // which Sync now the steps on screen belong to
    private var watcher: DispatchSourceFileSystemObject?
    private var pending: DispatchWorkItem?

    init(setUp: @escaping () -> Void) {
        self.setUp = setUp
    }

    /// Everything again; the check (which asks the server or Hardcover) unless only the files changed.
    func refresh(check: Bool = true) {
        if check { checks = nil }
        DispatchQueue.global(qos: .userInitiated).async {
            let status = answer(StatusAnswer.self, ["status", "--json"])
            let history = answer(HistoryAnswer.self, ["history", "--json"])
            let newer = newerVersion()
            DispatchQueue.main.async {
                switch status {
                case .success(let found):
                    self.status = found
                    self.broken = nil
                    self.elsewhere = found.syncing ?? ""
                case .failure(let why):
                    self.broken = why.said
                }
                if case .success(let found) = history {
                    self.syncs = found.syncs
                    self.foldIntoHistory()
                }
                self.newer = newer
            }
            guard check else { return }
            let doctor = answer(DoctorAnswer.self, ["doctor", "--json"])
            DispatchQueue.main.async {
                switch doctor {
                case .success(let found):
                    self.checks = found.checks
                    self.summary = found.summary
                case .failure(let why):
                    self.checks = [Check(group: "This computer", what: "Check", state: "fail", found: why.said, todo: "")]
                    self.summary = ""
                }
            }
        }
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                self.notifications = settings.authorizationStatus
                self.previews = settings.showPreviewsSetting
            }
        }
    }

    /// Sync now: the steps as they come, then the outcome; History follows by itself.
    /// While a sync the Kobo started runs, the window shows that one instead.
    func syncNow() {
        guard !syncing && elsewhere.isEmpty else { return }
        syncing = true
        steps = []
        outcome = nil
        foldSince = syncs.first?.id ?? ""
        run += 1
        if isPreview { return playSampleSync() }
        DispatchQueue.global(qos: .userInitiated).async {
            if case .success(let now) = answer(StatusAnswer.self, ["status", "--json"]), let started = now.syncing, !started.isEmpty {
                DispatchQueue.main.async {
                    self.syncing = false
                    self.elsewhere = started
                }
                return
            }
            let ended = toolLines(["sync", "--trigger", "app", "--steps"]) { line in
                guard case .success(let step) = decode(StepLine.self, line) else { return }
                DispatchQueue.main.async {
                    if let done = step.done { self.outcome = done } else { self.steps.append(step) }
                }
            }
            DispatchQueue.main.async {
                if self.outcome == nil {
                    self.outcome = StepLine.Done(ok: false, title: name, message: ended ? "Done." : stoppedWithoutWord)
                }
                self.syncing = false
                self.refresh(check: false)
            }
        }
    }

    /// Sync now's steps fold into History once a newer sync is there: their
    /// own, a few seconds after, to be read; or, after an answer History does
    /// not keep ("No Kobo found"), the next sync, which makes it old news.
    private func foldIntoHistory() {
        guard let since = foldSince, !syncing, outcome != nil, (syncs.first?.id ?? "") != since else { return }
        foldSince = nil
        let shown = run
        DispatchQueue.main.asyncAfter(deadline: .now() + 6) {
            guard shown == self.run, !self.syncing else { return }
            self.steps = []
            self.outcome = nil
        }
    }

    func askForNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert]) { _, _ in
            DispatchQueue.main.async { self.refresh(check: false) }
        }
    }

    /// History and the top line follow a sync the Kobo started in another
    /// process: the history file is replaced at the end of every sync.
    func watch() {
        let fd = open(stateDir().path, O_EVTONLY)
        guard fd >= 0 else { return }
        let source = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: .write, queue: .main)
        source.setEventHandler { [weak self] in
            guard let self, !self.syncing else { return }
            self.pending?.cancel()
            let later = DispatchWorkItem { self.refresh(check: false) }
            self.pending = later
            DispatchQueue.main.asyncAfter(deadline: .now() + 1, execute: later)
        }
        source.setCancelHandler { close(fd) }
        source.resume()
        watcher = source
    }

    func stop() {
        watcher?.cancel()
        watcher = nil
    }

    /// The preview build syncs nothing: it plays the steps a sync shows.
    private func playSampleSync() {
        let sample = [
            StepLine(schema: schema, step: "Kobo", state: "ok", text: "Kobo Clara Colour: 3 books updated", done: nil),
            StepLine(schema: schema, step: "Upload", state: "ok", text: "Sent to the server", done: nil),
            StepLine(schema: schema, step: "Collection", state: "ok", text: "'Hardcover' is up to date", done: nil),
        ]
        for (n, step) in sample.enumerated() {
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(700 * (n + 1))) { self.steps.append(step) }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(700 * (sample.count + 1))) {
            self.outcome = StepLine.Done(ok: true, title: "Kobo synced", message: "3 books updated. (Preview: nothing was synced.)")
            self.syncing = false
        }
    }
}

/// Why the tool gave no answer, in words for the window.
struct NoAnswer: Error {
    let said: String
}

/// An answer of the tool, or why there is none.
func answer<T: Codable>(_ type: T.Type, _ args: [String]) -> Result<T, NoAnswer> {
    let (_, output) = tool(args)
    let json = output.split(separator: "\n").last { $0.hasPrefix("{") }.map(String.init) ?? ""
    switch decode(type, json) {
    case .success(let found):
        return .success(found)
    case .failure(AnswerError.otherSchema(let other)):
        return .failure(NoAnswer(said: "The app and its tool do not agree (schema \(other)). Download the app again."))
    case .failure:
        let said = output.trimmingCharacters(in: .whitespacesAndNewlines)
        return .failure(NoAnswer(said: said.isEmpty ? "The app's tool did not answer. Download the app again." : said))
    }
}

// ---------- the window ----------
/// What the sidebar holds.
enum Pane: String, CaseIterable, Identifiable {
    case overview = "Overview", books = "Books", history = "History"

    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .overview: return "link"
        case .books: return "books.vertical"
        case .history: return "clock"
        }
    }
}

struct MainView: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        NavigationSplitView {
            List(selection: $model.pane) {
                ForEach(Pane.allCases) { pane in
                    Label(pane.rawValue, systemImage: pane.symbol)
                        .badge(pane == .books ? model.status?.books?.needsMatch ?? 0 : 0)  // books that wait for a match
                        .tag(pane)
                }
            }
            .navigationSplitViewColumnWidth(min: 150, ideal: 170, max: 220)
        } detail: {
            VStack(spacing: 0) {
                TopLine(model: model).padding(.horizontal, 20).padding(.vertical, 12)
                Divider()
                Form {
                    if let broken = model.broken {
                        Section { Row(state: "fail", what: "The tool", found: broken) }
                    } else {
                        switch model.pane ?? .overview {
                        case .overview: OverviewSections(model: model)
                        case .books: BooksSections(model: model)
                        case .history: HistorySection(model: model)
                        }
                    }
                }
                .formStyle(.grouped)
            }
        }
        .frame(minWidth: 700, minHeight: 520)
    }
}

struct TopLine: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Group {
                if busy {
                    ProgressView().controlSize(.small)
                } else {
                    Mark(state: readiness.state, size: 22)
                }
            }
            .frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(busy ? "Syncing…" : readiness.sentence).font(.title3.weight(.semibold))
                Text(subtitle).foregroundStyle(.secondary).textSelection(.enabled)
            }
            Spacer(minLength: 12)
            Button("Open the page") { _ = tool(["open"]) }
                .disabled(model.status?.mode.isEmpty ?? true)
            Button("Sync now") { model.syncNow() }
                .buttonStyle(.borderedProminent)
                .tint(Pencil.fill)  // red fills only what a sync sends
                .keyboardShortcut("r", modifiers: .command)
                .disabled(busy || (model.status?.mode.isEmpty ?? true))
        }
    }

    private var busy: Bool { model.syncing || !model.elsewhere.isEmpty }

    private var readiness: (sentence: String, state: String) {
        guard let status = model.status else { return ("Kobo Hardcover Sync", "note") }
        if status.mode.isEmpty { return ("Not set up yet", "warn") }
        guard model.checks != nil else { return ("Checking…", "note") }
        let links = model.links
        if let broken = links.first(where: { $0.state == "fail" }) { return ("Needs attention: \(broken.id)", "fail") }
        if links.contains(where: { $0.state == "warn" }) { return ("Ready, with a warning", "warn") }
        return ("Ready for the Kobo", "ok")
    }

    private var subtitle: String {
        guard let status = model.status else { return "" }
        if !model.elsewhere.isEmpty && !model.syncing {
            return model.elsewhere == "mount" ? "Started by plugging in the Kobo. It shows here when it is done." : "Started elsewhere. It shows here when it is done."
        }
        var parts: [String] = []
        switch status.mode {
        case "server": parts.append("With the server \(URL(string: status.server)?.host ?? status.server)")
        case "local": parts.append("On this Mac")
        default: parts.append("Choose where your reading goes")
        }
        if let last = status.lastSync, let date = last.date { parts.append("last sync \(spoken(date).lowercased())") }
        if status.kobo != nil { parts.append("Kobo plugged in") }
        return parts.joined(separator: " · ")
    }
}

/// The chain, a sync as it runs, and the checks of the link that is open:
/// by itself the first that needs the reader, else the one clicked.
struct OverviewSections: View {
    @ObservedObject var model: WindowModel
    @State private var chosen: String?  // nil: the first link with a problem; "": none

    var body: some View {
        if let version = model.newer {
            Section {
                Row(state: "note", what: "Version \(version) is out", found: "This is \(bundleVersion()).") {
                    Button("Get it") { if let link = URL(string: releases + version) { NSWorkspace.shared.open(link) } }
                }
            }
        }
        Section {
            ChainView(model: model, open: $chosen)
        } footer: {
            HStack {
                Text(model.checks == nil ? "Checking everything a sync depends on…" : model.summary).foregroundStyle(.secondary)
                Spacer()
                Button("Check again") { model.refresh() }.disabled(model.checks == nil)
            }
        }
        if model.syncing || model.outcome != nil { SyncSection(model: model) }
        if let link = model.links.first(where: { $0.id == open }), model.checks != nil {
            Section(link.id) {
                ForEach(link.checks) { check in
                    Row(state: check.state, what: check.what, found: check.found, todo: check.todo) { fix(check) }
                }
            }
        }
    }

    private var open: String? {
        if let chosen { return chosen.isEmpty ? nil : chosen }
        return model.links.first { $0.state == "fail" || $0.state == "warn" }?.id
    }

    /// The button that mends what a check found, where the app can.
    @ViewBuilder private func fix(_ check: Check) -> some View {
        if check.what == "Notifications" {
            switch model.notifications {
            case .denied: Button("Turn on") { if let url = URL(string: notificationSettings) { NSWorkspace.shared.open(url) } }
            case .notDetermined: Button("Allow") { model.askForNotifications() }
            default:
                if model.previews == .never {
                    Button("Show previews") { if let url = URL(string: notificationSettings) { NSWorkspace.shared.open(url) } }
                }
            }
        } else if check.state == "fail" || check.state == "warn" {
            switch check.what {
            case "Setup", "Upload token":
                Button("Set up") { model.setUp() }
            case "Trigger":
                Button("Open Login Items") { SMAppService.openSystemSettingsLoginItems() }
            case "Database" where check.found.contains("does not let"):
                Button("Open Privacy") { if let url = URL(string: privacySettings) { NSWorkspace.shared.open(url) } }
            case _ where check.todo.contains("on the page"):  // connecting to Hardcover, a match, the collection's name
                Button("Open the page") { _ = tool(["open"]) }
            default:
                EmptyView()
            }
        }
    }
}

struct SyncSection: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        Section("Sync now") {
            ForEach(Array(model.steps.enumerated()), id: \.offset) { _, step in
                Row(state: step.state ?? "note", what: step.step ?? "", found: step.text ?? "")
            }
            if let done = model.outcome {
                Row(state: done.ok ? "ok" : "fail", what: done.title, found: done.message, strong: true)
            } else if model.steps.isEmpty {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Looking for the Kobo…").foregroundStyle(.secondary)
                }
            }
        }
    }
}

/// Until the books are drawn here, what is known of them, and the page.
struct BooksSections: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        Section {
            if let books = model.status?.books {
                LabeledContent("From the Kobo", value: "\(books.total) \(books.total == 1 ? "book" : "books")")
                LabeledContent("Switched on to sync", value: "\(books.on)")
                if books.needsMatch > 0 {
                    Row(state: "warn", what: "\(books.needsMatch) need a match", found: "Hardcover has more than one book that could be it, or none.")
                }
                if books.next > 0 {
                    Row(
                        state: "next", what: books.live ? "\(books.next) change at the next sync" : "\(books.next) would change at the next sync",
                        found: books.live ? "Sync now sends them." : "A dry run: nothing is sent until you go live, on the page.")
                }
            } else if model.status?.mode == "server" {
                Text("Your books are on the server, behind its sign-in.").foregroundStyle(.secondary)
            } else {
                Text("No books yet: nothing was read from a Kobo so far. Plug it in.").foregroundStyle(.secondary)
            }
        } footer: {
            HStack {
                Text("The books open on the page, in your browser.").foregroundStyle(.secondary)
                Spacer()
                Button("Open the books") { _ = tool(["open"]) }.disabled(model.status?.mode.isEmpty ?? true)
            }
        }
    }
}

struct HistorySection: View {
    @ObservedObject var model: WindowModel
    private let started = ["mount": "Kobo plugged in", "app": "Sync now", "hand": "By hand"]

    var body: some View {
        Section {
            if model.syncs.isEmpty {
                Text("No syncs yet. Plug in the Kobo.").foregroundStyle(.secondary)
            }
            ForEach(model.syncs.prefix(25)) { sync in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Mark(state: sync.ok ? "ok" : "fail").alignmentGuide(.firstTextBaseline) { $0[.bottom] - 4 }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(sync.message.isEmpty ? "Nothing new." : sync.message)
                        Text([sync.date.map(spoken), started[sync.trigger]].compactMap { $0 }.joined(separator: " · "))
                            .font(.callout).foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .combine)
            }
        } header: {
            Text("History")
        } footer: {
            HStack {
                Spacer()
                Button("Show the log") { showLog() }
            }
        }
    }
}

/// A check, a step or a sync: its mark, what it is about, what was found.
struct Row<Fix: View>: View {
    let state: String
    let what: String
    let found: String
    var todo = ""
    var strong = false
    @ViewBuilder var fix: () -> Fix

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Mark(state: state).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 4 }
            VStack(alignment: .leading, spacing: 2) {
                Text(what).fontWeight(strong ? .semibold : .medium)
                Text(found).foregroundStyle(.secondary).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                if !todo.isEmpty {
                    Text(todo).font(.callout).fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 8)
            fix()
        }
        .accessibilityElement(children: .contain)
    }
}

extension Row where Fix == EmptyView {
    init(state: String, what: String, found: String, todo: String = "", strong: Bool = false) {
        self.init(state: state, what: what, found: found, todo: todo, strong: strong) { EmptyView() }
    }
}

/// "Today at 10:22", the way this Mac says dates.
func spoken(_ date: Date) -> String {
    let say = DateFormatter()
    say.dateStyle = .medium
    say.timeStyle = .short
    say.doesRelativeDateFormatting = true
    return say.string(from: date)
}

func bundleVersion() -> String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
}

/// agent.log in Console, which follows it as it grows.
func showLog() {
    let log = stateDir().appendingPathComponent("agent.log")
    let console = URL(fileURLWithPath: "/System/Applications/Utilities/Console.app")
    NSWorkspace.shared.open([log], withApplicationAt: console, configuration: NSWorkspace.OpenConfiguration())
}
