# merlijntishauser/tap

A [Homebrew](https://brew.sh) tap.

## kobo-hardcover-sync

Keeps your shelf on [Hardcover](https://hardcover.app) in step with what
you read on a Kobo e-reader.

```
brew install merlijntishauser/tap/kobo-hardcover-sync
kobo-hardcover-sync setup
```

On a Mac with Apple silicon and macOS 15 or newer Homebrew fetches a
ready-made build (a bottle), made by the workflow in this repository. On
other Macs it builds from source, which takes several minutes. What the
tool does, and everything after installing:
<https://github.com/merlijntishauser/kobo-hardcover-sync>

Before `brew uninstall kobo-hardcover-sync`, run `kobo-hardcover-sync
uninstall`, or the plug-in trigger stays behind.

The formula is written by a script in that repository
(`packaging/homebrew/make_formula.py`) from the versions its lock file
pins. Problems with the formula are welcome as issues there.
