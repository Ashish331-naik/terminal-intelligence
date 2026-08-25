# Stage 0 Decisions

This document summarizes the decisions that shape the foundation. The formal
architecture decision is recorded in `docs/adr/0001-stage-0-foundation.md`.

## Use Python 3.12+

Python is the project language and 3.12 is the minimum supported version. A
single modern baseline avoids compatibility branches while the project is small
and gives the team current typing and standard-library features. Supporting
older Python versions would increase CI and annotation complexity without a
Stage 0 requirement.

## Use a `src/` Package Layout

Source code is separated from repository tooling and tests. This prevents a
test from passing merely because Python found a source directory on the current
working directory path. Installation must work before imports work, which is
the same contract users and future packaging systems will rely on.

## Keep Runtime Dependencies Empty

The foundation does not need a framework or service client. An empty runtime
dependency set lowers supply-chain risk and keeps the architecture independent
of vendors. Development tools are still dependencies of the development
environment, but they are not shipped to users.

## Use `uv` and Commit the Lockfile

`uv` provides fast environment creation, dependency resolution, and lockfile
management. The lockfile makes CI and local development resolve the same
versions. Setup and execution use locked mode; dependency changes require the
explicit `make lock` operation. Without this separation, a verification command
could repair drift and hide a stale lockfile.

## Use Hatchling for Builds

Hatchling is a small, standards-based PEP 517 backend. It avoids custom build
logic and keeps packaging concerns in `pyproject.toml`.

## Use Ruff, Mypy, Pytest, and Coverage

Ruff catches style, import, and common correctness issues while also formatting
code. Mypy catches type-contract errors before runtime. Pytest provides a
simple, standard test model. `pytest-cov` makes coverage visible without
pretending that a percentage alone proves safety.

Together they cover different failure classes rather than duplicating one
check several times.

## Use Pre-Commit and CI

Pre-commit gives fast feedback at the contributor boundary. CI is still
required because local hooks can be bypassed and local environments differ.
The Makefile is the shared interface, and both CI and pull-request guidance use
`make verify` so they cannot silently omit the audit or hook checks.

## Make Future Boundaries Explicit

The future `domain`, `application`, `ports`, `adapters`, and `cli` boundaries
are documented before implementation. This prevents an early convenience
module from becoming an accidental architecture. Empty directories are not
created just for appearance; a boundary becomes real when it has reviewed
responsibility and tested behavior.

## Do Not Implement Product Behavior in Stage 0

The cost of delaying a feature is lower than the cost of embedding safety
assumptions in an unreviewed foundation. Command execution in particular must
not exist before approval, risk, output, and failure contracts are designed.
