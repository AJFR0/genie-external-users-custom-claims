CREATE VIEW `{{catalog}}`.`{{portal}}`.my_access (
  role COMMENT 'Role of this grant',
  scope_type COMMENT 'member, sponsor or pharmacy',
  scope_id COMMENT 'The member, sponsor or pharmacy this grant covers',
  valid_from COMMENT 'First day of the grant',
  valid_to COMMENT 'Last day of the grant. NULL means open-ended.',
  detail_level COMMENT 'own, aggregate or pharmacy',
  include_minor_dependents COMMENT 'Also sees claims of children under 18',
  mask_identity COMMENT 'Member identifiers are replaced by a one-way reference',
  min_cell_size COMMENT 'Aggregate groups with fewer members are hidden'
)
COMMENT 'What the signed-in user is entitled to see. Use for "what can I see?" or "what is my role?".'
AS SELECT role, scope_type, scope_id, valid_from, valid_to, detail_level, include_minor_dependents, mask_identity, min_cell_size
FROM `{{catalog}}`.`{{gov}}`.my_effective_grants;

CREATE VIEW `{{catalog}}`.`{{portal}}`.my_claims (
  claim_id COMMENT 'Claim identifier',
  member_id COMMENT 'Member the prescription was for',
  member_first_name COMMENT 'First name of that member',
  visible_as COMMENT 'self, or minor dependent for a subscriber child under 18',
  fill_date COMMENT 'Date filled',
  drug_name COMMENT 'Drug and strength',
  drug_class COMMENT 'Therapeutic class',
  generic_flag COMMENT 'true for generics',
  pharmacy_name COMMENT 'Pharmacy',
  quantity COMMENT 'Quantity dispensed',
  days_supply COMMENT 'Days supply',
  plan_paid COMMENT 'Paid by the plan in US dollars',
  member_paid COMMENT 'Paid by the member in US dollars',
  claim_status COMMENT 'paid, reversed or rejected'
)
COMMENT 'Pharmacy claims of the signed-in member and, for subscribers, their children under 18. 2026 plan year.'
AS
SELECT c.claim_id, c.member_id, m.first_name, mm.visible_as, c.fill_date, d.drug_name, d.drug_class, d.generic_flag,
       ph.pharmacy_name, c.quantity, c.days_supply, c.plan_paid, c.member_paid, c.claim_status
FROM `{{catalog}}`.`{{base}}`.pharmacy_claims AS c
JOIN `{{catalog}}`.`{{gov}}`.my_members AS mm ON mm.member_id = c.member_id
JOIN `{{catalog}}`.`{{base}}`.members AS m ON m.member_id = c.member_id
JOIN `{{catalog}}`.`{{base}}`.drugs AS d ON d.ndc = c.ndc
JOIN `{{catalog}}`.`{{base}}`.pharmacies AS ph ON ph.pharmacy_id = c.pharmacy_id;

CREATE VIEW `{{catalog}}`.`{{portal}}`.my_accumulators (
  member_id COMMENT 'Member',
  first_name COMMENT 'First name',
  visible_as COMMENT 'self, or minor dependent',
  plan_year COMMENT 'Plan year',
  deductible COMMENT 'Annual deductible in US dollars',
  deductible_met COMMENT 'Deductible met so far',
  deductible_remaining COMMENT 'Deductible still to meet',
  oop_max COMMENT 'Annual out-of-pocket maximum',
  oop_met COMMENT 'Out-of-pocket spending so far',
  oop_remaining COMMENT 'Out-of-pocket spending left before the maximum'
)
COMMENT 'Deductible and out-of-pocket progress for the signed-in member and, for subscribers, their children under 18.'
AS
SELECT a.member_id, m.first_name, mm.visible_as, a.plan_year, a.deductible, a.deductible_met, a.deductible - a.deductible_met,
       a.oop_max, a.oop_met, a.oop_max - a.oop_met
FROM `{{catalog}}`.`{{base}}`.accumulators AS a
JOIN `{{catalog}}`.`{{gov}}`.my_members AS mm ON mm.member_id = a.member_id
JOIN `{{catalog}}`.`{{base}}`.members AS m ON m.member_id = a.member_id;

CREATE VIEW `{{catalog}}`.`{{portal}}`.sponsor_spend_summary (
  sponsor_id COMMENT 'Plan sponsor (employer) identifier',
  sponsor_name COMMENT 'Employer name',
  fill_quarter COMMENT 'Calendar quarter, for example 2026-Q1',
  drug_class COMMENT 'Therapeutic class',
  members COMMENT 'Distinct members with a paid claim in this group',
  claims COMMENT 'Paid claims in this group',
  plan_paid COMMENT 'Paid by the plan in US dollars',
  member_paid COMMENT 'Paid by members in US dollars',
  generic_claims COMMENT 'Paid claims for generic drugs'
)
COMMENT 'Paid pharmacy spend by sponsor, quarter and drug class for the sponsors in scope. Groups with fewer members than the role minimum cell size are hidden for privacy, so totals cover the visible groups only. No member-level data.'
AS
WITH my_sponsors AS (
  SELECT scope_id AS sponsor_id, min(min_cell_size) AS min_cell_size
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants
  WHERE scope_type = 'sponsor' AND detail_level = 'aggregate'
  GROUP BY scope_id
)
SELECT c.sponsor_id, s.sponsor_name,
       concat(CAST(year(c.fill_date) AS STRING), '-Q', CAST(quarter(c.fill_date) AS STRING)),
       d.drug_class,
       COUNT(DISTINCT c.member_id), COUNT(*),
       CAST(SUM(c.plan_paid) AS DECIMAL(14,2)), CAST(SUM(c.member_paid) AS DECIMAL(14,2)),
       SUM(CASE WHEN d.generic_flag THEN 1 ELSE 0 END)
FROM `{{catalog}}`.`{{base}}`.pharmacy_claims AS c
JOIN my_sponsors AS ms ON ms.sponsor_id = c.sponsor_id
JOIN `{{catalog}}`.`{{base}}`.sponsors AS s ON s.sponsor_id = c.sponsor_id
JOIN `{{catalog}}`.`{{base}}`.drugs AS d ON d.ndc = c.ndc
WHERE c.claim_status = 'paid'
GROUP BY c.sponsor_id, s.sponsor_name, year(c.fill_date), quarter(c.fill_date), d.drug_class, ms.min_cell_size
HAVING COUNT(DISTINCT c.member_id) >= ms.min_cell_size;

CREATE VIEW `{{catalog}}`.`{{portal}}`.pharmacy_remittance (
  claim_id COMMENT 'Claim identifier',
  pharmacy_id COMMENT 'Pharmacy identifier',
  pharmacy_name COMMENT 'Pharmacy name',
  fill_date COMMENT 'Date filled',
  ndc COMMENT 'Drug dispensed',
  drug_name COMMENT 'Drug and strength',
  quantity COMMENT 'Quantity dispensed',
  days_supply COMMENT 'Days supply',
  member_ref COMMENT 'Member reference. A one-way reference, not a member id, when the role masks identity.',
  ingredient_cost COMMENT 'Ingredient cost in US dollars',
  dispensing_fee COMMENT 'Dispensing fee in US dollars',
  plan_paid COMMENT 'Paid by the plan in US dollars',
  member_paid COMMENT 'Paid by the member in US dollars',
  claim_status COMMENT 'paid, reversed or rejected'
)
COMMENT 'Claims filled at the pharmacies in scope, for remittance reconciliation. Member identity is masked for pharmacy users.'
AS
WITH my_pharmacies AS (
  SELECT scope_id AS pharmacy_id, bool_and(mask_identity) AS mask_identity
  FROM `{{catalog}}`.`{{gov}}`.my_effective_grants
  WHERE scope_type = 'pharmacy' AND detail_level = 'pharmacy'
  GROUP BY scope_id
)
SELECT c.claim_id, c.pharmacy_id, ph.pharmacy_name, c.fill_date, c.ndc, d.drug_name, c.quantity, c.days_supply,
       -- Demo-grade masking. In production use a keyed hash or a token vault so references can't be reversed.
       CASE WHEN mp.mask_identity THEN substr(sha2(concat('larkspur-demo:', c.member_id), 256), 1, 16) ELSE c.member_id END,
       c.ingredient_cost, c.dispensing_fee, c.plan_paid, c.member_paid, c.claim_status
FROM `{{catalog}}`.`{{base}}`.pharmacy_claims AS c
JOIN my_pharmacies AS mp ON mp.pharmacy_id = c.pharmacy_id
JOIN `{{catalog}}`.`{{base}}`.pharmacies AS ph ON ph.pharmacy_id = c.pharmacy_id
JOIN `{{catalog}}`.`{{base}}`.drugs AS d ON d.ndc = c.ndc;
