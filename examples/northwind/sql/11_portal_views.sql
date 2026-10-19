-- Portal views. None of them mentions the claim: they all join to governance.my_effective_grants.
-- Each scope is grouped first (one row per participant or plan), so a user with several matching
-- grants never sees duplicated rows. When grants disagree, the least restrictive one wins.

CREATE VIEW `{{catalog}}`.`{{portal}}`.my_access (
  role COMMENT 'Role of this grant: participant, sponsor or advisor',
  scope_type COMMENT 'participant or plan',
  scope_id COMMENT 'The participant or plan this grant covers',
  valid_from COMMENT 'First day of the grant',
  valid_to COMMENT 'Last day of the grant. NULL means open-ended.',
  can_view_own_accounts COMMENT 'May see own balances and contributions',
  can_view_plan_aggregates COMMENT 'May see plan totals',
  can_view_roster COMMENT 'May list plan participants',
  mask_dob COMMENT 'Date of birth is hidden in the roster'
)
COMMENT 'What the signed-in user is entitled to see. Use for questions like "what can I see?" or "what is my role?".'
AS SELECT role, scope_type, scope_id, valid_from, valid_to, can_view_own_accounts, can_view_plan_aggregates, can_view_roster, mask_dob
FROM `{{catalog}}`.`{{gov}}`.my_effective_grants;

CREATE VIEW `{{catalog}}`.`{{portal}}`.my_accounts (
  participant_id COMMENT 'Participant who owns the balance: the signed-in user',
  plan_id COMMENT 'Plan identifier: PLAN-A, PLAN-B or PLAN-C. Users call these Plan A, Plan B and Plan C.',
  plan_name COMMENT 'Plan name (the sponsor plan name, not Plan A or Plan B)',
  fund_name COMMENT 'Fund the money is invested in',
  asset_class COMMENT 'Fund asset class',
  balance COMMENT 'Market value in US dollars',
  as_of_date COMMENT 'Valuation date'
)
COMMENT 'Balances of the signed-in participant, one row per fund. Use for "my balance" questions. Empty for users who are not participants.'
AS
WITH my_participants AS (
  SELECT DISTINCT scope_id AS participant_id
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants
  WHERE scope_type = 'participant' AND can_view_own_accounts
)
SELECT b.participant_id, b.plan_id, pl.plan_name, f.fund_name, f.asset_class, b.balance, b.as_of_date
FROM `{{catalog}}`.`{{base}}`.account_balances AS b
JOIN my_participants AS m ON m.participant_id = b.participant_id
JOIN `{{catalog}}`.`{{base}}`.plans AS pl ON pl.plan_id = b.plan_id
JOIN `{{catalog}}`.`{{base}}`.funds AS f ON f.fund_id = b.fund_id;

CREATE VIEW `{{catalog}}`.`{{portal}}`.my_contributions (
  participant_id COMMENT 'Participant the contribution belongs to: the signed-in user',
  plan_id COMMENT 'Plan identifier: PLAN-A, PLAN-B or PLAN-C. Users call these Plan A, Plan B and Plan C.',
  plan_name COMMENT 'Plan name (the sponsor plan name, not Plan A or Plan B)',
  contribution_date COMMENT 'Payroll date',
  source COMMENT 'employee_pretax, employee_roth or employer_match',
  amount COMMENT 'Amount in US dollars'
)
COMMENT 'Payroll contributions of the signed-in participant in 2026. Empty for users who are not participants.'
AS
WITH my_participants AS (
  SELECT DISTINCT scope_id AS participant_id
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants
  WHERE scope_type = 'participant' AND can_view_own_accounts
)
SELECT c.participant_id, c.plan_id, pl.plan_name, c.contribution_date, c.source, c.amount
FROM `{{catalog}}`.`{{base}}`.contributions AS c
JOIN my_participants AS m ON m.participant_id = c.participant_id
JOIN `{{catalog}}`.`{{base}}`.plans AS pl ON pl.plan_id = c.plan_id;

CREATE VIEW `{{catalog}}`.`{{portal}}`.plan_summary (
  plan_id COMMENT 'Plan identifier: PLAN-A, PLAN-B or PLAN-C. Users call these Plan A, Plan B and Plan C.',
  plan_name COMMENT 'Plan name (the sponsor plan name, not Plan A or Plan B)',
  sponsor_name COMMENT 'Employer that sponsors the plan',
  fund_name COMMENT 'Fund',
  asset_class COMMENT 'Fund asset class',
  participants COMMENT 'Number of participants holding the fund',
  total_balance COMMENT 'Sum of balances in US dollars',
  average_balance COMMENT 'Average balance in US dollars',
  as_of_date COMMENT 'Valuation date'
)
COMMENT 'Plan totals by fund for the plans the signed-in user sponsors or advises. Sum total_balance for plan assets. Empty for participants.'
AS
WITH my_plans AS (
  SELECT DISTINCT scope_id AS plan_id
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants
  WHERE scope_type = 'plan' AND can_view_plan_aggregates
)
SELECT b.plan_id, pl.plan_name, pl.sponsor_name, f.fund_name, f.asset_class,
       COUNT(DISTINCT b.participant_id),
       CAST(SUM(b.balance) AS DECIMAL(16,2)),
       CAST(AVG(b.balance) AS DECIMAL(14,2)),
       MAX(b.as_of_date)
FROM `{{catalog}}`.`{{base}}`.account_balances AS b
JOIN my_plans AS m ON m.plan_id = b.plan_id
JOIN `{{catalog}}`.`{{base}}`.plans AS pl ON pl.plan_id = b.plan_id
JOIN `{{catalog}}`.`{{base}}`.funds AS f ON f.fund_id = b.fund_id
GROUP BY b.plan_id, pl.plan_name, pl.sponsor_name, f.fund_name, f.asset_class;

CREATE VIEW `{{catalog}}`.`{{portal}}`.plan_roster (
  participant_id COMMENT 'Participant identifier',
  plan_id COMMENT 'Plan identifier: PLAN-A, PLAN-B or PLAN-C. Users call these Plan A, Plan B and Plan C.',
  plan_name COMMENT 'Plan name (the sponsor plan name, not Plan A or Plan B)',
  first_name COMMENT 'First name',
  last_name COMMENT 'Last name',
  date_of_birth COMMENT 'Date of birth. NULL when the role of the signed-in user masks it.',
  hire_date COMMENT 'Hire date',
  status COMMENT 'active or terminated',
  total_balance COMMENT 'Total balance across funds in this plan, in US dollars'
)
COMMENT 'Participants of the plans the signed-in user sponsors or advises. Date of birth is masked for roles whose policy says so.'
AS
WITH roster_plans AS (
  SELECT scope_id AS plan_id, bool_and(mask_dob) AS mask_dob
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants
  WHERE scope_type = 'plan' AND can_view_roster
  GROUP BY scope_id
),
balances AS (
  SELECT participant_id, plan_id, SUM(balance) AS total_balance
  FROM `{{catalog}}`.`{{base}}`.account_balances
  GROUP BY participant_id, plan_id
)
SELECT p.participant_id, p.plan_id, pl.plan_name, p.first_name, p.last_name,
       CASE WHEN r.mask_dob THEN NULL ELSE p.date_of_birth END,
       p.hire_date, p.status, CAST(b.total_balance AS DECIMAL(16,2))
FROM `{{catalog}}`.`{{base}}`.participants AS p
JOIN roster_plans AS r ON r.plan_id = p.plan_id
JOIN `{{catalog}}`.`{{base}}`.plans AS pl ON pl.plan_id = p.plan_id
LEFT JOIN balances AS b ON b.participant_id = p.participant_id AND b.plan_id = p.plan_id;
