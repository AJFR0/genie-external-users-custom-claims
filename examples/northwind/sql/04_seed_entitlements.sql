INSERT INTO `{{catalog}}`.`{{gov}}`.role_policies VALUES
  ('participant', true,  false, false, false),
  ('sponsor',     false, true,  true,  false),
  ('advisor',     false, true,  true,  true);

INSERT INTO `{{catalog}}`.`{{gov}}`.portal_user_grants VALUES
  ('pu-1001', 'participant', 'participant', 'P-1001', DATE '2026-01-01', NULL, 'seed', current_timestamp()),
  ('pu-1002', 'participant', 'participant', 'P-1002', DATE '2026-01-01', NULL, 'seed', current_timestamp()),
  ('pu-2001', 'sponsor',     'plan',        'PLAN-A', DATE '2026-01-01', NULL, 'seed', current_timestamp()),
  ('pu-2001', 'participant', 'participant', 'P-2001', DATE '2026-01-01', NULL, 'seed', current_timestamp()),
  ('pu-3001', 'advisor',     'plan',        'PLAN-A', DATE '2026-01-01', NULL, 'seed', current_timestamp()),
  ('pu-3001', 'advisor',     'plan',        'PLAN-C', DATE '2026-01-01', NULL, 'seed', current_timestamp());
