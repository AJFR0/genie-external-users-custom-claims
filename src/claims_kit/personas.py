"""Personas (personas.yml) and their expectations (expectations.py) for one example."""
from __future__ import annotations

import importlib
import re
from dataclasses import dataclass

from .config import Example


@dataclass(frozen=True)
class ViewExpect:
    key: tuple
    ids: frozenset
    null_columns: tuple = ()
    not_null_columns: tuple = ()
    never_equal: tuple | None = None  # (column, frozenset of raw values that must never appear)


@dataclass(frozen=True)
class GenieCase:
    question: str
    must: tuple = ()
    must_not: tuple = ()


@dataclass(frozen=True)
class Persona:
    id: str
    claim: str
    name: str
    label: str
    blurb: str
    genie: tuple = ()


_LITERAL = re.compile(r"^[A-Za-z0-9 ._:-]{1,64}$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def sql_literal(value) -> str:
    """A SQL literal for probe values: numbers stay bare, strings are quoted. Quotes are never allowed."""
    text = str(value)
    if not _LITERAL.match(text):
        raise ValueError(f"unsafe probe value {text!r}")
    return text if _NUMBER.match(text) else f"'{text}'"


@dataclass(frozen=True)
class SideChannelProbe:
    id: str
    persona: str
    view: str
    match: tuple          # ((column, value), ...): true only for rows this persona may not see
    absent: tuple         # the same columns with values that exist nowhere
    error: str = "DIVIDE_BY_ZERO"  # or CAST_INVALID_INPUT
    source: str = ""      # where the value lives, for the evidence note


@dataclass(frozen=True)
class ExampleFixtures:
    personas: tuple
    views: dict
    genie_values: dict
    probes: tuple = ()

    def persona(self, persona_id: str) -> Persona:
        for p in self.personas:
            if p.id == persona_id:
                return p
        raise KeyError(persona_id)


def load_personas(ex: Example) -> tuple:
    raw = ex.load_yaml("personas.yml")
    return tuple(
        Persona(id=p["id"], claim=p["claim"], name=p["name"], label=p["label"], blurb=p.get("blurb", ""),
                genie=tuple(GenieCase(c["question"], tuple(c.get("must", ())), tuple(c.get("must_not", ())))
                            for c in p.get("genie", ())))
        for p in raw["personas"]
    )


def load_fixtures(ex: Example, data: dict | None = None) -> ExampleFixtures:
    generator = importlib.import_module(f"examples.{ex.name}.generate")
    expectations = importlib.import_module(f"examples.{ex.name}.expectations")
    data = generator.generate() if data is None else data
    probes = tuple(getattr(expectations, "side_channel_probes", lambda d: ())(data))
    fx = ExampleFixtures(load_personas(ex), expectations.view_expectations(data), expectations.genie_values(data), probes)
    problems = []
    portal = set(ex.portal_views)
    ids = {p.id for p in fx.personas}
    for probe in probes:
        if probe.persona not in ids or probe.view not in portal:
            problems.append(f"side-channel probe {probe.id}: unknown persona or view")
    for p in fx.personas:
        if set(fx.views.get(p.id, {})) != portal:
            problems.append(f"{p.id}: expectations must cover exactly {sorted(portal)}")
        for case in p.genie:
            problems += [f"{p.id}: unknown genie value {k!r}" for k in case.must + case.must_not if k not in fx.genie_values]
    if problems:
        raise ValueError("; ".join(problems))
    return fx
