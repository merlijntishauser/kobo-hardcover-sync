// CI: the app's reading of the tool's answers (Model.swift) against the
// samples in packaging/macos/samples, which the tool is held to as well
// (tests/test_app_answers.py). Built and run by the macos-app job:
//
//   swiftc -parse-as-library Model.swift CheckSamples.swift -o check && ./check samples

import Foundation

@main
struct CheckSamples {
    static func main() throws {
        let folder = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? "samples")
        func text(_ name: String) throws -> String { try String(contentsOf: folder.appendingPathComponent(name), encoding: .utf8) }
        var failed = false
        func check<T>(_ name: String, _ result: Result<T, Error>, _ fine: (T) -> Bool) {
            switch result {
            case .success(let answer) where fine(answer):
                print("ok    \(name)")
            case .success:
                print("wrong \(name): read, but not as expected")
                failed = true
            case .failure(let error):
                print("fail  \(name): \(error)")
                failed = true
            }
        }
        check("status.json", decode(StatusAnswer.self, try text("status.json"))) { $0.lastSync?.date != nil && $0.kobo != nil }
        check("status-local.json", decode(StatusAnswer.self, try text("status-local.json"))) { $0.books?.needsMatch == 2 && $0.kobo == nil }
        check("books.json", decode(BooksAnswer.self, try text("books.json"))) {
            $0.books.first?.details.onShelf == true && $0.sorts.allSatisfy { $0.order == [0] } && $0.words.legend.count == 7
        }
        check("doctor.json", decode(DoctorAnswer.self, try text("doctor.json"))) { !$0.checks.isEmpty }
        check("history.json", decode(HistoryAnswer.self, try text("history.json"))) { $0.syncs.allSatisfy { $0.date != nil } }
        check("settings.json", decode(SettingsAnswer.self, try text("settings.json"))) { !$0.uploadTokenHash.isEmpty }
        check("update.json", decode(UpdateAnswer.self, try text("update.json"))) { $0.newer && !$0.latest.isEmpty }
        let lines = try text("steps.jsonl").split(separator: "\n").map { decode(StepLine.self, String($0)) }
        for (n, line) in lines.enumerated() {
            check("steps.jsonl line \(n + 1)", line) { n == lines.count - 1 ? $0.done != nil : $0.step != nil }
        }
        if case .success = decode(HistoryAnswer.self, #"{"schema": 2, "syncs": []}"#) {
            print("wrong another schema: read as if it were this one")
            failed = true
        } else {
            print("ok    another schema: refused")
        }
        exit(failed ? 1 : 0)
    }
}
