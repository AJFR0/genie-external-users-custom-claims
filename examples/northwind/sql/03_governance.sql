-- Per-user entitlements. One row per user, role and scope; a user with two roles has two rows.
CREATE OR REPLACE TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants (
  portal_user_id STRING    NOT NULL COMMENT 'Opaque application user id. This exact value travels in the custom claim.',
  role           STRING    NOT NULL COMMENT 'participant, sponsor or advisor. Joins to role_policies.',
  scope_type     STRING    NOT NULL COMMENT 'participant (one person) or plan (a whole plan)',
  scope_id       STRING    NOT NULL COMMENT 'A participant_id when scope_type is participant, a plan_id when it is plan',
  valid_from     DATE      NOT NULL COMMENT 'First day the grant applies',
  valid_to       DATE               COMMENT 'Last day the grant applies. NULL means open-ended.',
  granted_by     STRING             COMMENT 'Who created the grant: seed, admin console or a provisioning job',
  granted_at     TIMESTAMP          COMMENT 'When the grant was created'
) COMMENT 'Per-user entitlements for the Northwind portal.';

-- regexp_extract instead of RLIKE '^...$': in Java regex `$` also matches before a trailing newline.
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT claim_format CHECK (regexp_extract(portal_user_id, '^[a-z0-9][a-z0-9._:-]{0,127}', 0) = portal_user_id);
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT known_role CHECK (role IN ('participant', 'sponsor', 'advisor'));
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT known_scope CHECK (scope_type IN ('participant', 'plan'));
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT valid_window CHECK (valid_to IS NULL OR valid_to >= valid_from);

-- Per-role entitlements. Change a row here and every user with that role changes on their next question.
CREATE OR REPLACE TABLE `{{catalog}}`.`{{gov}}`.role_policies (
  role                     STRING  NOT NULL COMMENT 'Role name used in portal_user_grants',
  can_view_own_accounts    BOOLEAN NOT NULL COMMENT 'May see balances and contributions of the participant in scope',
  can_view_plan_aggregates BOOLEAN NOT NULL COMMENT 'May see plan totals for plans in scope',
  can_view_roster          BOOLEAN NOT NULL COMMENT 'May list the participants of plans in scope',
  mask_dob                 BOOLEAN NOT NULL COMMENT 'Hide date of birth in the roster'
) COMMENT 'Per-role entitlements for the Northwind portal.';
