# CanvasRelay

CanvasRelay is a local-first AI media orchestration studio under active
foundation development.

This public repository currently provides a typed Next.js and FastAPI runtime,
an API health contract, and a responsive studio shell. Media generation,
provider adapters, job orchestration, the library, and the immersive 3D stage
are intentionally not implemented in this foundation revision.

## Current Stack

- Next.js App Router, React, and TypeScript
- TanStack Query
- FastAPI and Pydantic Settings
- OpenAPI-generated TypeScript contracts
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
