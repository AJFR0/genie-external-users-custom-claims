-- What the Larkspur portal service principal can do at runtime: read the portal views. Nothing else.
GRANT USE CATALOG ON CATALOG `{{catalog}}` TO `{{portal_sp}}`;
GRANT USE SCHEMA ON SCHEMA `{{catalog}}`.`{{portal}}` TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_access TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_claims TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.my_accumulators TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.sponsor_spend_summary TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.pharmacy_remittance TO `{{portal_sp}}`;
GRANT SELECT ON VIEW `{{catalog}}`.`{{portal}}`.drug_reference TO `{{portal_sp}}`;
