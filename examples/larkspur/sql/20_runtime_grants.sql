-- What the Larkspur portal can do at runtime: read the portal views. Nothing else.
-- Grants go to the application's account group, whose only member is its portal service principal. Rotate or
-- replace the service principal by changing group membership; no grant or policy changes.
-- No grants on {{base}} or {{gov}}: the views read those with their owner's rights.
GRANT USE CATALOG ON CATALOG `{{catalog}}` TO `{{portal_group}}`;
GRANT USE SCHEMA ON SCHEMA `{{catalog}}`.`{{portal}}` TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_access TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_claims TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_accumulators TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.sponsor_spend_summary TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.pharmacy_remittance TO `{{portal_group}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.drug_reference TO `{{portal_group}}`;
