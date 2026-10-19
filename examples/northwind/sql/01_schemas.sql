-- Three schemas keep pipelines, policy and the portal apart.
CREATE SCHEMA IF NOT EXISTS `{{catalog}}`.`{{base}}`
  COMMENT 'Northwind base data. Written by pipelines and read by internal users. Never granted to the portal service principal.';
CREATE SCHEMA IF NOT EXISTS `{{catalog}}`.`{{gov}}`
  COMMENT 'Northwind entitlements and the policy view that resolves the custom claim. Never granted to the portal service principal.';
CREATE SCHEMA IF NOT EXISTS `{{catalog}}`.`{{portal}}`
  COMMENT 'Northwind portal views keyed on the custom identity claim. The only schema the portal service principal can read.';
