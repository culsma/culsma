# BPL M4: retained CLI binding checks

Copied without modification on 16 November 2026 from
`notes/comparison/verification_2026-11-12/bpl_documented_syntax/` in the
manuscript repository. The original checks used BPL snapshot
`4e505740f5025d59ba655c6c955f83876f753007`. This packaging step did not rerun them.

`m4_let_10.bpl` and `m4_let_20.bpl` declare a local volume and use it in a
transfer. The matching `m4_let_10` and `m4_let_20` entries in `result.json`
record CLI `check`, `validate`, and `lower --target simulation` results:
exit 11 with `SEMANTIC_MISSING_VOLUME`.

`result.json` is the complete original multi-case report, not a filtered or
regenerated result. Other entries belong to the broader original audit.
The original recorder truncated check/validate messages to 220 characters
and failed-lowering messages to 300 characters; these are retained summaries,
not complete terminal logs.

SHA-256 of the unchanged copies:

- `m4_let_10.bpl`: `b611eda5d021a872f97932f355851b2b6d6c43897917dfde417cc78444e05417`
- `m4_let_20.bpl`: `c1dc0d5c2b1d18e1c9a2a5c661d2d01ffe79d7041b5c98f8c7d77ce6bed671e8`
- `result.json`: `c6d2f26f64abbc66e33e9f95166990a4aecfd09abda35b6a692d09465d91cc5f`

The unified replay now runs byte-identical copies in `cases/m4/bpl/` via
`check_bpl_m4.py`, preserving complete CLI messages in the new replay directory.
The original report here remains unchanged.
