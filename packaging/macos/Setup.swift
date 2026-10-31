// Setting up, in the window (docs/macos-app.md): where the reading goes,
// then what `setup` said, on the galley and in the app's words, the raw
// output behind Details. The alerts this replaces asked the same two
// questions and ended in a monospaced dump with this Mac's hash somewhere
// inside it. The order stays: the launch agent, `setup`, and only then
// macOS's question about notifications, once the galley is left.

import AppKit
import ServiceManagement
import SwiftUI

/// Setup as it runs, and how it ended.
struct SetupRun {
    var working = true
    var mode = "local"  // "local" or "server"
    var server = ""
    var ok = false
    var output = ""  // everything setup printed
    var said = ""  // its last word, without the tool's name, when it did not finish
    var hash = ""  // this Mac's upload token hash, in server mode: for the server's page
    var loginItems = false  // macOS wants the app allowed under Login Items first
}

extension WindowModel {
    /// The launch agent, then `setup`; the galley shows how it went.
    func runSetup(mode: String, server: String) {
        settingUp = true
        if isPreview {
            var run = SetupRun(working: false, mode: mode, server: server)
            run.said = "The preview sets nothing up. The app would now register its launch agent and run setup \(mode == "local" ? "--local" : "--server \(server)")."
            setupRun = run
            return
        }
        if let problem = register() {
            setupRun = SetupRun(working: false, mode: mode, server: server, said: problem, loginItems: true)
            return
        }
        setupRun = SetupRun(mode: mode, server: server)
        let args = mode == "local" ? ["setup", "--local"] : ["setup", "--server", server]
        DispatchQueue.global(qos: .userInitiated).async {
            let (ok, output) = tool(args)
            var hash = ""
            if ok && mode == "server", case .success(let settings) = answer(SettingsAnswer.self, ["settings", "--json"]) {
                hash = settings.uploadTokenHash
            }
            DispatchQueue.main.async {
                let printed = output.trimmingCharacters(in: .whitespacesAndNewlines)
                self.setupRun = SetupRun(
                    working: false, mode: mode, server: server, ok: ok, output: printed, said: ok ? "" : said(NoAnswer(said: printed)), hash: hash)
                if ok { self.refresh() }  // the status has a mode now; the galley stays until Continue
            }
        }
    }

    /// Continue: the window is the home now. Only now macOS's question about
    /// notifications: asked earlier, it came in the corner of the screen
    /// behind setup's own windows, and was missed.
    func finishSetup() {
        setupRun = nil
        settingUp = false
        if notifications == .notDetermined { askForNotifications() }
    }
}

/// Setting up, on the galley: where the reading goes, then what setup said.
struct SetupGalley: View {
    @ObservedObject var model: WindowModel
    @State private var mode = "local"
    @State private var address = ""
    @State private var filled = false

    private var server: Bool { mode == "server" }
    private var wanted: String { address.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var ready: Bool { !server || wanted.hasPrefix("https://") || wanted.hasPrefix("http://") }
    private var working: Bool { model.setupRun?.working ?? false }

    var body: some View {
        Galley {
            if let run = model.setupRun, !run.working {
                outcome(run)
            } else {
                choices
            }
        }
        .onAppear(perform: fill)
        .onChange(of: model.status?.server) { _ in fill() }
    }

    /// The mode and address chosen before, when setting up again.
    private func fill() {
        guard !filled, let status = model.status else { return }
        filled = true
        if !status.mode.isEmpty { mode = status.mode }
        address = status.server.isEmpty ? configuredServer() ?? "" : status.server
    }

    private func start() {
        guard ready && !working else { return }
        model.runSetup(mode: mode, server: wanted)
    }

    // ---------- where the reading goes ----------
    @ViewBuilder private var choices: some View {
        SheetHead("Where should your reading go?")
        ProofSheet {
            choice("local", "On this computer", "This Mac reads the Kobo when you plug it in, and keeps your shelf on Hardcover in step itself.")
            SoftRule()
            choice("server", "With a server", "Only if someone in your household runs one. This Mac sends what the Kobo knows to that Lastread server.")
            if server {
                TextField("The server's address", text: $address, prompt: Text("https://kobo.example.org"))
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(start)
                    .padding(.leading, 14 + 16 + 10)  // under the choice's words
                    .padding(.trailing, 14)
                    .padding(.bottom, 12)
            }
        }
        HStack(spacing: 10) {
            if working {
                ProgressView().controlSize(.small)
                Text("Setting up…").foregroundStyle(Pencil.graphite)
            } else if server {
                Text("The address of its page, starting with https://").font(.callout).foregroundStyle(Pencil.graphite)
            }
            Spacer()
            Button("Set up", action: start).keyboardShortcut(.defaultAction).disabled(!ready || working)
        }
        .padding(.horizontal, 4)
    }

    /// One of the two ways, as a radio in the pencils: blue is the reader's choice.
    private func choice(_ key: String, _ title: String, _ text: String) -> some View {
        let chosen = mode == key
        return Button { mode = key } label: {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                ZStack {
                    Circle().fill(chosen ? Pencil.blue : Pencil.sheet)
                    Circle().strokeBorder(chosen ? Pencil.blue : Pencil.edge, lineWidth: 1)
                    if chosen { Circle().fill(Pencil.onFlag).frame(width: 6, height: 6) }
                }
                .frame(width: 16, height: 16)
                .alignmentGuide(.firstTextBaseline) { $0[.bottom] - 3 }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).fontWeight(.medium).foregroundStyle(chosen ? Pencil.blue : Pencil.ink)
                    Text(text).foregroundStyle(Pencil.graphite).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .onSheet()
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }

    // ---------- what setup said ----------
    @ViewBuilder private func outcome(_ run: SetupRun) -> some View {
        let host = URL(string: run.server)?.host ?? run.server
        SheetHead(run.ok ? "\(name) is set up" : "Setup did not finish")
        ProofSheet {
            if run.ok {
                Row(
                    state: "ok", what: run.mode == "server" ? "Your reading goes to \(host)" : "Your reading stays on this Mac",
                    found: run.mode == "server"
                        ? "Plugging in the Kobo sends what it knows to the server. Add this Mac on the server's page, under Settings, Devices, by its hash, unless it is there already:"
                        : "Plugging in the Kobo starts a sync. The overview says what comes next: connect to Hardcover, plug in your Kobo, choose your books, go live."
                )
                .onSheet()
                if run.mode == "server" {  // the hash as the sign-in shows its code: to compare, or to copy
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text(run.hash.isEmpty ? "The hash is in the details below." : run.hash)
                            .font(.system(size: 14, weight: .semibold, design: .monospaced)).textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                        Button("Copy") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(run.hash, forType: .string)
                        }
                        .controlSize(.small)
                        .disabled(run.hash.isEmpty)
                    }
                    .padding(.leading, 14 + 18 + 10)
                    .padding(.trailing, 14)
                    .padding(.bottom, 12)
                }
            } else {
                Row(state: "fail", what: run.loginItems ? "Login Items" : "Setup", found: run.said) {
                    if run.loginItems { Button("Open Login Items") { SMAppService.openSystemSettingsLoginItems() } }
                }
                .onSheet()
            }
            if !run.output.isEmpty {
                SoftRule()
                DisclosureGroup("Details") {
                    Text(run.output).font(.system(.callout, design: .monospaced)).foregroundStyle(Pencil.graphite)
                        .textSelection(.enabled).fixedSize(horizontal: false, vertical: true).padding(.top, 6)
                }
                .onSheet()
            }
        }
        if run.ok && model.notifications == .notDetermined {
            Text("Next, macOS asks in the corner of the screen whether \(name) may show notifications. Allow it: that is how it tells you what a sync did.")
                .font(.callout).foregroundStyle(Pencil.graphite).fixedSize(horizontal: false, vertical: true).padding(.horizontal, 4)
        }
        HStack {
            if run.ok && run.mode == "server" {
                Button("Open Devices on \(host)") { if let page = URL(string: run.server + "/settings#devices") { NSWorkspace.shared.open(page) } }
            }
            Spacer()
            if run.ok {
                Button("Continue") { model.finishSetup() }.keyboardShortcut(.defaultAction)
            } else {
                Button("Try Again") { model.setupRun = nil }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(.horizontal, 4)
    }
}
