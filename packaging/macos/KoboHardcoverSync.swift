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
//   message, a newer version if there is one, Sync now and Open the page.
//
// It is the AppleScript app that `setup` builds for a Homebrew
// installation (computer/macos.py), ported, plus setup.

import AppKit
import ServiceManagement
import UserNotifications

let name = "Kobo Hardcover Sync"
let agentPlist = "org.gargleblaster.kobo-hardcover-sync.app.agent.plist"
let releases = "https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v"

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
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert]) { _, _ in }
        if let problem = registerAgent() {
            say("\(name) is not set up yet", problem)
            return
        }
        let (ok, output) = tool(args)
        let done = NSAlert()
        done.messageText = ok ? "\(name) is set up" : "Setup did not finish"
        done.accessoryView = textView(output)
        let local = ok && args[1] == "--local"
        done.addButton(withTitle: local ? "Open the page" : "OK")
        if local { done.addButton(withTitle: "Later") }
        if done.runModal() == .alertFirstButtonReturn && local {
            _ = tool(["open"])
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
        let newer = newerVersion()
        if let version = newer { text += "\n\nVersion \(version) is out." }
        let a = NSAlert()
        a.messageText = name
        a.informativeText = text
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Open the page")
        a.addButton(withTitle: "Sync now")
        if newer != nil { a.addButton(withTitle: "Get the new version") }
        let fourth = NSApplication.ModalResponse(rawValue: NSApplication.ModalResponse.alertThirdButtonReturn.rawValue + 1)
        switch a.runModal() {
        case .alertSecondButtonReturn:
            _ = tool(["open"])
        case .alertThirdButtonReturn:
            let (ok, output) = tool(["sync", "--trigger", "app"])
            begin()
            tell(output, ok: ok) { self.end() }
        case fourth:
            if let version = newer, let link = URL(string: releases + version) {
                NSWorkspace.shared.open(link)
            }
        default:
            break
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
        var said: [(String, String)] = []
        for line in output.split(separator: "\n") where line.hasPrefix("NOTIFY|") {
            let parts = line.split(separator: "|", maxSplits: 2, omittingEmptySubsequences: false)
            if parts.count == 3 { said.append((String(parts[1]), String(parts[2]))) }
        }
        if said.isEmpty && !ok {
            said = [(name, "The sync stopped before it could say why. Its log is agent.log, in Library/Application Support/kobo-hardcover-sync.")]
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
