"""The claim-value rule. The claim is an opaque application user id taken from a server-side session."""
from __future__ import annotations

import re

# Lowercase letters, digits and . _ : - ; 1-128 characters; starts with a letter or digit.
# Tighten this to your own id format (for example, a lowercase UUID).
CLAIM_PATTERN = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")


class InvalidClaim(ValueError):
    """Raised when a value can't be used as a custom identity claim."""


def validate_claim(value: object) -> str:
    """Return value unchanged if it is a canonical claim, else raise InvalidClaim.

    Unity Catalog trims surrounding spaces from the claim and keeps its case, so the backend
    must reject anything that isn't already canonical before it mints a token.
    """
    if not isinstance(value, str) or CLAIM_PATTERN.fullmatch(value) is None:
        raise InvalidClaim("claim must be 1-128 characters of [a-z0-9._:-] and start with a letter or digit")
    return value
