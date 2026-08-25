# Stage 0 Implementation

## Packaging

The Makefile workflow assumes Git, `make`, a POSIX shell, and uv. This
repository currently validates that workflow on Ubuntu in CI; Windows users
need a POSIX-compatible environment such as WSL or must invoke the underlying
uv commands directly.

`pyproject.toml` is the single configuration entry point. Hatchling is the PEP
517 build backend. Using a standard build backend means the package can be
built by modern packaging tools without a legacy `setup.py` or custom build
script.

The project supports Python 3.12 through 3.14 because the project targets
modern typing syntax and explicitly tests each supported minor version. The
distribution name uses hyphens, `terminal-intelligence`, while Python imports
use underscores, `terminal_intelligence`.

The wheel explicitly packages `src/terminal_intelligence`. This avoids relying
on accidental package discovery and makes the package boundary visible in the
build configuration.

## Dependency Management

There are no runtime dependencies. Terminal Intelligence will eventually touch
high-impact system operations, so reducing the initial runtime supply chain is
useful: every future dependency must have a concrete reason and review.

Development dependencies are kept in the `dev` dependency group:

- `pytest` runs tests;
- `pytest-cov` measures test coverage;
- `ruff` formats code and checks lint rules;
- `mypy` performs strict static type checking;
- `pre-commit` runs repository hooks before commits;
- `pip-audit` checks resolved packages for known vulnerabilities.

`uv.lock` records exact resolutions. `make setup` uses `uv sync --locked --dev`
and every `uv run` verification command uses `--locked`, so setup and checks
fail on dependency drift rather than silently rewriting the lockfile. The
separate `make lock` target is the intentional dependency-update operation.

The build backend is constrained to the reviewed exact version
`hatchling==1.27.0`. Build-system packages are resolved by the isolated PEP 517
build environment rather than as application dependencies, so the exact build
constraint is part of the package metadata while `uv.lock` governs the
development environment. The project also requires uv `0.11.16`, and CI
installs that exact uv version.

## Tool Configuration

Pytest discovers tests under `tests/`, reports failures with `-ra`, and rejects
unknown markers. Strict markers prevent a misspelled marker from silently
changing which tests run.

Ruff targets Python 3.12, uses a 100-character line limit, and checks common
bug, style, import, simplification, and upgrade rules. One tool for formatting
and linting reduces disagreement between local formatting and CI formatting.

Mypy checks both `src` and `tests` in strict mode. Strict typing is valuable at
the boundaries that will later connect policy to external mechanisms: an
incorrectly shaped result or an unhandled optional value should be found before
it reaches command execution code.

Coverage configuration enables branch coverage and provides a `make coverage`
report. Stage 0 does not impose an arbitrary percentage threshold because the
package has no product behavior yet; the report is a baseline, not evidence of
feature completeness.

## Pre-Commit Hooks

`.pre-commit-config.yaml` runs standard file hygiene hooks, YAML and TOML
validation, Ruff, and strict Mypy. The hooks are pinned by revision so a future
hook release cannot unexpectedly change local behavior.

The Makefile invokes pre-commit with `--all-files`, which is filename-safe and
does not rely on shell word splitting. This mode is intentionally based on the
Git index: contributors should make the initial repository commit before
relying on the hook as a complete file-set check. During bootstrap, explicit
`pre-commit run --files ...` can validate untracked files without unsafe shell
enumeration.

## Makefile Verification Graph

The intended workflow is:

```text
make verify
    -> format-check
    -> lint
    -> typecheck
    -> test
    -> audit
    -> pre-commit
    -> build and isolated artifact import
```

The individual targets remain useful when iterating on one class of failure.
`make verify` is the release and pull-request gate because it combines all
mandatory checks.

## Continuous Integration

`.github/workflows/ci.yml` tests Python 3.12, 3.13, and 3.14, installs the
pinned uv version, synchronizes with `--locked --dev`, and runs `make verify`.
CI and the contributor workflow therefore use the same mandatory gate. The
artifact step builds both an sdist and wheel, then imports the wheel from a
temporary environment outside the checkout.
