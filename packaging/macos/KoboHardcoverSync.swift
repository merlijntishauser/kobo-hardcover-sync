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

func toolProcess(_ args: [String], input: String? = nil) -> (Process, Pipe) {
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
    if let input {  // a webhook's token: never in the arguments, which anyone on this Mac can see
        let given = Pipe()
        p.standardInput = given
        given.fileHandleForWriting.write(Data(input.utf8))
        try? given.fileHandleForWriting.close()
    }
    return (p, out)
}

/// Runs the tool and returns whether it ended well, and everything it printed.
/// Notifications come back as NOTIFY|title|message lines, so that a click on
/// one lands on this app.
func tool(_ args: [String], input: String? = nil) -> (ok: Bool, output: String) {
    let (p, out) = toolProcess(args, input: input)
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

/// A NOTIFY|title|message[|picture] line the tool printed, as (title, body, picture file or "").
func notice(_ line: String) -> (title: String, body: String, picture: String)? {
    guard line.hasPrefix("NOTIFY|") else { return nil }
    let parts = line.split(separator: "|", maxSplits: 3, omittingEmptySubsequences: false).map(String.init)
    return parts.count >= 3 ? (parts[1], parts[2], parts.count == 4 ? parts[3] : "") : nil
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

/// `update --json`: is there a newer version? Asked on another queue, answered on the main one.
func lookForUpdate(_ answered: @escaping (Result<UpdateAnswer, NoAnswer>) -> Void) {
    DispatchQueue.global(qos: .userInitiated).async {
        let found = answer(UpdateAnswer.self, ["update", "--json"])
        DispatchQueue.main.async { answered(found) }
    }
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

/// Connect to Hardcover, from wherever it is asked for.
func connectToHardcover() {
    (NSApp.delegate as? App)?.connectInWindow()
}

/// A window as it is drawn, with its title bar and toolbar, as a PNG.
func picture(_ window: NSWindow, _ file: URL) {
    guard let view = window.contentView?.superview else { return }
    view.layoutSubtreeIfNeeded()
    guard let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
    view.cacheDisplay(in: view.bounds, to: rep)
    try? rep.representation(using: .png, properties: [:])?.write(to: file)
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

/// Notification Center shows a notification now; with a picture (a book's cover) where there is one.
func post(_ title: String, _ body: String, picture: String = "", then: @escaping () -> Void = {}) {
    let content = UNMutableNotificationContent()
    content.title = title
    content.body = body
    // Notification Center moves an attached file into its own store: it gets a copy, never the cover the window shows.
    if !picture.isEmpty, FileManager.default.fileExists(atPath: picture) {
        let copy = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".jpg")
        if (try? FileManager.default.copyItem(at: URL(fileURLWithPath: picture), to: copy)) != nil,
            let attached = try? UNNotificationAttachment(identifier: "cover", url: copy)
        {
            content.attachments = [attached]
        }
    }
    UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)) { _ in
        then()
    }
}

final class App: NSObject, NSApplicationDelegate, NSWindowDelegate, UNUserNotificationCenterDelegate {
    var busy = false  // setup's dialogs are open
    var running = 0  // things still to finish before quitting: a sync, the window
    var window: NSWindow?
    var model: WindowModel?
    var settings: NSWindow?
    var settingsModel: SettingsModel?
    var help: NSWindow?
    var guide = GuidePlace()
    let guideSearch = GuideSearch()

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
                    post(told.title, told.body, picture: told.picture) { posting.leave() }
                }
                if !ok && !said {
                    posting.enter()
                    post(name, stoppedWithoutWord) { posting.leave() }
                }
                if case .success(let list) = answer(BooksAnswer.self, ["books", "--json"]) {
                    keepShelf(list.books, tip: list.tip)  // the widget, as the sync left the books
                }
                posting.notify(queue: .main) { self.end() }
            }
            return
        }
        if isPreview, let folder = ProcessInfo.processInfo.environment["KHS_SNAPSHOT"], !folder.isEmpty {
            return snapshots(into: URL(fileURLWithPath: folder))
        }
        NSApp.registerUserInterfaceItemSearchHandler(guideSearch)  // the Help menu's search finds the guide too
        DispatchQueue.main.async { self.openedByHand() }
    }

    /// The preview's pictures of its windows (KHS_SNAPSHOT=folder): each
    /// pane of the window and each Settings tab as a PNG, then quit. For a look from a
    /// session that cannot see the screen.
    func snapshots(into folder: URL) {
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        showWindow()
        showSettings()
        settingsModel?.checkNow()  // so the General tab shows an answer
        let tabs = (settings?.contentViewController as? NSTabViewController)?.tabViewItems.count ?? 0
        var steps: [() -> Void] = []
        for pane in Pane.allCases {
            steps.append { self.model?.pane = pane }
            steps.append { self.window.map { picture($0, folder.appendingPathComponent("window-\(pane.rawValue.lowercased()).png")) } }
        }
        steps.append {  // Covers showing one selection: the books that sync
            self.model?.pane = .covers
            UserDefaults.standard.set("on", forKey: "CoversShow")
        }
        steps.append { self.window.map { picture($0, folder.appendingPathComponent("window-covers-synced.png")) } }
        steps.append { UserDefaults.standard.removeObject(forKey: "CoversShow") }
        steps.append {  // a book's Details
            self.model?.pane = .books
            self.model?.chosenBook = self.model?.shownBooks.first { !$0.details.hardcover.isEmpty }?.id ?? self.model?.shownBooks.first?.id
        }
        steps.append { self.window.map { picture($0, folder.appendingPathComponent("window-details.png")) } }
        var opened: String?
        steps.append {  // the same book, opened on Covers: the spread (Covers lets go of what Books chose)
            opened = self.model?.chosenBook
            self.model?.pane = .covers
        }
        steps.append { self.model?.chosenBook = opened }
        steps.append { self.window.map { picture($0, folder.appendingPathComponent("window-spread.png")) } }
        steps.append { self.model?.enlarged = self.model?.books?.books.first { $0.id == opened } }  // its cover over the window
        steps.append { self.window.map { picture($0, folder.appendingPathComponent("window-cover.png")) } }
        steps.append { self.model?.enlarged = nil }
        steps.append {  // the sign-in, as it shows a code to compare (the preview signs in nowhere)
            self.model?.chosenBook = nil
            self.model?.signIn = SignIn(link: "https://hardcover.app/link?code=ABCD-EFGH", code: "ABCD-EFGH")
        }
        steps.append { self.window?.attachedSheet.map { picture($0, folder.appendingPathComponent("window-connect.png")) } }
        steps.append { self.model?.signIn = nil }
        steps.append {  // a sync on the chain: the preview's plays its sample steps
            self.model?.pane = .overview
            self.model?.syncNow()
        }
        steps.append { self.window.map { picture($0, folder.appendingPathComponent("window-syncing.png")) } }
        for n in 0..<tabs {
            steps.append { (self.settings?.contentViewController as? NSTabViewController)?.selectedTabViewItemIndex = n }
            steps.append { self.settings.map { picture($0, folder.appendingPathComponent("settings-\(n + 1).png")) } }
        }
        steps.append { NSApp.terminate(nil) }
        for (n, step) in steps.enumerated() {  // the tool answers first, then a step a second
            DispatchQueue.main.asyncAfter(deadline: .now() + .seconds(6 + n), execute: step)
        }
    }

    // Opened again while it runs: a sync the Kobo started, or the window.
    /// A book chosen in Spotlight: the window, on Covers, at that book.
    func application(
        _ application: NSApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([NSUserActivityRestoring]) -> Void
    ) -> Bool {
        guard let id = spotlitBook(userActivity) else { return false }
        openedByHand()
        model?.pane = .covers
        model?.spotlit = id
        return true
    }

    /// A book clicked in the widget (ShelfWidget.swift): the window, on Covers, at that book.
    func application(_ application: NSApplication, open urls: [URL]) {
        guard let url = urls.first, url.scheme == "kobo-hardcover-sync", url.host == "book",
            let id = URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedPath.dropFirst().removingPercentEncoding
        else { return }
        openedByHand()
        model?.pane = .covers
        model?.spotlit = id
    }

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
    /// Settings' Connect…: the sign-in runs in the window, which has its sheet.
    func connectInWindow() {
        showWindow()
        model?.connect()
    }

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
        registerTitleFont()
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1040, height: 680),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = isPreview ? "\(name) (preview)" : name
        window.toolbar = NSToolbar()  // the sidebar reaches up under the title, as in a Mac app
        window.toolbarStyle = .unified
        window.contentView = NSHostingView(rootView: MainView(model: model))
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("Window")  // not "Main": that one kept the narrower window before the sidebar
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

    @objc func showSettings() {
        if let settings {
            NSApp.activate(ignoringOtherApps: true)
            settings.makeKeyAndOrderFront(nil)
            return
        }
        let model = SettingsModel(changed: { [weak self] in self?.model?.refresh(check: false) }, remove: { [weak self] in self?.removeHere() })
        let settings = settingsWindow(model)
        settings.delegate = self
        settings.center()
        self.settings = settings
        settingsModel = model
        begin()  // like the main window: the app stays while it is open
        settings.makeKeyAndOrderFront(nil)
        model.load()
    }

    func windowWillClose(_ notification: Notification) {
        let closing = notification.object as? NSWindow
        if closing === window {
            model?.stop()
            model = nil
            window = nil
        } else if closing === settings {
            settingsModel = nil
            settings = nil
        } else if closing === help {
            help = nil
            guide = GuidePlace()  // the next time it opens as new
        }
        if window == nil && settings == nil && help == nil { NSApp.setActivationPolicy(.accessory) }
        end()
    }

    /// Check for Updates… in the app menu: GitHub now, the answer in a dialog.
    @objc func checkForUpdates() {
        lookForUpdate { found in
            self.model?.refresh(check: false)
            let a = NSAlert()
            switch found {
            case .success(let update) where update.newer:
                a.messageText = "Version \(update.latest) is out"
                a.informativeText = "This is \(update.version). \(name) downloads the new one, checks that it is signed and notarised as this one is, puts it in this one's place and starts it again."
                a.addButton(withTitle: "Install and Restart")
                a.addButton(withTitle: "What's New")
                a.addButton(withTitle: "Later")
                switch a.runModal() {
                case .alertFirstButtonReturn: installUpdate(update.latest)
                case .alertSecondButtonReturn: if let link = URL(string: releases + update.latest) { NSWorkspace.shared.open(link) }
                default: break
                }
                return
            case .success(let update) where update.problem.isEmpty:
                a.messageText = "This is the newest version"
                a.informativeText = "\(name) \(update.version)."
            case .success(let update):
                a.messageText = "No answer about a newer version"
                a.informativeText = update.problem
            case .failure(let why):
                a.messageText = "No answer about a newer version"
                a.informativeText = why.said
            }
            a.addButton(withTitle: "OK")
            _ = a.runModal()
        }
    }

    // ---------- Remove… ----------
    /// Stop syncing on this Mac, or also delete what the app keeps; then
    /// say how the app itself goes, and quit.
    func removeHere() {
        let server = settingsModel?.current?.mode == "server"
        let keychain = server ? "the upload token" : "the Hardcover token and the webhook's token"
        let goes = (server ? [] : ["your books and reading as read from the Kobo,"]) + [
            "the copies of the Kobo's database, the settings and the log, in Library/Application Support/kobo-hardcover-sync,",
            "\(keychain), in the Keychain.",
        ]
        var text = """
            Stop syncing: plugging in the Kobo no longer starts a sync. Everything else stays, for when you open the app again.

            Delete everything: also deletes, from this Mac,
            """
        text += goes.map { "\n• " + $0 }.joined()
        if server { text += "\n\nYour books stay on the server. Remove this Mac there as well, under Settings, Devices." }
        let ask = NSAlert()
        ask.alertStyle = .warning
        ask.messageText = "Remove \(name) from this Mac?"
        ask.informativeText = text
        ask.addButton(withTitle: "Stop syncing")
        ask.addButton(withTitle: "Delete everything").hasDestructiveAction = true
        ask.addButton(withTitle: "Cancel")
        let finish = { (response: NSApplication.ModalResponse) in
            guard response != .alertThirdButtonReturn else { return }
            self.removed(purge: response == .alertSecondButtonReturn)
        }
        if let settings { ask.beginSheetModal(for: settings, completionHandler: finish) } else { finish(ask.runModal()) }
    }

    private func removed(purge: Bool) {
        if isPreview {
            say("Preview", "The preview removes nothing. The app would now stop its trigger\(purge ? ", and delete its folder and its tokens" : "").")
            return
        }
        try? SMAppService.agent(plistName: agentPlist).unregister()
        forgetBooks()  // out of Spotlight: the app no longer looks after them here
        forgetShelf()  // and the widget shows none
        let (ok, output) = tool(purge ? ["uninstall", "--purge"] : ["uninstall"])
        let done = NSAlert()
        done.messageText = ok ? "\(name) no longer syncs on this Mac" : "Not everything was removed"
        done.informativeText = ok
            ? "\(purge ? "What it kept here is deleted. " : "")To remove the app as well, drag it from Applications to the Bin."
            : output.replacingOccurrences(of: "kobo-hardcover-sync: ", with: "")
        done.addButton(withTitle: "Quit")
        done.addButton(withTitle: "Show the App in Finder")
        if done.runModal() == .alertSecondButtonReturn {
            NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL])
        }
        NSApp.terminate(nil)
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
        let settingsItem = item("Settings…", #selector(showSettings), ",")
        settingsItem.target = self
        let updatesItem = item("Check for Updates…", #selector(checkForUpdates), "")
        updatesItem.target = self
        _ = menu(name, [
            item("About \(name)", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            updatesItem,
            .separator(),
            settingsItem,
            .separator(),
            item("Hide \(name)", #selector(NSApplication.hide(_:)), "h"),
            .separator(),
            item("Quit \(name)", #selector(NSApplication.terminate(_:)), "q"),
        ])
        let redo = item("Redo", Selector(("redo:")), "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        _ = menu("Edit", [  // the text fields' keys go through these: without Paste, ⌘V does nothing in them
            item("Undo", Selector(("undo:")), "z"),
            redo,
            .separator(),
            item("Cut", #selector(NSText.cut(_:)), "x"),
            item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Paste", #selector(NSText.paste(_:)), "v"),
            item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])
        let syncItems = [
            item("Sync Now", #selector(syncFromMenu), "r"),
            item("Check Again", #selector(checkFromMenu), "r"),
            .separator(),
            item("Show the Log", #selector(logFromMenu), ""),
        ]
        syncItems[1].keyEquivalentModifierMask = [.command, .shift]
        syncItems.forEach { $0.target = self }
        _ = menu("Sync", syncItems)
        let sidebar = item("Show Sidebar", #selector(NSSplitViewController.toggleSidebar(_:)), "s")
        sidebar.keyEquivalentModifierMask = [.command, .control]
        let fullScreen = item("Enter Full Screen", #selector(NSWindow.toggleFullScreen(_:)), "f")
        fullScreen.keyEquivalentModifierMask = [.command, .control]
        let panes = Pane.allCases.enumerated().map { n, pane in
            let it = item(pane.rawValue, #selector(paneFromMenu(_:)), "\(n + 1)")
            it.tag = n
            it.target = self
            return it
        }
        _ = menu("View", panes + [.separator(), sidebar, fullScreen])
        NSApp.windowsMenu = menu("Window", [
            item("Close", #selector(NSWindow.performClose(_:)), "w"),
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Zoom", #selector(NSWindow.performZoom(_:)), ""),
            .separator(),
            item("Bring All to Front", #selector(NSApplication.arrangeInFront(_:)), ""),
        ])
        let helpItem = item("\(name) Help", #selector(helpFromMenu), "?")
        helpItem.target = self
        NSApp.helpMenu = menu("Help", [helpItem])  // macOS puts its search above it: of the menus, and of the guide (GuideSearch)
        return bar
    }

    // ---------- the Sync menu: the window's buttons, with their keys ----------
    @objc func syncFromMenu() { model?.syncNow() }
    @objc func checkFromMenu() { model?.refresh() }
    @objc func logFromMenu() { showLog() }

    // ---------- the View and Help menus ----------
    /// ⌘1 to ⌘4: the sidebar's panes, in its order.
    @objc func paneFromMenu(_ sender: NSMenuItem) {
        showWindow()
        model?.pane = Pane.allCases[sender.tag]
    }

    /// The guide, in a window of its own.
    @objc func helpFromMenu() {
        if let help {
            NSApp.activate(ignoringOtherApps: true)
            return help.makeKeyAndOrderFront(nil)
        }
        let help = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 760, height: 560),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        help.title = "\(name) Help"
        help.toolbar = NSToolbar()
        help.toolbarStyle = .unified
        help.contentView = NSHostingView(rootView: HelpView(place: guide))
        help.isReleasedWhenClosed = false
        help.delegate = self
        help.center()
        help.setFrameAutosaveName("Help")
        self.help = help
        begin()  // as Settings: the app stays while it is open
        help.makeKeyAndOrderFront(nil)
    }

    /// The guide at a topic, searching for what was typed in the Help menu.
    func showGuide(at topic: String?, search: String) {
        guide.search = search
        guide.chosen = topic
        helpFromMenu()
    }

    // ---------- the first time ----------
    /// Where the reading goes, the launch agent, `setup`. Whether to go on to the window: set up, and Continue chosen.
    func setUpHere() -> Bool {
        let ask = NSAlert()
        ask.messageText = "Set up \(name)"
        ask.informativeText = """
            Where should your reading go?

            On this computer: this Mac reads the Kobo when you plug it in, and keeps your shelf on Hardcover in step itself.

            With a server: only if someone in your household runs one. This Mac sends what the Kobo knows to that Kobo Hardcover Sync server.
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
        // The window is the home now: Getting started, on its Overview, says what comes next.
        done.addButton(withTitle: ok ? "Continue" : "OK")
        if ok { done.addButton(withTitle: "Later") }
        let goOn = done.runModal() == .alertFirstButtonReturn && ok
        if askNext { askForNotifications() }
        return goOn
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

extension App: NSMenuItemValidation {
    /// Sync Now and Check Again as their buttons in the window: not while a sync or a check runs, nor before setup.
    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(syncFromMenu):
            guard let model else { return false }
            return !model.syncing && model.elsewhere.isEmpty && !(model.status?.mode.isEmpty ?? true)
        case #selector(checkFromMenu):
            return model?.checks != nil
        case #selector(paneFromMenu(_:)):
            item.state = model?.pane == Pane.allCases[item.tag] ? .on : .off
            return model != nil
        default:
            return true
        }
    }
}
