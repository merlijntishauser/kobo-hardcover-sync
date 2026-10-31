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
/// One shelf for the widget at a time.
private let shelfQueue = DispatchQueue(label: "shelf", qos: .utility)

final class WindowModel: ObservableObject {
    @Published var status: StatusAnswer?
    @Published var checks: [Check]?  // nil while being checked
    @Published var summary = ""
    @Published var syncs: [Sync] = []
    @Published var broken: String?  // the tool did not answer: nothing else can be shown
    @Published var steps: [StepLine] = []
    @Published var outcome: StepLine.Done? {
        didSet {
            guard let outcome else { return }  // folded into History: the top line keeps what it said
            told = Told(ok: outcome.ok, message: outcome.message, date: Date())
            announce("\(outcome.title). \(outcome.message)")
        }
    }
    @Published var syncing = false {  // Sync now, in this window
        didSet { if syncing && !oldValue { announce("Syncing") } }
    }
    @Published var elsewhere = "" {  // a sync this window did not start, while it runs: what started it
        didSet {
            if oldValue.isEmpty && !elsewhere.isEmpty {
                elsewhereSince = syncs.first?.id ?? ""
                told = nil
            }
        }
    }
    /// What the last sync that ended while this window was open said: on the
    /// top line, from every pane, until the next sync starts or a check is run.
    @Published var told: Told?
    @Published var notifications = UNAuthorizationStatus.notDetermined
    @Published var previews = UNShowPreviewsSetting.always
    @Published var newer: String?
    @Published var pane: Pane? = .overview
    @Published var books: BooksAnswer? {  // local mode: the list, from `books --json`
        didSet {
            guard let books else { return }
            shelfQueue.async { keepShelf(books.books, tip: books.tip) }  // the widget's shelf (Shelf.swift)
        }
    }
    @Published var booksBroken: String?
    @Published var search = ""
    @Published var filter = UserDefaults.standard.string(forKey: "BooksShow") ?? "all" {  // Show: remembered, apart from Covers'
        didSet { UserDefaults.standard.set(filter, forKey: "BooksShow") }
    }
    @Published var sort = "last_read"
    @Published var chosenBook: String?  // the book whose Details are open
    @Published var spotlit: String?  // a book chosen in Spotlight: Covers brings it up
    @Published var enlarged: BooksAnswer.Book?  // its cover over the whole window (Covers: Space, or a click in the spread)
    private var largeCovers: [String: String] = [:]  // id: the cover large, as the tool gave it
    @Published var changing: Set<String> = []  // books the tool is changing now
    @Published var problem: String?  // what the tool said when a change did not happen
    @Published var signIn: SignIn?  // connecting to Hardcover, while the sheet is open
    var signInProcess: Process?
    private var coversFetched = false  // once per window: the covers this Mac does not have yet

    let register: () -> String?  // the launch agent, before setup: nil when it is in place
    @Published var settingUp = false  // the galley shows setup (Setup.swift): the first time, or asked for from a check
    @Published var setupRun: SetupRun?
    private var foldSince: String?  // the newest sync in History when Sync now was clicked
    private var elsewhereSince: String?  // the newest sync in History when a sync elsewhere began
    private var run = 0  // which Sync now the steps on screen belong to
    private var watcher: DispatchSourceFileSystemObject?
    private var pending: DispatchWorkItem?

    init(register: @escaping () -> String?) {
        self.register = register
    }

    /// Everything again; the check (which asks the server or Hardcover) unless only the files changed.
    func refresh(check: Bool = true) {
        if check {
            checks = nil
            told = nil
        }
        DispatchQueue.global(qos: .userInitiated).async {
            let status = answer(StatusAnswer.self, ["status", "--json"])
            let history = answer(HistoryAnswer.self, ["history", "--json"])
            let newer = newerVersion()
            DispatchQueue.main.async {
                let was = self.elsewhere
                switch status {
                case .success(let found):
                    self.status = found
                    self.broken = nil
                    self.elsewhere = found.syncing ?? ""
                    self.loadBooks()
                case .failure(let why):
                    self.broken = why.said
                }
                if case .success(let found) = history {
                    self.syncs = found.syncs
                    self.foldIntoHistory()
                }
                if !self.syncing && was.isEmpty && !self.elsewhere.isEmpty {  // a sync this window did not start: said, as the top line shows it
                    announce(self.elsewhere == "mount" ? "Syncing: started by plugging in the Kobo" : "Syncing: started elsewhere")
                } else if !was.isEmpty && self.elsewhere.isEmpty, let last = self.syncs.first, last.id != self.elsewhereSince {
                    // It ended, and History has it: the top line says what it did, as the subtitle promised.
                    let message = last.message.isEmpty ? "Nothing new." : last.message
                    self.told = Told(ok: last.ok, message: message, date: last.date ?? Date())
                    announce("\(last.ok ? "Synced" : "The sync failed"). \(message)")
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

    /// A book's cover large (`book ID --large-cover`): the tool fetches it once and keeps it; asked once here.
    func largeCover(_ id: String, _ then: @escaping (String) -> Void) {
        if let kept = largeCovers[id] { return then(kept) }
        DispatchQueue.global(qos: .userInitiated).async {
            let found = answer(BookAnswer.self, ["book", id, "--large-cover", "--json"])
            guard case .success(let one) = found, let large = one.large, !large.isEmpty else { return }
            let ready = Cover.prepare(large)  // read and decoded here, not while drawing
            DispatchQueue.main.async {
                if let ready { Cover.keep(large, ready) }
                self.largeCovers[id] = large
                then(large)
            }
        }
    }

    /// The list of books (in server mode the server's, for this Mac's reader); then, once, again with the covers fetched.
    func loadBooks(covers: Bool = false) {
        guard status?.mode == "local" || status?.mode == "server" else {
            books = nil
            return
        }
        DispatchQueue.global(qos: .userInitiated).async {
            let found = answer(BooksAnswer.self, covers ? ["books", "--covers", "--json"] : ["books", "--json"])
            DispatchQueue.main.async {
                switch found {
                case .success(let list):
                    self.books = list
                    self.booksBroken = nil
                    DispatchQueue.global(qos: .utility).async { indexBooks(list.books) }
                    if !covers && !self.coversFetched && list.books.contains(where: { $0.cover.isEmpty }) {
                        self.coversFetched = true
                        self.loadBooks(covers: true)
                    }
                case .failure(let why):
                    if self.books == nil { self.booksBroken = why.said }
                }
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
        told = nil
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
                for book in step.done?.finished ?? [] {  // marked Read on Hardcover: a notification with its cover, as after a plug-in
                    post("Finished: \(book.title)", "Marked as read on your Hardcover shelf.", picture: book.cover)
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

/// What a sync that ended while the window was open said, for the top line.
struct Told {
    let ok: Bool
    let message: String
    let date: Date
}

/// Said by VoiceOver: a sync's start and outcome, which change the window without moving its focus.
func announce(_ text: String) {
    NSAccessibility.post(
        element: NSApp.mainWindow ?? NSApp as Any, notification: .announcementRequested,
        userInfo: [.announcement: text, .priority: NSAccessibilityPriorityLevel.high.rawValue])
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
    case overview = "Overview", books = "Books", covers = "Covers", history = "History"

    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .overview: return "point.3.connected.trianglepath.dotted"  // the chain, not a hyperlink
        case .books: return "books.vertical"
        case .covers: return "rectangle.stack"
        case .history: return "clock"
        }
    }
}

struct MainView: View {
    @ObservedObject var model: WindowModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        NavigationSplitView {
            List(selection: $model.pane) {
                ForEach(Pane.allCases) { pane in
                    Label(pane.rawValue, systemImage: pane.symbol)
                        .badge(pane == .books ? model.status?.books?.needsMatch ?? model.books?.needsYou?.match ?? 0 : 0)  // books that wait for a match; in server mode from the server's books
                        .tag(pane)
                }
            }
            .navigationSplitViewColumnWidth(min: 150, ideal: 170, max: 220)
            .disabled(settingUp)  // the galley is setup: a click on a pane would do nothing
            .withoutSidebarToggle()  // the window's toolbar has AppKit's (Lastread.swift)
        } detail: {
            VStack(spacing: 0) {
                TopLine(model: model).padding(.horizontal, 20).padding(.vertical, 12)
                Divider()
                if let broken = model.broken {
                    Galley { ProofSheet { Row(state: "fail", what: "The tool", found: broken).onSheet() } }
                } else if settingUp {
                    SetupGalley(model: model)
                } else {
                    switch model.pane ?? .overview {
                    case .overview: OverviewSections(model: model)
                    case .history: HistorySection(model: model)
                    case .books: BooksPane(model: model)
                    case .covers: CoversPane(model: model)
                    }
                }
            }
        }
        .overlay { if let book = model.enlarged { Lightbox(model: model, book: book) } }  // over the whole window
        .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: model.enlarged?.id)
        .frame(minWidth: 920, minHeight: 520)  // the sidebar (170), the list (440) and a book's Details (300) side by side
        .sheet(isPresented: Binding(get: { model.signIn != nil }, set: { if !$0 { model.cancelSignIn() } })) { ConnectSheet(model: model) }
        .alert("Nothing was changed", isPresented: Binding(get: { model.problem != nil }, set: { if !$0 { model.problem = nil } })) {  // as Settings says it
            Button("OK") { model.problem = nil }
        } message: {
            Text(model.problem ?? "")
        }
    }
}

extension MainView {
    /// Not set up yet, or setting up again from a check: the galley is setup (Setup.swift).
    private var settingUp: Bool { model.settingUp || model.status?.mode == "" }
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
                    .foregroundStyle(busy ? Pencil.ink : said(readiness.state))  // the first line in its mark's colour
                if let told = model.told, !busy {  // a sync ended while the window was open: what it did, with its mark; a failure in ink
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Mark(state: told.ok ? "ok" : "fail", size: 15).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 3 }
                        Text(toldLine(told)).fontWeight(told.ok ? .regular : .semibold).foregroundStyle(told.ok ? Pencil.graphite : Pencil.ink)
                            .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityElement(children: .combine)
                } else {
                    Text(subtitle).foregroundStyle(Pencil.graphite).textSelection(.enabled)
                }
            }
            Spacer(minLength: 12)
            Button(model.pageTitle) { openThePage() }
                .disabled(model.status?.mode.isEmpty ?? true)
            Button("Sync now") { model.syncNow() }
                .buttonStyle(.borderedProminent)
                .tint(Pencil.fill)  // red fills only what a sync sends
                .help("Sync now (⌘R, also in the Sync menu)")
                .disabled(busy || (model.status?.mode.isEmpty ?? true))
        }
    }

    private var busy: Bool { model.syncing || !model.elsewhere.isEmpty }

    private func said(_ state: String) -> Color {
        switch state {
        case "ok": return Pencil.green
        case "warn": return Pencil.blue
        default: return Pencil.ink
        }
    }

    private var readiness: (sentence: String, state: String) {
        guard let status = model.status else { return ("Lastread", "note") }
        if status.mode.isEmpty { return ("Not set up yet", "warn") }
        guard model.checks != nil else { return ("Checking…", "note") }
        let links = model.links
        if let broken = links.first(where: { $0.state == "fail" }) { return ("Needs attention: \(broken.id)", "fail") }
        if links.contains(where: { $0.state == "warn" }) { return ("Ready, with a warning", "warn") }
        return ("Ready for the Kobo", "ok")
    }

    /// "11 books updated · today at 10:22 · Kobo plugged in": what the sync said, in the subtitle's place, with the subtitle's facts after it.
    private func toldLine(_ told: Told) -> String {
        let message = told.message.hasSuffix(".") ? String(told.message.dropLast()) : told.message  // a fragment, as the facts are
        var parts = [message, spokenInSentence(told.date)]
        if model.status?.kobo != nil { parts.append("Kobo plugged in") }
        return parts.joined(separator: " · ")
    }

    private var subtitle: String {
        guard let status = model.status else { return "" }
        if !model.elsewhere.isEmpty && !model.syncing {
            return model.elsewhere == "mount" ? "Started by plugging in the Kobo. It shows here when it is done." : "Started elsewhere. It shows here when it is done."
        }
        var parts: [String] = []
        switch status.mode {
        case "server": parts.append("With the server")  // named on the chain and on the button beside this line
        case "local": parts.append("On this Mac")
        default: parts.append("Choose where your reading goes")
        }
        if let last = status.lastSync, let date = last.date { parts.append("last sync \(spokenInSentence(date))") }
        if status.kobo != nil { parts.append("Kobo plugged in") }
        return parts.joined(separator: " · ")
    }
}

/// The overview on the galley stock: Getting started until the reader is
/// live, the chain on a proof sheet, a sync as it runs, and the checks of the
/// link that is open: by itself the first that needs the reader, else the one
/// clicked.
struct OverviewSections: View {
    @ObservedObject var model: WindowModel
    @State private var chosen: String?  // nil: the first link with a problem; "": none

    var body: some View {
        Galley {
            if let version = model.newer {
                ProofSheet {
                    Row(state: "note", what: "Version \(version) is out", found: "This is \(bundleVersion()).") {
                        HStack {
                            Button("What's New") { if let link = URL(string: releases + version) { NSWorkspace.shared.open(link) } }
                            Button("Install and Restart") { installUpdate(version) }
                        }
                    }
                    .onSheet()
                }
                .padding(.bottom, 8)
            }
            if let start = model.books?.start {  // until live: what to do, step by step; the chain under it stays the status board
                StartSteps(model: model, start: start).padding(.bottom, 14)
            }
            ProofSheet {
                ChainView(model: model, open: $chosen).padding(12)
            }
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(model.checks == nil ? "Checking everything a sync depends on…" : model.summary).font(.callout).foregroundStyle(Pencil.graphite)
                    if model.checks != nil && open == nil {  // nothing opened by itself: say that a step can be
                        Text("Click a step for its checks.").font(.callout).foregroundStyle(Pencil.graphite)
                    }
                }
                Spacer()
                Button("Check again") { model.refresh() }.disabled(model.checks == nil)
            }
            .padding(.horizontal, 4)
            if model.syncing || model.outcome != nil {
                SyncSection(model: model).padding(.top, 14)
            } else if model.elsewhere.isEmpty, let last = model.syncs.first {  // nothing runs: the last sync, as History has it; History keeps the rest
                SheetHead("Last sync").padding(.top, 14)
                ProofSheet { SyncRow(sync: last) }
            }
            if let link = model.links.first(where: { $0.id == open }), model.checks != nil {
                SheetHead(link.id).padding(.top, 14)
                ProofSheet {
                    ForEach(Array(link.checks.enumerated()), id: \.element.id) { n, check in
                        if n > 0 { SoftRule() }
                        Row(state: check.state, what: check.what, found: check.found, todo: check.todo) { fix(check) }.onSheet()
                    }
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
                Button("Set up") { model.settingUp = true }
            case "Trigger":
                Button("Open Login Items") { SMAppService.openSystemSettingsLoginItems() }
            case "Hardcover" where model.status?.mode == "local":  // not connected, or no longer usable
                Button("Connect…") { model.connect() }
            case "Database" where check.found.contains("does not let"):
                Button("Open Privacy") { if let url = URL(string: privacySettings) { NSWorkspace.shared.open(url) } }
            case _ where check.todo.contains("on the page"):  // connecting to Hardcover, a match, the collection's name
                Button(model.pageTitle) { openThePage() }
            default:
                EmptyView()
            }
        }
    }
}

struct SyncSection: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SheetHead("Sync now")
            if !model.steps.isEmpty || model.outcome == nil {
                ProofSheet {
                    ForEach(Array(model.steps.enumerated()), id: \.offset) { n, step in
                        if n > 0 { SoftRule() }
                        Row(state: step.state ?? "note", what: step.step ?? "", found: step.text ?? "").onSheet()
                    }
                    if model.steps.isEmpty {
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text("Looking for the Kobo…").foregroundStyle(Pencil.graphite)
                        }
                        .onSheet()
                    }
                }
            }
            if let done = model.outcome {  // as the page's messages: what worked on Green Wash, a failure ruled in ink
                Row(state: done.ok ? "ok" : "fail", what: done.title, found: done.message, strong: true)
                    .onSheet()
                    .background(done.ok ? Pencil.greenWash : Pencil.sheet, in: RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(done.ok ? Pencil.greenWash : Pencil.flag, lineWidth: 1))
            }
        }
    }
}

/// The galley stock under the overview and History: its sheets at most 720 points wide, in the middle, scrolled.
struct Galley<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10, content: content)
                .frame(maxWidth: 720)
                .padding(.horizontal, 24)
                .padding(.vertical, 22)
                .frame(maxWidth: .infinity)
        }
        .background(Pencil.ground)
    }
}

/// A proof sheet on the galley stock (DESIGN.md): the sheet's colour inside a hairline rule, square-cut.
struct ProofSheet<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Pencil.sheet, in: RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(Pencil.rule, lineWidth: 1))
    }
}

/// The head over a sheet.
struct SheetHead: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text).font(.headline).foregroundStyle(Pencil.ink).padding(.leading, 4).accessibilityAddTraits(.isHeader)
    }
}

/// The line between rows on a sheet.
struct SoftRule: View {
    var body: some View { Pencil.ruleSoft.frame(height: 1).padding(.leading, 14) }
}

extension View {
    /// A row on a proof sheet, set in from its edge.
    func onSheet() -> some View { padding(.horizontal, 14).padding(.vertical, 10).frame(maxWidth: .infinity, alignment: .leading) }

    /// A sidebar without SwiftUI's own toggle button in the toolbar (macOS 14 on; 13 keeps it).
    @ViewBuilder func withoutSidebarToggle() -> some View {
        if #available(macOS 14, *) { toolbar(removing: .sidebarToggle) } else { self }
    }
}

/// The server's page, at Settings: in server mode the Hardcover connection is made there.
func openServerSettings(_ server: String) {
    if let url = URL(string: server)?.appendingPathComponent("settings") { NSWorkspace.shared.open(url) }
}

struct HistorySection: View {
    @ObservedObject var model: WindowModel

    var body: some View {
        Galley {
            SheetHead("History")
            ProofSheet {
                if model.syncs.isEmpty {
                    Text("No syncs yet. Plug in the Kobo.").foregroundStyle(Pencil.graphite).onSheet()
                }
                ForEach(Array(model.syncs.prefix(25).enumerated()), id: \.element.id) { n, sync in
                    if n > 0 { SoftRule() }
                    SyncRow(sync: sync)
                }
            }
            HStack {
                Spacer()
                Button("Show the log") { showLog() }
            }
        }
    }
}

/// A sync as History has it: its mark, what it said, when and what started it.
struct SyncRow: View {
    let sync: Sync
    private let started = ["mount": "Kobo plugged in", "app": "Sync now", "hand": "By hand"]

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Mark(state: sync.ok ? "ok" : "fail").alignmentGuide(.firstTextBaseline) { $0[.bottom] - 4 }
            VStack(alignment: .leading, spacing: 2) {
                Text(sync.message.isEmpty ? "Nothing new." : sync.message).foregroundStyle(Pencil.ink)
                Text([sync.date.map(spoken), started[sync.trigger]].compactMap { $0 }.joined(separator: " · "))
                    .font(.callout).foregroundStyle(Pencil.graphite)
            }
        }
        .onSheet()
        .accessibilityElement(children: .combine)
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
                Text(found).foregroundStyle(Pencil.graphite).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
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

/// The same, mid-sentence: "today at 10:22", but a date keeps its capitals ("28 Oct 2026 at 23:21").
func spokenInSentence(_ date: Date) -> String {
    let said = spoken(date)
    let plain = DateFormatter()
    plain.dateStyle = .medium
    plain.timeStyle = .short
    return said == plain.string(from: date) ? said : said.prefix(1).lowercased() + said.dropFirst()
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
