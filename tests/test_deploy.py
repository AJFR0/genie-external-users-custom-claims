import pytest

from claims_kit.config import load_example
from claims_kit.deploy import apply_runtime_grants, deploy_claim_views, revoke_temporary_grants, temporary_grants
from claims_kit.sql import StatementError

EX = load_example("northwind")
KW = dict(catalog="cat", portal_sp="app-id", view_owner="owner@example.com")


class Recorder:
    def __init__(self):
        self.statements = []

    def __call__(self, stmt):
        self.statements.append(stmt)


class FakeSP:
    def __init__(self, fail_at=None):
        self.statements, self.fail_at = [], fail_at

    def execute(self, stmt, parameters=None):
        self.statements.append(stmt)
        if self.fail_at is not None and len(self.statements) == self.fail_at:
            raise StatementError("[SOMETHING] failed")


def test_null_mode_admin_creates_everything():
    admin = Recorder()
    deploy_claim_views(EX, mode="null", admin_sql=admin, **KW)
    s = admin.statements
    assert s[0].startswith("DROP VIEW IF EXISTS `cat`.`northwind_portal`.`plan_roster`")
    assert any(x.startswith("CREATE VIEW `cat`.`northwind_governance`.my_effective_grants") for x in s)
    assert not any(x.startswith("GRANT") for x in s)
    assert s[-1] == "ALTER VIEW `cat`.`northwind_portal`.`plan_roster` OWNER TO `owner@example.com`"


def test_throw_mode_order_and_separation_of_duties():
    admin, sp = Recorder(), FakeSP()
    deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=sp, **KW)
    assert all(x.startswith("CREATE VIEW") for x in sp.statements) and len(sp.statements) == len(EX.claim_views)
    assert not any(x.startswith("CREATE VIEW") for x in admin.statements)
    kinds = [x.split()[0] for x in admin.statements]
    first_grant, first_alter, first_revoke = kinds.index("GRANT"), kinds.index("ALTER"), kinds.index("REVOKE")
    assert kinds.index("DROP") < first_grant < first_alter < first_revoke
    assert admin.statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_redeploy_drops_existing_views_first():
    admin = Recorder()
    deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=FakeSP(), **KW)
    drops = [x for x in admin.statements if x.startswith("DROP VIEW")]
    assert len(drops) == len(EX.claim_views) and admin.statements[: len(drops)] == drops


def test_throw_mode_failure_still_transfers_and_revokes():
    admin, sp = Recorder(), FakeSP(fail_at=2)
    with pytest.raises(StatementError):
        deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=sp, **KW)
    assert sum(x.startswith("ALTER VIEW") for x in admin.statements) == len(EX.claim_views)
    assert admin.statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_missing_view_during_ownership_transfer_is_skipped():
    statements = []

    def admin(stmt):
        statements.append(stmt)
        if stmt.startswith("ALTER VIEW") and "plan_roster" in stmt:
            raise RuntimeError("[TABLE_OR_VIEW_NOT_FOUND] not there")

    log = deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=FakeSP(), **KW)
    assert any("skipped ownership" in line for line in log) and statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_owner_transfer_error_still_revokes():
    statements = []

    def admin(stmt):
        statements.append(stmt)
        if stmt.startswith("ALTER VIEW") and "my_accounts" in stmt:
            raise RuntimeError("[PERMISSION_DENIED] cannot change owner")

    with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
        deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=FakeSP(), **KW)
    assert statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_mode_validation():
    with pytest.raises(ValueError):
        deploy_claim_views(EX, mode="maybe", admin_sql=Recorder(), **KW)
    with pytest.raises(ValueError):
        deploy_claim_views(EX, mode="throws", admin_sql=Recorder(), **KW)


def test_temporary_grants_cover_base_gov_portal():
    g = temporary_grants(EX, "cat", "app-id")
    assert g[0] == "GRANT USE CATALOG ON CATALOG `cat` TO `app-id`"
    assert "GRANT USE SCHEMA, SELECT ON SCHEMA `cat`.`northwind_base` TO `app-id`" in g


def test_runtime_grants_only_portal_views():
    admin = Recorder()
    apply_runtime_grants(EX, admin_sql=admin, **KW)
    text = "\n".join(admin.statements)
    assert "northwind_base" not in text and "northwind_governance" not in text
    assert text.count("GRANT SELECT ON VIEW") == len(EX.portal_views) + len(EX.public_views)


def test_runtime_grants_go_to_the_application_group_only():
    admin = Recorder()
    apply_runtime_grants(EX, admin_sql=admin, **KW)
    assert admin.statements and all(s.endswith(f"TO `{EX.portal_group}`") for s in admin.statements)
    assert not any("app-id" in s for s in admin.statements)


def _failing_admin(predicate, message):
    statements = []

    def admin(stmt):
        statements.append(stmt)
        if predicate(stmt):
            raise RuntimeError(message)
    return admin, statements


def test_grant_failure_still_attempts_every_owner_transfer_and_revoke():
    admin, statements = _failing_admin(lambda s: s.startswith("GRANT USE SCHEMA, SELECT, CREATE TABLE"), "[PERMISSION_DENIED] grant 3")
    with pytest.raises(RuntimeError, match="grant 3"):
        deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=FakeSP(), **KW)
    assert sum(s.startswith("ALTER VIEW") for s in statements) == len(EX.claim_views)
    assert statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_owner_transfer_error_still_attempts_every_view():
    admin, statements = _failing_admin(lambda s: s.startswith("ALTER VIEW") and "my_accounts" in s, "[PERMISSION_DENIED] owner")
    with pytest.raises(RuntimeError, match="owner"):
        deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=FakeSP(), **KW)
    assert sum(s.startswith("ALTER VIEW") for s in statements) == len(EX.claim_views)


def test_revoke_failure_still_attempts_remaining_revokes():
    first_revoke = revoke_temporary_grants(EX, "cat", "app-id")[0]
    admin, statements = _failing_admin(lambda s: s == first_revoke, "[INTERNAL_ERROR] revoke")
    with pytest.raises(RuntimeError, match="revoke"):
        deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=FakeSP(), **KW)
    assert statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_several_cleanup_errors_are_reported_together():
    from claims_kit.deploy import DeployError
    admin, _ = _failing_admin(lambda s: s.startswith("ALTER VIEW") or s.startswith("REVOKE"), "[PERMISSION_DENIED] nope")
    with pytest.raises(DeployError) as err:
        deploy_claim_views(EX, mode="throws", admin_sql=admin, sp_runner=FakeSP(fail_at=1), **KW)
    assert len(err.value.errors) == 1 + len(EX.claim_views) + 3


from claims_kit.deploy import apply_row_policies, deploy_policy_functions, remove_row_policies
from claims_kit.tags import load_tag_set


class FailingRecorder(Recorder):
    def __init__(self, prefix, message):
        super().__init__()
        self.prefix, self.message = prefix, message

    def __call__(self, stmt):
        self.statements.append(stmt)
        if stmt.startswith(self.prefix):
            raise StatementError(self.message)


def test_temporary_grants_allow_creating_functions_and_revoke_it():
    assert any("CREATE FUNCTION" in g and "northwind_governance" in g for g in temporary_grants(EX, "cat", "app-id"))
    assert any("CREATE FUNCTION" in r and "northwind_governance" in r for r in revoke_temporary_grants(EX, "cat", "app-id"))


def test_policy_functions_in_throw_mode_run_as_sp_then_change_owner():
    admin, sp = Recorder(), FakeSP()
    deploy_policy_functions(EX, mode="throws", admin_sql=admin, sp_runner=sp, **KW)
    assert len(sp.statements) == len(EX.claim_functions)
    assert all(x.startswith("CREATE OR REPLACE FUNCTION") for x in sp.statements)
    owners = [s for s in admin.statements if s.startswith("ALTER FUNCTION")]
    assert owners == [f"ALTER FUNCTION `cat`.`northwind_governance`.`{f}` OWNER TO `owner@example.com`" for f in EX.claim_functions]
    assert admin.statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_policy_functions_in_null_mode_are_created_by_the_admin():
    admin = Recorder()
    deploy_policy_functions(EX, mode="null", admin_sql=admin, **KW)
    assert sum(s.startswith("CREATE OR REPLACE FUNCTION") for s in admin.statements) == len(EX.claim_functions)
    assert not any(s.startswith("GRANT") for s in admin.statements)


def test_policy_functions_revoke_even_when_creation_fails():
    admin, sp = Recorder(), FakeSP(fail_at=2)
    with pytest.raises(StatementError):
        deploy_policy_functions(EX, mode="throws", admin_sql=admin, sp_runner=sp, **KW)
    assert admin.statements[-3:] == revoke_temporary_grants(EX, "cat", "app-id")


def test_apply_row_policies_tags_before_policies():
    admin = Recorder()
    apply_row_policies(EX, catalog="cat", tags=load_tag_set("governed"), group=EX.portal_group, admin_sql=admin)
    first_policy = next(i for i, s in enumerate(admin.statements) if s.startswith("CREATE OR REPLACE POLICY"))
    assert first_policy > 0 and all(s.startswith("ALTER TABLE") for s in admin.statements[:first_policy])
    assert all(s.startswith("CREATE OR REPLACE POLICY") for s in admin.statements[first_policy:])


def test_remove_row_policies_tolerates_missing():
    admin = FailingRecorder("DROP POLICY", "[POLICY_NOT_FOUND] Cannot execute deletePolicy command because the policy cannot be found.")
    log = remove_row_policies(EX, catalog="cat", admin_sql=admin)
    assert len(log) == 5 and all(line.startswith("skipped (absent)") for line in log)


def test_remove_row_policies_raises_other_errors():
    admin = FailingRecorder("DROP POLICY", "[INSUFFICIENT_PERMISSIONS] no MANAGE")
    with pytest.raises(StatementError):
        remove_row_policies(EX, catalog="cat", admin_sql=admin)
