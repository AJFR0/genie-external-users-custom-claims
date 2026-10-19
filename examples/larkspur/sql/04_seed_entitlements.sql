INSERT INTO `{{catalog}}`.`{{gov}}`.role_policies VALUES
  ('subscriber',    'own',       true,  false, 0),
  ('member',        'own',       false, false, 0),
  ('sponsor_admin', 'aggregate', false, true,  11),
  ('consultant',    'aggregate', false, true,  20),
  ('pharmacy',      'pharmacy',  false, true,  0);

INSERT INTO `{{catalog}}`.`{{gov}}`.portal_user_grants VALUES
  ('rx-1001', 'subscriber',    'member',   'M-1001',    DATE '2026-01-01', NULL,              'seed', current_timestamp()),
  ('rx-1002', 'member',        'member',   'M-1002',    DATE '2026-01-01', NULL,              'seed', current_timestamp()),
  ('rx-2001', 'sponsor_admin', 'sponsor',  'SPN-ALDER', DATE '2026-01-01', NULL,              'seed', current_timestamp()),
  ('rx-2001', 'subscriber',    'member',   'M-2001',    DATE '2026-01-01', NULL,              'seed', current_timestamp()),
  ('rx-3001', 'consultant',    'sponsor',  'SPN-ALDER', DATE '2026-01-01', NULL,              'seed', current_timestamp()),
  ('rx-3001', 'consultant',    'sponsor',  'SPN-BIRCH', DATE '2026-01-01', NULL,              'seed', current_timestamp()),
  ('rx-3001', 'consultant',    'sponsor',  'SPN-CEDAR', DATE '2026-01-01', DATE '2026-06-30', 'seed', current_timestamp()),
  ('rx-4001', 'pharmacy',      'pharmacy', 'PH-0007',   DATE '2026-01-01', NULL,              'seed', current_timestamp());
