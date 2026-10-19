-- The one place where the custom claim is read. Every portal view joins to this view.
-- A grant counts only when ALL of these hold:
--   1. it belongs to the user named in the signed token     current_oauth_custom_identity_claim()
--   2. the caller is this application's service principal    session_user()
--   3. today is inside the grant's validity window
--   4. the grant's role has a policy row
-- A missing, unknown or malformed claim matches no grant, so every portal view returns no rows.
CREATE VIEW `{{catalog}}`.`{{gov}}`.my_effective_grants
COMMENT 'Active grants of the signed-in portal user, joined to their role policy. Answers only for the Northwind portal service principal.'
AS
SELECT
  g.portal_user_id, g.role, g.scope_type, g.scope_id, g.valid_from, g.valid_to,
  p.can_view_own_accounts, p.can_view_plan_aggregates, p.can_view_roster, p.mask_dob
FROM `{{catalog}}`.`{{gov}}`.portal_user_grants AS g
JOIN `{{catalog}}`.`{{gov}}`.role_policies AS p ON p.role = g.role
WHERE g.portal_user_id = current_oauth_custom_identity_claim()
  AND session_user() = '{{portal_sp}}'
  AND current_date() >= g.valid_from
  AND (g.valid_to IS NULL OR current_date() <= g.valid_to);
