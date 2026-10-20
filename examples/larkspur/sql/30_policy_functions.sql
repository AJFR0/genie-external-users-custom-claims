-- Row-filter functions for the ABAC row policies (layered enforcement). Unity Catalog applies them to every base
-- table a portal view reads, for this application's account group only, so pipelines and administrators are
-- unaffected. Each function admits exactly the rows some portal view exposes from its table, for the signed-in user.
-- They read the claim through my_effective_grants and policy_members, which also check the service principal and the
-- grant dates. A policy function may read only tables without a policy of their own, so the household rule comes
-- from the derived governance.household table, never from the protected members table.

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_members(p_member_id STRING)
RETURNS BOOLEAN
COMMENT 'Members: the signed-in user, and their children under 18 when the role includes minor dependents'
RETURN EXISTS (SELECT 1 FROM `{{catalog}}`.`{{gov}}`.policy_members AS mm WHERE mm.member_id = p_member_id);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_claims(p_member_id STRING, p_pharmacy_id STRING)
RETURNS BOOLEAN
COMMENT 'Claims: members the signed-in user may see, and claims filled at pharmacies the user works for'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.policy_members AS mm WHERE mm.member_id = p_member_id
) OR EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'pharmacy' AND e.detail_level = 'pharmacy' AND e.scope_id = p_pharmacy_id
);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_accumulators(p_member_id STRING)
RETURNS BOOLEAN
COMMENT 'Accumulators: members the signed-in user may see'
RETURN EXISTS (SELECT 1 FROM `{{catalog}}`.`{{gov}}`.policy_members AS mm WHERE mm.member_id = p_member_id);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_sponsors(p_sponsor_id STRING)
RETURNS BOOLEAN
COMMENT 'Sponsors: employers the signed-in user may see totals for. The client list stays private.'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'sponsor' AND e.detail_level = 'aggregate' AND e.scope_id = p_sponsor_id
);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_cells(p_sponsor_id STRING, p_members BIGINT)
RETURNS BOOLEAN
COMMENT 'Spend cells: sponsors in scope, and only groups at or above the role minimum group size'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'sponsor' AND e.detail_level = 'aggregate' AND e.scope_id = p_sponsor_id
    AND p_members >= e.min_cell_size
);

-- Column mask: members the user may see keep their id; claims reached only through a pharmacy grant that masks
-- identity get a one-way reference. Demo grade: in production use a keyed hash or a token vault.
CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.cm_member_id(p_member_id STRING, p_pharmacy_id STRING)
RETURNS STRING
COMMENT 'Member id, or a one-way reference for pharmacy staff'
RETURN CASE
  WHEN EXISTS (SELECT 1 FROM `{{catalog}}`.`{{gov}}`.policy_members AS mm WHERE mm.member_id = p_member_id) THEN p_member_id
  WHEN EXISTS (
    SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
    WHERE e.scope_type = 'pharmacy' AND e.detail_level = 'pharmacy' AND e.scope_id = p_pharmacy_id AND e.mask_identity
  ) THEN substr(sha2(concat('larkspur-demo:', p_member_id), 256), 1, 16)
  ELSE NULL
END;

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_deny()
RETURNS BOOLEAN
COMMENT 'Default deny: no rows for tables without a portal grain tag'
RETURN false;
