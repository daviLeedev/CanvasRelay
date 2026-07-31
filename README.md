# CanvasRelay

CanvasRelay is a local-first AI media orchestration studio under active
vertical development.

This public repository provides a typed Next.js and FastAPI runtime, a responsive
2D/3D studio shell, deterministic image jobs, and an optional local ComfyUI image
provider. The deterministic provider remains the default so the complete flow
runs without credentials, models, or a GPU.

## Current Stack

- Next.js App Router, React, and TypeScript
- TanStack Query
- FastAPI and Pydantic Settings
- OpenAPI-generated TypeScript contracts
- Provider-neutral image jobs with Demo and optional ComfyUI adapters
- SQLite-backed job history and a filesystem result library
- Server-sent job updates with polling fallback
- Pytest, Ruff, MyPy, Vitest, and Testing Library
- pnpm workspaces and uv
- Docker Compose demo runtime

## Native Development

Requirements:

- Node.js 22.13 or newer
- pnpm 11.9
- Python 3.12
- uv 0.12

```bash
pnpm install
uv sync --directory apps/api
pnpm contracts:generate
pnpm dev
```

Open:

- Web: <http://localhost:3000>
- API: <http://localhost:8000>
- API documentation: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health>

## Docker Compose

```bash
docker compose up --build
```

No provider credentials, model files, or GPU are required for the foundation
runtime.

## Verification

```bash
pnpm policy:check
pnpm contracts:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
docker compose config
```

## Configuration

Copy the names from `.env.example` into your own untracked environment file or
shell environment. Only the public API base URL is exposed to browser code.

`CANVASRELAY_DATA_DIR` controls the private runtime directory that contains the
SQLite job index and generated media. It defaults to the ignored `.canvasrelay/`
directory. Completed results are available from the Studio history and the
`/library` route, including after an API restart.

### Optional local ComfyUI generation

CanvasRelay can submit a user-owned API-format workflow to a local ComfyUI
server. The browser never receives the ComfyUI address or workflow path.

1. Export a working ComfyUI workflow in API format.
2. Replace its runtime inputs with the exact placeholders `{{prompt}}`,
   `{{seed}}`, `{{width}}`, and `{{height}}`. `{{filename_prefix}}` is optional.
3. Store the configured workflow outside Git or under the ignored `.local/`
   directory.
4. Set `CANVASRELAY_IMAGE_PROVIDER=comfyui` and
   `CANVASRELAY_COMFYUI_WORKFLOW_PATH` in the API process environment.
5. Start ComfyUI, then start CanvasRelay normally.

See [the ComfyUI adapter example](examples/comfyui/README.md) for the template,
status behavior, cancellation limits, and safe setup details.

## Documentation

Architecture, product, migration, and decision records are available in the
[bilingual documentation index](docs/README.md).

---

## 한국어

CanvasRelay는 현재 기반 구조를 구축 중인 로컬 우선 AI 미디어 오케스트레이션
스튜디오다.

현재 공개 저장소에는 타입이 연결된 Next.js와 FastAPI 런타임, API 상태 계약,
반응형 스튜디오 셸만 포함한다. 미디어 생성, 공급자 어댑터, 작업 오케스트레이션,
라이브러리, 이머시브 3D 스테이지는 이번 foundation 단계에서 의도적으로
구현하지 않는다.

### 로컬 실행

Node.js 22.13 이상, pnpm 11.9, Python 3.12, uv 0.12가 필요하다.

```bash
pnpm install
uv sync --directory apps/api
pnpm contracts:generate
pnpm dev
```

### Docker 실행

```bash
docker compose up --build
```

Foundation 런타임에는 공급자 인증정보, 모델 파일, GPU가 필요하지 않다.

### 문서

제품, 아키텍처, 마이그레이션, 결정 기록은
[영문·한국어 문서 인덱스](docs/README.md)에서 확인할 수 있다.
