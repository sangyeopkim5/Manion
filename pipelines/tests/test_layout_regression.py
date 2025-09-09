import pathlib, sys
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from libs.layout import reading_order


def test_layout_regression():
    items = [
        {"bbox": [10, 0, 20, 10], "category": "Text", "text": "B"},
        {"bbox": [0, 0, 10, 10], "category": "Text", "text": "A"},
        {"bbox": [0, 20, 10, 30], "category": "Text", "text": "C"},
    ]
    ordered = reading_order(items)
    assert [i["text"] for i in ordered] == ["A", "B", "C"]
