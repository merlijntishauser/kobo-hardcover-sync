# The Homebrew formula

```
brew install merlijntishauser/tap/kobo-hardcover-sync
kobo-hardcover-sync setup
```

The tap is `merlijntishauser/homebrew-tap`. The formula in it is written
from this folder at every release.

## How it is built

From source, the way Homebrew's own formulae are: the tool's source
package, and one `resource` for each Python package it needs, each with
the address and SHA-256 that `uv.lock` pins. What Homebrew installs is
what the tests ran with.

Two of those packages (pydantic-core, cryptography) are written in Rust,
so Rust is a build dependency and the first install takes several minutes.
`make_formula.py` writes the formula; nobody edits it by hand.

| | |
|---|---|
| Install | `brew install`, then `kobo-hardcover-sync setup`. `setup` makes the trigger and, on a Mac, the small app that needs Full Disk Access once. |
| Upgrade | `brew upgrade`. The trigger starts the tool by Homebrew's own path, which stays the same, and the app is not rebuilt, so the permission stays. |
| Uninstall | `kobo-hardcover-sync uninstall` first (it removes the trigger and the app), then `brew uninstall`. Books, settings and tokens stay unless you add `--purge`. |

Homebrew services are not used: nothing runs in between syncs, so there
is no service to keep.

`tap-README.md` in this folder is the README of the tap repository.

## Cutting the formula for a release

1. Publish the release, so its source package has a public address.
2. Write the formula:

   ```
   uv run python packaging/homebrew/make_formula.py --url <address of the .tar.gz> --sha256 <its sha256> > kobo-hardcover-sync.rb
   ```

3. Put it in the tap as `Formula/kobo-hardcover-sync.rb`, and there:
   `brew audit --strict --online kobo-hardcover-sync`, `brew install
   --build-from-source kobo-hardcover-sync`, `brew test kobo-hardcover-sync`.

A dependency bump changes `uv.lock`, and with it the formula the next
release writes.

## Trying it before there is a release

On a Mac, in a checkout:

```
uv build --sdist
uv run python packaging/homebrew/make_formula.py --sdist dist/kobo_hardcover_sync-*.tar.gz > /tmp/kobo-hardcover-sync.rb
brew tap-new --no-git merlijntishauser/tap
cp /tmp/kobo-hardcover-sync.rb "$(brew --repository merlijntishauser/tap)/Formula/"
brew install --build-from-source merlijntishauser/tap/kobo-hardcover-sync
brew test merlijntishauser/tap/kobo-hardcover-sync
```

`--sdist` points the formula at the file on that Mac, so nothing has to be
public. `brew tap-new --no-git` makes a tap that exists on that Mac only;
`brew untap merlijntishauser/tap` removes it again.

## What has been checked, and what has not

Checked on Linux, without Homebrew (2026-10-02): all 17 source packages
download and match their SHA-256; 13 of them and the tool itself build
from source with the options Homebrew passes to pip. The other four
(cffi, cryptography, pydantic-core, PyYAML) need a C or Rust compiler,
which that machine does not have.

Run on a Mac (macOS 27, Apple silicon, 2026-10-02), from a formula written
with `--sdist`: `brew install --build-from-source` built all 17 resources,
the four compiled ones included, and `brew test` ran. That run showed one
fault, fixed since: Homebrew read the version of a development build as
"0", so such a version is now written into the formula.

The same day, on that Mac: `setup` run from Homebrew's copy, a sync on
plug-in, `brew reinstall`, and another sync on plug-in without a new
permission: Full Disk Access stayed. `brew audit --strict --online` found
one thing, the homepage answering 404 while the repository is private.

