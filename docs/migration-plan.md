# CanvasRelay Migration Plan

**English** | [한국어](ko/migration-plan.md)

| Field | Value |
| --- | --- |
| Status | Draft |
| Strategy | Clean public repository, vertical slices, parallel legacy runtime |
| Last updated | 2026-07-31 |

## 1. Objective

Migrate the proven product behavior of the private local studio into a public,
reviewable Next.js and FastAPI monorepo without copying private data, secrets,
provider workarounds, model files, or the legacy frontend structure.

The target is not line-for-line parity. The target is a smaller, coherent,
executable portfolio product that demonstrates the hardest engineering work.

## 2. Source Baseline

At planning time, the private application contains:

- A FastAPI backend serving Jinja2 templates and static assets.
- One Jinja2 page of approximately 2,649 lines.
- One main vanilla JavaScript file of approximately 9,141 lines.
- A stylesheet of approximately 5,144 lines.
- Approximately 50 FastAPI route declarations.
- 46 test files and a large set of private model workflows.
- Local logs, media, user configuration, and machine-specific paths that must
  not enter the public repository.

These counts describe migration risk. They are not targets to reproduce.

## 3. Migration Principles

1. **Clean-room public history.** Copy reviewed concepts and generic code only.
2. **Vertical slices.** Finish one useful workflow across UI, API, persistence,
   and tests before starting another.
3. **Strangler migration.** Keep the private application usable until public
   slices reach acceptance criteria.
4. **Contract first.** Stabilize normalized API schemas before moving UI logic.
5. **Mock first.** Every slice works in deterministic demo mode before a real
   provider is attached.
6. **No parity theater.** Migrate product value, not every legacy toggle.
7. **3D as progressive enhancement.** Functional DOM UI lands before or with
   each immersive representation.
8. **Small reviewable changes.** Avoid a single generated migration commit.

## 4. Public Boundary Audit

Before copying any implementation, classify source material:

| Category | Public handling |
| --- | --- |
| Generic domain logic | Rewrite or copy after review and tests |
| Provider API adapter | Include only for documented, verifiable integrations |
| Private workflow JSON | Exclude; provide a safe illustrative fixture |
| Model weights and LoRA files | Exclude and document optional placement |
| Generated media and character references | Exclude; use curated sample assets |
| `.env`, OAuth files, tokens | Exclude; rotate if ever committed elsewhere |
| Logs and absolute paths | Exclude and redact from examples |

Run secret and large-file scans before the first push containing migrated code.

## 5. Target Milestones

### Phase 0: Product And Architecture Baseline

Deliverables:

- Product brief, architecture, migration plan, and ADR 0001.
- Public scope and non-goals.
- Initial domain vocabulary and route map.
- Threat boundary and demo-mode requirements.

Exit criteria:

- The four documents do not contradict one another.
- A reviewer can explain the product and intended runtime from docs alone.
- No private implementation or asset has been copied.

### Phase 1: Monorepo Foundation

Deliverables:

- `apps/web` with Next.js App Router, TypeScript, linting, and tests.
- `apps/api` with FastAPI, Pytest, health endpoint, and settings model.
- Root scripts, `.env.example`, formatting, and GitHub Actions.
- Docker Compose demo profile.
- OpenAPI export and generated TypeScript contract check.

Exit criteria:

- A new contributor can start web and API from documented commands.
- CI passes on a credential-free clone.
- `/api/v1/health` is represented by a typed web client.

### Phase 2: Product Shell And 3D Technical Spike

Deliverables:

- Responsive studio shell, sidebar, top status, and route error boundaries.
- Design tokens and accessible form/control primitives.
- Client-only React Three Fiber stage using deterministic mock jobs.
- Persistent 2D/3D display preference and reduced-motion behavior.
- Desktop, tablet, and mobile visual tests.

Exit criteria:

- Three mock jobs visibly transition through queued, running, and completed.
- The same jobs are fully usable in 2D mode.
- The canvas is nonblank, framed correctly, and releases resources on unmount.
- Forms and navigation remain usable without loading the 3D bundle.

### Phase 3: Image Generation Vertical Slice

Deliverables:

- Prompt, negative prompt, image upload, provider, preset, and parameters.
- `POST /api/v1/jobs` for `text_to_image` and `image_to_image`.
- Mock image provider and immutable request snapshot.
- Large result preview and safe media persistence.
- Unit, API integration, and Playwright happy/failure tests.

Exit criteria:

- A reviewer can submit, observe, inspect, and reuse a mock image.
- Empty, malformed, and intentionally failed outputs return normalized errors.
- Refresh does not confuse the selected result with a running job.

### Phase 4: Job Center And Media Library

Deliverables:

- Job list, details, cancellation, retry, and SSE updates with polling fallback.
- Library filters, density control, selection/delete mode, and detail view.
- Provenance including prompt, model, provider, parameters, references, and time.
- Spatial compare as an optional view over the same asset selection model.

Exit criteria:

- Queued work can be cancelled and failed work can be retried.
- Terminal results update without page refresh.
- Pagination never causes previously loaded assets to disappear incorrectly.
- Delete removes selected metadata and owned files without touching uploads that
  are still referenced by other records.

### Phase 5: Video Generation Vertical Slice

Deliverables:

- Image-to-video request editor and video-specific parameter schema.
- Mock video provider with queue, sampling, encoding, and persistence phases.
- Looping preview, thumbnail, metadata, and library reuse.
- Cancellation and timeout semantics documented and tested.

Exit criteria:

- A library image can start a video request without a missing source path.
- The resulting video and thumbnail belong to the submitted job, not an older
  provider history entry.
- Video duration and frame metadata reflect the persisted artifact.

### Phase 6: Prompt Copilot And System Status

Deliverables:

- Prompt suggestion adapter and new-prompt behavior.
- Prompt and negative-prompt insertion actions.
- Provider, API, storage, and optional inference-server status.
- Redacted recent error display and request IDs.

Exit criteria:

- No browser response or application log contains a raw credential.
- The assistant is optional and generation remains usable when it is offline.

### Phase 7: Real Provider Adapters

Deliverables:

- Optional ComfyUI adapter based on a small safe reference workflow.
- Capability descriptors for supported operations and parameter limits.
- Provider contract tests with captured, sanitized fixtures.
- Setup documentation that separates required and optional assets.

Exit criteria:

- Demo CI stays independent of ComfyUI.
- Provider parsing handles null, empty, delayed, and unexpected responses.
- Output collection uses the submitted provider job ID and declared output node.
- Provider-specific failures map to normalized domain errors.

### Phase 8: Portfolio Release Hardening

Deliverables:

- README with product screenshot, short demo, architecture diagram, and commands.
- Seeded safe demo library.
- Accessibility and keyboard review.
- Performance trace and documented 3D budgets.
- Dependency, license, secret, and large-file audit.
- Tagged `v0.1.0` portfolio release.

Exit criteria:

- A clean clone completes the documented demo and all automated checks.
- No private path, secret, model weight, or unlicensed sample is included.
- The README claims only features visible in the tagged revision.

## 6. Legacy-To-Target Mapping

| Legacy responsibility | Target location |
| --- | --- |
| Jinja tab markup | Next.js routes and feature components |
| Global DOM queries and event listeners | Component events and feature hooks |
| Global mutable request state | React Hook Form plus explicit draft schema |
| Polling timers in one script | TanStack Query and centralized event client |
| Inline provider branching | FastAPI provider registry |
| JSON response shape assumptions | Pydantic schemas and generated TS types |
| Media cards and detail modal | Shared media feature module |
| Local-storage keys | Versioned, namespaced preference repository |
| CSS selector accumulation | Tokens, primitives, feature-scoped styles |
| JSON metadata runtime | SQLite repository plus one-time importer |

## 7. State Migration

### Preferences

- Use a `canvasrelay:v1:*` namespace.
- Persist only user preferences and drafts, never server job truth.
- Version every persisted object and provide a reset path.
- Store provider IDs rather than display labels.

### Media Metadata

- Build a one-time importer for sanitized legacy JSON only after the new schema
  stabilizes.
- Derive checksums and dimensions while importing.
- Reject paths outside the configured legacy media root.
- Report skipped records without aborting the entire import.

### Provider Presets

- Define public presets from explicit safe defaults.
- Do not import private provider or workflow names automatically.
- Version presets so old job provenance remains interpretable.

## 8. Definition Of Done For Every Slice

- User-visible loading, empty, success, error, and retry states exist.
- Desktop, tablet, and mobile layouts are verified.
- Keyboard and screen-reader labels cover required actions.
- Pydantic and TypeScript contracts agree.
- Unit tests cover domain decisions, not implementation trivia.
- At least one Playwright flow covers the slice in demo mode.
- Logs include request and job IDs without secrets.
- Documentation and screenshots match the implementation.
- 3D behavior has an equivalent required action in 2D.

## 9. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Migrating all private workflows | Release never stabilizes | Curate representative providers and declare non-goals |
| Large React components replace large vanilla files | Architecture improves only cosmetically | Enforce feature boundaries and component review limits |
| WebGL memory leaks from media textures | Browser and GPU instability | One canvas, explicit disposal, visibility pause, diagnostics |
| 3D captures scroll or hides controls | Tablet and mobile workflow failure | Focus-gated controls, DOM overlay, mandatory 2D mode |
| API contract drifts | Runtime request failures | Generated types and CI drift check |
| Provider output is associated with old history | Wrong media shown for a job | Collect by submitted job ID and output identity |
| Secrets or personal assets enter Git history | Public exposure | Clean history, scans, reviewed allowlist migration |
| Demo depends on unavailable infrastructure | Reviewer cannot run project | First-class deterministic mock provider |
| Big-bang migration blocks private use | Loss of working tool | Parallel runtime and vertical cutover |

## 10. Suggested Pull Request Sequence

1. `docs: define product, architecture, migration, and ADR`
2. `chore: scaffold Next.js and FastAPI monorepo`
3. `feat: add typed health contract and studio shell`
4. `feat: add accessible design primitives and responsive navigation`
5. `feat: visualize deterministic jobs in 2D and 3D`
6. `feat: complete mock image generation vertical slice`
7. `feat: add job center with cancel, retry, and events`
8. `feat: add media provenance and library workflows`
9. `feat: complete mock image-to-video vertical slice`
10. `feat: add optional ComfyUI adapter and sanitized fixtures`
11. `docs: publish portfolio walkthrough and performance findings`

Each pull request must remain independently understandable and keep the default
branch runnable.

## 11. Cutover And Rollback

- The private studio remains the production tool during migration.
- Public routes are considered replacements only after their exit criteria pass.
- No public migration step modifies private media or configuration in place.
- Importers default to dry run and copy metadata into a separate public database.
- If a real provider adapter regresses, demo mode and other providers remain
  available through capability flags.

## 12. First Implementation Checkpoint

The first code checkpoint is intentionally narrow:

1. Start Next.js and FastAPI.
2. Fetch typed health data.
3. Submit three deterministic mock jobs.
4. See them transition in an accessible 2D list and the 3D generation stage.
5. Select a completed mock asset without losing the active job state.
6. Run lint, type checks, unit tests, build, and one Playwright scenario.

This checkpoint validates the architecture before any legacy provider workflow
is migrated.
