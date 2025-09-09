import pathlib, sys, types, json
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
import server
from apps.codegen import codegen


class DummyResp:
    choices = [
        types.SimpleNamespace(
            message=types.SimpleNamespace(
                content="print([[CAS:a:1+1]])\n---CAS-JOBS---\n[[CAS:a:1+1]]"
            )
        )
    ]


def test_e2e_pipeline(monkeypatch):
    monkeypatch.setattr(codegen, "get_openai_client", lambda: object())
    monkeypatch.setattr(codegen, "_chat_completion_with_retry", lambda *a, **k: DummyResp())

    client = TestClient(server.app)
    base = pathlib.Path(__file__).resolve().parents[2] / "Probleminput/중1-2도형"
    img = base / "중1-2도형.jpg"
    items = json.load(open(base / "중1-2도형.json", "r"))
    payload = {"image_path": str(img), "items": items}
    res = client.post("/e2e", json=payload)
    assert res.status_code == 200
    assert "[[CAS:" not in res.json()["manim_code"]
