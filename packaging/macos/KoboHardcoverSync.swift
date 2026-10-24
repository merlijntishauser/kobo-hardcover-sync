// Kobo Hardcover Sync: the Mac app around the tool (docs/macos-app.md).
//
// The tool is the Python package in Resources/python, unchanged; this
// wrapper starts it and shows what it says. It is started three ways:
//
// - by its launch agent when a volume is mounted (KHS_TRIGGER=mount): a
//   sync, its notification, and quit;
// - opened by hand before it is set up: where the reading goes, then
//   `setup`;
// - opened by hand afterwards, or by a click on a notification: the last
//   message, a newer version if there is one, whether notifications are
//   off, Sync now and Open the page.
//
// It is the AppleScript app that `setup` builds for a Homebrew
// installation (computer/macos.py), ported, plus setup.

import AppKit
import ServiceManagement
import UserNotifications

let name = "Kobo Hardcover Sync"
let agentPlist = "org.gargleblaster.kobo-hardcover-sync.app.agent.plist"
let releases = "https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v"
let notificationSettings = "x-apple.systempreferences:com.apple.Notifications-Settings.extension?id=org.gargleblaster.kobo-hardcover-sync.app"
let stoppedWithoutWord = "The sync stopped before it could say why. Its log is agent.log, in Library/Application Support/kobo-hardcover-sync."

/// The tool's folder: the same as a Homebrew installation's (computer/config.py).
func stateDir() -> URL {
    if let home = ProcessInfo.processInfo.environment["KHS_HOME"], !home.isEmpty {
        return URL(fileURLWithPath: home)
    }
    return FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support")
        .appendingPathComponent("kobo-hardcover-sync")
}

func stateFile(_ file: String) -> String? {
    try? String(contentsOf: stateDir().appendingPathComponent(file), encoding: .utf8)
}

/// Runs the tool and returns whether it ended well, and everything it printed.
/// Notifications come back as NOTIFY|title|message lines, so that a click on
/// one lands on this app.
func tool(_ args: [String]) -> (ok: Bool, output: String) {
    let p = Process()
    p.executableURL = Bundle.main.resourceURL!.appendingPathComponent("python/bin/python3")
    // -I: nothing from the environment or the person's own packages.
    // -B: nothing written into the bundle, which would break its signature.
    p.arguments = ["-I", "-B", "-m", "kobo_hardcover_sync"] + args
    var env = ProcessInfo.processInfo.environment
    env["KHS_APP"] = Bundle.main.bundlePath
    env["KHS_NOTIFY"] = "stdout"
    env["PYTHONDONTWRITEBYTECODE"] = "1"  // for what the tool starts in turn (the page)
    p.environment = env
    let out = Pipe()
    p.standardOutput = out
    p.standardError = out  // a refusal (`setup` with a wrong address) is said there
    do {
        try p.run()
    } catch {
        return (false, "\(name) could not start its tool: \(error.localizedDescription)")
    }
    let data = out.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus == 0, String(decoding: data, as: UTF8.self))
}

/// "0.12.0" when the tool's last look (computer/update.py) found a release
/// newer than this app, and looking is not switched off.
func newerVersion() -> String? {
    if let cfg = stateFile("config.toml"), cfg.split(separator: "\n").contains("check_for_updates = false") {
        return nil
    }
    guard let data = stateFile("update.json")?.data(using: .utf8),
          let kept = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let latest = kept["latest"] as? String,
          let theirs = numbers(latest),
          let mine = numbers(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")
    else { return nil }
    return theirs.lexicographicallyPrecedes(mine) || theirs == mine ? nil : latest
}

/// The NOTIFY|title|message lines the tool printed.
func notices(_ output: String) -> [(title: String, body: String)] {
    var said: [(title: String, body: String)] = []
    for line in output.split(separator: "\n") where line.hasPrefix("NOTIFY|") {
        let parts = line.split(separator: "|", maxSplits: 2, omittingEmptySubsequences: false)
        if parts.count == 3 { said.append((String(parts[1]), String(parts[2]))) }
    }
    return said
}

/// What macOS lets this app do with notifications. The answer comes on
/// another queue, so waiting for it here does not hold it up.
func notificationStatus() -> UNAuthorizationStatus {
    let answered = DispatchSemaphore(value: 0)
    var status = UNAuthorizationStatus.notDetermined
    UNUserNotificationCenter.current().getNotificationSettings { settings in
        status = settings.authorizationStatus
        answered.signal()
    }
    _ = answered.wait(timeout: .now() + 2)
    return status
}

func numbers(_ version: String) -> [Int]? {
    let parts = version.split(separator: ".", omittingEmptySubsequences: false).map { Int($0) }
    guard parts.count == 3, parts.allSatisfy({ $0 != nil && $0! >= 0 }) else { return nil }
    return parts.map { $0! }
}

/// The server address `setup` chose before, if any: to start from when setting up again.
func configuredServer() -> String? {
    for line in (stateFile("config.toml") ?? "").split(separator: "\n") where line.hasPrefix("server = \"") && line.hasSuffix("\"") {
        return String(line.dropFirst("server = \"".count).dropLast())
    }
    return nil
}

func textView(_ text: String) -> NSView {
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 540, height: 280))
    scroll.hasVerticalScroller = true
    scroll.borderType = .bezelBorder
    let view = NSTextView(frame: scroll.bounds)
    view.isEditable = false
    view.isSelectable = true  // a server's hash is copied from here
    view.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
    view.string = text.trimmingCharacters(in: .whitespacesAndNewlines)
    view.autoresizingMask = [.width]
    scroll.documentView = view
    return scroll
}

final class App: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    var busy = false  // a window is open
    var running = 0  // things still to finish before quitting

    func begin() { running += 1 }

    func end() {
        running -= 1
        if running <= 0 { NSApp.terminate(nil) }
    }

    func applicationWillFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self  // before a click that started the app is handed over
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if ProcessInfo.processInfo.environment["KHS_TRIGGER"] == "mount" {
            begin()
            DispatchQueue.global(qos: .userInitiated).async {
                let (ok, output) = tool(["sync", "--trigger", "mount"])
                DispatchQueue.main.async { self.tell(output, ok: ok) { self.end() } }
            }
            return
        }
        DispatchQueue.main.async { self.openedByHand() }
    }

    // Opened again while a sync started by the Kobo is still running.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openedByHand()
        return false
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler done: @escaping () -> Void
    ) {
        DispatchQueue.main.async { self.openedByHand() }
        done()
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter, willPresent notification: UNNotification,
        withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        done([.banner, .list])
    }

    func openedByHand() {
        guard !busy else { return }
        busy = true
        begin()
        NSApp.activate(ignoringOtherApps: true)
        let setUp = stateFile("config.toml") != nil && SMAppService.agent(plistName: agentPlist).status == .enabled
        if setUp { lastMessage() } else { setUpHere() }
        busy = false
        end()
    }

    // ---------- the first time ----------
    func setUpHere() {
        let ask = NSAlert()
        ask.messageText = "Set up \(name)"
        ask.informativeText = """
            Where should your reading go?

            On this computer: this Mac reads the Kobo when you plug it in, and keeps your shelf on Hardcover in step itself.

            With a server: this Mac sends what the Kobo knows to a Kobo Hardcover Sync server, such as a household's.
            """
        ask.addButton(withTitle: "On this computer")
        ask.addButton(withTitle: "With a server")
        ask.addButton(withTitle: "Cancel")
        let choice = ask.runModal()
        let args: [String]
        if choice == .alertFirstButtonReturn {
            args = ["setup", "--local"]
        } else if choice == .alertSecondButtonReturn, let address = askAddress() {
            args = ["setup", "--server", address]
        } else {
            return
        }
        if let problem = registerAgent() {
            say("\(name) is not set up yet", problem)
            return
        }
        let (ok, output) = tool(args)
        let done = NSAlert()
        done.messageText = ok ? "\(name) is set up" : "Setup did not finish"
        done.accessoryView = textView(output)
        // Asked only now: asked earlier, the question came in the corner of
        // the screen while setup's own windows were open, and was missed.
        let askNext = ok && notificationStatus() == .notDetermined
        if askNext {
            done.informativeText = """
                Next, macOS asks in the corner of the screen whether \(name) may show notifications. \
                Allow it: that is how it tells you what a sync did.
                """
        }
        let local = ok && args[1] == "--local"
        done.addButton(withTitle: local ? "Open the page" : "OK")
        if local { done.addButton(withTitle: "Later") }
        let openPage = done.runModal() == .alertFirstButtonReturn && local
        if askNext { askForNotifications() }
        if openPage { _ = tool(["open"]) }
    }

    /// macOS's question whether this app may show notifications. The app
    /// stays until it is answered, so the answer is not lost.
    func askForNotifications() {
        begin()
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert]) { _, _ in
            DispatchQueue.main.async { self.end() }
        }
    }

    func askAddress() -> String? {
        let a = NSAlert()
        a.messageText = "The server's address"
        a.informativeText = "The address of its page, starting with https://"
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24))
        field.placeholderString = "https://kobo.example.org"
        field.stringValue = configuredServer() ?? ""
        a.accessoryView = field
        a.addButton(withTitle: "Set up")
        a.addButton(withTitle: "Cancel")
        a.window.initialFirstResponder = field
        guard a.runModal() == .alertFirstButtonReturn else { return nil }
        let address = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        return address.isEmpty ? nil : address
    }

    /// The launch agent that starts a sync when a volume is mounted: the
    /// app's own background item. nil when it is in place.
    func registerAgent() -> String? {
        let agent = SMAppService.agent(plistName: agentPlist)
        if agent.status != .enabled {
            do {
                try agent.register()
            } catch {
                if agent.status != .requiresApproval {
                    return "It could not register what starts a sync when the Kobo is plugged in: \(error.localizedDescription)"
                }
            }
        }
        if agent.status == .requiresApproval {
            SMAppService.openSystemSettingsLoginItems()
            return "macOS asks you to allow \(name) under Login Items first. Allow it there, then open the app again."
        }
        return nil
    }

    // ---------- afterwards ----------
    func lastMessage() {
        var text = stateFile("last-message.txt")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if text.isEmpty { text = "Nothing synced yet." }
        let a = NSAlert()
        a.messageText = name
        var actions: [() -> Void] = []
        func button(_ title: String, _ action: @escaping () -> Void) {
            a.addButton(withTitle: title)
            actions.append(action)
        }
        button("OK") {}
        button("Open the page") { _ = tool(["open"]) }
        button("Sync now") { self.syncByHand() }
        if let version = newerVersion(), let link = URL(string: releases + version) {
            text += "\n\nVersion \(version) is out."
            button("Get the new version") { NSWorkspace.shared.open(link) }
        }
        let notifications = notificationStatus()
        if notifications == .denied {
            text += "\n\nNotifications are off, so a sync started by plugging in the Kobo does not say what it did."
            if let settings = URL(string: notificationSettings) {
                button("Turn on notifications") { NSWorkspace.shared.open(settings) }
            }
        }
        a.informativeText = text
        let chosen = a.runModal().rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
        if actions.indices.contains(chosen) { actions[chosen]() }
        if notifications == .notDetermined { askForNotifications() }  // never answered: asked once this window is gone
    }

    /// Sync now: a window that says it is busy while the tool runs, then
    /// what the sync did, in a window rather than a notification.
    func syncByHand() {
        let busy = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 320, height: 90), styleMask: [.titled], backing: .buffered, defer: false)
        busy.title = name
        let spinner = NSProgressIndicator(frame: NSRect(x: 24, y: 29, width: 32, height: 32))
        spinner.style = .spinning
        spinner.startAnimation(nil)
        let label = NSTextField(labelWithString: "Syncing…")
        label.frame = NSRect(x: 72, y: 35, width: 230, height: 20)
        busy.contentView?.addSubview(spinner)
        busy.contentView?.addSubview(label)
        busy.center()
        var result = (ok: false, output: "")
        DispatchQueue.global(qos: .userInitiated).async {
            let finished = tool(["sync", "--trigger", "app"])
            DispatchQueue.main.async {
                result = finished
                NSApp.stopModal()
                // stopModal takes effect at the next event; this is one.
                if let wake = NSEvent.otherEvent(
                    with: .applicationDefined, location: .zero, modifierFlags: [], timestamp: 0, windowNumber: 0, context: nil,
                    subtype: 0, data1: 0, data2: 0)
                {
                    NSApp.postEvent(wake, atStart: true)
                }
            }
        }
        NSApp.runModal(for: busy)
        busy.orderOut(nil)
        let said = notices(result.output)
        if said.isEmpty {
            say(name, result.ok ? "Done." : stoppedWithoutWord)
        } else {
            say(said[0].title, said.map { $0.body }.joined(separator: "\n\n"))
        }
    }

    func say(_ title: String, _ text: String) {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = text
        a.addButton(withTitle: "OK")
        _ = a.runModal()
    }

    // ---------- notifications ----------
    /// Shows each NOTIFY| line as a notification, then calls done.
    func tell(_ output: String, ok: Bool, done: @escaping () -> Void) {
        var said = notices(output)
        if said.isEmpty && !ok {
            said = [(name, stoppedWithoutWord)]
        }
        let group = DispatchGroup()
        for (title, body) in said {
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            group.enter()
            UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)) { _ in
                group.leave()
            }
        }
        group.notify(queue: .main, execute: done)
    }
}

let app = NSApplication.shared
let delegate = App()  // the application only keeps a weak reference
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
