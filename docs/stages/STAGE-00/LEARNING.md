# Stage 0 Learning Guide

This stage is deliberately more about engineering controls than features. The
following points are the concepts an engineer should be able to defend in an
architecture interview.

## Architecture Is a Dependency Decision

Layers are not valuable because there are many folders. They are valuable when
they control which code is allowed to know about which details. A domain rule
that imports a shell adapter is coupled to an operating system mechanism and is
harder to test. A shell adapter that implements an application-owned port can
be replaced without rewriting the use case.

The important interview statement is: dependencies point inward, and external
mechanisms implement contracts owned by the application or domain boundary.

## A `src/` Layout Tests the Real Package

Python can import local files accidentally when the repository root is on the
module search path. The `src/` layout makes installation part of the test
setup. If packaging metadata is wrong, the importability test exposes it rather
than allowing a false green test caused by the checkout layout.

## Quality Tools Are Complementary

Formatting makes source shape predictable. Linting detects classes of likely
mistakes and inconsistent constructs. Type checking verifies contracts without
executing code. Tests check runtime behavior. Coverage shows which code tests
reach. Dependency auditing checks a different risk surface entirely.

No single tool proves correctness. The verification pipeline is stronger
because these tools catch different classes of defects.

## A Lockfile Is Part of Reproducibility

Declaring `pytest>=8.3` expresses compatibility, not a reproducible install.
`uv.lock` records the selected release and its transitive dependencies. CI uses
`--locked` so dependency drift fails visibly instead of silently changing a
build.

## Small Tests Can Be Correct

Stage 0 has one importability test because it has one behavior: the package
foundation is importable. Adding artificial tests to increase a coverage number
would create noise. When Stage 1 adds domain behavior, tests should mirror that
behavior and grow with the actual risk.

## Boundaries Matter More for Safety-Critical Features

The future product can cause operating-system side effects. The planner must
not bypass approval, and the executor must not decide policy by itself. Keeping
those responsibilities separate allows approval and risk rules to be tested as
policy and execution to be tested as a controlled mechanism.

Stage 0 does not solve that safety problem. It creates the discipline needed to
solve it deliberately later.

## Verification Must Be Honest

The pre-commit issue demonstrated that a passing command can do no useful work
if its input set is empty. Verification design must ask not only "did the
command exit zero?" but also "did it inspect the files and behaviors that
matter?" The repository uses pre-commit's safe `--all-files` mode after files
are tracked and documents the bootstrap limitation instead of adding unsafe
shell filename handling.

## How to Defend the Scope

A concise defense of Stage 0 is:

> We established a standard, reproducible Python package and an automated
> quality gate before introducing side-effecting behavior. The package has no
> runtime dependencies and only an importability test because product behavior
> is intentionally deferred. Future layers and dependency direction are
> documented, and architectural changes require review and an ADR.
