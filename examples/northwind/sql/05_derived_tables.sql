-- Derived policy inputs. A row-filter function may read only tables without a policy of their own, so the facts the
-- rules need are copied into the governance schema. rf_plans uses this to let participants see the plans their own
-- accounts are in. Rebuilt on every deploy; in production, refresh it with the pipeline that loads the accounts.
CREATE OR REPLACE TABLE `{{catalog}}`.`{{gov}}`.participant_plans
COMMENT 'Policy input: which plans each participant holds accounts or contributions in. Read only by row-filter functions.'
AS
SELECT DISTINCT participant_id, plan_id FROM `{{catalog}}`.`{{base}}`.account_balances
UNION
SELECT DISTINCT participant_id, plan_id FROM `{{catalog}}`.`{{base}}`.contributions;

-- Precomputed totals for sponsors and advisors (see 02_base_tables.sql). A row policy can only admit whole rows, so
-- a role entitled to totals reads totals: it then never reaches the per-fund balances behind them, even through a
-- mistaken grant or a probing question.
INSERT OVERWRITE `{{catalog}}`.`{{base}}`.plan_fund_balances
SELECT plan_id, fund_id, COUNT(DISTINCT participant_id), CAST(SUM(balance) AS DECIMAL(16,2)),
       CAST(AVG(balance) AS DECIMAL(14,2)), MAX(as_of_date)
FROM `{{catalog}}`.`{{base}}`.account_balances
GROUP BY plan_id, fund_id;

INSERT OVERWRITE `{{catalog}}`.`{{base}}`.participant_plan_balances
SELECT participant_id, plan_id, CAST(SUM(balance) AS DECIMAL(16,2))
FROM `{{catalog}}`.`{{base}}`.account_balances
GROUP BY participant_id, plan_id;
