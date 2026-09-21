# Versioned benchmark coverage snapshots

Each JSON file in this directory is an immutable release summary generated from
the case-local source.md, protocol.culs, and coverage.json files. A snapshot
records the benchmark revision separately from the Culsma language version.

The summary keeps two results separate:

- **Step correspondence** is the automatic matched/total check.
- **Open language gaps** are reviewer-approved
  `// Language gap S<n>: ...` declarations next to the affected code. They
  identify language capability still missing even when a source step has a code
  region.

Generate a new snapshot only after every case record has been regenerated with
one language version and implementation revision:

```sh
python benchmarks/tools/build_coverage_snapshot.py \
  --cases-root benchmarks/modules \
  --benchmark-version modules-2026.09.1 \
  --benchmark-revision FULL_BENCHMARK_COMMIT \
  --released-at 2026-09-16 \
  --previous benchmarks/releases/modules-2026.08.1.json \
  --out benchmarks/releases/modules-2026.09.1.json
```

The generator rejects stale hashes and mixed implementation versions. It
compares only cases whose source hash is unchanged. Changed source material is
reported as source-changed, because its percentage is not a language-version
improvement. Do not overwrite a snapshot; publish a new version.
