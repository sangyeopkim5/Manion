Manion Main — E2E Math Problem → Manim Pipeline
🎯 목적 (Objective)

이미지 또는 PDF 형태의 수학 문제를 결정론적 파이프라인으로 처리:

OCR (텍스트/레이아웃 인식)

GraphSampling (앵커 추출 + LinearIR 변환)

CodeGen (LLM 기반 Manim 코드 + CAS-JOBS 생성)

CAS (Sympy로 수학적 검증/계산)

Render (CAS 결과 치환 → 최종 Manim 코드)

📂 디렉터리 구조 (수정 반영)
manion-main/
├─ apps/
│  ├─ a_ocr/             # OCR (Pass-1, Pass-2)
│  ├─ b_graphsampling/   # 앵커(Anchor), LinearIR 생성
│  ├─ c_codegen/         # GPT 기반 코드 생성
│  ├─ d_cas/             # Sympy 계산
│  └─ e_render/          # 결과 치환 및 코드 완성
│
├─ Probleminput/         # ← 문제 입력 디렉터리 (이제 루트에 위치)
│  ├─ sample1/
│  │   ├─ sample1.jpg
│  │   └─ sample1.json (optional: 이미 OCR한 경우)
│  └─ sample2/
│      └─ ...
│
├─ libs/                 # 공통 schema/util
├─ configs/              # openai.toml, sympy.toml, render.toml
├─ pipelines/            # e2e/stage 실행 스크립트
├─ server.py             # (선택) FastAPI 서버
├─ README.md
└─ requirements.txt

🔗 데이터 플로우 (전체 파이프라인)
Probleminput/<문제명>/*.jpg
   │
   ▼
(1) a_ocr: OCR + post-process + picture-children
   ▶ <문제명>.json / <문제명>.md / <문제명>.jpg (OCR 시각화)
   │
   ▼
(2) b_graphsampling: 앵커 감지 + LinearIR 변환
   ▶ outputschema.json (px→manim 변환행렬 포함)
   │
   ▼
(3) c_codegen: GPT 호출
   ▶ Manim Scene draft + ---CAS-JOBS---
   │
   ▼
(4) d_cas: Sympy 계산
   ▶ cas_results.json
   │
   ▼
(5) e_render: 치환/완성
   ▶ 최종 <문제명>.py (Manim 실행 가능)

⚙ 설치
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt


(옵션) OCR 모델 다운로드:

python apps/a_ocr/tools/download_model.py --type huggingface --name rednote-hilab/dots.ocr

▶ 실행 예시 (루트에서 실행)
1) 전체 파이프라인 (OCR부터)
python -m pipelines.e2e ".\Probleminput\sample1\sample1.jpg"

2) OCR은 이미 끝난 경우 (JSON 동봉)
python -m pipelines.e2e `
  ".\Probleminput\sample1\sample1.jpg" `
  ".\Probleminput\sample1\sample1.json"

🧩 단계별 실행 (디버깅)
# 1단계 OCR
python -m pipelines.cli_stage --stage 1 --image ".\Probleminput\sample1\sample1.jpg"

# 2단계 GraphSampling
python -m pipelines.cli_stage --stage 2 --dir ".\Probleminput\sample1"

# 3단계 CodeGen
python -m pipelines.cli_stage --stage 3 --schema ".\Probleminput\sample1\outputschema.json"

# 4단계 CAS
python -m pipelines.cli_stage --stage 4 --cas ".\Probleminput\sample1\cas_jobs.json"

# 5단계 Render
python -m pipelines.cli_stage --stage 5 --code ".\Probleminput\sample1\manim_draft.py" --casres ".\Probleminput\sample1\cas_results.json"

🌐 서버 실행 (옵션)

웹 또는 외부 서비스에서 호출하려면:

uvicorn server:app --reload --port 8001


/e2e_with_ocr: 이미지를 업로드 → 단계 1~5 수행

/e2e: OCR JSON과 함께 → 단계 2~5 수행

🔧 설정 파일

configs/openai.toml : 모델 이름, 토큰 제한

configs/sympy.toml : 변수 도메인, 계산 전략

configs/render.toml : 치환 정책, 출력 경로

🛠 체크리스트

 Probleminput/<문제명>에 이미지/JSON 존재?

 outputschema.json에 px→manim 변환행렬 포함?

 CodeGen에서 [[CAS:id]] 토큰 포함 여부 확인?

 CAS 결과가 정상 치환되었는지 확인?

 최종 Manim 코드 실행 시 좌표 왜곡 없는지 시각 검증?

🧠 권장 워크플로우

Probleminput/에 문제 이미지 저장

python -m pipelines.e2e <이미지> 실행

outputschema.json 및 최종 <문제명>.py 확인

필요시 단계별 실행으로 디버깅

이제 문제 입력과 출력이 모두 루트 기준에서 관리되므로,
CLI 명령어와 e2e 파이프라인이 더 단순해지고 팀원 간 공유도 쉬워집니다.