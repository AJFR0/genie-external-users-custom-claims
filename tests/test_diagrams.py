import xml.etree.ElementTree as ET

from docs.diagrams.build_diagrams import DIAGRAMS


def test_every_diagram_is_valid_svg_with_text():
    assert set(DIAGRAMS) == {"previous-patterns", "request-flow", "layers", "entitlement-route", "object-map", "deploy-flow",
                             "decision-tree", "failure-matrix"}
    for name, build in DIAGRAMS.items():
        root = ET.fromstring(build().render())
        texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text") if t.text]
        assert root.get("viewBox") and len(texts) >= 8, name
        assert not any("\u2014" in t for t in texts), f"{name}: no em dashes in public text"



def _texts(name):
    root = ET.fromstring(DIAGRAMS[name]().render())
    return " ".join(t.text for t in root.iter("{http://www.w3.org/2000/svg}text") if t.text)


def test_layers_diagram_has_five_layers_including_row_policies():
    text = _texts("layers")
    assert "Five layers" in text and "Row policies" in text
    assert all(f"{i}  " in text for i in range(1, 6))


def test_failure_matrix_compares_the_three_models_on_six_mistakes():
    text = _texts("failure-matrix")
    for heading in ("Views only", "ABAC only", "Layered"):
        assert heading in text
    for mistake in ("Error probe", "New table", "View without its filter", "Tag removed", "Policy names another group",
                    "Base table granted"):
        assert mistake in text, mistake
