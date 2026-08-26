# Terminal Intelligence Layer

Terminal Intelligence will provide a safe workflow for turning natural-language
terminal requests into approved, verified command execution.

This repository contains the Stage 0 engineering foundation, Stage 1 immutable
domain models, and Stage 2 deterministic direct-argv command execution. LLM
integration, planning, safety policy, UI, verification, diagnosis, repair, and
persistence remain future stages.

## Development

The documented Makefile workflow assumes Git, `make`, a POSIX shell, and uv.
CI runs on Ubuntu. Windows users should use a POSIX-compatible environment
such as WSL, or invoke the underlying `uv` commands directly.

Install the locked development environment:

```text
make setup
```

`make setup` fails if `pyproject.toml` and `uv.lock` disagree. Update
dependencies intentionally with `make lock`, review the resulting lockfile,
and then run verification again.

Run the complete verification suite:

```text
make verify
```

Install the repository's Git hooks locally:

```text
make install-hooks
```

Individual commands are documented in the `Makefile`.

The supported interpreter range is Python 3.12 through 3.14. CI verifies each
supported minor version.
