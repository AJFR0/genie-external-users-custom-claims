import pytest

from claims_kit.claims import InvalidClaim, validate_claim


@pytest.mark.parametrize("value", ["pu-1001", "rx-9999", "deploy-session", "a", "u.123:x_y-z"])
def test_valid_claims(value):
    assert validate_claim(value) == value


@pytest.mark.parametrize("value", ["", " pu-1001", "pu-1001 ", "PU-1001", "pu-1001\t", "pu-1001' OR '1'='1", "%", "-x", "x" * 129, None, 5])
def test_invalid_claims(value):
    with pytest.raises(InvalidClaim):
        validate_claim(value)
