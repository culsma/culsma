# Culsma Docs Layout

Last updated: 2026-06-18

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
  global_architecture_diagrams.md
  architecture/
    pipeline/
  assets/
```

## Directory Rules

| Directory | What goes here | What does not go here |
| --- | --- | --- |
| `docs/` root | repository-level docs layout and global architecture maps | module-internal architecture diagrams |
| `architecture/` | current module implementation structure, module boundaries, and design diagrams | temporary refactor notes, reading plans, release checklists |
| `architecture/pipeline/` | pipeline-wide, IR, compile, validation, typecheck, and plan-lowering diagrams | parser, runtime, material-compute, or driver diagrams |
| `assets/` | repository logo, wordmark, and affiliation marks used by public docs | generated scratch images or temporary diagrams |

## Global Architecture

- [global_architecture_diagrams.md](global_architecture_diagrams.md)

## Current Module Architecture Notes

- [pipeline_module_diagrams.md](architecture/pipeline/pipeline_module_diagrams.md)
- [parser_module_diagrams.md](architecture/parser_module_diagrams.md)
- [ir_structure_diagrams.md](architecture/pipeline/ir_structure_diagrams.md)
- [compile_module_diagrams.md](architecture/pipeline/compile_module_diagrams.md)
- [validate_module_diagrams.md](architecture/pipeline/validate_module_diagrams.md)
- [typecheck_module_diagrams.md](architecture/pipeline/typecheck_module_diagrams.md)
- [plan_module_diagrams.md](architecture/pipeline/plan_module_diagrams.md)
- [scope_module_diagrams.md](architecture/pipeline/scope_module_diagrams.md)
- [runtime_module_diagrams.md](architecture/runtime_module_diagrams.md)
- [material_compute_module_diagrams.md](architecture/material_compute_module_diagrams.md)
- [driver_module_diagrams.md](architecture/driver_module_diagrams.md)

Release notes belong in the repository changelog and GitHub Releases, not in
this `docs/` tree.
