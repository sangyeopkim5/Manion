import os
from openai import OpenAI

class OpenAICompatLLM:
    def __init__(self, base_url: str, api_key: str, model: str,
                 system_prompt_path=None, temperature: float = 0.2):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature

        if system_prompt_path is None:
            here = os.path.dirname(__file__)
            system_prompt_path = os.path.join(here, "postproc_prompt.md")
        if not os.path.exists(system_prompt_path):
            raise FileNotFoundError(f"System prompt file not found: {system_prompt_path}")

        with open(system_prompt_path, "r", encoding="utf-8") as f:
            self.system = f.read()

    def propose_patch(self, code: str, error_log: str) -> str:
        user = f"[ERROR LOG]\n{error_log}\n\n[CODE]\n{code}\n"
        res = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": self.system},
                {"role": "user", "content": user},
            ],
        )
        return res.choices[0].message.content.strip()
