📘 Manion-CAS README
🚀 개요

Manion-CAS는 수학 문제를 입력하면 다음 과정을 자동화하는 시스템입니다:

Graphsampling → 문제 이미지 + OCR JSON에서 outputschema.json 생성

CodeGen → outputschema.json + 이미지 → GPT 호출

---CAS-JOBS--- JSON (계산 태스크)

ManimCode (문제 풀이 시각화 코드)

CAS → CAS-JOBS를 Sympy로 계산

저장 → Manim 코드 파일(.py)과 실행 가이드(README.md) 자동 생성

📂 디렉토리 구조 (중요 부분만)
manion-main/
├── apps/
│   ├── codegen/
│   │   └── codegen.py        # CodeGen (outputschema + 이미지 → GPT 호출)
│   ├── cas/
│   │   └── compute.py        # Sympy 기반 CAS 실행
│   ├── graphsampling/
│   │   └── builder.py        # outputschema.json 생성
│   └── render/
│       └── fill.py           # (이전 방식, placeholder 채움 — 현재는 불필요)
├── libs/
│   └── schemas.py            # Pydantic 모델 정의 (ProblemDoc, CASJob, CASResult 등)
├── configs/
│   ├── openai.toml           # OpenAI API 모델 설정
│   ├── render.toml
│   └── sympy.toml
├── system_prompt.txt          # CodeGen용 프롬프트 (CAS-JOBS + ManimCode 규칙 포함)
├── server.py                  # FastAPI 서버 (e2e / codegen / cas API 제공)
├── requirements.txt
└── ManimcodeOutput/           # 출력 코드/README 저장 디렉토리

⚙️ 설치 방법
1. 환경 설정
git clone <repo-url>
cd manion-main
py -3.11 -m venv .venv311
.venv311\Scripts\activate   

# (Windows PowerShell)

2. 의존성 설치
python -m pip install --upgrade pip setuptools wheel

pip install -r requirements.txt

3. OpenAI API 키 설정

PowerShell:

$env:OPENAI_API_KEY="sk-여기에_API키"


혹은 .env 파일 생성:

OPENAI_API_KEY=sk-여기에_API키

▶️ 실행 방법
1. 서버 실행
uvicorn server:app --reload --port 8000


실행 후:

http://127.0.0.1:8000
 → 기본 상태 메시지

http://127.0.0.1:8000/health
 → 상태 체크

🔌 API 엔드포인트
1. /codegen/generate

입력: ProblemDoc (OCR items + 이미지 경로)
출력:

{
  "status": "ok",
  "cas_results": [
    {"task": "simplify", "expr": "x^2+2x+1", "result": "x**2+2*x+1"},
    {"task": "factor", "expr": "x^2+2x+1", "result": "(x + 1)**2"}
  ],
  "manim_code": "from manim import *\n\nclass ManimCode(Scene): ..."
}


cas_results: 사람이 읽기 좋은 CAS 실행 결과 (task, expr, result)

manim_code: Manim 시각화 코드 (앞부분 미리보기만 반환, 전체는 파일 저장됨)

결과 파일: ManimcodeOutput/<problem_name>/<problem_name>.py

2. /cas/run

입력: CASJob 리스트

[
  {"id": "1", "task": "simplify", "target_expr": "x^2+2x+1", "variables": ["x"]}
]


출력:

[
  {"id": "1", "result_tex": "x^{2} + 2 x + 1", "result_py": "x**2 + 2*x + 1"}
]

3. /e2e

입력: ProblemDoc

이미지와 OCR JSON을 받아 Graphsampling → CodeGen → CAS → ManimCode 저장을 한 번에 실행

출력: /codegen/generate와 동일 (cas_results_pretty + manim_code).

📜 CodeGen Prompt (system_prompt.txt)

출력은 반드시 ---CAS-JOBS--- JSON + ManimCode(Scene=ManimCode)

CAS 태스크 예시:

{
  "task": "solve",
  "target_expr": "x^2 - 4",
  "variables": ["x"]
}


ManimCode는 SEC_PROBLEM → SEC_GIVENS → SEC_WORK → SEC_RESULT 구조

정답은 마지막에 강조 표시

🧩 전체 처리 흐름
ProblemDoc (OCR + Image)
   ↓
Graphsampling (builder.py) → outputschema.json
   ↓
CodeGen (codegen.py + GPT)
   ↓
 ┌───────────────┐
 │ ---CAS-JOBS---│ → run_cas() → CAS 결과
 │ ManimCode     │ → .py 파일 저장
 └───────────────┘
   ↓
최종 반환: {"cas_results": [...], "manim_code": "..."}

✅ 예시 실행
요청
curl -X POST "http://127.0.0.1:8000/e2e" \
  -H "Content-Type: application/json" \
  -d '{
        "items": [{"bbox": [0,0,10,10], "category": "equation", "text": "x^2+2x+1"}],
        "image_path": "apps/graphsampling/Probleminput/중1sample/중1sample.jpg"
      }'

응답
{
  "status": "ok",
  "cas_results": [
    {"task": "simplify", "expr": "x^2+2x+1", "result": "x**2 + 2*x + 1"},
    {"task": "factor", "expr": "x^2+2x+1", "result": "(x + 1)**2"}
  ],
  "manim_code": "from manim import *\n\nclass ManimCode(Scene): ..."
}

🛠️ 개발자 노트

libs/schemas.py

CASJob: task, target_expr, variables, constraints, assumptions 필드

apps/cas/compute.py

Sympy 기반 실행. task에 따라 simplify, expand, factor, evaluate, solve 지원

apps/codegen/codegen.py

GPT에 outputschema.json + .jpg 전달

system_prompt에 따라 CAS-JOBS + ManimCode 생성

server.py

/codegen/generate, /cas/run, /e2e API 제공

결과 파일은 ManimcodeOutput/<problem_name>/에 저장

🔄 엔드투엔드 데이터 흐름(상세)

- **1) 입력 수신**: `ProblemDoc(items, image_path)`을 API(`/e2e`, `/codegen/generate`) 또는 CLI(`pipelines/e2e.py`)로 전달
- **2) 작업 디렉토리 준비**: `ManimcodeOutput/<문제이름>/` 생성, `input.json` 저장, 원본 이미지 복사
- **3) Graphsampling → outputschema.json**: `apps/graphsampling/builder.py::build_outputschema()`가 LinearIR(`schema="LinearIR.v1"`)과 리소스 메타를 생성. `emit_anchors=True`면 `anchor_ir.py::build_anchor_item()`으로 `_anchorir_out.svg` 및 `raster_with_anchors` 삽입
- **4) CodeGen (GPT 호출)**: `apps/codegen/codegen.py::run_codegen()`이 `outputschema.json`과 이미지(base64)를 `system_prompt.txt`와 함께 모델로 보내 `ManimCode + ---CAS-JOBS---` 텍스트를 반환하고 `codegen_output.py`로 저장
- **5) CAS 작업 추출/정규화**: `server.py::_extract_jobs_and_code()` 또는 `pipelines/e2e.py::_extract_jobs_and_code()`가 `---CAS-JOBS---` JSON 배열과 상단 Manim 코드를 분리. `\frac{a}{b}` → `(a)/(b)` 등 SymPy 친화 표기로 정규화
- **6) CAS 실행(SymPy)**: `apps/cas/compute.py::run_cas()`가 `CASJob` 리스트를 받아 `simplify/expand/factor/evaluate/solve` 수행 → `CASResult(id, result_tex, result_py)` 반환. CLI 경로는 `_resolve_and_run_cas()`로 `[[CAS:id]]` 의존성 순서를 자동 해결
- **7) 코드 치환/저장**: `apps/render/fill.py::fill_placeholders()`가 Manim 코드 내 `[[CAS:id]]`를 `{result_tex}`로 치환. 최종 코드 `ManimcodeOutput/<문제>/<문제>.py`와 실행 가이드 `README.md` 저장

📌 주요 엔드포인트/실행 진입점
- **API**: `POST /e2e`(E2E 전체), `POST /codegen/generate`(동일 플로우), `POST /cas/run`(CAS 단독)
- **서버 앱**: `server.py` (라우터 포함)
- **로컬 파이프라인**: `python -m pipelines.e2e <image_path> <json_path>`

📎 산출물
- `ManimcodeOutput/<문제>/input.json`, `<원본이미지>`, `outputschema.json`, `codegen_output.py`, `<문제>.py`, `README.md`

⚙️ 설정
- OpenAI 모델: `configs/openai.toml`
- SymPy 기본 가정: `configs/sympy.toml`
- 렌더 옵션: `configs/render.toml`