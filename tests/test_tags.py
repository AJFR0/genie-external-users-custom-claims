import pytest

from claims_kit.tags import TAG_SETS, Tag, load_tag_set


def test_governed_set_uses_two_keys_with_values():
    t = load_tag_set("governed")
    assert t.grain("accounts") == Tag("portal_grain", "accounts")
    assert t.key("member").condition() == "has_tag_value('portal_key', 'member')"
    assert t.key("member").assignment() == "'portal_key' = 'member'"
    assert t.any_grain() == "has_tag('portal_grain')"


def test_stand_in_set_is_key_only_distinct_system_tags():
    t = load_tag_set("stand_in")
    tags = [*t.grains.values(), *t.keys.values()]
    assert all(x.value is None and x.key.startswith("class.") for x in tags)
    assert len({x.key for x in tags}) == len(tags)
    g = t.grain("accounts")
    assert g.condition() == f"has_tag('{g.key}')" and g.assignment() == f"'{g.key}'"
    assert t.any_grain().count(" OR ") == len(t.grains) - 1


def test_both_sets_map_the_same_logical_tags():
    a, b = (load_tag_set(n) for n in TAG_SETS)
    assert set(a.grains) == set(b.grains) and set(a.keys) == set(b.keys)


def test_unknown_set_is_rejected():
    with pytest.raises(ValueError, match="unknown tag set"):
        load_tag_set("everything")


def test_unsafe_tag_names_are_rejected():
    with pytest.raises(ValueError, match="unsafe"):
        Tag("x'); DROP TABLE t; --")


def test_stand_in_must_map_every_logical_tag(tmp_path):
    p = tmp_path / "tags.yml"
    p.write_text("grains: [a, b]\nkeys: [k]\nsets:\n  governed: {grain_key: g, key_key: kk}\n"
                 "  stand_in:\n    grains: {a: class.x}\n    keys: {k: class.y}\n")
    with pytest.raises(ValueError, match="no mapping"):
        load_tag_set("stand_in", p)


def test_stand_in_rejects_a_reused_key(tmp_path):
    p = tmp_path / "tags.yml"
    p.write_text("grains: [a, b]\nkeys: [k]\nsets:\n  governed: {grain_key: g, key_key: kk}\n"
                 "  stand_in:\n    grains: {a: class.x, b: class.x}\n    keys: {k: class.y}\n")
    with pytest.raises(ValueError, match="reused"):
        load_tag_set("stand_in", p)
