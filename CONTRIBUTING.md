# Contributing

The Makefile workflow is supported on POSIX environments with Git, `make`, a
POSIX shell, and uv. CI runs on Ubuntu.

## Development Workflow

1. Create a short-lived branch from `main`.
2. Make the smallest change that satisfies the task.
3. Add or update tests for behavioral changes.
4. Run `make verify`.
5. Open a pull request and wait for CI to pass.

Use branch names such as `feat/<name>`, `fix/<name>`, and `chore/<name>`.
Use conventional commit prefixes: `feat`, `fix`, `chore`, `test`, `docs`,
`refactor`.

## Agent Rules

Agents must inspect the current repository and Git state before editing. They
must not overwrite unrelated work, commit secrets, or use destructive Git
commands. They must report changed files, verification commands, and any
limitations when completing a task.

Agents must not add product functionality during Stage 0. In particular, shell
command planning, execution, approval, risk classification, diagnosis, and
repair behavior are future stages.

Significant architectural decisions belong in `docs/adr/`.
