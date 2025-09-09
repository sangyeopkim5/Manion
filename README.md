Manion

수학 문제를 점 데이터로 샘플링하고, CAS 계산을 거쳐 Manim 애니메이션으로 변환하는 AI 기반 시스템입니다.

Features

수학 문제 이미지 분석 및 좌표 샘플링

GPT-5 기반 Manim 코드 생성

CAS(Computer Algebra System) 계산 지원

자동 placeholder 치환 및 최종 코드 생성

전체 시스템 로직 흐름
1. 데이터 입력 (Input)
apps/graphsampling/Probleminput/
├── .jpg 파일: 수학 문제 이미지
└── .json 파일: OCR 결과 및 문제 구조화 데이터

2. 그래프 샘플링 단계 (Graph Sampling)
apps/graphsampling/builder.py
├── 이미지 → 좌표화 (anchor_ir.py)
├── 좌표 검증 및 JSON 저장
└── outputjson/ 폴더에 점 데이터 결과 저장

3. 메인 파이프라인 (E2E Processing)
server.py → /e2e 엔드포인트
├── 1단계: route_problem() - 문제 분류 및 라우팅
├── 2단계: generate_manim() - GPT-5를 사용한 Manim 코드 생성
├── 3단계: run_cas() - CAS 계산 실행
└── 4단계: fill_placeholders() - 최종 코드 생성

4. CAS 계산 단계
apps/cas/compute.py
├── SymPy 기반 수식 파싱 및 계산
├── 보안 검증: SAFE_FUNCS 내 함수만 허용
└── 결과: LaTeX 및 Python 문자열

5. 렌더링 단계
apps/render/fill.py
├── CAS 결과 매핑
├── Placeholder 치환 ([[CAS:id]])
└── 최종 Manim 코드 생성

6. 출력 (Output)
ManimcodeOutput/ 폴더에 결과 저장
├── 문제 이름별 폴더 생성
├── 실행 가능한 Manim 코드 (.py)
└── 실행 방법 안내 README.md 포함

7. API 구조
FastAPI 기반 엔드포인트:
├── /e2e: 전체 파이프라인 실행
├── /codegen/generate: 코드 생성만
├── /cas/compute: CAS 계산만
└── /render/fill: 렌더링만

Layout
manion/
├── apps/
│   ├── graphsampling/              # 입력 및 샘플링
│   │   ├── anchor_ir.py
│   │   ├── builder.py
│   │   ├── outputjson/
│   │   └── Probleminput/
│   ├── cas/
│   │   ├── compute.py
│   │   ├── server.py
│   │   └── tests/
│   ├── codegen/
│   │   ├── codegen.py
│   │   ├── server.py
│   │   ├── prompt_templates/
│   │   └── tests/
│   ├── render/
│   │   ├── fill.py
│   │   ├── server.py
│   │   └── tests/
│   └── router/
│       ├── router.py
│       ├── server.py
│       └── tests/
├── configs/
│   ├── openai.toml
│   ├── render.toml
│   └── sympy.toml
├── libs/
│   ├── io_utils.py
│   ├── layout.py
│   ├── schemas.py
│   └── tokens.py
├── pipelines/
│   ├── e2e.py
│   └── tests/
├── ManimcodeOutput/
│   ├── 중1sample/
│   │   ├── 중1sample.py
│   │   └── README.md
│   └── ...
├── server.py
├── requirements.txt
├── system_prompt.txt
└── README.md

실행법
1. 가상환경 생성 및 활성화
# Windows PowerShell
cd manion
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -U pip setuptools wheel
pip install -r requirements.txt

2. 환경 변수 설정 (.env)
OPENAI_API_KEY=your_api_key_here

3. 서버 실행
uvicorn server:app --reload --port 8000

4. API 문서

http://127.0.0.1:8000/docs

Health Check: http://127.0.0.1:8000/health

5. E2E 테스트
python -m pipelines.e2e "apps/graphsampling/Probleminput/중1sample/중1sample.jpg" "apps/graphsampling/Probleminput/중1sample/중1sample.json"

##python 11ver 필수. portrace와 inkscape 때문. 10이상은 내장 함수때문.