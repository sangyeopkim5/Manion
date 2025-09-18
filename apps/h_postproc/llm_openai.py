import os
from openai import OpenAI
from dotenv import load_dotenv

class OpenAICompatLLM:
    def __init__(self, base_url: str = None, api_key: str = None, model: str = None,
                 system_prompt_path=None, temperature: float = 0.2):
        # .env 파일에서 설정 로드 (다른 모듈들과 동일)
        load_dotenv()
        
        # 기본값 설정 (다른 모듈들과 동일)
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""))
        self.model = model or "gpt-4o-mini"
        self.temperature = temperature

        if system_prompt_path is None:
            here = os.path.dirname(__file__)
            system_prompt_path = os.path.join(here, "postproc_prompt.md")
        if not os.path.exists(system_prompt_path):
            raise FileNotFoundError(f"System prompt file not found: {system_prompt_path}")

        with open(system_prompt_path, "r", encoding="utf-8") as f:
            self.system = f.read()

    def propose_patch(self, code: str, error_log: str = "") -> str:
        if error_log:
            # 두 번째 호출: 에러 로그가 있을 때
            user = f"[ERROR LOG]\n{error_log}\n\n[CODE]\n{code}\n"
        else:
            # 첫 번째 호출: 에러 로그 없이 코드만
            user = f"[CODE]\n{code}\n"
        
        res = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": self.system},
                {"role": "user", "content": user},
            ],
        )
        return res.choices[0].message.content.strip()
