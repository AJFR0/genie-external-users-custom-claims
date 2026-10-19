import pytest

from claims_kit.claims import InvalidClaim
from claims_kit.tokens import ClaimTokenProvider, MintedToken, TokenError, decode_jwt_unverified, mint_claim_token
from conftest import FakeResponse, make_jwt


def test_mint_sends_custom_claim_and_basic_auth(fake_http):
    fake_http.route("POST", "/oidc/v1/token", FakeResponse(200, {"access_token": "t1", "expires_in": 3600}))
    tok = mint_claim_token("https://h/", "cid", "sec", "pu-1001", http=fake_http, now=lambda: 100.0)
    call = fake_http.calls[0]
    assert call["url"] == "https://h/oidc/v1/token"
    assert call["data"] == {"grant_type": "client_credentials", "scope": "all-apis", "custom_claim": "pu-1001"}
    assert call["auth"] == ("cid", "sec")
    assert tok == MintedToken("t1", 3700.0, "pu-1001")


def test_mint_without_claim_omits_parameter(fake_http):
    fake_http.route("POST", "/oidc/v1/token", FakeResponse(200, {"access_token": "t", "expires_in": 60}))
    mint_claim_token("https://h", "c", "s", None, http=fake_http)
    assert "custom_claim" not in fake_http.calls[0]["data"]


def test_mint_403_not_enabled(fake_http):
    fake_http.route("POST", "/oidc/v1/token", FakeResponse(403, text='{"error":"custom_claim is not enabled for account"}'))
    with pytest.raises(TokenError) as err:
        mint_claim_token("https://h", "c", "s", "pu-1", http=fake_http)
    assert err.value.status == 403 and err.value.custom_claim_not_enabled


def test_decode_jwt_unverified():
    decoded = decode_jwt_unverified(make_jwt({"custom": {"claim": "pu-1001"}, "sub": "app"}))
    assert decoded["payload"]["custom"]["claim"] == "pu-1001" and decoded["header"]["alg"] == "RS256"


def test_decode_rejects_non_jwt():
    with pytest.raises(ValueError):
        decode_jwt_unverified("abc")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _minter(log):
    def mint(host, cid, secret, claim):
        log.append(claim)
        return MintedToken(f"tok-{claim}-{len(log)}", 1000.0 + 3600, claim)
    return mint


def test_provider_caches_until_refresh_margin():
    log, clock = [], Clock()
    p = ClaimTokenProvider("h", "c", "s", minter=_minter(log), now=clock, refresh_margin_s=300)
    t1, hit1 = p.token_for("pu-1001")
    t2, hit2 = p.token_for("pu-1001")
    assert (hit1, hit2) == (False, True) and t1 == t2
    clock.t = 1000.0 + 3600 - 299
    _, hit3 = p.token_for("pu-1001")
    assert hit3 is False and len(log) == 2


def test_provider_keys_cache_by_claim():
    log = []
    p = ClaimTokenProvider("h", "c", "s", minter=_minter(log), now=Clock())
    p.token_for("pu-1001")
    p.token_for("pu-1002")
    assert log == ["pu-1001", "pu-1002"]


@pytest.mark.parametrize("bad", [" pu-1001 ", "PU-1001", "pu-1001\t", "pu-1001' OR '1'='1", ""])
def test_provider_rejects_bad_claims_before_minting(bad):
    log = []
    p = ClaimTokenProvider("h", "c", "s", minter=_minter(log), now=Clock())
    with pytest.raises(InvalidClaim):
        p.token_for(bad)
    assert log == []


def test_auth_for_returns_bearer_header():
    p = ClaimTokenProvider("h", "c", "s", minter=_minter([]), now=Clock())
    assert p.auth_for("pu-1001")() == {"Authorization": "Bearer tok-pu-1001-1"}


def test_forget_forces_new_mint_and_mint_raw_skips_validation():
    log = []
    p = ClaimTokenProvider("h", "c", "s", minter=_minter(log), now=Clock())
    p.token_for("pu-1001")
    p.forget("pu-1001")
    p.token_for("pu-1001")
    assert log == ["pu-1001", "pu-1001"]
    assert p.mint_raw("pu-1001' OR '1'='1").claim == "pu-1001' OR '1'='1"
    assert p.client_id == "c"
