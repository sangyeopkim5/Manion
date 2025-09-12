Manion Main — E2E Math Problem → Manim Pipeline
🎯 목적 (Objective)

이미지 또는 PDF 형태의 수학 문제를 결정론적 파이프라인으로 처리:

OCR (텍스트/레이아웃 인식)

GraphSampling (앵커 추출 + LinearIR 변환) - **조건부 실행**

CodeGen (LLM 기반 Manim 코드 + CAS-JOBS 생성) - **2가지 경로 지원**

CAS (Sympy로 수학적 검증/계산)

Render (CAS 결과 치환 → 최종 Manim 코드)

🚀 **새로운 기능: Picture 유무에 따른 조건부 처리**

- **경로 1 (Picture 없음)**: system_prompt + a_ocr JSON 바로 전달 (b_graphsampling 스킵)
- **경로 2 (Picture 있음)**: system_prompt + b_graphsampling 결과 + crop 이미지들

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

🔗 데이터 플로우 (전체 파이프라인 - 조건부 처리)
Probleminput/<문제명>/*.jpg
   │
   ▼
(1) a_ocr: OCR + post-process + picture-children
   ▶ <문제명>.json / <문제명>.md / <문제명>.jpg (OCR 시각화)
   │
   ▼
   ┌─────────────────────────────────┐
   │     Picture 블록 확인           │
   └─────────────────────────────────┘
   │
   ▼
   ┌─────────────────┐
   │   Picture 있음?  │
   └─────────────────┘
   │
   ▼                ▼
경로 2 (있음)      경로 1 (없음)
   │                │
   ▼                ▼
(2) b_graphsampling (2) b_graphsampling
   + crop 이미지들     스킵
   ▶ outputschema.json ▶ 빈 outputschema.json
   │                │
   ▼                ▼
(3) c_codegen: GPT 호출 (3) c_codegen: GPT 호출
   ▶ b_graphsampling   ▶ a_ocr JSON
   + crop 이미지들     직접 전달
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

**환경 설정 (필수)**
```powershell
# 의존성 설치
pip install -r requirements.txt

# OpenAI API 키 설정
echo "OPENAI_API_KEY=your_api_key_here" > .env
```

**1) 전체 파이프라인 (OCR부터) - 새로운 조건부 처리**

```powershell
# Picture가 있는 경우 (경로 2)
python pipelines\cli_e2e.py Probleminput\중1-2도형\중1-2도형.jpg --problem-name "중1-2도형"

# Picture가 없는 경우 (경로 1)  
python pipelines\cli_e2e.py Probleminput\중3-1사다리꼴넓이\중3-1사다리꼴넓이.jpg --problem-name "중3-1사다리꼴넓이"
```

**2) OCR은 이미 끝난 경우 (JSON 동봉)**
```powershell
python -m pipelines.e2e ".\Probleminput\sample1\sample1.jpg" ".\Probleminput\sample1\sample1.json"
```

**3) 서버로 테스트**
```powershell
# 서버 시작
python server.py

# 다른 터미널에서 API 호출
curl -X POST "http://localhost:8000/e2e_with_ocr" -H "Content-Type: application/json" -d "{\"image_path\": \"Probleminput/중1-2도형/중1-2도형.jpg\", \"problem_name\": \"중1-2도형\"}"
```

🧩 단계별 실행 (디버깅)

**Picture가 있는 경우 (경로 2)**
```powershell
# 1단계 OCR
python pipelines\cli_stage.py 1 Probleminput\중1-2도형\중1-2도형.jpg

# 2단계 GraphSampling (조건부 실행)
python pipelines\cli_stage.py 2 ManimcodeOutput\중1-2도형

# 3단계 CodeGen (b_graphsampling + crop 이미지들)
python pipelines\cli_stage.py 3 ManimcodeOutput\중1-2도형\outputschema.json

# 4단계 CAS
python pipelines\cli_stage.py 4 "$(Get-Content ManimcodeOutput\중1-2도형\codegen_output.py)"

# 5단계 Render
python pipelines\cli_stage.py 5 "$(Get-Content ManimcodeOutput\중1-2도형\manim_draft.py)" ManimcodeOutput\중1-2도형\cas_results.json ManimcodeOutput\중1-2도형\final.py
```

**Picture가 없는 경우 (경로 1)**
```powershell
# 1단계 OCR
python pipelines\cli_stage.py 1 Probleminput\중3-1사다리꼴넓이\중3-1사다리꼴넓이.jpg

# 2단계 GraphSampling (스킵됨)
python pipelines\cli_stage.py 2 ManimcodeOutput\중3-1사다리꼴넓이

# 3단계 CodeGen (a_ocr JSON 직접 전달)
python pipelines\cli_stage.py 3 ManimcodeOutput\중3-1사다리꼴넓이\outputschema.json

# 4단계 CAS
python pipelines\cli_stage.py 4 "$(Get-Content ManimcodeOutput\중3-1사다리꼴넓이\codegen_output.py)"

# 5단계 Render
python pipelines\cli_stage.py 5 "$(Get-Content ManimcodeOutput\중3-1사다리꼴넓이\manim_draft.py)" ManimcodeOutput\중3-1사다리꼴넓이\cas_results.json ManimcodeOutput\중3-1사다리꼴넓이\final.py
```

🌐 서버 실행 (옵션)

웹 또는 외부 서비스에서 호출하려면:

```powershell
uvicorn server:app --reload --port 8001
```

**API 엔드포인트:**
- `/e2e_with_ocr`: 이미지를 업로드 → 단계 1~5 수행 (조건부 처리)
- `/e2e`: OCR JSON과 함께 → 단계 2~5 수행

🔧 설정 파일

configs/openai.toml : 모델 이름, 토큰 제한

configs/sympy.toml : 변수 도메인, 계산 전략

configs/render.toml : 치환 정책, 출력 경로

📁 결과 확인 위치

```
ManimcodeOutput/
├── 중1-2도형/                    # Picture가 있는 경우
│   ├── 중1-2도형.json            # OCR 결과
│   ├── 중1-2도형.jpg             # OCR 시각화
│   ├── outputschema.json         # b_graphsampling 결과
│   ├── 중1-2도형__pic_i0_outputschema.json  # crop 이미지 outputschema
│   ├── codegen_output.py         # CodeGen 결과
│   └── 중1-2도형_final.py        # 최종 Manim 코드
│
└── 중3-1사다리꼴넓이/              # Picture가 없는 경우
    ├── 중3-1사다리꼴넓이.json      # OCR 결과
    ├── 중3-1사다리꼴넓이.jpg       # OCR 시각화
    ├── outputschema.json         # 빈 outputschema (b_graphsampling 스킵)
    ├── codegen_output.py         # CodeGen 결과 (a_ocr JSON 직접 사용)
    └── 중3-1사다리꼴넓이_final.py  # 최종 Manim 코드
```

🛠 체크리스트

- [ ] Probleminput/<문제명>에 이미지 존재?
- [ ] OCR 결과에서 Picture 블록 확인?
- [ ] Picture 있음: b_graphsampling + crop 이미지들 처리됨?
- [ ] Picture 없음: b_graphsampling 스킵됨?
- [ ] CodeGen에서 [[CAS:id]] 토큰 포함 여부 확인?
- [ ] CAS 결과가 정상 치환되었는지 확인?
- [ ] 최종 Manim 코드 실행 시 좌표 왜곡 없는지 시각 검증?

🧠 권장 워크플로우

1. **Probleminput/에 문제 이미지 저장**
2. **조건부 파이프라인 실행**:
   ```powershell
   # Picture가 없없는 경우
   python pipelines\cli_e2e.py Probleminput\중1-2도형\중1-2도형.jpg --problem-name "중1-2도형"
   
   # Picture가 있는 경우
   python pipelines\cli_e2e.py Probleminput\중3-1사다리꼴넓이\중3-1사다리꼴넓이.jpg --problem-name "중3-1사다리꼴넓이"
   ```
3. **결과 확인**: ManimcodeOutput/<문제명>/ 디렉토리에서 outputschema.json 및 최종 <문제명>.py 확인
4. **디버깅**: 필요시 단계별 실행으로 디버깅

🎯 **예상 로그 메시지**
- Picture 있음: `[CodeGen] Picture blocks detected - using b_graphsampling + crop images`
- Picture 없음: `[CodeGen] No Picture blocks - using a_ocr JSON directly`

이제 Picture 유무에 따라 자동으로 최적화된 경로로 처리되므로, 더 효율적이고 빠른 파이프라인이 됩니다!