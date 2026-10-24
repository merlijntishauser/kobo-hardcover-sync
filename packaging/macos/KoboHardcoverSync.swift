// Kobo Hardcover Sync: the Mac app around the tool (docs/macos-app.md).
//
// The tool is the Python package in Resources/python, unchanged; this
// wrapper starts it and shows what it says. It is started three ways:
//
// - by its launch agent when a volume is mounted (KHS_TRIGGER=mount): a
//   sync, its notification, and quit;
// - opened by hand before it is set up: where the reading goes, then
//   `setup`, then its window;
// - opened by hand afterwards, or by a click on a notification: its
//   window (Window.swift), until that is closed.
//
// A preview build (build.sh with KHS_PREVIEW=1) has its own bundle id and
// a folder of its own, registers no launch agent and syncs nothing: the
// window can be looked at on a Mac without touching an installed app.

import AppKit
import ServiceManagement
import SwiftUI
import UserNotifications

let name = "Kobo Hardcover Sync"
let agentPlist = "org.gargleblaster.kobo-hardcover-sync.app.agent.plist"
let releases = "https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v"
let notificationSettings = "x-apple.systempreferences:com.apple.Notifications-Settings.extension?id=" + (Bundle.main.bundleIdentifier ?? "")
let privacySettings = "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders"
let stoppedWithoutWord = "The sync stopped before it could say why. Its log is agent.log, in Library/Application Support/kobo-hardcover-sync."
let isPreview = Bundle.main.object(forInfoDictionaryKey: "KHSPreview") as? Bool ?? false

/// The tool's folder: the same as a Homebrew installation's (computer/config.py);
/// the preview's own, beside it.
func stateDir() -> URL {
    if let home = ProcessInfo.processInfo.environment["KHS_HOME"], !home.isEmpty {
        return URL(fileURLWithPath: home)
    }
    return FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support")
        .appendingPathComponent(isPreview ? "kobo-hardcover-sync-preview" : "kobo-hardcover-sync")
}

func stateFile(_ file: String) -> String? {
    try? String(contentsOf: stateDir().appendingPathComponent(file), encoding: .utf8)
}

func toolProcess(_ args: [String]) -> (Process, Pipe) {
    let p = Process()
    p.executableURL = Bundle.main.resourceURL!.appendingPathComponent("python/bin/python3")
    // -I: nothing from the environment or the person's own packages.
    // -B: nothing written into the bundle, which would break its signature.
    p.arguments = ["-I", "-B", "-m", "kobo_hardcover_sync"] + args
    var env = ProcessInfo.processInfo.environment
    env["KHS_APP"] = Bundle.main.bundlePath
    env["KHS_NOTIFY"] = "stdout"
    env["KHS_HOME"] = stateDir().path
    env["PYTHONDONTWRITEBYTECODE"] = "1"  // for what the tool starts in turn (the page)
    p.environment = env
    let out = Pipe()
    p.standardOutput = out
    p.standardError = out  // a refusal (`setup` with a wrong address) is said there
    return (p, out)
}

/// Runs the tool and returns whether it ended well, and everything it printed.
/// Notifications come back as NOTIFY|title|message lines, so that a click on
/// one lands on this app.
func tool(_ args: [String]) -> (ok: Bool, output: String) {
    let (p, out) = toolProcess(args)
    do {
        try p.run()
    } catch {
        return (false, "\(name) could not start its tool: \(error.localizedDescription)")
    }
    let data = out.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus == 0, String(decoding: data, as: UTF8.self))
}

/// Runs the tool and hands over each line as it is printed; whether it ended well.
func toolLines(_ args: [String], _ each: (String) -> Void) -> Bool {
    let (p, out) = toolProcess(args)
    do {
        try p.run()
    } catch {
        each("NOTIFY|\(name)|\(name) could not start its tool: \(error.localizedDescription)")
        return false
    }
    var rest = Data()
    let reader = out.fileHandleForReading
    while case let chunk = reader.availableData, !chunk.isEmpty {
        rest.append(chunk)
        while let end = rest.firstIndex(of: UInt8(ascii: "\n")) {
            each(String(decoding: rest[rest.startIndex..<end], as: UTF8.self))
            rest = Data(rest[rest.index(after: end)...])
        }
    }
    if !rest.isEmpty { each(String(decoding: rest, as: UTF8.self)) }
    p.waitUntilExit()
    return p.terminationStatus == 0
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
          let mine = numbers(bundleVersion())
    else { return nil }
    return theirs.lexicographicallyPrecedes(mine) || theirs == mine ? nil : latest
}

/// A NOTIFY|title|message line the tool printed, as (title, body).
func notice(_ line: String) -> (title: String, body: String)? {
    guard line.hasPrefix("NOTIFY|") else { return nil }
    let parts = line.split(separator: "|", maxSplits: 2, omittingEmptySubsequences: false)
    return parts.count == 3 ? (String(parts[1]), String(parts[2])) : nil
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

/// Notification Center shows a notification now.
func post(_ title: String, _ body: String, then: @escaping () -> Void = {}) {
    let content = UNMutableNotificationContent()
    content.title = title
    content.body = body
    UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)) { _ in
        then()
    }
}

final class App: NSObject, NSApplicationDelegate, NSWindowDelegate, UNUserNotificationCenterDelegate {
    var busy = false  // setup's dialogs are open
    var running = 0  // things still to finish before quitting: a sync, the window
    var window: NSWindow?
    var model: WindowModel?

    func begin() { running += 1 }

    func end() {
        running -= 1
        if running <= 0 { NSApp.terminate(nil) }
    }

    func applicationWillFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self  // before a click that started the app is handed over
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if ProcessInfo.processInfo.environment["KHS_TRIGGER"] == "mount" && !isPreview {
            begin()
            DispatchQueue.global(qos: .userInitiated).async {
                // Each notification as soon as the tool says it, not after
                // what the tool does next (the update check).
                let posting = DispatchGroup()
                var said = false
                let ok = toolLines(["sync", "--trigger", "mount"]) { line in
                    guard let told = notice(line) else { return }
                    said = true
                    posting.enter()
                    post(told.title, told.body) { posting.leave() }
                }
                if !ok && !said {
                    posting.enter()
                    post(name, stoppedWithoutWord) { posting.leave() }
                }
                posting.notify(queue: .main) { self.end() }
            }
            return
        }
        DispatchQueue.main.async { self.openedByHand() }
    }

    // Opened again while it runs: a sync the Kobo started, or the window.
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
        if window != nil { return showWindow() }
        busy = true
        begin()
        NSApp.activate(ignoringOtherApps: true)
        if isPreview {
            if stateFile("config.toml") == nil {
                say("Nothing to preview", "The preview reads a copy of the tool's folder, at \(stateDir().path). Copy one there, then open it again.")
            } else {
                showWindow()
            }
        } else if stateFile("config.toml") != nil && SMAppService.agent(plistName: agentPlist).status == .enabled {
            showWindow()
        } else if setUpHere() {
            showWindow()
        }
        busy = false
        end()
    }

    // ---------- the window ----------
    func showWindow() {
        if let window {
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            return
        }
        let model = WindowModel { [weak self] in
            guard let self, !self.busy else { return }
            self.busy = true
            _ = self.setUpHere()
            self.busy = false
            self.model?.refresh()
        }
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 720),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = isPreview ? "\(name) (preview)" : name
        window.contentView = NSHostingView(rootView: MainView(model: model))
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("Main")
        self.window = window
        self.model = model
        begin()  // the window keeps the app until it is closed
        NSApp.setActivationPolicy(.regular)  // a Dock icon and a menu bar while it is open
        NSApp.mainMenu = mainMenu()
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        model.refresh()
        model.watch()
    }

    func windowWillClose(_ notification: Notification) {
        model?.stop()
        model = nil
        window = nil
        NSApp.setActivationPolicy(.accessory)
        end()
    }

    func mainMenu() -> NSMenu {
        let bar = NSMenu()
        func menu(_ title: String, _ items: [NSMenuItem]) -> NSMenu {
            let m = NSMenu(title: title)
            items.forEach(m.addItem)
            let holder = NSMenuItem()
            holder.submenu = m
            bar.addItem(holder)
            return m
        }
        func item(_ title: String, _ action: Selector, _ key: String) -> NSMenuItem {
            NSMenuItem(title: title, action: action, keyEquivalent: key)
        }
        _ = menu(name, [
            item("About \(name)", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            item("Hide \(name)", #selector(NSApplication.hide(_:)), "h"),
            .separator(),
            item("Quit \(name)", #selector(NSApplication.terminate(_:)), "q"),
        ])
        _ = menu("Edit", [
            item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])
        NSApp.windowsMenu = menu("Window", [
            item("Close", #selector(NSWindow.performClose(_:)), "w"),
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
        ])
        return bar
    }

    // ---------- the first time ----------
    /// Where the reading goes, the launch agent, `setup`. Whether it ended set up.
    func setUpHere() -> Bool {
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
            return false
        }
        if let problem = registerAgent() {
            say("\(name) is not set up yet", problem)
            return false
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
        return ok
    }

    /// macOS's question whether this app may show notifications. The app
    /// stays until it is answered, so the answer is not lost.
    func askForNotifications() {
        begin()
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert]) { _, _ in
            DispatchQueue.main.async {
                self.model?.refresh(check: false)
                self.end()
            }
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

    func say(_ title: String, _ text: String) {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = text
        a.addButton(withTitle: "OK")
        _ = a.runModal()
    }
}

@main
struct Main {
    static func main() {
        let app = NSApplication.shared
        let delegate = App()  // the application only keeps a weak reference
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
        _ = delegate
    }
}
