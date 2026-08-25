# Agent Development Rules

These rules apply to every coding agent working in this repository.

## Architecture Boundaries

Stage 0 provides repository infrastructure only. Do not implement command
planning, risk classification, approval, shell execution, output capture,
verification, diagnosis, or repair behavior.

The intended future package boundaries are:

- `domain/`: framework-independent models, rules, and errors.
- `application/`: use cases and orchestration.
- `ports/`: interfaces between the application and external systems.
- `adapters/`: shell, process, model, and persistence integrations.
- `cli/`: terminal input and presentation.

Dependencies should point inward. The domain must not depend on adapters or the
CLI. Adapters implement ports rather than becoming application-level APIs.

Agents must not silently alter these boundaries, introduce a new architectural
layer, or move responsibilities between layers. Architectural changes require
explicit approval and an ADR under `docs/adr/`.

## Coding Conventions

- Target Python 3.12 or newer.
- Use the `src/` layout and import the package as `terminal_intelligence`.
- Keep runtime dependencies at zero in Stage 0. Adding a runtime dependency
  requires explicit user or repository-owner approval.
- Use Ruff for formatting and linting.
- Keep code compatible with strict Mypy checking.
- Annotate functions and public attributes.
- Prefer small, explicit functions and standard-library types.
- Tools may create ignored, ephemeral caches and build output while verifying a
  change. Do not manually modify or commit those artifacts, credentials, or
  local environment files.

Run `make verify` before reporting work as complete.

## Testing Requirements

- All new behavior requires tests in the same change.
- Use Pytest and mirror source responsibilities under `tests/`.
- Keep unit tests deterministic, offline, and free of destructive operations.
- Do not execute real user shell commands in unit tests.
- Use fakes or controlled temporary fixtures for future external boundaries.
- Add integration tests only when a real boundary must be validated.

Stage 0 should contain infrastructure and importability tests only.

## Files Agents May Change

Agents may change files directly relevant to the task in these areas:

- `src/**`
- `tests/**`
- `pyproject.toml`, `uv.lock`, and `Makefile`
- `.pre-commit-config.yaml`, `.editorconfig`, and `.gitignore`
- `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, and `docs/**`
- `.github/workflows/**`

The following changes require explicit approval from the user or repository
owner before editing:

- `AGENTS.md` itself;
- `.github/workflows/**` and other CI policy;
- runtime dependencies or build-system requirements in `pyproject.toml`;
- package boundaries, dependency direction, or new architectural layers.

An ADR records an approved architectural decision; an ADR by itself does not
grant approval. Development-only tooling changes remain subject to the normal
task scope and verification requirements.

Agents must not modify `.venv/`, caches, build output, secrets, or unrelated
user changes. When a required change falls outside the allowed areas or needs
protected approval, stop and request approval rather than silently expanding
the architecture or repository scope.

## Change Discipline

Inspect the current worktree before editing. Make the smallest correct change,
preserve unrelated work, and report changed files plus verification results.
Never use destructive Git commands such as `git reset --hard` or
`git checkout --`.
