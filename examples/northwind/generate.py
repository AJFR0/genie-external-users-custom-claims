"""Deterministic synthetic data for Northwind Retirement Services (fictional).

Same seed, same rows: the runbook's expected numbers and the isolation suite depend on it.
"""
from __future__ import annotations

import random
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

AS_OF = date(2026, 9, 30)
PLANS = (
    ("PLAN-A", "Kestrel Engineering 401(k) Plan", "Kestrel Engineering"),
    ("PLAN-B", "Osprey Freight Retirement Savings Plan", "Osprey Freight"),
    ("PLAN-C", "Wren Architecture 401(k) Plan", "Wren Architecture"),
)
FUNDS = (
    ("F-TD2035", "Northwind Target Date 2035", "Target date", "0.0012"),
    ("F-TD2045", "Northwind Target Date 2045", "Target date", "0.0012"),
    ("F-TD2055", "Northwind Target Date 2055", "Target date", "0.0012"),
    ("F-USIDX", "Northwind US Total Market Index", "US equity", "0.0004"),
    ("F-SMCAP", "Northwind Small Cap Growth", "US equity", "0.0068"),
    ("F-INTL", "Northwind International Index", "International equity", "0.0007"),
    ("F-BOND", "Northwind Core Bond Index", "Bond", "0.0005"),
    ("F-STABLE", "Northwind Stable Value", "Stable value", "0.0030"),
)
PERSONAS = (
    ("P-1001", "PLAN-A", "Maya", "Alvarez", date(1988, 4, 12), date(2015, 6, 1)),
    ("P-1002", "PLAN-A", "James", "Whitfield", date(1979, 11, 3), date(2009, 2, 16)),
    ("P-2001", "PLAN-B", "Linda", "Okafor", date(1975, 7, 22), date(2004, 9, 7)),
)
PLAN_SIZES = (("PLAN-A", 57), ("PLAN-B", 50), ("PLAN-C", 40))
FIRST = ("Avery", "Blake", "Carmen", "Dev", "Elena", "Farah", "Gabe", "Hana", "Ivan", "Jules", "Kai", "Lena", "Mateo", "Nia",
         "Omar", "Priya", "Quinn", "Rosa", "Sam", "Tara", "Uma", "Victor", "Wes", "Ximena", "Yusuf", "Zoe")
LAST = ("Abara", "Brennan", "Castillo", "Dimitrov", "Eklund", "Fontaine", "Garza", "Hartley", "Ishikawa", "Jensen", "Kowalski",
        "Lindqvist", "Mbeki", "Novak", "Ortega", "Petrov", "Quintero", "Rasmussen", "Sato", "Tanaka", "Underwood", "Varga")


def _money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate(seed: int = 20261019) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    participants = [
        {"participant_id": pid, "plan_id": plan, "first_name": first, "last_name": last, "date_of_birth": dob,
         "hire_date": hire, "status": "active"}
        for pid, plan, first, last, dob, hire in PERSONAS
    ]
    n = 1
    for plan_id, size in PLAN_SIZES:
        for _ in range(size):
            participants.append({
                "participant_id": f"P-{n:04d}", "plan_id": plan_id, "first_name": rng.choice(FIRST), "last_name": rng.choice(LAST),
                "date_of_birth": date(rng.randint(1960, 2001), rng.randint(1, 12), rng.randint(1, 28)),
                "hire_date": date(rng.randint(2000, 2025), rng.randint(1, 12), rng.randint(1, 28)),
                "status": "terminated" if rng.random() < 0.08 else "active",
            })
            n += 1
    balances, contributions = [], []
    for p in participants:
        for fund in rng.sample(FUNDS, rng.randint(2, 4)):
            balances.append({"participant_id": p["participant_id"], "plan_id": p["plan_id"], "fund_id": fund[0],
                             "balance": _money(rng.uniform(1500, 240000)), "as_of_date": AS_OF})
        if p["status"] != "active":
            continue
        salary = rng.uniform(45000, 180000)
        deferral = salary * rng.choice((0.03, 0.04, 0.05, 0.06, 0.08, 0.10)) / 12
        source = "employee_roth" if rng.random() < 0.25 else "employee_pretax"
        for month in range(1, 10):
            day = date(2026, month, 15)
            contributions.append({"participant_id": p["participant_id"], "plan_id": p["plan_id"], "contribution_date": day,
                                  "source": source, "amount": _money(deferral)})
            contributions.append({"participant_id": p["participant_id"], "plan_id": p["plan_id"], "contribution_date": day,
                                  "source": "employer_match", "amount": _money(min(deferral, salary * 0.04 / 12))})
    return {
        "plans": [{"plan_id": a, "plan_name": b, "sponsor_name": c, "plan_type": "401(k)"} for a, b, c in PLANS],
        "participants": participants,
        "funds": [{"fund_id": a, "fund_name": b, "asset_class": c, "expense_ratio": Decimal(d)} for a, b, c, d in FUNDS],
        "account_balances": balances,
        "contributions": contributions,
    }
