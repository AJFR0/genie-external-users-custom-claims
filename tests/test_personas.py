import pytest

from claims_kit.claims import validate_claim
from claims_kit.config import load_example
from claims_kit.personas import load_fixtures

EXAMPLES = ["northwind", "larkspur"]


@pytest.mark.parametrize("name", EXAMPLES)
def test_fixtures_cover_every_portal_view(name):
    ex = load_example(name)
    fx = load_fixtures(ex)
    for p in fx.personas:
        assert validate_claim(p.claim).startswith(ex.claim_prefix)
        assert set(fx.views[p.id]) == set(ex.portal_views)
    assert any(not any(e.ids for e in fx.views[p.id].values()) for p in fx.personas), "need a persona with no entitlements"


@pytest.mark.parametrize("name", EXAMPLES)
def test_genie_values_are_distinguishable(name):
    fx = load_fixtures(load_example(name))
    for p in fx.personas:
        for case in p.genie:
            for m in case.must:
                for n in case.must_not:
                    a, b = fx.genie_values[m], fx.genie_values[n]
                    assert abs(a - b) / max(abs(a), abs(b)) > 0.01, (p.id, m, n)


def test_unknown_genie_value_is_reported(monkeypatch):
    import examples.northwind.expectations as exp
    monkeypatch.setattr(exp, "genie_values", lambda data: {})
    with pytest.raises(ValueError, match="unknown genie value"):
        load_fixtures(load_example("northwind"))
