from fastapi.testclient import TestClient

from app.audit import AuditLog
from app.conversations import ConversationStore
from app.main import create_app
from app.services import ExampleRuntime, Services
from app.settings import Settings
from claims_kit.config import load_example
from claims_kit.genie import GenieAnswer, GenieQuery
from claims_kit.personas import load_personas
from claims_kit.sql import StatementResult
from claims_kit.tokens import MintedToken
from conftest import make_jwt


class FakeProvider:
    client_id = "app-id"

    def __init__(self):
        self.minted, self.forgotten = [], []

    def token_for(self, claim):
        hit = claim in self.minted
        if not hit:
            self.minted.append(claim)
        payload = {"custom": {"claim": claim}, "sub": "app-id-1234", "client_id": "app-id-1234", "aud": "123456789012",
                   "iss": "https://host.example/oidc", "exp": 9999999999}
        return MintedToken(make_jwt(payload), 9e9, claim), hit

    def auth_for(self, claim):
        return lambda: {"X-Claim": claim}

    def forget(self, claim):
        self.forgotten.append(claim)


class FakeGenie:
    def __init__(self, status="COMPLETED"):
        self.asked, self.deleted, self.status, self.n = [], [], status, 0

    def ask(self, question, conversation_id=None):
        self.n += 1
        self.asked.append((question, conversation_id))
        queries = [GenieQuery("SELECT 1", None, "stmt-1", ["balance"], [["10.00"]])] if self.status == "COMPLETED" else []
        return GenieAnswer(conversation_id or f"conv-{self.n}", f"msg-{self.n}", self.status, ["Your balance is $10.00"], queries,
                           [(0.5, "EXECUTING_QUERY"), (1.0, self.status)])

    def delete_conversation(self, conversation_id):
        self.deleted.append(conversation_id)


class FakeRunner:
    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = [], result, error

    def execute(self, sql, parameters=None):
        self.calls.append((sql, parameters))
        if self.error:
            raise self.error
        return self.result or StatementResult("s", ["role", "scope_id"], [["participant", "P-1001"]])


def make_client(tmp_path, *, genie=None, runner=None, admin=None, redact_ids=False):
    ex = load_example("northwind")
    runtime = ExampleRuntime(ex, load_personas(ex), FakeProvider(), "space-1")
    genie = genie or FakeGenie()
    runner = runner or FakeRunner()
    services = Services(catalog="cat", examples={"northwind": runtime}, conversations=ConversationStore(),
                        audit=AuditLog(tmp_path / "audit.jsonl"), admin_runner=admin,
                        make_runner=lambda auth: runner, make_genie=lambda space_id, auth: genie)
    settings = Settings(env=None, session_secret="test-secret", audit_path=tmp_path / "audit.jsonl", redact_ids=redact_ids)
    return TestClient(create_app(settings, services)), services, genie, runner
