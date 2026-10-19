"""Three checks that tell you whether OAuth custom identity claims work in this workspace.

1. Does the SQL function resolve?                      DESCRIBE FUNCTION (does not evaluate it)
2. What happens without a claim?                       NULL, or OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED
3. Can the portal service principal mint a token with
   custom_claim, and does SQL read it back?            token request + Statement API round trip
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable

from .sql import StatementError, StatementRunner
from .tokens import TokenError, mint_claim_token

PROBE_CLAIM = "availability-probe"
NO_CLAIM_SQL = "SELECT current_oauth_custom_identity_claim() AS claim"
DESCRIBE_SQL = "DESCRIBE FUNCTION current_oauth_custom_identity_claim"
ROUNDTRIP_SQL = "SELECT current_oauth_custom_identity_claim() AS claim, session_user() AS caller"
_NOT_FOUND = ("UNRESOLVED_ROUTINE", "ROUTINE_NOT_FOUND", "CANNOT BE FOUND")
_EXPLAIN = {
    "null": "returns NULL; claim-keyed views can be created by any identity",
    "throws": "raises OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED; claim-keyed views are created from a claim-carrying session",
    "unavailable": "is not available in this workspace yet",
    "unknown": "returned something unexpected",
}


def classify_no_claim(run_scalar: Callable[[str], object]) -> str:
    """'null' | 'throws' | 'unavailable' | 'unknown' for a session that carries no claim."""
    try:
        value = run_scalar(NO_CLAIM_SQL)
    except Exception as exc:  # engines raise different exception types
        text = str(exc).upper()
        if "OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED" in text:
            return "throws"
        if any(k in text for k in _NOT_FOUND):
            return "unavailable"
        return "unknown"
    return "null" if value is None else "unknown"


def function_available(run_any: Callable[[str], object]) -> bool:
    try:
        run_any(DESCRIBE_SQL)
        return True
    except Exception as exc:
        if any(k in str(exc).upper() for k in _NOT_FOUND):
            return False
        raise


@dataclass
class AvailabilityReport:
    function_available: bool
    no_claim_behavior: str
    mint_status: str
    mint_detail: str = ""
    echoed_claim: str | None = None
    caller: str | None = None

    @property
    def ready(self) -> bool:
        return self.function_available and self.mint_status == "ok" and self.echoed_claim == PROBE_CLAIM

    @property
    def deploy_mode(self) -> str:
        """How claim-keyed views must be created: 'null' = directly, 'throws' = from a claim-carrying session."""
        return "null" if self.no_claim_behavior == "null" else "throws"

    def lines(self) -> list[str]:
        out = [
            f"1. Function resolves in this workspace: {'yes' if self.function_available else 'NO'}",
            f"2. Without a claim the function {_EXPLAIN[self.no_claim_behavior]}",
            f"3. Token with custom_claim: {self.mint_status}" + (f" ({self.mint_detail})" if self.mint_detail else ""),
            f"4. SQL read back claim {self.echoed_claim!r} for caller {self.caller!r}",
        ]
        if self.ready:
            how = "directly" if self.deploy_mode == "null" else "from a claim-carrying session"
            out.append(f"READY: claim-keyed views will be created {how}.")
        else:
            out.append("NOT READY: see the lines above.")
        return out


def run_availability(*, admin_scalar, admin_any, mint, sp_runner_for) -> AvailabilityReport:
    """admin_* run SQL as the deploying identity (no claim). mint(claim) mints for the portal SP.
    sp_runner_for(claim) returns a StatementRunner that authenticates with that claim."""
    report = AvailabilityReport(function_available=function_available(admin_any),
                                no_claim_behavior=classify_no_claim(admin_scalar), mint_status="error")
    try:
        mint(PROBE_CLAIM)
        report.mint_status = "ok"
    except TokenError as exc:
        report.mint_status = "not_enabled" if exc.custom_claim_not_enabled else "error"
        report.mint_detail = f"HTTP {exc.status}: {exc.body[:200]}"
        return report
    try:
        row = sp_runner_for(PROBE_CLAIM).execute(ROUNDTRIP_SQL).rows[0]
        report.echoed_claim, report.caller = row[0], row[1]
    except StatementError as exc:
        report.mint_detail = f"SQL round trip failed: {exc.message[:200]}"
    return report


def main(argv: list[str] | None = None) -> int:
    from .local import LocalEnv, admin_client, read_env
    from .tokens import ClaimTokenProvider

    parser = argparse.ArgumentParser(description="Check custom identity claim availability")
    parser.add_argument("--example", default="northwind", help="whose portal service principal to use")
    args = parser.parse_args(argv)
    env = LocalEnv.from_mapping(read_env())
    creds = env.examples[args.example]
    admin = StatementRunner(env.host, env.warehouse_id, admin_client(env.admin_profile).config.authenticate)
    provider = ClaimTokenProvider(env.host, creds.client_id, creds.client_secret)
    report = run_availability(
        admin_scalar=lambda q: admin.execute(q).scalar(),
        admin_any=lambda q: admin.execute(q).rows,
        mint=lambda claim: mint_claim_token(env.host, creds.client_id, creds.client_secret, claim),
        sp_runner_for=lambda claim: StatementRunner(env.host, env.warehouse_id, provider.auth_for(claim)),
    )
    print("\n".join(report.lines()))
    return 0 if report.ready else 1


if __name__ == "__main__":
    sys.exit(main())
