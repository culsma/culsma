# Culsma Docs Layout

Last updated: 2026-04-30

## Purpose

This directory is the lightweight implementation-design documentation layer for
the Culsma repository.

It is not the language reference manual, a user manual, a release workspace, or
a code-reading notebook. The public language reference is maintained in the
companion `culsma-reference` repository/worktree.

## Structure

```text
docs/
  README.md
  architecture/
  assets/
```

## Directory Rules

| Directory | What goes here | What does not go here |
| --- | --- | --- |
| `architecture/` | current implementation structure, module boundaries, pipeline maps, and design diagrams | temporary refactor notes, reading plans, release checklists |
| `assets/` | repository logo and wordmark assets used by public docs | generated scratch images or temporary diagrams |

## Current Architecture Notes

- [parser_module_diagrams.md](architecture/parser_module_diagrams.md)
- [ir_structure_diagrams.md](architecture/ir_structure_diagrams.md)
- [compile_module_diagrams.md](architecture/compile_module_diagrams.md)
- [validate_module_diagrams.md](architecture/validate_module_diagrams.md)
- [typecheck_module_diagrams.md](architecture/typecheck_module_diagrams.md)
- [plan_module_diagrams.md](architecture/plan_module_diagrams.md)
- [runtime_module_diagrams.md](architecture/runtime_module_diagrams.md)
- [driver_module_diagrams.md](architecture/driver_module_diagrams.md)

Release notes belong in the repository changelog and GitHub Releases, not in
this `docs/` tree.
