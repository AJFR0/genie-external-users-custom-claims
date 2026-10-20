-- Derived tables, rebuilt on every deploy. In production, refresh them with the pipeline that loads the claims.

-- Policy input: household relationships. A row-filter function may read only tables without a policy of their own,
-- so the household rule (subscribers see their children under 18) reads this copy, never the protected members table.
CREATE OR REPLACE TABLE `{{catalog}}`.`{{gov}}`.household
COMMENT 'Policy input: subscriber, relationship and date of birth for every member. Read only by governance views and row-filter functions.'
AS
SELECT member_id, subscriber_id, relationship, date_of_birth FROM `{{catalog}}`.`{{base}}`.members;

-- Precomputed spend cells. Aggregate-only roles read these instead of member-level claims, so a user's query is never
-- evaluated against the member rows behind a suppressed group. Groups smaller than the smallest minimum of any
-- aggregate role are never stored; the row policy on this table applies each role's own minimum.
INSERT OVERWRITE `{{catalog}}`.`{{base}}`.sponsor_spend_cells
SELECT c.sponsor_id,
       concat(CAST(year(c.fill_date) AS STRING), '-Q', CAST(quarter(c.fill_date) AS STRING)) AS fill_quarter,
       d.drug_class,
       COUNT(DISTINCT c.member_id) AS members,
       COUNT(*) AS claims,
       CAST(SUM(c.plan_paid) AS DECIMAL(14,2)) AS plan_paid,
       CAST(SUM(c.member_paid) AS DECIMAL(14,2)) AS member_paid,
       SUM(CASE WHEN d.generic_flag THEN 1 ELSE 0 END) AS generic_claims
FROM `{{catalog}}`.`{{base}}`.pharmacy_claims AS c
JOIN `{{catalog}}`.`{{base}}`.drugs AS d ON d.ndc = c.ndc
WHERE c.claim_status = 'paid'
GROUP BY c.sponsor_id, year(c.fill_date), quarter(c.fill_date), d.drug_class
HAVING COUNT(DISTINCT c.member_id) >= (
  SELECT min(min_cell_size) FROM `{{catalog}}`.`{{gov}}`.role_policies WHERE detail_level = 'aggregate');
