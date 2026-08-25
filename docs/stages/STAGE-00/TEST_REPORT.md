# Stage 0 Test Report

## Scope

Stage 0 intentionally has one test. It imports the installed package and
asserts that its module documentation is present. This is an importability and
packaging smoke test, not a product test.

The small test count is correct for this stage. There are no command planners,
risk policies, executors, or diagnosis rules to test yet.

## Verification Commands

The following commands were run successfully:

```text
make test
make lint
make typecheck
make verify
make coverage
uv lock --check
```

`make verify` ran these mandatory checks together:

```text
format-check
ruff check
mypy
pytest
pip-audit
pre-commit
artifact build and isolated wheel import
```

The test result was one test passed. Strict Mypy reported no issues, Ruff
reported no violations, and all configured pre-commit hooks passed during the
explicit bootstrap hook run. Coverage
reported 100 percent for the current module; the module has no executable
statements beyond its documentation string, so this number must not be
interpreted as product coverage.

The dependency audit reported no known vulnerabilities. The local project is
not published on PyPI, so `pip-audit` reports it as skipped while auditing the
resolved third-party packages.

The artifact check built both the source distribution and wheel, installed the
wheel into an isolated temporary environment outside the checkout, and imported
`terminal_intelligence`. This verifies the distributable package rather than
only the editable development installation.

CI additionally runs the same verification gate for Python 3.12, 3.13, and
3.14. The local environment used for this report was Python 3.12.

## Evidence and Limits

These results show that the repository can be installed, imported, checked, and
tested consistently. They do not show that the eventual terminal workflow is
safe, because no workflow exists in Stage 0. Safety claims require later tests
for approval, command boundaries, execution controls, captured output, and
failure handling.
