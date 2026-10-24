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

Once the GitHub release is there, `release.yml` starts the Mac app's
own run (`macos-app.yml`, under Actions). Its signing job waits in the
`macos-signing` environment until the maintainer approves it under the
run's *Review deployments*. It then signs and notarises the app and adds
`Kobo-Hardcover-Sync-<version>.dmg` to the release. Notarisation usually
takes a few minutes, sometimes an hour. If it fails, start `macos-app` by
hand from the tag ("Use workflow from": the tag) with the tag as input:
it replaces the disk image on the release.

## After the tag

1. The Homebrew formula: see
   [packaging/homebrew/README.md](../packaging/homebrew/README.md). The
   address and SHA-256 of the source package are on the PyPI page of the
   release, under *Download files*. Pushing the formula to the tap is the
   whole job: the tap builds the bottles and adds them to the formula.
2. Set the version in `pyproject.toml` to the next one with `.dev0`, and
   open a new heading in `CHANGELOG.md`.

## Once, before the very first release

- On pypi.org, under *Publishing*, add a pending trusted publisher:
  owner `merlijntishauser`, repository `kobo-hardcover-sync`, workflow
  `release.yml`, environment `pypi`.
- In the repository's settings: an environment named `pypi`; private
  vulnerability reporting switched on (SECURITY.md points at it).

## Once, before the first release with the Mac app

What signing needs is in one environment and nowhere else: not in the
repository's own secrets, and not in any other workflow.

1. In the repository's settings, an environment named `macos-signing`:
   *Required reviewers* the maintainer, *Prevent self-review* off (the
   maintainer pushes the tag), *Deployment branches and tags* only tags
   matching `v*`.
2. A **Developer ID Application** certificate (Apple Developer, Certificates;
   or Xcode, Settings, Accounts, Manage Certificates), exported from
   Keychain Access as a `.p12` with a password of its own. Not the
   *Developer ID Installer* certificate, which signs `.pkg` files.
3. An **App Store Connect API key** for notarisation: App Store Connect,
   Users and Access, Integrations, *Team Keys*, with the *Developer* role.
   Its `.p8` file can be downloaded only once.
4. The environment's secrets:

   | Secret | What |
   |---|---|
   | `DEVELOPER_ID_P12` | the `.p12`, base64 (`base64 -i cert.p12 \| pbcopy`) |
   | `DEVELOPER_ID_P12_PASSWORD` | its password |
   | `NOTARY_KEY_P8` | the `.p8` file, base64 (`base64 -i AuthKey.p8 \| pbcopy`) |
   | `NOTARY_KEY_ID` | the key's id |
   | `NOTARY_ISSUER_ID` | the issuer id shown above the keys |

   One certificate and one key serve every app of the same developer
   team: a Developer ID is not tied to a bundle id. Secrets cannot be
   read back from GitHub, so they are set from the files, not copied
   from another repository.

5. Delete the `.p12` and `.p8` files from the computer they were made on,
   or keep them in a password manager. A leaked Developer ID certificate
   can sign software in the maintainer's name until Apple revokes it.

Replacing the certificate (it lasts five years) or the key means replacing
those secrets and nothing else. An app signed with the new certificate
has the same team id, so the permissions that Macs gave the app stay.
