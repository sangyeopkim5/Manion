import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from libs.schemas import ProblemDoc, CodegenJob
from pipelines import e2e as pipeline


def test_pipeline_without_cas(monkeypatch):
    """The pipeline should bypass CAS when there are no jobs."""

    # Stub generate_manim to return code without CAS jobs
    def fake_generate(doc):
        return CodegenJob(manim_code_draft="print('hello')", cas_jobs=[])

    # Ensure CAS and rendering steps are not invoked
    def fail_run_cas(*args, **kwargs):
        raise AssertionError("run_cas should not be called")

    def fail_fill(*args, **kwargs):
        raise AssertionError("fill_placeholders should not be called")

    monkeypatch.setattr(pipeline, "generate_manim", fake_generate)
    monkeypatch.setattr(pipeline, "run_cas", fail_run_cas)
    monkeypatch.setattr(pipeline, "fill_placeholders", fail_fill)

    doc = ProblemDoc(items=[], image_path=None)
    result = pipeline.run_pipeline(doc)
    assert result.strip() == "print('hello')"
