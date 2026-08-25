# Stage 0 Failures and Fixes

The foundation was built and verified incrementally. Recording failures is
useful because it shows how the final design responds to evidence rather than
only documenting the successful end state.

## Vulnerable Pytest Resolution

The first dependency range constrained pytest to `<9`. The resolver selected
pytest 8.4.2, and `pip-audit` reported `PYSEC-2026-1845`, with pytest 9.0.3 as a
fixed version.

The fix was to widen the development constraint to `pytest>=8.3,<10`, explicitly
upgrade the locked pytest package, and regenerate the lockfile. The final
environment resolved pytest 9.1.1 and the audit reported no known
vulnerabilities.

The lesson is that a version range is not the same as a security policy. A
reasonable-looking upper bound can prevent the resolver from selecting a
security fix. Auditing the resolved environment is therefore part of
verification, not an optional afterthought.

## Pre-Commit Could Not Run Without Git

The workspace initially contained no Git repository. Pre-commit relies on Git
to discover files, so the first `make verify` attempt failed before running its
hooks.

The local repository was initialized on the `main` branch. No commit was
created by the implementation process. This is consistent with the documented
workflow while making the repository capable of running its own hooks.

## Pre-Commit Skipped an Empty Index

After Git initialization, `pre-commit run --all-files` completed but skipped
the hooks because the new files were untracked. That result was technically
successful but weak evidence: skipped hooks had not validated the files.

The permanent fix was to keep the Makefile on pre-commit's filename-safe
`--all-files` mode rather than introduce shell word splitting. The normal Git
workflow tracks files before pull-request verification. During bootstrap, the
hooks were run explicitly with `pre-commit run --files ...`, and all passed.

This is a useful distinction between a command exiting zero and a verification
actually exercising the intended inputs. It also avoids mishandling filenames
containing spaces, glob characters, or newlines.

## No Product Failures Were Tested

There are no failures involving command execution, permissions, risk, approval,
or repair because those behaviors are prohibited in Stage 0. Treating the
absence of those tests as a gap would encourage scope expansion. They belong in
later stage-specific test reports after their contracts have been approved.
