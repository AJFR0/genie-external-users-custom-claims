-- Public reference data: the same for every user, so no claim is involved and prompt matching can stay on.
CREATE OR REPLACE VIEW `{{catalog}}`.`{{portal}}`.fund_lineup (
  fund_id COMMENT 'Fund identifier',
  fund_name COMMENT 'Fund name',
  asset_class COMMENT 'Asset class',
  expense_ratio COMMENT 'Annual expense ratio as a fraction: 0.0012 means 0.12 percent'
)
COMMENT 'Funds offered on the Northwind platform. Same for every user.'
AS SELECT fund_id, fund_name, asset_class, expense_ratio FROM `{{catalog}}`.`{{base}}`.funds;
