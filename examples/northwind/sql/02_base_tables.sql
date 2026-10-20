-- Base tables carry no claim logic, so pipelines and administrators work on them normally.
CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.plans (
  plan_id      STRING NOT NULL COMMENT 'Plan identifier, for example PLAN-A',
  plan_name    STRING NOT NULL COMMENT 'Plan display name',
  sponsor_name STRING NOT NULL COMMENT 'Employer that sponsors the plan',
  plan_type    STRING NOT NULL COMMENT 'Plan type, for example 401(k)'
) CLUSTER BY (plan_id) COMMENT 'Retirement plans administered by Northwind.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.participants (
  participant_id STRING NOT NULL COMMENT 'Participant identifier, for example P-1001',
  plan_id        STRING NOT NULL COMMENT 'Plan the participant belongs to',
  first_name     STRING NOT NULL COMMENT 'First name',
  last_name      STRING NOT NULL COMMENT 'Last name',
  date_of_birth  DATE   NOT NULL COMMENT 'Date of birth',
  hire_date      DATE   NOT NULL COMMENT 'Date hired by the plan sponsor',
  status         STRING NOT NULL COMMENT 'active or terminated'
) CLUSTER BY (plan_id) COMMENT 'People enrolled in a plan.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.funds (
  fund_id       STRING       NOT NULL COMMENT 'Fund identifier',
  fund_name     STRING       NOT NULL COMMENT 'Fund name',
  asset_class   STRING       NOT NULL COMMENT 'Target date, US equity, International equity, Bond or Stable value',
  expense_ratio DECIMAL(6,4) NOT NULL COMMENT 'Annual expense ratio as a fraction: 0.0012 means 0.12 percent'
) COMMENT 'Investment options on the Northwind platform.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.account_balances (
  participant_id STRING        NOT NULL COMMENT 'Participant who owns the balance',
  plan_id        STRING        NOT NULL COMMENT 'Plan that holds the balance',
  fund_id        STRING        NOT NULL COMMENT 'Fund the balance is invested in',
  balance        DECIMAL(14,2) NOT NULL COMMENT 'Market value in US dollars',
  as_of_date     DATE          NOT NULL COMMENT 'Valuation date'
) CLUSTER BY (participant_id, plan_id) COMMENT 'Current balance per participant and fund.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.contributions (
  participant_id    STRING        NOT NULL COMMENT 'Participant the contribution belongs to',
  plan_id           STRING        NOT NULL COMMENT 'Plan that received the contribution',
  contribution_date DATE          NOT NULL COMMENT 'Payroll date',
  source            STRING        NOT NULL COMMENT 'employee_pretax, employee_roth or employer_match',
  amount            DECIMAL(12,2) NOT NULL COMMENT 'Amount in US dollars'
) CLUSTER BY (participant_id) COMMENT 'Payroll contributions in 2026.';
