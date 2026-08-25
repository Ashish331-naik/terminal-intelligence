# ADR 0001: Stage 0 Repository Foundation

## Status

Accepted

## Decision

Use a `src/`-layout Python package with no runtime dependencies. Use `uv` for
dependency resolution and lockfile management, Ruff for linting and formatting,
Mypy in strict mode for typing, and Pytest for tests.

Keep future product boundaries visible in the package design through domain,
application, ports, adapters, and CLI areas, but do not implement those areas
until their respective stages.

## Rationale

This keeps the initial install surface small, prevents accidental imports from
the repository root, and establishes automated checks before product behavior
is introduced.
