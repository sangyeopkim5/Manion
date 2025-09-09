import pathlib, sys
sys.path.append(str(pathlib.Path(__file__).resolve().parents[3]))

import logging
import pytest
from apps.render.fill import fill_placeholders
from libs.schemas import CASResult


def test_fill_duplicates(caplog):
    draft = "print([[CAS:a]])"
    repls = [
        CASResult(id="a", result_tex="1", result_py="1"),
        CASResult(id="a", result_tex="2", result_py="2"),
    ]
    with caplog.at_level(logging.WARNING):
        out = fill_placeholders(draft, repls)
    assert out.manim_code_final == "print({1})"
    assert "duplicate CAS id a" in caplog.text


def test_fill_unreplaced():
    with pytest.raises(ValueError):
        fill_placeholders("print([[CAS:a]])", [])
