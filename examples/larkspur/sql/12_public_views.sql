CREATE OR REPLACE VIEW `{{catalog}}`.`{{portal}}`.drug_reference (
  ndc COMMENT 'National Drug Code (synthetic)',
  drug_name COMMENT 'Drug and strength',
  drug_class COMMENT 'Therapeutic class',
  generic_flag COMMENT 'true for generics',
  specialty_flag COMMENT 'true for specialty drugs'
)
COMMENT 'Drug reference data. Same for every user.'
AS SELECT ndc, drug_name, drug_class, generic_flag, specialty_flag FROM `{{catalog}}`.`{{base}}`.drugs;
