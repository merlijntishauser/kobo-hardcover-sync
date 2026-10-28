// The app updates itself (docs/macos-app.md, "Updating"): the release's disk
// image, from a link built from the version number alone; the app on it
// installed only when Apple notarised it and it is signed with this app's own
// Developer ID team and identifier; then it takes this one's place and starts.

import AppKit
import Security
import SwiftUI

/// Install version `version` of the app, in a small window that shows how far it is.
func installUpdate(_ version: String) {
    Updater.shared.start(version)
}

/// Why an update stopped, in the words the window shows.
struct Refusal: Error {
    let said: String
}

final class Updater: NSObject, ObservableObject, URLSessionDownloadDelegate, NSWindowDelegate {
    static let shared = Updater()

    @Published private(set) var version = ""
    @Published private(set) var step = ""
    @Published private(set) var fraction: Double?  // the download's part done; nil while it checks or installs
    @Published private(set) var refused: String?
    private var window: NSWindow?
    private var download: URLSessionDownloadTask?
    private var work: URL?
    private var installing = false  // the check and the swap: not to be broken off

    // ---------- the start: what can be known before anything is fetched ----------
    func start(_ version: String) {
        if let window {
            NSApp.activate(ignoringOtherApps: true)
            return window.makeKeyAndOrderFront(nil)
        }
        self.version = version
        refused = nil
        fraction = 0
        step = "Downloading…"
        show()
        guard version.range(of: #"^\d+\.\d+\.\d+$"#, options: .regularExpression) != nil else {
            return stop("“\(version)” is not a version number.")
        }
        guard team() != nil else {
            return stop("This copy is not the released app: it has no Developer ID signature to check the new one against.")
        }
        let here = Bundle.main.bundleURL
        guard !here.path.contains("/AppTranslocation/") else {
            return stop("macOS runs this copy from a hidden place. Move \(name) to Applications, open it from there, and try again.")
        }
        guard FileManager.default.isWritableFile(atPath: here.deletingLastPathComponent().path) else {
            return stop("This account cannot replace the app in \(here.deletingLastPathComponent().path).")
        }
        let link = URL(string: "https://github.com/merlijntishauser/kobo-hardcover-sync/releases/download/v\(version)/Kobo-Hardcover-Sync-\(version).dmg")!
        let session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: .main)
        download = session.downloadTask(with: link)
        download?.resume()
    }

    // ---------- the download ----------
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData _: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        guard totalBytesExpectedToWrite > 0 else { return }
        fraction = Double(totalBytesWritten) / Double(totalBytesExpectedToWrite)
        let size = ByteCountFormatter.string(fromByteCount: totalBytesExpectedToWrite, countStyle: .file)
        step = "Downloading… \(Int((fraction ?? 0) * 100))% of \(size)"
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        session.finishTasksAndInvalidate()
        guard let answer = downloadTask.response as? HTTPURLResponse, answer.statusCode == 200 else {
            let code = (downloadTask.response as? HTTPURLResponse)?.statusCode ?? 0
            return stop(code == 404 ? "Version \(version) has no disk image on GitHub yet. Try again in a while." : "GitHub answered \(code).")
        }
        do {  // the file goes when this returns: kept in a folder of its own first
            let work = FileManager.default.temporaryDirectory.appendingPathComponent("khs-update-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true)
            let image = work.appendingPathComponent("update.dmg")
            try FileManager.default.moveItem(at: location, to: image)
            self.work = work
            install(image)
        } catch {
            stop("The download could not be kept: \(error.localizedDescription)")
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let error, (error as? URLError)?.code != .cancelled else { return }
        stop("The download stopped: \(error.localizedDescription)")
    }

    // ---------- the check and the swap, away from the window's thread ----------
    private func install(_ image: URL) {
        fraction = nil
        step = "Checking the new version…"
        installing = true
        let version = self.version
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Result { try Self.put(image, version: version) }
            DispatchQueue.main.async {
                self.installing = false
                switch result {
                case .success(let installed): self.restart(installed)
                case .failure(let why): self.stop((why as? Refusal)?.said ?? why.localizedDescription)
                }
            }
        }
    }

    /// The app on the disk image, checked, copied next to this one, checked again, and swapped in.
    private static func put(_ image: URL, version: String) throws -> URL {
        let disk = image.deletingLastPathComponent().appendingPathComponent("disk")
        guard run("/usr/bin/hdiutil", ["attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", disk.path, image.path]) else {
            throw Refusal(said: "The disk image could not be opened.")
        }
        defer { _ = run("/usr/bin/hdiutil", ["detach", "-force", disk.path]) }
        let new = disk.appendingPathComponent("\(name).app")
        try check(new, version: version)
        let here = Bundle.main.bundleURL
        let staging = try FileManager.default.url(for: .itemReplacementDirectory, in: .userDomainMask, appropriateFor: here, create: true)
        let staged = staging.appendingPathComponent(here.lastPathComponent)
        guard run("/usr/bin/ditto", [new.path, staged.path]) else { throw Refusal(said: "The new version could not be copied.") }
        try check(staged, version: version)  // what is installed is the copy: checked as itself
        if let status = try? answer(StatusAnswer.self, ["status", "--json"]).get(), !(status.syncing ?? "").isEmpty {
            throw Refusal(said: "A sync is running. Try again when it has finished.")
        }
        do {
            return try FileManager.default.replaceItemAt(here, withItemAt: staged) ?? here
        } catch {
            throw Refusal(said: "The app could not be replaced: \(error.localizedDescription)")
        }
    }

    /// Notarised, signed by this app's team as this app, intact to the last file, and the version asked for.
    private static func check(_ app: URL, version: String) throws {
        guard let team = team(), let id = Bundle.main.bundleIdentifier else { throw Refusal(said: "This copy has no signature to compare with.") }
        var code: SecStaticCode?
        var requirement: SecRequirement?
        let wanted = "anchor apple generic and identifier \"\(id)\" and certificate leaf[subject.OU] = \"\(team)\" and notarized"
        guard SecStaticCodeCreateWithPath(app as CFURL, [], &code) == errSecSuccess, let code,
            SecRequirementCreateWithString(wanted as CFString, [], &requirement) == errSecSuccess, let requirement
        else { throw Refusal(said: "The disk image does not hold \(name).") }
        let flags = SecCSFlags(rawValue: kSecCSCheckAllArchitectures | kSecCSStrictValidate | kSecCSCheckNestedCode)
        guard SecStaticCodeCheckValidity(code, flags, requirement) == errSecSuccess else {
            throw Refusal(said: "The new version is not signed and notarised as \(name) is. It was not installed.")
        }
        let info = NSDictionary(contentsOf: app.appendingPathComponent("Contents/Info.plist"))
        guard info?["CFBundleShortVersionString"] as? String == version else {
            throw Refusal(said: "The disk image holds another version than \(version).")
        }
    }

    // ---------- the end ----------
    /// The new one starts once this one has quit.
    private func restart(_ installed: URL) {
        step = "Restarting…"
        let wait = Process()
        wait.executableURL = URL(fileURLWithPath: "/bin/sh")
        wait.arguments = ["-c", "while /bin/kill -0 \"$0\" 2>/dev/null; do /bin/sleep 0.2; done; /usr/bin/open \"$1\"", "\(getpid())", installed.path]
        do {
            try wait.run()
        } catch {
            return stop("Version \(version) is installed; open \(name) again to start it.")
        }
        cleanUp()
        NSApp.terminate(nil)
    }

    private func stop(_ said: String) {
        refused = said
        fraction = nil
        step = ""
        cleanUp()
    }

    func cancel() {
        download?.cancel()
        window?.close()
    }

    private func cleanUp() {
        download = nil
        if let work { try? FileManager.default.removeItem(at: work) }
        work = nil
    }

    private func show() {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 420, height: 150), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Update"
        window.contentView = NSHostingView(rootView: UpdateView(updater: self))
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.center()
        self.window = window
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool { !installing }

    func windowWillClose(_ notification: Notification) {
        download?.cancel()
        cleanUp()
        window = nil
    }
}

/// The team of this app's own Developer ID signature: none for a preview or a build signed ad hoc.
func team() -> String? {
    var me: SecCode?
    var code: SecStaticCode?
    var info: CFDictionary?
    guard SecCodeCopySelf([], &me) == errSecSuccess, let me, SecCodeCopyStaticCode(me, [], &code) == errSecSuccess, let code,
        SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
        let found = (info as? [String: Any])?[kSecCodeInfoTeamIdentifier as String] as? String,
        found.range(of: "^[A-Z0-9]{10}$", options: .regularExpression) != nil
    else { return nil }
    return found
}

/// A program, waited for: whether it ended well.
private func run(_ program: String, _ args: [String]) -> Bool {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: program)
    p.arguments = args
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    do { try p.run() } catch { return false }
    p.waitUntilExit()
    return p.terminationStatus == 0
}

struct UpdateView: View {
    @ObservedObject var updater: Updater

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Updating to \(updater.version)").font(.headline)
            if let refused = updater.refused {
                Text(refused).foregroundStyle(Pencil.graphite).fixedSize(horizontal: false, vertical: true)
                HStack {
                    Spacer()
                    Button("Download by Hand") {
                        if let link = URL(string: releases + updater.version) { NSWorkspace.shared.open(link) }
                        updater.cancel()
                    }
                    Button("Close") { updater.cancel() }.keyboardShortcut(.defaultAction)
                }
            } else {
                if let fraction = updater.fraction {
                    ProgressView(value: fraction)
                } else {
                    ProgressView().progressViewStyle(.linear)
                }
                Text(updater.step).font(.callout.monospacedDigit()).foregroundStyle(Pencil.graphite)
                HStack {
                    Spacer()
                    Button("Cancel") { updater.cancel() }.keyboardShortcut(.cancelAction).disabled(updater.fraction == nil)
                }
            }
        }
        .padding(20)
        .frame(width: 420)
    }
}
