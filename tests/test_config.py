import pytest

from claims_kit.config import SQL_KEYS, load_example


@pytest.mark.parametrize("name,prefix", [("northwind", "pu-"), ("larkspur", "rx-")])
def test_examples_load(name, prefix):
    ex = load_example(name)
    assert ex.claim_prefix == prefix and set(ex.sql) == set(SQL_KEYS)
    assert ex.claim_views[0] == "governance.my_effective_grants"
    assert "my_access" in ex.portal_views and not set(ex.portal_views) & {v.split(".")[1] for v in ex.public_views}


def test_fq_and_template_values():
    ex = load_example("northwind")
    assert ex.fq("cat", "governance.my_effective_grants") == "`cat`.`northwind_governance`.`my_effective_grants`"
    assert ex.template_values("cat", "app-id", "me@example.com") == {
        "catalog": "cat", "base": "northwind_base", "gov": "northwind_governance", "portal": "northwind_portal",
        "portal_sp": "app-id", "view_owner": "me@example.com"}


def test_unknown_example():
    with pytest.raises(FileNotFoundError):
        load_example("nope")
