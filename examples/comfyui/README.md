# Optional ComfyUI image provider

CanvasRelay accepts a ComfyUI workflow exported in **API format**. It does not
read a canvas/UI workflow and it does not commit model weights or generated
media.

## Setup

1. Open a working text-to-image workflow in ComfyUI.
2. Export it in API format.
3. Replace the values that CanvasRelay owns with these exact tokens:

| Token | Replacement |
| --- | --- |
| `{{prompt}}` | Normalized user prompt |
| `{{seed}}` | Integer seed |
| `{{width}}` | Width selected from the aspect ratio |
| `{{height}}` | Height selected from the aspect ratio |
| `{{filename_prefix}}` | Optional unique output prefix |

The first four tokens are required. A token replaces the entire JSON value, so
numeric tokens may be written as quoted strings in the template and are bound
as integers before submission.

Copy `workflow.template.example.json` to an ignored location such as
`.local/comfyui-workflow.json`, update the model filename for your own install,
and configure the API process. Relative workflow paths resolve from the
CanvasRelay repository root:

```powershell
$env:CANVASRELAY_IMAGE_PROVIDER = "comfyui"
$env:CANVASRELAY_COMFYUI_BASE_URL = "http://127.0.0.1:8188"
$env:CANVASRELAY_COMFYUI_WORKFLOW_PATH = ".local/comfyui-workflow.json"
```

Set `CANVASRELAY_COMFYUI_OUTPUT_NODE_ID` only when a workflow contains multiple
Save Image outputs and CanvasRelay should collect one specific node.

## Runtime behavior

- `POST /prompt` submits the bound graph.
- `/queue` distinguishes queued from running work.
- `/history/{prompt_id}` supplies terminal status and output metadata.
- `/view` is proxied by FastAPI; the browser never calls ComfyUI directly.
- Pending cancellation removes only the matching prompt. Active cancellation
  uses ComfyUI's interrupt endpoint and should be used on a dedicated local
  inference instance.
- Local ComfyUI's polling API does not retain sampler progress. CanvasRelay
  displays `progress unavailable` instead of inventing a percentage.

Provider errors are normalized. Raw node payloads, stack traces, server URLs,
workflow paths, and local output paths are not returned to the browser.

## ComfyUI 로컬 공급자

ComfyUI에서 정상 동작하는 워크플로를 API 형식으로 내보낸 뒤 위 토큰을
입력값에 배치합니다. 모델 파일명과 워크플로 경로는 Git에 올리지 않고
`.local/` 또는 저장소 밖에서 관리합니다. CanvasRelay는 작업을 ComfyUI에
제출하고 상태와 결과만 정규화해 브라우저에 전달합니다.
