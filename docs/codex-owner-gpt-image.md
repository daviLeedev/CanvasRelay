# GPT Image via Owner Codex Login

CanvasRelay can optionally route GPT image jobs through a loopback-only proxy that uses the Codex login already present on the owner computer.

## Scope

- This is an owner-managed local connection, not a visitor sign-in feature.
- CanvasRelay never displays, uploads, stores, or logs authentication files, tokens, request headers, or absolute credential paths.
- The connection is disabled by default. Enable it only in the local server environment.
- Remote generation and connection management are disabled by default. Enable either explicitly only after adding a real user and authorization model.

## Local setup

1. Sign in to Codex using the supported local Codex flow on the owner computer.
2. Set `CANVASRELAY_CODEX_OAUTH_ENABLED=true` in a local, untracked environment file.
3. Start CanvasRelay and open **Settings / Owner GPT connection** from the same computer.
4. Choose **Detect local login**, then confirm the connection status before creating a GPT image job.

The proxy launcher uses the pinned `openai-oauth` package version in `pnpm-lock.yaml`. It starts a child process without a shell and never runs a live package command.

### Proxy dependency

- Source: `https://github.com/EvanZhouDev/openai-oauth`
- License: Apache-2.0
- Pinned package: `openai-oauth@2.0.0`

The package is used only as a local, loopback-bound compatibility proxy. CanvasRelay
does not copy the owner's Codex credential material into its database, media store,
browser state, or application logs.

### Container boundary

Docker Compose is intended for the demo and integration environment. It deliberately
does not mount `CODEX_HOME`, authentication files, or host credential directories
into a container. Keep this provider disabled in Compose, and run the API natively
on the owner computer when enabling the local Codex connection. This keeps the
owner credential boundary on the host while preserving Docker for database and
application verification.

## Data handling

- Job metadata, prompts, settings, and provider job identifiers use the existing repository.
- Uploaded references and completed image outputs use the configured `DATA_DIR` media store.
- Multiple reference inputs and result assets are saved as rows in `image_job_inputs` and `image_job_assets`.
- The legacy primary result field remains available for Library compatibility.

## Operational limits

The provider has its own in-process queue, separate from ComfyUI, with a default maximum of two concurrent jobs. The server also applies configurable daily global and per-client limits.

The owner must verify the applicable account terms, entitlements, and any usage charges with the provider. CanvasRelay does not infer, guarantee, or display subscription allowance or billing information.
