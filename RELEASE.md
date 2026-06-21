# Release Process

This repository uses a tag-driven release workflow for versions after
`v1.0.2`. The `v1.0.2` release was created before this workflow existed and
should continue to use the manual GitHub Release path that was already planned.

## Standard Release Path

1. Update `pyproject.toml` to the new version.
2. Update `CHANGELOG.md` with release notes for the same version.
3. Merge the release change to `main`.
4. Tag the release from `main`:

   ```bash
   git switch main
   git pull --ff-only origin main
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

5. Let the `Release` GitHub Actions workflow complete.

The release workflow validates that the pushed tag exactly matches the
`pyproject.toml` version. For example, `version = "1.0.3"` must be released
with the `v1.0.3` tag.

## What the Workflow Does

On a `v*` tag push, `.github/workflows/release.yml`:

1. validates the tag and package version;
2. runs the test suite on Python 3.11, 3.12, and 3.13;
3. builds the source distribution and wheel;
4. runs `twine check`;
5. installs the built wheel and runs the CLI smoke check;
6. publishes the distributions to PyPI through the `pypi` environment.

GitHub Releases are intentionally maintained manually. After PyPI succeeds,
write the GitHub Release notes from the accepted changelog/release body and
publish the GitHub Release by hand. This keeps human-facing release notes from
being replaced by generated compare-link notes.

## Manual PyPI Fallback

`.github/workflows/publish-pypi.yml` is a manual fallback only. It is not part of
the standard release path and does not listen to `release.published`.

Use it only if a maintainer needs to retry PyPI publishing for a version that
has already been validated. The manual input version must match
`pyproject.toml`, and the workflow must run from `main`.

## Zenodo

Zenodo should archive the manually published GitHub Release. Before pushing the
tag, confirm that:

- the version in `pyproject.toml`, `CHANGELOG.md`, `CITATION.cff`, and the tag
  agree where applicable;
- `.zenodo.json` does not hard-code a stale release version;
- release notes describe the public package changes;
- no private reference content is included in the software release archive.

If release metadata must be corrected after publication, edit metadata in
Zenodo/GitHub rather than replacing already-published release files. Confirm
the Zenodo record displays the release tag version after publication. If archive
content changes, publish a new version.
