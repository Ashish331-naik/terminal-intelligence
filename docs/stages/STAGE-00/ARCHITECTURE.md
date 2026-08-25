# Stage 0 Architecture

## Architectural Goal

The architecture separates policy from mechanisms before either becomes large.
The future system will need to decide whether a proposed operation is allowed
before an adapter can cause an external effect. That is why the dependency
direction is designed now, even though the packages are not yet populated.

The intended structure is:

```text
src/terminal_intelligence/
    domain/       framework-independent concepts and rules
    application/  use cases and orchestration
    ports/        interfaces owned by the application
    adapters/     shell, process, model, and persistence integrations
    cli/          terminal input and presentation
```

The current implementation contains only `__init__.py`. The directories above
are future responsibilities, not empty promises that already contain product
code. Git does not need empty directories, and creating placeholder modules
would make an empty architecture look like implemented behavior.

## Boundary Responsibilities

The `domain` layer will contain rules and models that do not know how a shell,
LLM, operating system, or terminal UI works. For example, a future risk policy
belongs here if it can be evaluated from domain data alone.

The `application` layer will coordinate use cases. It may ask a port for a
model proposal or an executor, but it owns the workflow rather than directly
constructing an adapter.

The `ports` layer defines the interfaces that the application needs from the
outside world. Defining the interface inward keeps the application from being
designed around a particular shell library or model vendor. Python `Protocol`
types are a good fit when those contracts are introduced.

The `adapters` layer will implement ports. Shell and process integrations belong
there because they are mechanisms with operating-system side effects. Model
and persistence integrations belong there for the same reason: they depend on
external systems and should be replaceable.

The `cli` layer will translate terminal input into application requests and
application results into presentation. It must not become a second application
orchestrator.

The dependency rule is inward:

```text
cli and adapters -> application -> domain
                         ^
                         ports define needed external contracts
```

The exact import graph will be refined when the first behavior is implemented,
but the domain must never import adapters or CLI code. An adapter implements a
port; it does not become a public application API.

## Why `src/` Layout

The package lives under `src/` so tests and tools use the installed package
rather than accidentally importing a same-named directory from the repository
root. This catches packaging errors early. It also makes the import contract
explicit: application code imports `terminal_intelligence`, not files by path.

## Why Stage 0 Has No Runtime Architecture

Adding an executor, planner, or risk classifier now would force decisions about
security and failure semantics before they have been reviewed. Stage 0 instead
provides the place where those decisions can be added with tests and ADRs.
Future work must preserve these boundaries and must not introduce a new layer
without explicit approval and an ADR.
