// The app's Settings, ⌘-, (docs/plans/2026-10-24-mac-app-window-design.md):
// where the reading goes, how a sync behaves, the app itself and its
// removal; in local mode the Hardcover connection and going live. The
// books are in the window. Every change goes through the tool
// (`settings --set`, `setup`, `token`, `webhook`, `export`, `uninstall`),
// as it would in a terminal.
//
// The preview build changes what is in its own folder, and nothing that
// is this Mac's: the Keychain, the trigger, the server.

import AppKit
import ServiceManagement
import SwiftUI
import UserNotifications

final class SettingsModel: ObservableObject {
    @Published var current: SettingsAnswer?
    @Published var problem: String?  // the tool did not answer, or refused a change
    @Published var working = false
    @Published var notifications = UNAuthorizationStatus.notDetermined
    @Published var previews = UNShowPreviewsSetting.always
    @Published var update: Result<UpdateAnswer, NoAnswer>?
    @Published var checking = false

    weak var window: NSWindow?  // where its sheets go
    let changed: () -> Void  // the main window looks again
    let remove: () -> Void

    init(changed: @escaping () -> Void, remove: @escaping () -> Void) {
        self.changed = changed
        self.remove = remove
    }

    func load() {
        ask(["settings", "--json"])
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                self.notifications = settings.authorizationStatus
                self.previews = settings.showPreviewsSetting
            }
        }
    }

    /// Check now: GitHub is asked, also with the daily look switched off.
    func checkNow() {
        checking = true
        lookForUpdate { found in
            self.checking = false
            self.update = found
            self.changed()
        }
    }

    /// One of the settings that are true or false.
    func set(_ name: String, _ value: Bool) {
        ask(["settings", "--json", "--set", "\(name)=\(value)"])
    }

    private func ask(_ args: [String]) {
        working = true
        DispatchQueue.global(qos: .userInitiated).async {
            let found = answer(SettingsAnswer.self, args)
            DispatchQueue.main.async {
                self.working = false
                switch found {
                case .success(let settings):
                    self.current = settings
                    self.problem = nil
                case .failure(let why):
                    self.problem = why.said
                }
                self.changed()
            }
        }
    }

    /// A change the tool says something about: what it said, in a sheet.
    /// `buttons` after a change that went well; then the button chosen.
    func change(
        _ args: [String], input: String? = nil, done: String, buttons: [String] = ["OK"], then: @escaping (Int) -> Void = { _ in }
    ) {
        working = true
        DispatchQueue.global(qos: .userInitiated).async {
            let (ok, output) = tool(args, input: input)
            DispatchQueue.main.async {
                self.working = false
                self.load()
                if ok {
                    self.sheet(done, output, buttons, then)
                } else {
                    self.sheet("Nothing was changed", output.replacingOccurrences(of: "kobo-hardcover-sync: ", with: ""), ["OK"]) { _ in }
                }
            }
        }
    }

    /// Asks first; `yes` when the first button is chosen.
    func confirm(_ title: String, _ text: String, _ button: String, destructive: Bool = false, yes: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = text
        a.addButton(withTitle: button).hasDestructiveAction = destructive
        a.addButton(withTitle: "Cancel")
        present(a) { if $0 == 0 { yes() } }
    }

    /// The preview stops here, before anything of this Mac's is touched.
    func allowed(_ wouldNow: String) -> Bool {
        guard isPreview else { return true }
        sheet("Preview", "The preview changes nothing on this Mac. The app would now \(wouldNow).", ["OK"]) { _ in }
        return false
    }

    func sheet(_ title: String, _ text: String, _ buttons: [String], _ then: @escaping (Int) -> Void) {
        let a = NSAlert()
        a.messageText = title
        if text.count > 160 || text.contains("\n") {
            a.accessoryView = textView(text)
        } else {
            a.informativeText = text
        }
        buttons.forEach { a.addButton(withTitle: $0) }
        present(a, then)
    }

    private func present(_ alert: NSAlert, _ then: @escaping (Int) -> Void) {
        let index = { (r: NSApplication.ModalResponse) in r.rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue }
        if let window {
            alert.beginSheetModal(for: window) { then(index($0)) }
        } else {
            then(index(alert.runModal()))
        }
    }
}

// ---------- the tabs ----------
struct ModeTab: View {
    @ObservedObject var model: SettingsModel
    @State private var choice = ""
    @State private var address = ""

    var body: some View {
        Form {
            Section {
                Picker("Your reading goes", selection: $choice) {
                    Text("On this computer").tag("local")
                    Text("With a server").tag("server")
                }
                .pickerStyle(.radioGroup)
                TextField("Server's address", text: $address, prompt: Text("https://kobo.example.org"))
                    .disabled(choice != "server")
            } footer: {
                HStack(alignment: .top) {
                    Text(explained).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("Switch") { switchMode() }.disabled(!isChange || model.working)
                }
            }
            if let settings = model.current, settings.mode == "server" {
                TokenSection(model: model, settings: settings)
            }
            ProblemSection(model: model)
        }
        .formStyle(.grouped)
        .onAppear(perform: fill)
        .onChange(of: model.current?.mode) { _ in fill() }
        .onChange(of: model.current?.server) { _ in fill() }
    }

    private var explained: String {
        choice == "local"
            ? "This Mac reads the Kobo and keeps your shelf on Hardcover in step itself. You connect to Hardcover under Sync."
            : "This Mac sends what the Kobo knows to the server, which keeps your shelf in step. The server is asked first; if it does not answer, nothing changes."
    }

    private var isChange: Bool {
        guard let settings = model.current else { return false }
        let wanted = address.trimmingCharacters(in: .whitespacesAndNewlines)
        if choice == "server" { return !wanted.isEmpty && (settings.mode != "server" || wanted != settings.server) }
        return settings.mode != choice
    }

    private func fill() {
        guard let settings = model.current else { return }
        choice = settings.mode.isEmpty ? "local" : settings.mode
        address = settings.server
    }

    private func switchMode() {
        let wanted = address.trimmingCharacters(in: .whitespacesAndNewlines)
        let local = choice == "local"
        guard model.allowed(local ? "run setup --local" : "ask \(wanted) whether it answers, then run setup --server") else { return }
        let args = local ? ["setup", "--local"] : ["setup", "--server", wanted, "--check"]
        model.change(args, done: local ? "Now on this computer" : "Now with the server", buttons: local ? ["Open the page", "Later"] : ["OK"]) {
            if local && $0 == 0 { _ = tool(["open"]) }
        }
    }
}

struct TokenSection: View {
    @ObservedObject var model: SettingsModel
    let settings: SettingsAnswer

    var body: some View {
        Section {
            LabeledContent("Its hash") {
                Text(settings.uploadTokenHash.isEmpty ? "No upload token yet" : settings.uploadTokenHash)
                    .font(.system(.body, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
            }
            HStack {
                Button("Copy the hash") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(settings.uploadTokenHash, forType: .string)
                }
                .disabled(settings.uploadTokenHash.isEmpty)
                Button("Open Devices on the page") {
                    if let page = URL(string: settings.server + "/settings") { NSWorkspace.shared.open(page) }
                }
                Spacer()
                Button("New upload token…") { renew() }.disabled(model.working)
            }
        } header: {
            Text("Upload token")
        } footer: {
            Text("The server knows this Mac by this hash, under Settings, Devices. The token itself stays in this Mac's Keychain.")
                .foregroundStyle(.secondary)
        }
    }

    private func renew() {
        model.confirm(
            "Make a new upload token?",
            "The server then no longer knows this Mac: add the new hash on its page, under Settings, Devices. Until then it refuses this Mac's syncs.",
            "Make a new token"
        ) {
            guard model.allowed("make a new upload token") else { return }
            model.change(["setup", "--new-token", "--check"], done: "A new upload token")
        }
    }
}

struct SyncTab: View {
    @ObservedObject var model: SettingsModel

    var body: some View {
        Form {
            if let settings = model.current {
                Section {
                    Choice(model: model, name: "eject_after_sync", on: settings.settings.ejectAfterSync, label: "Eject the Kobo after a sync",
                           about: "Then it can be unplugged at once. Without this, eject it yourself before you unplug it.")
                    Choice(model: model, name: "verbose_log", on: settings.settings.verboseLog, label: "A detailed log",
                           about: "A line per book and per request in the log, from the next sync on. The log then names your books.")
                    Choice(model: model, name: "allow_untested_kobo", on: settings.settings.allowUntestedKobo,
                           label: "Allow an untested Kobo software version",
                           about: """
                               A version nobody has tried yet is refused: the collection on the Kobo is left alone, the rest of the sync goes on. \
                               Allowed, the collection is written anyway, after a copy of the Kobo's database is saved. \
                               A database it does not understand is still refused.
                               """)
                } footer: {
                    HStack {
                        Spacer()
                        Button("Show the log") { showLog() }
                    }
                }
                if settings.mode == "local" {
                    HardcoverSection(model: model, settings: settings)
                    WebhookSection(model: model, saved: settings.settings.webhookUrl)
                    ExportSection(model: model, everySync: settings.settings.exportTo)
                }
            }
            ProblemSection(model: model)
        }
        .formStyle(.grouped)
    }
}

struct HardcoverSection: View {
    @ObservedObject var model: SettingsModel
    let settings: SettingsAnswer

    var body: some View {
        Section {
            LabeledContent("Connection") {
                HStack {
                    Mark(state: settings.hardcoverConnected ? "ok" : "note")
                    Text(settings.hardcoverConnected ? (settings.hardcoverUser.isEmpty ? "Connected" : "Connected as @\(settings.hardcoverUser)") : "Not connected")
                    if settings.hardcoverConnected {
                        Button("Disconnect…") {
                            guard model.allowed("disconnect from Hardcover") else { return }
                            model.confirm(
                                "Disconnect from Hardcover?", "The connection is ended on Hardcover too, and syncing goes back to a dry run.", "Disconnect",
                                destructive: true
                            ) { model.change(["token", "--remove"], done: "Disconnected") }
                        }
                    } else {
                        Button("Connect…") { connectToHardcover() }
                    }
                }
            }
            Toggle(isOn: Binding(get: { settings.live }, set: { model.set("live", $0) })) {
                Text("Send to Hardcover")
                Text(settings.live ? "Live: each sync sends what the red marks say." : "A dry run: each sync says what it would send, and sends nothing.")
            }
            .disabled(!settings.hardcoverConnected && !settings.live)
        } header: {
            Text("Hardcover")
        } footer: {
            HStack(alignment: .top) {
                Text("The collection on the Kobo is named on the page, under Settings.")
                    .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                Spacer()
                Button("Open the page") { _ = tool(["open"]) }
            }
        }
    }
}

struct WebhookSection: View {
    @ObservedObject var model: SettingsModel
    let saved: String
    @State private var address = ""
    @State private var token = ""

    var body: some View {
        Section {
            TextField("Address", text: $address, prompt: Text("https://example.org/hook"))
            SecureField("Token", text: $token, prompt: Text(saved.isEmpty ? "If it asks for one" : "Empty: keep the one it has"))
            HStack {
                Button("Send a test") {
                    guard model.allowed("send a test to \(saved)") else { return }
                    model.change(["webhook", "--test"], done: "Test sent")
                }
                .disabled(saved.isEmpty || model.working)
                Button("Remove") {
                    guard model.allowed("forget the webhook") else { return }
                    model.change(["webhook", "--remove"], done: "No webhook any more")
                }
                .disabled(saved.isEmpty || model.working)
                Spacer()
                Button("Test and save") { save() }.disabled(!isChange || model.working)
            }
        } header: {
            Text("Webhook")
        } footer: {
            Text("After every sync that reads something new from the Kobo, your reading is sent to this address, as JSON. A test goes first; nothing is saved if it is not taken.")
                .foregroundStyle(.secondary)
        }
        .onAppear { address = saved }
        .onChange(of: saved) { address = $0 }
    }

    private var wanted: String { address.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var isChange: Bool { !wanted.isEmpty && (wanted != saved || !token.isEmpty) }

    private func save() {
        guard model.allowed("send a test to \(wanted), then keep it") else { return }
        // A new address is sent alone or with the token typed; the same address only with a new token.
        var args = ["webhook"]
        if wanted != saved { args.append(wanted) }
        if !token.isEmpty { args.append("--token") }
        model.change(args, input: token.isEmpty ? nil : token + "\n", done: "Webhook saved")
        token = ""
    }
}

struct ExportSection: View {
    @ObservedObject var model: SettingsModel
    let everySync: String

    var body: some View {
        Section {
            if !everySync.isEmpty {
                LabeledContent("After every sync") {
                    HStack {
                        Text(everySync).lineLimit(1).truncationMode(.middle).textSelection(.enabled)
                        Button("Stop") { model.change(["export", "--stop"], done: "No longer written after a sync") }
                            .disabled(model.working)
                    }
                }
            }
            HStack {
                Spacer()
                Button("Export my reading…") { exportReading() }.disabled(model.working)
            }
        } header: {
            Text("Export")
        } footer: {
            Text("Your reading as JSON, for a database or a dashboard of your own. Only you can read the file.")
                .foregroundStyle(.secondary)
        }
    }

    private func exportReading() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "my-reading.json"
        panel.allowedContentTypes = [.json]
        let again = NSButton(checkboxWithTitle: "Write it again after every sync", target: nil, action: nil)
        panel.accessoryView = again
        let chosen = { (response: NSApplication.ModalResponse) in
            guard response == .OK, let file = panel.url else { return }
            var args = ["export", "--output", file.path]
            if again.state == .on { args.append("--every-sync") }
            model.change(args, done: "Exported")
        }
        if let window = model.window {
            panel.beginSheetModal(for: window, completionHandler: chosen)
        } else {
            chosen(panel.runModal())
        }
    }
}

struct AppTab: View {
    @ObservedObject var model: SettingsModel

    var body: some View {
        Form {
            Section {
                LabeledContent("Version", value: bundleVersion())
                if let settings = model.current {
                    Choice(model: model, name: "check_for_updates", on: settings.settings.checkForUpdates, label: "Look for a newer version",
                           about: "At most once a day, after a sync, the app asks GitHub for the latest release. It only says so; it never updates itself.")
                }
                HStack {
                    Text(updateSaid).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    if case .success(let found) = model.update, found.newer, let link = URL(string: releases + found.latest) {
                        Button("Get it") { NSWorkspace.shared.open(link) }
                    }
                    Button("Check now") { model.checkNow() }.disabled(model.checking)
                }
            }
            Section {
                LabeledContent("Notifications") {
                    Text(notificationsSaid).foregroundStyle(.secondary)
                }
                HStack {
                    Spacer()
                    Button("Open Notification Settings") { if let url = URL(string: notificationSettings) { NSWorkspace.shared.open(url) } }
                }
            } footer: {
                Text("They say what a sync did when the Kobo started it, with the window closed. With Show previews at Never, macOS hides what they say.")
                    .foregroundStyle(.secondary)
            }
            Section {
                HStack(alignment: .top) {
                    Text("Stop syncing on this Mac, or also delete what the app keeps here.")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("Remove…", role: .destructive) { model.remove() }.disabled(model.working)
                }
            }
            ProblemSection(model: model)
        }
        .formStyle(.grouped)
    }

    private var updateSaid: String {
        if model.checking { return "Asking GitHub…" }
        switch model.update {
        case .none: return ""
        case .failure(let why): return why.said
        case .success(let found):
            if found.newer { return "Version \(found.latest) is out." }
            return found.problem.isEmpty ? "This is the newest version." : found.problem
        }
    }

    private var notificationsSaid: String {
        switch model.notifications {
        case .denied: return "Off"
        case .notDetermined: return "Not asked yet"
        default: return model.previews == .never ? "On, showing only the app's name" : "On"
        }
    }
}

/// A setting that is true or false, with what it does under it.
struct Choice: View {
    @ObservedObject var model: SettingsModel
    let name: String
    let on: Bool
    let label: String
    let about: String

    var body: some View {
        Toggle(isOn: Binding(get: { on }, set: { model.set(name, $0) })) {
            Text(label)
            Text(about).fixedSize(horizontal: false, vertical: true)
        }
        .disabled(model.working)
    }
}

struct ProblemSection: View {
    @ObservedObject var model: SettingsModel

    var body: some View {
        if let problem = model.problem {
            Section { Row(state: "fail", what: "The tool", found: problem) }
        }
    }
}

/// The Settings window: a tab per subject, as in macOS's own apps.
func settingsWindow(_ model: SettingsModel) -> NSWindow {
    let tabs = NSTabViewController()
    tabs.tabStyle = .toolbar
    let pages: [(String, String, AnyView)] = [
        ("Mode", "arrow.triangle.branch", AnyView(ModeTab(model: model))),
        ("Sync", "arrow.triangle.2.circlepath", AnyView(SyncTab(model: model))),
        ("App", "app.badge", AnyView(AppTab(model: model))),
    ]
    for (label, symbol, page) in pages {
        let controller = NSHostingController(rootView: page.frame(width: 540, height: 520))
        controller.sizingOptions = [.preferredContentSize]  // the window takes this size, so nothing is cut off at its sides
        controller.title = label  // the window's title, as in macOS's own Settings
        let item = NSTabViewItem(viewController: controller)
        item.label = label
        item.image = NSImage(systemSymbolName: symbol, accessibilityDescription: label)
        tabs.addTabViewItem(item)
    }
    let window = NSWindow(contentViewController: tabs)
    window.styleMask = [.titled, .closable]
    window.isReleasedWhenClosed = false
    model.window = window
    return window
}
