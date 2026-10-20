CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.sponsors (
  sponsor_id   STRING NOT NULL COMMENT 'Plan sponsor (employer) identifier, for example SPN-ALDER',
  sponsor_name STRING NOT NULL COMMENT 'Employer name',
  industry     STRING NOT NULL COMMENT 'Employer industry'
) CLUSTER BY (sponsor_id) COMMENT 'Employers whose pharmacy benefits Larkspur manages.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.plans (
  plan_id    STRING        NOT NULL COMMENT 'Pharmacy benefit plan identifier',
  sponsor_id STRING        NOT NULL COMMENT 'Sponsor that offers the plan',
  plan_name  STRING        NOT NULL COMMENT 'Plan name',
  plan_year  INT           NOT NULL COMMENT 'Plan year',
  deductible DECIMAL(10,2) NOT NULL COMMENT 'Annual pharmacy deductible per member in US dollars',
  oop_max    DECIMAL(10,2) NOT NULL COMMENT 'Annual out-of-pocket maximum per member in US dollars'
) COMMENT 'Pharmacy benefit plans for the 2026 plan year.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.members (
  member_id     STRING NOT NULL COMMENT 'Member identifier, for example M-1001',
  subscriber_id STRING NOT NULL COMMENT 'member_id of the employee whose coverage this member is on',
  relationship  STRING NOT NULL COMMENT 'subscriber, spouse or child',
  first_name    STRING NOT NULL COMMENT 'First name',
  last_name     STRING NOT NULL COMMENT 'Last name',
  date_of_birth DATE   NOT NULL COMMENT 'Date of birth',
  sponsor_id    STRING NOT NULL COMMENT 'Sponsor of the coverage',
  plan_id       STRING NOT NULL COMMENT 'Plan'
) CLUSTER BY (member_id) COMMENT 'Covered people. Dependents carry the subscriber_id of the employee.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.pharmacies (
  pharmacy_id   STRING NOT NULL COMMENT 'Pharmacy identifier, for example PH-0007',
  pharmacy_name STRING NOT NULL COMMENT 'Pharmacy name',
  city          STRING NOT NULL COMMENT 'City',
  state         STRING NOT NULL COMMENT 'State',
  network_type  STRING NOT NULL COMMENT 'retail, mail or specialty'
) COMMENT 'Network pharmacies.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.drugs (
  ndc            STRING  NOT NULL COMMENT 'National Drug Code. Synthetic values in this example.',
  drug_name      STRING  NOT NULL COMMENT 'Drug name and strength',
  drug_class     STRING  NOT NULL COMMENT 'Therapeutic class',
  generic_flag   BOOLEAN NOT NULL COMMENT 'true for generic drugs',
  specialty_flag BOOLEAN NOT NULL COMMENT 'true for specialty drugs'
) COMMENT 'Drug reference data.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.pharmacy_claims (
  claim_id        STRING        NOT NULL COMMENT 'Claim identifier',
  member_id       STRING        NOT NULL COMMENT 'Member the prescription was filled for',
  sponsor_id      STRING        NOT NULL COMMENT 'Sponsor of the coverage',
  plan_id         STRING        NOT NULL COMMENT 'Plan',
  pharmacy_id     STRING        NOT NULL COMMENT 'Pharmacy that filled the prescription',
  ndc             STRING        NOT NULL COMMENT 'Drug dispensed',
  fill_date       DATE          NOT NULL COMMENT 'Date filled',
  quantity        DECIMAL(10,2) NOT NULL COMMENT 'Quantity dispensed',
  days_supply     INT           NOT NULL COMMENT 'Days supply',
  ingredient_cost DECIMAL(12,2) NOT NULL COMMENT 'Ingredient cost in US dollars',
  dispensing_fee  DECIMAL(8,2)  NOT NULL COMMENT 'Dispensing fee in US dollars',
  plan_paid       DECIMAL(12,2) NOT NULL COMMENT 'Amount paid by the plan in US dollars',
  member_paid     DECIMAL(12,2) NOT NULL COMMENT 'Amount paid by the member (copay or coinsurance) in US dollars',
  claim_status    STRING        NOT NULL COMMENT 'paid, reversed or rejected'
) CLUSTER BY (member_id) COMMENT 'Adjudicated pharmacy claims, January to September 2026.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.accumulators (
  member_id      STRING        NOT NULL COMMENT 'Member',
  plan_year      INT           NOT NULL COMMENT 'Plan year',
  deductible     DECIMAL(10,2) NOT NULL COMMENT 'Annual deductible in US dollars',
  deductible_met DECIMAL(10,2) NOT NULL COMMENT 'Deductible met so far in US dollars',
  oop_max        DECIMAL(10,2) NOT NULL COMMENT 'Annual out-of-pocket maximum in US dollars',
  oop_met        DECIMAL(10,2) NOT NULL COMMENT 'Out-of-pocket spending so far in US dollars'
) CLUSTER BY (member_id) COMMENT 'Deductible and out-of-pocket accumulators per member.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.sponsor_spend_cells (
  sponsor_id     STRING        NOT NULL COMMENT 'Plan sponsor (employer) identifier',
  fill_quarter   STRING        NOT NULL COMMENT 'Calendar quarter, for example 2026-Q1',
  drug_class     STRING        NOT NULL COMMENT 'Therapeutic class',
  members        BIGINT        NOT NULL COMMENT 'Distinct members with a paid claim in this group',
  claims         BIGINT        NOT NULL COMMENT 'Paid claims in this group',
  plan_paid      DECIMAL(14,2)          COMMENT 'Paid by the plan in US dollars',
  member_paid    DECIMAL(14,2)          COMMENT 'Paid by members in US dollars',
  generic_claims BIGINT                 COMMENT 'Paid claims for generic drugs'
) CLUSTER BY (sponsor_id) COMMENT 'Paid spend by sponsor, quarter and drug class, precomputed so aggregate-only roles never reach member rows. Only groups at or above the smallest aggregate role minimum group size are stored.';

CREATE OR REPLACE TABLE `{{catalog}}`.`{{base}}`.pharmacy_remittance_rows (
  claim_id        STRING        NOT NULL COMMENT 'Claim identifier',
  pharmacy_id     STRING        NOT NULL COMMENT 'Pharmacy that filled the prescription',
  fill_date       DATE          NOT NULL COMMENT 'Date filled',
  ndc             STRING        NOT NULL COMMENT 'Drug dispensed',
  quantity        DECIMAL(10,2) NOT NULL COMMENT 'Quantity dispensed',
  days_supply     INT           NOT NULL COMMENT 'Days supply',
  member_ref      STRING        NOT NULL COMMENT 'One-way member reference; the raw member id is never stored here',
  ingredient_cost DECIMAL(12,2) NOT NULL COMMENT 'Ingredient cost in US dollars',
  dispensing_fee  DECIMAL(8,2)  NOT NULL COMMENT 'Dispensing fee in US dollars',
  plan_paid       DECIMAL(12,2) NOT NULL COMMENT 'Paid by the plan in US dollars',
  member_paid     DECIMAL(12,2) NOT NULL COMMENT 'Paid by the member in US dollars',
  claim_status    STRING        NOT NULL COMMENT 'paid, reversed or rejected'
) CLUSTER BY (pharmacy_id) COMMENT 'Claims for pharmacy remittance, precomputed with a one-way member reference so pharmacy staff never reach member ids.';
