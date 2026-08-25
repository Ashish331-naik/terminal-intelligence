# Stage 0 Overview

## Purpose

Stage 0 establishes the engineering foundation for the Terminal Intelligence
Layer. It does not attempt to understand terminal requests or run commands. Its
purpose is to make later product work safe to change, easy to review, and
repeatable on another machine.

The product vision eventually describes this flow:

```text
natural-language request
        -> intent
        -> proposed command
        -> risk and approval
        -> bounded execution
        -> captured result
        -> verification
        -> diagnosis and repair
```

None of those arrows are implemented in Stage 0. Implementing them before the
boundaries and verification process exist would make it difficult to tell
whether a later failure came from product logic or from the repository itself.

## What Stage 0 Establishes

The project is a Python 3.12+ package using the `src/` layout. It can be
installed as `terminal-intelligence` and imported as `terminal_intelligence`.
Runtime dependencies are intentionally empty. Development tools are isolated
and locked with `uv`.

The repository has one infrastructure test that proves the package is
importable. It also has automated formatting, linting, type checking, tests,
dependency auditing, and pre-commit hooks. GitHub Actions runs the same
verification path used by contributors.

## Non-Goals

Stage 0 does not contain:

- natural-language interpretation or model integration;
- command planning, command execution, or output capture;
- risk classification or approval prompts;
- success verification, failure diagnosis, or repair;
- a user-facing CLI;
- production domain models or application use cases.

Keeping these non-goals explicit is an architectural control. A small feature
that appears useful, such as a helper that runs `lsof`, would violate the stage
boundary because it would introduce execution behavior before approval and
safety contracts exist.

## Definition of Done

Stage 0 is complete when a clean checkout can install the locked development
environment and run `make verify` successfully. That command must check code
formatting, lint rules, strict typing, tests, dependency vulnerabilities, and
pre-commit hooks.

The repository must also document how agents contribute, which files they may
change, and how architectural changes are approved. The test suite is expected
to be small at this stage; its small size is evidence that product behavior has
not accidentally been added.

## How to Read the Stage Documentation

Start with `ARCHITECTURE.md` to understand the dependency direction. Read
`IMPLEMENTATION.md` to connect that design to the configuration. Use
`TEST_REPORT.md` for evidence that the foundation works. The remaining
documents explain the decisions, the problems encountered while building the
foundation, and the lessons that should guide the next stage.
