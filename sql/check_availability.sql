-- Is OAuth custom identity claims support available in this workspace?
-- Run checks 1 and 2 in the SQL editor. Check 3 needs a service principal token (see README).

-- Check 1: does the workspace know the function? (Describes it without evaluating it.)
DESCRIBE FUNCTION current_oauth_custom_identity_claim;
--   A description comes back   -> available.
--   [UNRESOLVED_ROUTINE] ...    -> not available in this workspace yet.

-- Check 2: what happens without a claim? Your SQL editor session carries no claim.
SELECT current_oauth_custom_identity_claim() AS claim;
--   NULL                                        -> available. Claim-keyed views can be created by any identity.
--   [OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED]  -> available. Create claim-keyed views from a session that
--                                                  carries a claim (the bundle in this repo does that for you).
--   [UNRESOLVED_ROUTINE]                         -> not available yet.

-- Check 3: send this through the SQL Statement Execution API with a token minted with
-- custom_claim=availability-probe. It must return the claim and the service principal's application id.
SELECT current_oauth_custom_identity_claim() AS claim, session_user() AS caller;
