-- Derived policy inputs. A row-filter function may read only tables without a policy of their own, so the facts the
-- rules need are copied into the governance schema. rf_plans uses this to let participants see the plans their own
-- accounts are in. Rebuilt on every deploy; in production, refresh it with the pipeline that loads the accounts.
CREATE OR REPLACE TABLE `{{catalog}}`.`{{gov}}`.participant_plans
COMMENT 'Policy input: which plans each participant holds accounts or contributions in. Read only by row-filter functions.'
AS
SELECT DISTINCT participant_id, plan_id FROM `{{catalog}}`.`{{base}}`.account_balances
UNION
SELECT DISTINCT participant_id, plan_id FROM `{{catalog}}`.`{{base}}`.contributions;
