-- Row-filter functions for the ABAC row policies (layered enforcement). Unity Catalog applies them to every base
-- table a portal view reads, for this application's account group only, so pipelines and administrators are
-- unaffected. Each function admits exactly the rows some portal view exposes from its table, for the signed-in user.
-- They read the claim through my_effective_grants, which also checks the service principal and the grant dates.
-- A policy function may read only tables without a policy of their own, so the functions read governance objects
-- only: the grants, the role policies and the derived participant_plans mapping.

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_accounts(p_participant_id STRING, p_plan_id STRING)
RETURNS BOOLEAN
COMMENT 'Balances: own accounts, or plans the signed-in user may total or list'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE (e.scope_type = 'participant' AND e.scope_id = p_participant_id AND e.can_view_own_accounts)
     OR (e.scope_type = 'plan' AND e.scope_id = p_plan_id AND (e.can_view_plan_aggregates OR e.can_view_roster))
);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_contributions(p_participant_id STRING)
RETURNS BOOLEAN
COMMENT 'Contributions: own only. Sponsors and advisors never reach contribution rows.'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'participant' AND e.scope_id = p_participant_id AND e.can_view_own_accounts
);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_roster(p_plan_id STRING)
RETURNS BOOLEAN
COMMENT 'Participants: plans whose roster the signed-in user may list'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'plan' AND e.scope_id = p_plan_id AND e.can_view_roster
);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_plans(p_plan_id STRING)
RETURNS BOOLEAN
COMMENT 'Plans: plans the signed-in user sponsors or advises, and the plans of their own accounts'
RETURN EXISTS (
  SELECT 1 FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'plan' AND e.scope_id = p_plan_id
) OR EXISTS (
  SELECT 1
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  JOIN `{{catalog}}`.`{{gov}}`.participant_plans AS pp ON pp.participant_id = e.scope_id
  WHERE e.scope_type = 'participant' AND e.can_view_own_accounts AND pp.plan_id = p_plan_id
);

CREATE OR REPLACE FUNCTION `{{catalog}}`.`{{gov}}`.rf_deny()
RETURNS BOOLEAN
COMMENT 'Default deny: no rows for tables without a portal grain tag'
RETURN false;
