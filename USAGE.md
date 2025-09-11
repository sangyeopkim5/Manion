# Manion-CAS 사용법

## 📋 전체 구조

```
manion-main/
├── apps/                    # 개별 모듈들
│   ├── 1ocr/               # OCR 모듈 (dots.ocr2)
│   ├── 2graphsampling/     # GraphSampling 모듈
│   ├── 3codegen/           # CodeGen 모듈
│   ├── 4cas/               # CAS 모듈
│   └── 5render/            # Render 모듈
├── pipelines/              # 파이프라인 실행
│   ├── e2e.py              # E2E 로직
│   ├── stages.py           # 개별 단계 실행
│   ├── cli_e2e.py          # E2E CLI
│   └── cli_stage.py        # 개별 단계 CLI
├── libs/                   # 공통 라이브러리
├── configs/                # 설정 파일들
└── server.py               # FastAPI 서버
```

## 🚀 사용 방법

### 1. E2E 파이프라인 (전체 실행)

#### CLI 사용
```bash
# OCR 방식 (이미지만 입력)
python -m pipelines.cli_e2e input.jpg
python -m pipelines.cli_e2e input.jpg --problem-name "중1-2도형"

# 기존 방식 (이미지 + JSON)
python -m pipelines.cli_e2e input.jpg data.json

# 상세 출력
python -m pipelines.cli_e2e input.jpg --verbose
```

#### Python 모듈 사용
```python
from pipelines.e2e import run_pipeline_with_ocr, run_pipeline

# OCR 방식
result = run_pipeline_with_ocr("input.jpg", "중1-2도형")

# 기존 방식
from libs.schemas import ProblemDoc
doc = ProblemDoc(items=items, image_path="input.jpg")
result = run_pipeline(doc)
```

### 2. 개별 단계 실행

#### CLI 사용
```bash
# Stage 1: OCR 처리
python -m pipelines.cli_stage 1 --image-path input.jpg --problem-name "중1-2도형"

# Stage 2: GraphSampling 처리
python -m pipelines.cli_stage 2 --problem-dir "./temp_ocr_output/중1-2도형/중1-2도형"

# Stage 3: CodeGen 처리
python -m pipelines.cli_stage 3 --outputschema-path "outputschema.json" --image-paths "image.jpg" --output-dir "."

# Stage 4: CAS 처리
python -m pipelines.cli_stage 4 --code-text "$(cat codegen_output.py)"

# Stage 5: Render 처리
python -m pipelines.cli_stage 5 --manim-code "$(cat manim_draft.py)" --cas-results "cas_results.json" --output-path "final.py"
```

#### Python 모듈 사용
```python
from pipelines.stages import stage1_ocr, stage2_graphsampling, stage3_codegen, stage4_cas, stage5_render

# Stage 1: OCR
ocr_dir = stage1_ocr("input.jpg", problem_name="중1-2도형")

# Stage 2: GraphSampling
schema_path = stage2_graphsampling(ocr_dir)

# Stage 3: CodeGen
code_text = stage3_codegen(schema_path, ["image.jpg"], ".")

# Stage 4: CAS
jobs, manim_code, cas_results = stage4_cas(code_text)

# Stage 5: Render
final_code = stage5_render(manim_code, cas_results, "final.py")
```

### 3. API 서버 사용

#### 서버 실행
```bash
uvicorn server:app --reload --port 8000
```

#### API 호출
```bash
# OCR + E2E
curl -X POST "http://127.0.0.1:8000/e2e_with_ocr" \
  -H "Content-Type: application/json" \
  -d '{"image_path": "input.jpg", "problem_name": "중1-2도형"}'

# 기존 E2E
curl -X POST "http://127.0.0.1:8000/e2e" \
  -H "Content-Type: application/json" \
  -d '{"items": [...], "image_path": "input.jpg"}'

# CAS 단독
curl -X POST "http://127.0.0.1:8000/cas/run" \
  -H "Content-Type: application/json" \
  -d '[{"id": "1", "task": "simplify", "target_expr": "x^2+2x+1", "variables": ["x"]}]'
```

## 📁 출력 구조

```
ManimcodeOutput/<문제이름>/
├── <문제이름>.json         # OCR JSON
├── <문제이름>.jpg          # OCR 이미지
├── outputschema.json       # LinearIR.v1 스키마
├── codegen_output.py       # GPT 원본 출력
├── <문제이름>.py          # 최종 Manim 코드
└── README.md              # 실행 가이드
```

## ⚙️ 설정

### 환경 변수
```bash
export OPENAI_API_KEY="your-api-key"
```

### 설정 파일
- `configs/openai.toml`: GPT 모델 설정
- `configs/sympy.toml`: SymPy 기본 가정
- `configs/render.toml`: 렌더링 옵션

## 🔧 개발자 정보

### 모듈 구조
- **1ocr**: dots.ocr2 기반 OCR 처리
- **2graphsampling**: OCR JSON을 LinearIR.v1로 변환
- **3codegen**: GPT를 사용한 Manim 코드 생성
- **4cas**: SymPy 기반 수학 계산
- **5render**: Placeholder 치환 및 최종 코드 생성

### 주요 함수
- `run_pipeline_with_ocr()`: OCR + 전체 파이프라인
- `run_pipeline()`: 기존 전체 파이프라인
- `stage1_ocr()` ~ `stage5_render()`: 개별 단계 실행
- `run_stage()`: 단계별 실행 래퍼

### 에러 처리
- 각 단계별 try-catch로 안전한 에러 처리
- 상세한 에러 메시지와 traceback 제공
- 중단 시 적절한 exit code 반환
