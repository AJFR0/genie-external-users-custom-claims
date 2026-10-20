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

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_claims(p_member_id STRING)
RETURNS BOOLEAN
COMMENT 'Claims: members the signed-in user may see. Pharmacy staff read precomputed remittance rows instead.'
RETURN EXISTS (SELECT 1 FROM `{{catalog}}`.`{{gov}}`.policy_members AS mm WHERE mm.member_id = p_member_id);

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

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_remittance(p_pharmacy_id STRING)
RETURNS BOOLEAN
COMMENT 'Remittance rows: claims filled at pharmacies the signed-in user works for'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'pharmacy' AND e.detail_level = 'pharmacy' AND e.scope_id = p_pharmacy_id
);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_deny()
RETURNS BOOLEAN
COMMENT 'Default deny: no rows for tables without a portal grain tag'
RETURN false;
