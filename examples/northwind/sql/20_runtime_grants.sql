-- What the Northwind portal service principal can do at runtime: read the portal views. Nothing else.
-- No grants on {{base}} or {{gov}}: the views read those with their owner's rights.
GRANT USE CATALOG ON CATALOG `{{catalog}}` TO `{{portal_sp}}`;
GRANT USE SCHEMA ON SCHEMA `{{catalog}}`.`{{portal}}` TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_access TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_accounts TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_contributions TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.plan_summary TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.plan_roster TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.fund_lineup TO `{{portal_sp}}`;
