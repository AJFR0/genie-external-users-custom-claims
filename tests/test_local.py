import pytest

from claims_kit.local import LocalEnv, read_env


def test_read_env_file_with_environment_precedence(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# c\nDATABRICKS_HOST=https://h\nWAREHOUSE_ID='w1'\nCATALOG=c1\n")
    env = read_env({"CATALOG": "c2"}, dotenv_path=f)
    assert env == {"DATABRICKS_HOST": "https://h", "WAREHOUSE_ID": "w1", "CATALOG": "c2"}


def test_local_env_from_mapping():
    env = LocalEnv.from_mapping({"DATABRICKS_HOST": "https://h/", "WAREHOUSE_ID": "w", "NORTHWIND_CLIENT_ID": "a",
                                 "NORTHWIND_CLIENT_SECRET": "b", "NORTHWIND_GENIE_SPACE_ID": ""})
    assert env.host == "https://h" and env.catalog == "genie_claims_ref" and env.admin_profile is None
    assert env.examples["northwind"].client_id == "a" and env.examples["northwind"].genie_space_id is None
    assert "larkspur" not in env.examples


def test_local_env_reads_the_enforcement_model():
    base = {"DATABRICKS_HOST": "https://h", "WAREHOUSE_ID": "w"}
    assert LocalEnv.from_mapping(base).enforcement == "layered"
    assert LocalEnv.from_mapping({**base, "ENFORCEMENT": "views"}).enforcement == "views"
    with pytest.raises(ValueError):
        LocalEnv.from_mapping({**base, "ENFORCEMENT": "neither"})


def test_local_env_reads_the_tag_set():
    base = {"DATABRICKS_HOST": "https://h", "WAREHOUSE_ID": "w"}
    assert LocalEnv.from_mapping(base).tag_set == "governed"
    assert LocalEnv.from_mapping({**base, "TAG_SET": "stand_in"}).tag_set == "stand_in"
