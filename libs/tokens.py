import os
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing (.env)")
    kwargs = {"api_key": api_key}
    base = os.getenv("OPENAI_BASE_URL")
    if base:
        kwargs["base_url"] = base
    project = os.getenv("OPENAI_PROJECT")
    if project:
        kwargs["project"] = project
    return OpenAI(**kwargs)

