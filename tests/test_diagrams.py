import xml.etree.ElementTree as ET

from docs.diagrams.build_diagrams import DIAGRAMS


def test_every_diagram_is_valid_svg_with_text():
    assert set(DIAGRAMS) == {"previous-patterns", "request-flow", "layers", "entitlement-route", "object-map", "deploy-flow", "decision-tree"}
    for name, build in DIAGRAMS.items():
        root = ET.fromstring(build().render())
        texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text") if t.text]
        assert root.get("viewBox") and len(texts) >= 8, name
        assert not any("\u2014" in t for t in texts), f"{name}: no em dashes in public text"
