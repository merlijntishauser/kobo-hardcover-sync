// Hardcover in the app (docs/plans/2026-10-24-mac-app-native-books-design.md,
// step 4): signing in, as the page does it (`token --json`: where to
// approve, then who signed in), a pasted token as the second way, and
// going live (`settings --set live=true`). Getting started, on the
// Overview and above the list of books, leads there.

import AppKit
import SwiftUI

/// A sign-in while it runs, for the sheet that shows it.
struct SignIn {
    var link = ""
    var code = ""
    var done: TokenLine.Done?
    var problem = ""
    var pasting = false
}

/// Where a token is made, with what it may do: hardcover.NEW_TOKEN_URL.
let newTokenURL = "https://hardcover.app/account/api/keys/new?scope=read:me:content+read:catalog+read:library+write:library"

/// The preview shares the Keychain item with the app itself: it touches no connection and no shelf.
let previewLeavesHardcover = "The preview changes nothing on Hardcover and leaves the Hardcover connection in the Keychain alone, which the app itself uses."

extension WindowModel {
    /// Sign in on Hardcover: the tool opens the browser and says where; the sheet follows it.
    func connect(code: Bool = false) {
        guard !isPreview else {
            problem = previewLeavesHardcover
            return
        }
        signInProcess?.terminate()
        signIn = SignIn()
        let (p, out) = toolProcess(["token", "--json"] + (code ? ["--code"] : []))
        signInProcess = p
        DispatchQueue.global(qos: .userInitiated).async {
            var lines: [String] = []
            do {
                try p.run()
            } catch {
                DispatchQueue.main.async { self.signIn?.problem = "\(name) could not start its tool: \(error.localizedDescription)" }
                return
            }
            var rest = Data()
            let reader = out.fileHandleForReading
            while case let chunk = reader.availableData, !chunk.isEmpty {
                rest.append(chunk)
                while let end = rest.firstIndex(of: UInt8(ascii: "\n")) {
                    let line = String(decoding: rest[rest.startIndex..<end], as: UTF8.self)
                    rest = Data(rest[rest.index(after: end)...])
                    lines.append(line)
                    guard case .success(let step) = decode(TokenLine.self, line) else { continue }
                    DispatchQueue.main.async {
                        if let open = step.open {
                            self.signIn?.link = open
                            self.signIn?.code = step.code ?? ""
                        }
                        if let done = step.done { self.signIn?.done = done }
                    }
                }
            }
            p.waitUntilExit()
            let last = lines.last { !$0.hasPrefix("{") && !$0.trimmingCharacters(in: .whitespaces).isEmpty } ?? ""
            DispatchQueue.main.async {
                guard p === self.signInProcess else { return }  // cancelled, or started again
                self.signInProcess = nil
                if self.signIn?.done == nil && p.terminationReason != .uncaughtSignal {
                    self.signIn?.problem = said(NoAnswer(said: last.isEmpty ? "The sign-in ended without a word." : last))
                }
                self.refresh()
            }
        }
    }

    func cancelSignIn() {
        let p = signInProcess
        signInProcess = nil
        p?.terminate()
        signIn = nil
    }

    /// The second way: a token made on Hardcover, given on standard input, never as an argument.
    func paste(_ token: String) {
        signInProcess?.terminate()
        signInProcess = nil
        DispatchQueue.global(qos: .userInitiated).async {
            let (_, output) = tool(["token", "--paste", "--json"], input: token)
            let json = output.split(separator: "\n").last { $0.hasPrefix("{") }.map(String.init) ?? ""
            DispatchQueue.main.async {
                if case .success(let line) = decode(TokenLine.self, json), let done = line.done {
                    self.signIn?.done = done
                } else {
                    self.signIn?.problem = said(NoAnswer(said: output.trimmingCharacters(in: .whitespacesAndNewlines)))
                }
                self.refresh()
            }
        }
    }

    /// Go live: from now on a sync sends what the red marks say.
    func goLive() {
        DispatchQueue.global(qos: .userInitiated).async {
            let found = answer(SettingsAnswer.self, ["settings", "--set", "live=true", "--json"])
            DispatchQueue.main.async {
                if case .failure(let why) = found { self.problem = said(why) }
                self.refresh(check: false)
            }
        }
    }
}

/// Signing in, as it happens: where to approve, the code to compare, and how it ended.
struct ConnectSheet: View {
    @ObservedObject var model: WindowModel
    @State private var token = ""

    var body: some View {
        let signIn = model.signIn ?? SignIn()
        VStack(alignment: .leading, spacing: 14) {
            Text("Connect to Hardcover").font(.title2.weight(.semibold))
            if let done = signIn.done {
                HStack(spacing: 8) {
                    Mark(state: "ok", size: 22)
                    Text(done.message)
                }
                Text("Your books stay in a dry run until you go live: each sync says what it would send.")
                    .foregroundStyle(Pencil.graphite).fixedSize(horizontal: false, vertical: true)
                HStack {
                    Spacer()
                    Button("Done") { model.cancelSignIn() }.keyboardShortcut(.defaultAction)
                }
            } else if !signIn.problem.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Mark(state: "fail", size: 22)
                    Text(signIn.problem).fixedSize(horizontal: false, vertical: true)
                }
                HStack {
                    Button("Connect with a code instead") { model.connect(code: true) }
                    Spacer()
                    Button("Cancel") { model.cancelSignIn() }
                    Button("Try Again") { model.connect() }.keyboardShortcut(.defaultAction)
                }
            } else if signIn.pasting {
                Text("Make a token on Hardcover with what this app needs, and paste it here. It is kept in the Keychain.")
                    .fixedSize(horizontal: false, vertical: true)
                SecureField("Hardcover token", text: $token).textFieldStyle(.roundedBorder)
                HStack {
                    Button("Make a Token on Hardcover") { if let url = URL(string: newTokenURL) { NSWorkspace.shared.open(url) } }
                    Spacer()
                    Button("Cancel") { model.cancelSignIn() }
                    Button("Keep It") {
                        model.paste(token)
                        token = ""
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(token.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            } else {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(signIn.link.isEmpty ? "Asking Hardcover…" : "Approve on Hardcover, in your browser. This finishes by itself.")
                }
                if !signIn.code.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Check that Hardcover shows this code:").foregroundStyle(Pencil.graphite)
                        Text(signIn.code).font(.system(size: 26, weight: .semibold, design: .monospaced)).textSelection(.enabled)
                    }
                }
                HStack {
                    Button("Paste a token instead…") {
                        model.signInProcess?.terminate()
                        model.signInProcess = nil
                        model.signIn?.pasting = true
                    }
                    Spacer()
                    Button("Cancel") { model.cancelSignIn() }.keyboardShortcut(.cancelAction)
                    Button("Open Hardcover Again") { if let url = URL(string: signIn.link) { NSWorkspace.shared.open(url) } }
                        .disabled(signIn.link.isEmpty)
                }
            }
        }
        .padding(20)
        .frame(width: 440)
    }
}

/// Getting started (start.py): the four steps from a new reader to a live
/// shelf, the same as above the page's books, each with the one button that
/// does it. On the Overview a sheet of its own above the chain; above Books
/// the same steps in one band (`compact`).
struct StartSteps: View {
    @ObservedObject var model: WindowModel
    let start: BooksAnswer.Start
    var compact = false
    @State private var asking = false

    var body: some View {
        Group {
            if compact {
                HStack(alignment: .top, spacing: 18) {
                    ForEach(start.steps) { step in
                        HStack(alignment: .top, spacing: 8) {
                            number(step, size: 18)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(step.title).font(.callout.weight(.semibold)).foregroundStyle(step.state == "now" ? Pencil.blue : Pencil.ink)
                                if step.key == "books" {
                                    tally.font(.callout)
                                }
                                action(step)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityElement(children: .contain)
                    }
                }
                .padding(14)
                .background(Pencil.sheet, in: RoundedRectangle(cornerRadius: 4))  // a proof sheet, as on the overview
                .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(Pencil.rule, lineWidth: 1))
                .padding(.horizontal, 14)
                .padding(.bottom, 10)
                .accessibilityElement(children: .contain)
                .accessibilityLabel(start.title)
            } else {
                VStack(alignment: .leading, spacing: 10) {
                SheetHead(start.title)
                ProofSheet {
                    ForEach(Array(start.steps.enumerated()), id: \.element.id) { n, step in
                        if n > 0 { SoftRule() }
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            number(step, size: 22).alignmentGuide(.firstTextBaseline) { $0[.bottom] - 5 }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(step.title).fontWeight(step.state == "now" ? .semibold : .medium)
                                    .foregroundStyle(step.state == "now" ? Pencil.blue : step.state == "done" ? Pencil.graphite : Pencil.ink)
                                if step.key == "books" && step.state != "done" {
                                    (Text(step.text + " ") + tally).foregroundStyle(Pencil.graphite).fixedSize(horizontal: false, vertical: true)
                                } else {
                                    Text(step.text).foregroundStyle(Pencil.graphite).fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            Spacer(minLength: 8)
                            action(step)
                        }
                        .onSheet()
                        .accessibilityElement(children: .contain)
                    }
                }
                }
            }
        }
        .confirmationDialog("Go live?", isPresented: $asking) {
            Button("Go Live") { model.goLive() }
        } message: {
            Text(
                "From the next sync on, Hardcover is told what the red marks say, for the \(start.on == 1 ? "book" : "\(start.on) books") switched on. \(model.status?.mode == "server" ? "Settings on the page" : "Settings, General,") turns it off again."
            )
        }
    }

    /// "41 switched on so far.", the number in ink and tabular, as the page's tally.
    private var tally: Text {
        Text("\(start.on)").fontWeight(.semibold).monospacedDigit().foregroundColor(Pencil.ink)
            + Text(" \(start.tally)").foregroundColor(Pencil.graphite)
    }

    /// The step's number in a ring (filled blue for the step of now: the reader's), or a tick once done.
    @ViewBuilder private func number(_ step: BooksAnswer.Start.Step, size: CGFloat) -> some View {
        if step.state == "done" {
            Mark(state: "ok", size: size).accessibilityLabel("Done")
        } else {
            let now = step.state == "now"
            Text("\(step.n)").font(.callout.weight(.semibold).monospacedDigit())
                .foregroundStyle(now ? Pencil.onFlag : Pencil.graphite)
                .frame(width: size, height: size)
                .background(Circle().fill(now ? Pencil.blue : Color.clear))
                .overlay(Circle().stroke(now ? Pencil.blue : Pencil.edge, lineWidth: 1))
                .accessibilityLabel(now ? "Step \(step.n), now" : "Step \(step.n)")
        }
    }

    /// The step's one button: what the tool says it is (start.py, `action`).
    @ViewBuilder private func action(_ step: BooksAnswer.Start.Step) -> some View {
        switch step.action {
        case "connect":
            Button("Connect…") { model.connect() }.controlSize(compact ? .small : .regular)
        case "server_page":
            Button("Open the page") { if let server = model.status?.server { openServerSettings(server) } }
                .controlSize(compact ? .small : .regular)
        case "show_books" where !compact:  // above Books the list is right below
            Button("Show the books") { model.pane = .books }
        case "go_live":
            Button("Go live") { asking = true }
                .buttonStyle(.borderedProminent)
                .tint(Pencil.fill)  // red fills only what a sync sends
                .controlSize(compact ? .small : .regular)
                .disabled(!start.canGoLive)
                .help(start.canGoLive ? "" : "Connect to Hardcover first.")
        default:
            EmptyView()
        }
    }
}
