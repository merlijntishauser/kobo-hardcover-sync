// Spotlight (docs/plans/2026-10-26-mac-app-server-books-and-covers-design.md,
// step 4): each book's title and author in Spotlight on this Mac, with its
// cover, so that typing a title opens Covers at that book. The index is the
// system's own, on this Mac; nothing is sent anywhere. Removing the app here
// takes the books out again.

import CoreSpotlight
import CryptoKit
import Foundation
import UniformTypeIdentifiers

private let spotlightDomain = "books"
private let indexedKey = "SpotlightIndexed"  // what was indexed last: an unchanged list is not indexed again

/// The books as Spotlight should have them, when they changed since the last time.
func indexBooks(_ books: [BooksAnswer.Book]) {
    guard !isPreview else { return }  // the preview would put a second copy of every book in Spotlight
    let said = books.map { "\($0.id)\t\($0.title)\t\($0.author)\t\($0.cover)" }.joined(separator: "\n")
    let mark = SHA256.hash(data: Data(said.utf8)).map { String(format: "%02x", $0) }.joined()
    guard UserDefaults.standard.string(forKey: indexedKey) != mark else { return }
    let items = books.map { book -> CSSearchableItem in
        let about = CSSearchableItemAttributeSet(contentType: .content)
        about.title = book.title
        about.displayName = book.title
        about.contentDescription = book.author
        about.authorNames = [book.author]
        if !book.cover.isEmpty { about.thumbnailURL = URL(fileURLWithPath: book.cover) }
        return CSSearchableItem(uniqueIdentifier: book.id, domainIdentifier: spotlightDomain, attributeSet: about)
    }
    let index = CSSearchableIndex.default()
    index.deleteSearchableItems(withDomainIdentifiers: [spotlightDomain]) { _ in
        index.indexSearchableItems(items) { error in
            if error == nil { UserDefaults.standard.set(mark, forKey: indexedKey) }
        }
    }
}

/// No books of this app in Spotlight any more: it was removed from this Mac.
func forgetBooks() {
    CSSearchableIndex.default().deleteSearchableItems(withDomainIdentifiers: [spotlightDomain]) { _ in }
    UserDefaults.standard.removeObject(forKey: indexedKey)
}

/// The book a Spotlight result stands for, when this activity is one.
func spotlitBook(_ activity: NSUserActivity) -> String? {
    guard activity.activityType == CSSearchableItemActionType else { return nil }
    return activity.userInfo?[CSSearchableItemActivityIdentifier] as? String
}
