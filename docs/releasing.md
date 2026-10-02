# Releasing

For whoever cuts a release. A release is a tag; the rest follows from it.

## Before the tag

1. Everything green: `uv run pytest -q tests`, `uv run ruff check .`,
   `uv run ruff format --check .`,
   `uv run --group browser pytest -q browser_tests`.
2. `pyproject.toml`: the version, without `.dev0`.
3. `CHANGELOG.md`: the version's heading gets its date (`## 0.2.0 -
   2026-11-01`), and says what changed for someone who uses the tool. The
   release workflow refuses a version without a dated entry.
4. If a Kobo software version was newly seen working: add it to
   `KNOWN_VERSIONS` in `engine/collection.py` and to the table in the
   README (a test keeps the two the same).
5. Commit, and push `main`.

## The tag

```
git tag -s v0.2.0 -m "0.2.0"
git push origin v0.2.0
```

The `release` workflow then: checks that the tag and the package agree,
runs the tests, builds the source package and the wheel, uploads them to
PyPI (trusted publishing: no token is stored anywhere), and makes the
GitHub release with this version's part of the changelog as its notes.

The README that PyPI shows is the repository's, with its pictures and
links pointing at the tag on GitHub.

## After the tag

1. The Homebrew formula: see
   [packaging/homebrew/README.md](../packaging/homebrew/README.md). The
   address and SHA-256 of the source package are on the PyPI page of the
   release, under *Download files*.
2. Set the version in `pyproject.toml` to the next one with `.dev0`, and
   open a new heading in `CHANGELOG.md`.

## Once, before the very first release

- On pypi.org, under *Publishing*, add a pending trusted publisher:
  owner `merlijntishauser`, repository `kobo-hardcover-sync`, workflow
  `release.yml`, environment `pypi`.
- In the repository's settings: an environment named `pypi`; private
  vulnerability reporting switched on (SECURITY.md points at it).
