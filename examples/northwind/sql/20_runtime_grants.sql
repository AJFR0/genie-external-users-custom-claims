-- What the Northwind portal can do at runtime: read the portal views. Nothing else.
-- Grants go to the application's account group, whose only member is its portal service principal. Rotate or
-- replace the service principal by changing group membership; no grant or policy changes.
-- No grants on {{base}} or {{gov}}: the views read those with their owner's rights.
GRANT USE CATALOG ON CATALOG `{{catalog}}` TO `{{portal_group}}`;
GRANT USE SCHEMA ON SCHEMA `{{catalog}}`.`{{portal}}` TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_access TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_accounts TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_contributions TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.plan_summary TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.plan_roster TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.fund_lineup TO `{{portal_group}}`;
