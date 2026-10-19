-- The one place where the custom claim is read (the Northwind example explains the four conditions).
CREATE VIEW `{{catalog}}`.`{{gov}}`.my_effective_grants
COMMENT 'Active grants of the signed-in portal user, joined to their role policy. Answers only for the Larkspur portal service principal.'
AS
SELECT
  g.portal_user_id, g.role, g.scope_type, g.scope_id, g.valid_from, g.valid_to,
  p.detail_level, p.include_minor_dependents, p.mask_identity, p.min_cell_size
FROM `{{catalog}}`.`{{gov}}`.portal_user_grants AS g
JOIN `{{catalog}}`.`{{gov}}`.role_policies AS p ON p.role = g.role
WHERE g.portal_user_id = current_oauth_custom_identity_claim()
  AND session_user() = '{{portal_sp}}'
  AND current_date() >= g.valid_from
  AND (g.valid_to IS NULL OR current_date() <= g.valid_to);

-- A relationship rule derived from data, not from grant rows: a subscriber whose role includes minor
-- dependents also sees their children under 18. Spouses and adult children (18+) are never included.
CREATE VIEW `{{catalog}}`.`{{gov}}`.my_members
COMMENT 'Members whose claims the signed-in user may see, and why.'
AS
SELECT member_id, min(visible_as) AS visible_as
FROM (
  SELECT e.scope_id AS member_id, 'self' AS visible_as
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  WHERE e.scope_type = 'member' AND e.detail_level = 'own'
  UNION ALL
  SELECT m.member_id, 'minor dependent' AS visible_as
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants AS e
  JOIN `{{catalog}}`.`{{base}}`.members AS m ON m.subscriber_id = e.scope_id
  WHERE e.scope_type = 'member' AND e.detail_level = 'own' AND e.include_minor_dependents
    AND m.relationship = 'child'
    AND m.date_of_birth > add_months(current_date(), -216)
) AS visible
GROUP BY member_id;
