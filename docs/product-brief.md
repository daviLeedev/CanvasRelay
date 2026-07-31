# CanvasRelay Product Brief

**English** | [한국어](ko/product-brief.md)

| Field | Value |
| --- | --- |
| Status | Draft |
| Audience | Product reviewers, senior engineers, contributors |
| Last updated | 2026-07-31 |

## Product Summary

CanvasRelay is a local-first AI media orchestration studio for creating, editing,
tracking, and reusing image and video assets across local and cloud providers.

It is not a gallery of model-specific forms. The product normalizes different
generation engines behind one observable job lifecycle and gives creators a
consistent workspace for references, prompts, progress, results, provenance,
and reuse.

## Problem

AI media workflows are fragmented across provider websites, local inference
servers, model-specific controls, temporary download folders, and one-off
scripts. This creates recurring problems:

- Every provider exposes a different request and status model.
- Long-running jobs are difficult to observe, cancel, retry, and compare.
- Prompt, model, reference, and parameter provenance is easily lost.
- Results become disconnected files instead of reusable production assets.
- Local tools often expose implementation details instead of a coherent user
  workflow.

## Product Positioning

> A production console for routing creative intent through heterogeneous AI
> media engines without losing operational visibility or asset provenance.

CanvasRelay should demonstrate more than model integration. It should show how
a frontend and backend cooperate around asynchronous work, typed contracts,
failure recovery, media lifecycle management, and progressive enhancement.

## Target Users

### Primary

- A creator running local image or video models who wants one reliable studio.
- A technical artist comparing providers, presets, and references.
- A developer evaluating how to integrate long-running AI jobs into a product.

### Portfolio Reviewer

A senior engineer is also an intentional audience. The repository should answer
their questions at four levels:

| Review time | The repository should answer |
| --- | --- |
| 30 seconds | What problem does this solve, and what does it look like? |
| 5 minutes | Can I run a meaningful workflow without credentials or a GPU? |
| 20 minutes | Are UI, domain, provider, and persistence responsibilities separated? |
| 60 minutes | Are tradeoffs, tests, failure behavior, and migration decisions credible? |

## Jobs To Be Done

1. When I have a prompt and optional references, I want to create an image or
   video without learning a different interface for every provider.
2. When generation takes several minutes, I want to know whether it is queued,
   executing, stalled, completed, or failed.
3. When a result is useful, I want to understand exactly how it was produced
   and reuse it as an input to another operation.
4. When a provider is unavailable, I want an actionable error without losing
   my inputs or destabilizing the rest of the studio.
5. When I evaluate the project, I want a deterministic demo that does not
   require paid credentials, proprietary models, or a high-end GPU.

## Core Product Areas

### Image Workspace

- Text-to-image and image-to-image operations.
- Prompt, negative prompt, references, provider, preset, and advanced controls.
- A large, uncropped result stage with compare and reuse actions.
- Mock and optional ComfyUI provider support.

### Video Workspace

- Image-to-video operation with duration, frame, motion, and quality controls.
- Clear queue, execution, encoding, and completion states.
- Video preview, metadata, retry, and reuse actions.

### Job Center

- Unified queued, running, completed, failed, and cancelled states.
- Progress based on provider events when available.
- Cancellation for queued jobs and best-effort interruption for active jobs.
- Retry from an immutable snapshot of the original request.

### Media Library

- Image and video filters, responsive density, and detail inspection.
- Prompt, references, provider, model, parameters, timestamps, and file origin.
- Reuse as image input, video input, or a new editable request.
- A practical 2D grid with an optional spatial compare mode.

### Prompt Copilot

- Produces a new prompt and negative prompt from the current creative intent.
- Uses a provider adapter and never exposes credentials to the browser.
- Is an assistant to the workflow, not a hidden dependency for generation.

### System Status

- API, provider, storage, and optional inference-server readiness.
- Redacted authentication status and actionable recent errors.
- No raw token, secret, or personal filesystem path in UI responses.

## Immersive 3D Experience

The 3D layer must communicate product state rather than decorate the screen.

- The generation stage can project references, active processing, and results
  as interactive media planes.
- The pipeline view can map Prompt -> Provider -> Job -> Asset transitions.
- Spatial compare can arrange multiple outputs for selection and inspection.
- Forms, metadata, logs, and destructive actions remain accessible DOM UI.
- A complete 2D fallback remains available on unsupported or constrained
  devices.

The first screen is the usable studio, not a marketing landing page.

## Product Principles

1. **Operational clarity over spectacle.** Motion and depth must explain state.
2. **Progressive disclosure.** Common controls are immediate; provider-specific
   parameters are available without dominating the workflow.
3. **Local-first and provider-neutral.** The product runs in mock mode and can
   attach local or cloud providers through explicit adapters.
4. **Provenance by default.** Every asset can explain which request produced it.
5. **Failure is a first-class state.** Inputs remain recoverable and errors lead
   to a next action.
6. **Accessible core workflow.** 3D, motion, and advanced hardware are optional.
7. **Honest capability.** The public project advertises only implemented and
   verifiable provider integrations.

## Public Portfolio Scope

### In Scope

- Next.js and TypeScript web application.
- FastAPI orchestration API.
- First-class deterministic mock provider.
- Optional ComfyUI adapter with documented setup.
- Image generation, image editing, image-to-video, job center, and library.
- Functional 3D generation stage and spatial comparison.
- Typed API contracts, tests, CI, and architecture documentation.

### Explicit Non-Goals For The First Public Release

- Migrating every private workflow or model preset.
- Shipping model weights, generated private media, or provider credentials.
- Reproducing every control from the legacy interface before release.
- Building a general node editor or replacing ComfyUI.
- Claiming support for providers that cannot be tested through documented APIs.
- Making the 3D scene mandatory for completing a workflow.

## Demo Strategy

`DEMO_MODE=true` is a supported product mode, not a screenshot-only facade.

- It creates deterministic queued, running, and completed jobs.
- It can intentionally produce typed failures for recovery demonstrations.
- It serves a curated set of safe example assets and metadata.
- It supports cancel, retry, filter, detail, and reuse flows.
- It requires no account, secret, model file, or GPU.

## Success Measures

### User Experience

- A first-time user can create and locate a mock result without instructions.
- Job status always distinguishes queued, executing, and unknown progress.
- The last submitted prompt and selected result survive non-destructive refreshes.
- Core workflows remain usable at desktop, tablet, and mobile breakpoints.

### Engineering Quality

- Web types are generated from or checked against the API contract.
- Provider-specific response parsing cannot leak unhandled exceptions to users.
- Core domain tests cover job transitions, cancellation, retry, and provenance.
- End-to-end tests cover one image and one video workflow in demo mode.
- CI performs formatting, linting, type checking, tests, build, and secret scans.

### Performance And Accessibility

- The application shell and primary controls do not wait for the 3D bundle.
- The 3D renderer pauses when hidden or idle and releases unused textures.
- Reduced-motion and 2D fallback modes preserve all required actions.
- Keyboard focus, labels, status announcements, and error messages work without
  interacting with the WebGL canvas.

## Release Definition

The first portfolio release is complete when a reviewer can clone the
repository, start demo mode with documented commands, submit an image job,
observe its lifecycle, inspect the resulting asset and provenance, reuse it in
a video request, and run the automated checks without private dependencies.
