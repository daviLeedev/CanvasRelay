# ADR 0001: Next.js And FastAPI In A Monorepo

**English** | [한국어](../ko/adr/0001-nextjs-fastapi-monorepo.md)

| Field | Value |
| --- | --- |
| Status | Proposed |
| Date | 2026-07-31 |
| Decision owners | CanvasRelay maintainers |

## Context

The private predecessor to CanvasRelay is a Python FastAPI application that
serves one large Jinja2 template, a large vanilla JavaScript client, and a large
global stylesheet. It successfully integrates local inference, long-running
jobs, media persistence, and external providers, but the frontend has reached a
scale where state ownership and feature boundaries are difficult to reason
about.

The public portfolio version must:

- Demonstrate current React and TypeScript engineering practices.
- Preserve Python-based orchestration and the existing local AI ecosystem.
- Make frontend and backend changes reviewable together.
- Offer a credential-free, GPU-free demo.
- Support a functional Three.js experience without making WebGL mandatory.
- Avoid importing private Git history, workflows, assets, or configuration.

## Decision

CanvasRelay will use a monorepo containing:

- A Next.js App Router web application written in TypeScript.
- A FastAPI orchestration API written in Python.
- OpenAPI-derived TypeScript contracts checked in CI.
- React Three Fiber as a client-only progressive enhancement for spatial work.
- A deterministic mock provider as a first-class runtime profile.

The browser will call FastAPI for all domain operations. Next.js route handlers
will not duplicate generation orchestration or hold provider credentials.

The initial repository shape is:

```text
apps/web        Next.js UI and immersive scenes
apps/api        FastAPI domain, services, providers, repositories
packages/contracts
docs
```

## Decision Drivers

1. The portfolio should visibly demonstrate React, TypeScript, routing, state
   management, responsive interaction, and testing.
2. Python remains the strongest fit for ComfyUI integration, media processing,
   and the existing orchestration logic.
3. A monorepo makes cross-contract changes atomic and easier for a reviewer to
   discover.
4. App Router provides layouts, route-level loading and error boundaries, and a
   clear path for a public project page while allowing client-heavy workspaces.
5. The 3D scene needs React lifecycle integration and must remain isolated from
   server rendering and domain state.
6. The public project must run without private infrastructure.

## Detailed Decisions

### Next.js Is The Web Framework

The application will use App Router and TypeScript. Interactive studio routes
will primarily use client components where browser APIs and immediate input are
required. Server components are used only where they reduce client work or
clarify data ownership.

Next.js is not selected because the studio requires SEO or server rendering.
It is selected for project structure, routing, production conventions, and its
value as a recognizable React framework in a portfolio.

### FastAPI Remains The Domain Boundary

FastAPI owns:

- Provider credentials and capability discovery.
- Upload validation and media storage.
- Job lifecycle, cancellation, retry, and progress normalization.
- Provider request and response translation.
- Persistence and structured operational logging.

No inference or provider orchestration is rewritten in Node.js merely to place
it inside the Next.js process.

### The Repository Is A Monorepo

Web and API code share one review and one documented release. The monorepo does
not imply one runtime process. Web and API remain separately buildable and can
be deployed or started independently.

### OpenAPI Is The Contract Source

Pydantic request and response models produce OpenAPI. TypeScript types and the
browser client are generated from that contract. CI fails when generated output
is stale.

Shared hand-written TypeScript/Python domain models are avoided because they
create two competing sources of truth.

### 3D Is A Progressive Client Feature

React Three Fiber wraps Three.js scene lifecycle inside React. The scene is
dynamically loaded in the browser, receives a projection of domain state, and
emits semantic commands such as `selectAsset` or `focusJob`.

The WebGL scene does not own jobs, requests, media metadata, or destructive
actions. Every required workflow remains available through accessible DOM UI.

### Demo Mode Is A Product Profile

The mock provider implements the same provider contract as real adapters. It
supports deterministic progress, success, failure, cancellation, retry, and
sample media. Automated end-to-end tests run against this profile.

## Alternatives Considered

### Keep FastAPI, Jinja2, And Vanilla JavaScript

**Advantages**

- Lowest migration effort.
- One runtime and no frontend build tool.
- Existing behavior remains intact.

**Rejected because**

- It does not address frontend state ownership or component boundaries.
- The portfolio would not demonstrate the target React and TypeScript skills.
- Adding a complex state-driven 3D workspace would increase global coupling.

### React With Vite And FastAPI

**Advantages**

- Smaller client toolchain.
- Natural fit for a client-heavy local dashboard.
- Simple static deployment.

**Not selected because**

- CanvasRelay also needs a structured public project surface, nested layouts,
  and explicit route-level loading and error conventions.
- Next.js is a deliberate portfolio signal while still supporting client-only
  rendering for the studio.

Vite remains a valid fallback if Next.js complexity stops providing value.

### Move The Entire Backend Into Next.js

**Advantages**

- One language and potentially one deployment artifact.
- Direct use of Next.js route handlers.

**Rejected because**

- It discards mature Python integration and tests without product benefit.
- AI workflow and media tooling are already Python-oriented.
- Local inference orchestration should not be coupled to the web renderer.

### Separate Web And API Repositories

**Advantages**

- Independent ownership and release cadence.
- Smaller individual repositories.

**Rejected for the portfolio phase because**

- Cross-contract changes become harder to review atomically.
- Setup and discovery are worse for a reviewer evaluating one project.
- The current team and release process do not require repository-level
  separation.

### Direct Three.js Without React Three Fiber

**Advantages**

- Full imperative control and no renderer abstraction.
- Easier reuse of standalone Three.js examples.

**Rejected because**

- Manual scene lifecycle would sit beside React lifecycle and invite duplicate
  state ownership.
- React Three Fiber better supports component composition and cleanup within the
  selected frontend architecture.

## Consequences

### Positive

- The public repository demonstrates modern frontend and Python backend work.
- Web and API contracts can change atomically.
- Provider adapters remain isolated from presentation concerns.
- The 3D experience can be ambitious without controlling the whole product.
- Demo mode makes review and CI deterministic.
- The private application can continue operating during vertical migration.

### Negative

- Contributors need both Node.js and Python toolchains.
- Local development runs at least two application processes.
- OpenAPI generation adds a required synchronization step.
- Next.js can add framework complexity to client-heavy screens.
- Three.js increases bundle, GPU, testing, and accessibility responsibilities.
- A monorepo requires disciplined boundaries to avoid accidental coupling.

### Neutral Or Accepted Tradeoffs

- The web and API may deploy independently even though they share a repository.
- Some legacy UI behavior will be intentionally omitted.
- Server components are not a goal by themselves.
- The first public provider set will be much smaller than the private set.

## Guardrails

- FastAPI is the only public domain API.
- Provider credentials never enter `NEXT_PUBLIC_*` variables.
- The web application imports generated contracts, not Python internals.
- The 3D bundle is route-split and has a tested 2D fallback.
- Real provider support cannot break demo-mode CI.
- Model files, generated private media, logs, and personal paths stay ignored.
- Every migrated slice includes loading, failure, retry, and responsive states.

## Validation

This decision is validated by the first implementation checkpoint:

1. Both applications start from documented commands.
2. The web client consumes typed FastAPI health data.
3. Three mock jobs progress through the same API used by future providers.
4. The jobs render in accessible 2D and in a nonblank interactive 3D stage.
5. CI verifies Python tests, TypeScript types, web tests, build, and contract
   freshness.

If this checkpoint requires duplicated domain state or provider logic in
Next.js, the boundary must be corrected before further migration.

## Review Triggers

Revisit this ADR if:

- Next.js server features remain unused while materially complicating delivery.
- The web and API require independent teams or release histories.
- OpenAPI generation cannot represent required provider schemas cleanly.
- The 3D scene cannot meet fallback, performance, or accessibility requirements.
- A hosted architecture requires durable distributed workers and object storage.

## Status Transition

Change this ADR from `Proposed` to `Accepted` after the architecture checkpoint
passes and before migrating the first real provider.
