# Support Policy

This repository is a public open-source reference implementation of the current
Culsma language and execution stack.

## Scope of Maintainer Review

Maintainer review is limited to narrowly scoped, reproducible defects in the
current public baseline, such as:

- parser or frontend regressions on current public source forms
- validation or typecheck regressions against current public contracts
- plan, runtime, replay, or artifact regressions in released public examples
- packaging or release breakage in the published CLI surface

Review is discretionary and no response-time commitment is provided.

## Out of Scope

The public issue tracker is not a general support channel. The following are
normally out of scope:

- usage questions already covered by the public docs or reference
- requests for custom integration or workflow adaptation
- broad feature requests or roadmap discussions
- support for private forks or local modifications
- requests to prioritize one research or product direction over another

## Before Opening an Issue

Before opening an issue, check:

1. the public docs
2. the public reference
3. the current changelog or GitHub Release notes
4. whether the problem reproduces on the current public baseline

## What Makes a Bug Report Actionable

Actionable reports should include:

- the exact command or input file used
- the current version or commit/tag tested
- the observed behavior
- the expected behavior
- a minimal reproduction when possible

If a report cannot be reproduced from the submitted information, it may be
closed without further action.
