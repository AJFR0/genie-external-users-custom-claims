"""Wiring for the app: one runtime per configured example, plus shared stores. Tests pass fakes instead."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from claims_kit.config import Example, load_example
from claims_kit.genie import GenieClient
from claims_kit.genie_space import find_space_by_title, space_title
from claims_kit.local import admin_client
from claims_kit.personas import load_personas
from claims_kit.sql import StatementRunner
from claims_kit.tokens import ClaimTokenProvider

from .audit import AuditLog
from .conversations import ConversationStore


@dataclass
class ExampleRuntime:
    example: Example
    personas: tuple
    provider: object
    genie_space_id: str | None

    def persona(self, persona_id: str):
        return next((p for p in self.personas if p.id == persona_id), None)


@dataclass
class Services:
    catalog: str
    examples: dict
    conversations: ConversationStore
    audit: AuditLog
    admin_runner: object | None
    make_runner: Callable
    make_genie: Callable


def build_services(settings) -> Services:
    env = settings.env
    admin = admin_client(env.admin_profile) if env.admin_profile else None
    examples = {}
    for name, creds in env.examples.items():
        ex = load_example(name)
        space_id = creds.genie_space_id
        if not space_id and admin is not None:
            space_id = find_space_by_title(admin.api_client.do, space_title(ex.load_yaml("genie.yml"), env.catalog))
        examples[name] = ExampleRuntime(ex, load_personas(ex), ClaimTokenProvider(env.host, creds.client_id, creds.client_secret), space_id)
    return Services(
        catalog=env.catalog, examples=examples, conversations=ConversationStore(), audit=AuditLog(settings.audit_path),
        admin_runner=StatementRunner(env.host, env.warehouse_id, admin.config.authenticate) if admin else None,
        make_runner=lambda auth: StatementRunner(env.host, env.warehouse_id, auth),
        make_genie=lambda space_id, auth: GenieClient(env.host, space_id, auth),
    )
