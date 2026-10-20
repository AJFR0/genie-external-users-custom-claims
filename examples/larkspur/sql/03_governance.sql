CREATE OR REPLACE TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants (
  portal_user_id STRING    NOT NULL COMMENT 'Opaque application user id. This exact value travels in the custom claim.',
  role           STRING    NOT NULL COMMENT 'subscriber, member, sponsor_admin, consultant or pharmacy. Joins to role_policies.',
  scope_type     STRING    NOT NULL COMMENT 'member, sponsor or pharmacy',
  scope_id       STRING    NOT NULL COMMENT 'A member_id, sponsor_id or pharmacy_id, matching scope_type',
  valid_from     DATE      NOT NULL COMMENT 'First day the grant applies',
  valid_to       DATE               COMMENT 'Last day the grant applies. NULL means open-ended.',
  granted_by     STRING             COMMENT 'Who created the grant',
  granted_at     TIMESTAMP          COMMENT 'When the grant was created'
) CLUSTER BY (portal_user_id) COMMENT 'Per-user entitlements for the Larkspur portal.';

-- regexp_extract instead of RLIKE '^...$': in Java regex `$` also matches before a trailing newline.
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT claim_format CHECK (regexp_extract(portal_user_id, '^[a-z0-9][a-z0-9._:-]{0,127}', 0) = portal_user_id);
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT known_role CHECK (role IN ('subscriber', 'member', 'sponsor_admin', 'consultant', 'pharmacy'));
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT known_scope CHECK (scope_type IN ('member', 'sponsor', 'pharmacy'));
ALTER TABLE `{{catalog}}`.`{{gov}}`.portal_user_grants ADD CONSTRAINT valid_window CHECK (valid_to IS NULL OR valid_to >= valid_from);

CREATE OR REPLACE TABLE `{{catalog}}`.`{{gov}}`.role_policies (
  role                     STRING  NOT NULL COMMENT 'Role name used in portal_user_grants',
  detail_level             STRING  NOT NULL COMMENT 'own (member data), aggregate (sponsor totals) or pharmacy (remittance)',
  include_minor_dependents BOOLEAN NOT NULL COMMENT 'A subscriber also sees claims of their children under 18',
  mask_identity            BOOLEAN NOT NULL COMMENT 'Replace member identifiers with a one-way reference',
  min_cell_size            INT     NOT NULL COMMENT 'Aggregate groups with fewer distinct members are hidden'
) COMMENT 'Per-role entitlements for the Larkspur portal.';

ALTER TABLE `{{catalog}}`.`{{gov}}`.role_policies ADD CONSTRAINT known_detail CHECK (detail_level IN ('own', 'aggregate', 'pharmacy'));
ALTER TABLE `{{catalog}}`.`{{gov}}`.role_policies ADD CONSTRAINT non_negative_cell CHECK (min_cell_size >= 0);
