// What the tool answers (`status --json`, `doctor --json`, `history --json`,
// `settings --json`, `sync --steps`), as the app reads it. The samples in
// packaging/macos/samples have the same shape: tests/test_app_answers.py
// holds the tool to them, CheckSamples.swift holds these types to them.
//
// Foundation only, so that CI can compile it without the app.

import Foundation

/// The schema this app reads; the tool raises it when a field changes meaning.
let schema = 1

struct Sync: Codable, Equatable, Identifiable {
    let at: String  // ISO 8601, with the offset
    let trigger: String  // "mount", "app", "hand", or "" before there was a history
    let ok: Bool
    let title: String
    let message: String

    var id: String { at + trigger + title }
    var date: Date? { ISO8601DateFormatter().date(from: at) }
}

struct StatusAnswer: Codable {
    let schema: Int
    let version: String
    let mode: String  // "server", "local", or "" before setup
    let server: String
    let folder: String
    let kobo: String?  // where it is mounted, when one is plugged in
    let lastSync: Sync?
}

struct Check: Codable, Equatable, Identifiable {
    let group: String
    let what: String
    let state: String  // "ok", "note", "warn", "fail"
    let found: String
    let todo: String

    var id: String { group + what }
}

struct DoctorAnswer: Codable {
    let schema: Int
    let version: String
    let summary: String
    let problems: Int
    let checks: [Check]
}

struct HistoryAnswer: Codable {
    let schema: Int
    let syncs: [Sync]
}

struct SettingsAnswer: Codable {
    struct Values: Codable {
        let ejectAfterSync: Bool
        let verboseLog: Bool
        let allowUntestedKobo: Bool
        let checkForUpdates: Bool
        let exportTo: String
        let webhookUrl: String
    }

    let schema: Int
    let mode: String
    let server: String
    let uploadTokenHash: String
    let hardcoverConnected: Bool
    let settings: Values
}

/// One line of `sync --steps`: a step as it finishes, or, last, the outcome.
struct StepLine: Codable {
    struct Done: Codable {
        let ok: Bool
        let title: String
        let message: String
    }

    let schema: Int
    let step: String?
    let state: String?
    let text: String?
    let done: Done?
}

enum AnswerError: Error {
    case otherSchema(Int)
}

/// An answer of the tool, or nil with why not. A line that is not JSON (a
/// warning on stderr) is not an answer.
func decode<T: Codable>(_ type: T.Type, _ text: String) -> Result<T, Error> {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    do {
        let data = Data(text.utf8)
        let found = try decoder.decode(SchemaOnly.self, from: data).schema
        guard found == schema else { return .failure(AnswerError.otherSchema(found)) }
        return .success(try decoder.decode(T.self, from: data))
    } catch {
        return .failure(error)
    }
}

private struct SchemaOnly: Codable {
    let schema: Int
}
