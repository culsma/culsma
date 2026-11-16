# Culsma Reference

This repository is the standalone home for the public language reference of
Culsma.

It is intentionally separate from:

- the public reference implementation and CLI release boundary
- `culsma-docs/`: public docs portal and onboarding material
- `culsma-site/`: `culsma.com` homepage
- `papers/arxiv_v1/`: manuscript workspace
- internal theory, spec, module, and implementation planning workspaces

## Purpose

The role of this repository is:

1. hold the current source-level language reference
2. track implementation conformance against the public reference
3. remove stale legacy terminology that can mislead readers and AI tooling

## Local Preview

This repository also includes a VitePress layer so the reference can be browsed
like the public docs portal.

```bash
npm install
npm run dev
```

Build static output:

```bash
npm run build
```

## Public Site

The browsable language reference will use the canonical address
[reference.culsma.dev](https://reference.culsma.dev/). It is deployed as a
separate Cloudflare Pages project and linked from the main documentation at
[culsma.dev](https://culsma.dev/).

See [deploy-cloudflare.md](deploy-cloudflare.md) for the deployment boundary,
build settings, and publication checklist.

## Release and Citation

The public reference snapshot is versioned independently from executable
software releases. Snapshot `2026.0908`, dated 2026-09-08, consolidates accepted
updates aligned with Culsma 1.0.6. Citation, package, and index metadata are
aligned. Zenodo publication remains a separate, explicitly reviewed step.

For DOI archival, publish a curated reference snapshot rather than the full
authoring workspace. The snapshot should include:

- the public reference chapters
- the generated static site
- `README.md`
- `LICENSE`
- `CITATION.cff`
- `THIRD_PARTY_NOTICES.md`

The snapshot should exclude review trackers, release work plans, draft
appendices, dependency directories, build caches, and Git history.

Reference documentation is licensed under CC-BY-4.0. Third-party assets retain
their own licenses as listed in `THIRD_PARTY_NOTICES.md`.

## Scope

This repository contains the current imported reference set from the root
workspace `docs/reference/`.

Current files include:

- notation
- lexical structure
- source files
- names and bindings
- operation vocabulary
- operational semantics
- validation and diagnostics
- execution model
- configuration and modes
- type and units
- conformance and test mapping
- scientific-model extension contracts and modular provider specifications

Files outside this public reference snapshot may remain in the authoring
workspace as review aids, draft appendices, or future reference material. They
are not part of the DOI-ready public baseline unless listed above or included
in a tagged curated snapshot.

## Maintenance Notes

### Zenodo archive preparation

Run **Prepare Zenodo reference draft** from GitHub Actions with the repository
secret `ZENODO_TOKEN` (`deposit:write` and `deposit:actions`). Updating its
workflow on `main` also triggers preparation. Ordinary website updates
do not trigger archival. The workflow uploads a curated, checksum-verified ZIP
to the designated unpublished draft in concept DOI `10.5281/zenodo.20059696`.
Existing Zenodo creators and contributors are inherited. The run summary links
to the draft. For this release, only trial draft `22665596` may be updated via
`--update-draft 22665596`; its series, unpublished status and version are checked.
The replacement ZIP is uploaded and verified before old draft attachments are
removed. Other drafts are not modified. No publish API is called.

Validate packaging locally after `npm run build` with
`python3 scripts/zenodo_draft.py` (no credentials or network required).

1. Keep the public reference pages aligned with accepted language semantics.
2. Treat review aids, draft appendices, and future reference material as
   authoring-workspace content unless they are explicitly promoted into a
   tagged public snapshot.
3. Update `CITATION.cff` and package metadata together for each public
   reference snapshot.
