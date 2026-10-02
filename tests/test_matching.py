"""Which search hit is the book: only one that agrees in title and author,
never the first hit because it is the first. The made-up hits here have the
shapes that turned up on a real shelf."""

import json

from kobo_hardcover_sync.engine import hardcover
from kobo_hardcover_sync.engine.hardcover import EXACT, PART, PREFIX, agreement, choose
from tests.test_hardcover import READING, FakeHC, row, run, setup


def hit(book_id, title, authors, also=()):
    return {"book_id": book_id, "title": title, "authors": list(authors), "pages": 300, "slug": "s", "also": list(also)}


JORDAN = hit(1, "The Eye of the World", ["Robert Jordan"], also=["Het Oog van de Wereld", "L'Œil du monde", "Das Auge der Welt"])


def test_a_title_agrees_exactly_as_a_part_or_as_a_start():
    blind = hit(80, "Blindness", ["Jose Saramago"])
    assert agreement("Blindness", "José Saramago", blind) == EXACT  # accents and case do not count
    assert agreement("Tempel der winden", "Terry Goodkind", hit(2, "De tempel der winden", ["Terry Goodkind"])) == EXACT  # nor an article
    assert agreement("The", "A", hit(3, "The", ["A"])) == EXACT and hardcover.title_key("The") == "the"  # a title that is only an article
    # One part of the book's own title: the title before its subtitle, or after a series name.
    assert agreement("Helgoland", "Carlo Rovelli", hit(4, "Helgoland: Making Sense of the Quantum Revolution", ["Carlo Rovelli"])) == PART
    lennep = hit(5, "Lopen met Van Lennep: De zomer van 1823: Dagboek", ["Jacob van Lennep"])
    assert agreement("De zomer van 1823", "Jacob van Lennep, Geert Mak", lennep) == PART
    assert agreement("Dune", "Frank Herbert", hit(6, "Dune - The Graphic Novel", ["Frank Herbert"])) == PART
    # One title starts with the other: only believed of the first hit.
    kings = hit(7, "A Clash of Kings", ["George R.R. Martin"])
    assert agreement("A Clash of Kings: A Song of Ice and Fire 2", "George R.R. Martin", kings, first=True) == PREFIX
    assert agreement("A Clash of Kings: A Song of Ice and Fire 2", "George R.R. Martin", kings) == 0
    assert agreement("Item", "A", hit(8, "It", ["A"]), first=True) == 0  # whole words
    # Nothing in common.
    assert agreement("Het verre huis", "Jan Jansen", hit(9, "The Far House", ["Jan Jansen"])) == 0
    assert agreement("", "A", hit(10, "", ["A"])) == 0


def test_a_translation_is_known_by_the_titles_hardcover_lists_for_the_book():
    assert agreement("Het Oog van de Wereld", "Robert Jordan", JORDAN) == EXACT
    assert agreement("L'œil du monde", "Robert Jordan", JORDAN) == EXACT
    # A title Hardcover does not list for it: a translation is never guessed at.
    assert agreement("De strijd der koningen", "George R.R. Martin", hit(7, "A Clash of Kings", ["George R.R. Martin"])) == 0
    # One of the other titles has to be the title: a part or a start of one is not enough.
    assert agreement("Het Oog", "Robert Jordan", JORDAN, first=True) == 0
    assert agreement("Het Oog van de Wereld 2.0", "Robert Jordan", JORDAN, first=True) == 0
    wheel = hit(1, "The Eye of the World", ["Robert Jordan"], also=["Het Rad des Tijds: Het Oog van de Wereld"])
    assert agreement("Het Rad des Tijds", "Robert Jordan", wheel) == 0  # a series name inside another title is not this book
    series = hit(11, "The Final Empire", ["Brandon Sanderson"], also=["Mistborn", "Mistborn: The Final Empire"])
    assert agreement("Mistborn: Secret History", "Brandon Sanderson", series, first=True) == 0


def test_an_author_has_to_agree_and_may_be_any_name_the_kobo_lists():
    fire = hit(12, "The Waking Fire", ["Anthony Ryan"], also=["Het Vuur van de Draak"])
    assert agreement("Het Vuur van de Draak", "Niels van Eekelen, Jet Matla, Anthony Ryan", fire) == EXACT  # translators listed first
    assert agreement("Het Vuur van de Draak", "Niels van Eekelen, Jet Matla", fire) == 0
    assert agreement("Blindness", "", hit(80, "Blindness", ["Jose Saramago"])) == 0  # the Kobo names nobody
    assert agreement("Blindness", "José Saramago", hit(80, "Blindness", [])) == 0  # Hardcover names nobody
    summary = hit(13, "Summary of Carlo Rovelli's Helgoland", ["Everest Media,"])
    assert agreement("Helgoland", "Carlo Rovelli", summary, first=True) == 0  # the same words, someone else's book


def test_which_hit_is_taken():
    summary = hit(13, "Summary of Carlo Rovelli's Helgoland", ["Everest Media,"])
    helgoland = hit(4, "Helgoland: Making Sense of the Quantum Revolution", ["Carlo Rovelli"])
    assert choose("Helgoland", "Carlo Rovelli", [summary, helgoland]) is helgoland  # not the first hit: the one that agrees
    assert choose("Helgoland", "Carlo Rovelli", [summary]) is None and choose("Helgoland", "Carlo Rovelli", []) is None
    # The exact title goes before a title that only starts the same.
    dune, messiah = hit(20, "Dune", ["Frank Herbert"]), hit(21, "Dune Messiah", ["Frank Herbert"])
    assert choose("Dune Messiah", "Frank Herbert", [dune, messiah]) is messiah
    assert choose("Dune", "Frank Herbert", [messiah, dune]) is dune
    # The same book twice in Hardcover's catalogue: the one the search puts first.
    twice = [hit(30, "Blindness", ["Jose Saramago"]), hit(31, "Blindness", ["José Saramago"])]
    assert choose("Blindness", "José Saramago", twice) is twice[0]
    # Two books that agree equally, and neither is the first hit: the reader says which.
    assert choose("Blindness", "José Saramago", [summary, *twice]) is None
    # The same book twice among the hits is one book.
    assert choose("Blindness", "José Saramago", [summary, twice[0], dict(twice[0])]) is twice[0]


def test_a_translation_matches_by_itself_and_what_is_kept_for_the_reader_is_small(tmp_path):
    eye = ("eye", "Het Oog van de Wereld", "Robert Jordan, Lia Belt", "9789000000001", 30, 1, "2026-09-29T10:00:00Z", 900)
    kings = ("kings", "De strijd der koningen", "George R.R. Martin", "9789000000002", 10, 1, "2026-09-29T10:00:00Z", 900)
    st = setup(tmp_path, [eye, kings])
    fake = FakeHC(search={"Het": [JORDAN], "De": [hit(7, "A Clash of Kings", ["George R.R. Martin"], also=["Juego de tronos II"])]})
    r = run(tmp_path, fake, live=False)
    assert (r["matched"], r["uncertain"]) == (1, 1)
    assert (row(st, "eye")["hc_how"], row(st, "eye")["hc_book_id"], row(st, "eye")["hc_title"]) == ("search", 1, "The Eye of the World")
    waiting = row(st, "kings")
    assert waiting["hc_how"] == "uncertain" and json.loads(waiting["hc_candidates"]) == [
        {"book_id": 7, "title": "A Clash of Kings", "authors": ["George R.R. Martin"], "pages": 300, "slug": "s"}
    ]  # the other titles are for matching, not for keeping


class Counting(FakeHC):
    def search(self, text, n=5):
        self.calls.append(("search", text))
        return super().search(text, n)


def test_a_waiting_book_gets_one_more_look_when_the_rules_have_changed(tmp_path):
    eye = ("eye", "Het Oog van de Wereld", "Robert Jordan", "9789000000001", 30, 1, "2026-09-29T10:00:00Z", 900)
    st = setup(tmp_path, [eye, READING])
    # As an earlier version left them: looked up, not sure, waiting.
    st.execute("update book set hc_how = 'uncertain', hc_candidates = '[]', hc_looked = null")
    st.commit()
    fake = Counting(search={"Het": [JORDAN]})  # Hardcover knows the first, not the second
    r = run(tmp_path, fake, live=False)
    assert sorted(c[1] for c in fake.calls) == ["Blindness José Saramago", "Het Oog van de Wereld Robert Jordan"]
    assert (r["matched"], r["uncertain"]) == (1, 1) and row(st, "eye")["hc_book_id"] == 1
    assert row(st, "rd")["hc_how"] == "none" and row(st, "rd")["hc_looked"] == hardcover.MATCH_RULES
    # Once: the book that is still not found waits for the reader again.
    fake.calls.clear()
    assert run(tmp_path, fake, live=False)["uncertain"] == 0 and fake.calls == []
    # A match the reader chose in the meantime is not looked up again, whatever version looked last.
    st.execute("update book set hc_how = 'manual', hc_book_id = 99, hc_looked = null where content_id = 'rd'")
    st.commit()
    run(tmp_path, fake, live=False)
    assert fake.calls == [] and row(st, "rd")["hc_book_id"] == 99
