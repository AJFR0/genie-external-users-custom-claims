"""Deterministic synthetic data for Larkspur Pharmacy Benefits, a fictional pharmacy benefit manager.

Drug names are ordinary generic names; NDC values use a 00000 labeler so they never match a real product.
Quotas pin a few group sizes so that minimum-cell-size suppression visibly changes sponsor totals.
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

PLAN_YEAR = 2026
FILL_MONTHS = tuple(range(1, 10))  # January to September 2026
AS_OF = date(PLAN_YEAR, 9, 30)
SPONSORS = (("SPN-ALDER", "Alder Manufacturing", "Manufacturing"),
            ("SPN-BIRCH", "Birchwood Unified Schools", "Education"),
            ("SPN-CEDAR", "Cedar Logistics", "Logistics"))
PLAN_TERMS = {"SPN-ALDER": (250, 2500), "SPN-BIRCH": (150, 2000), "SPN-CEDAR": (400, 3000)}
HOUSEHOLDS = {"SPN-ALDER": 64, "SPN-BIRCH": 46, "SPN-CEDAR": 30}
PHARMACIES = (
    ("PH-0001", "Larkspur Mail Pharmacy", "Columbus", "OH", "mail"),
    ("PH-0002", "Harborside Specialty Pharmacy", "Cleveland", "OH", "specialty"),
    ("PH-0003", "Elm Street Drug", "Dayton", "OH", "retail"),
    ("PH-0004", "Riverbend Pharmacy", "Toledo", "OH", "retail"),
    ("PH-0005", "Northgate Pharmacy", "Akron", "OH", "retail"),
    ("PH-0006", "Lakeview Apothecary", "Sandusky", "OH", "retail"),
    ("PH-0007", "Maple Street Pharmacy", "Dayton", "OH", "retail"),
    ("PH-0008", "Hilltop Pharmacy", "Athens", "OH", "retail"),
)
RETAIL = tuple(p[0] for p in PHARMACIES if p[4] == "retail")
DRUGS = (  # ndc, name, class, generic, specialty, cost per 30 days
    ("00000-0101-01", "Atorvastatin 20 mg", "Statins", True, False, 12.0),
    ("00000-0102-01", "Rosuvastatin 10 mg", "Statins", True, False, 18.0),
    ("00000-0201-01", "Metformin 500 mg", "Antidiabetics", True, False, 9.0),
    ("00000-0202-01", "Sitagliptin 100 mg", "Antidiabetics", False, False, 520.0),
    ("00000-0301-01", "Lisinopril 10 mg", "Antihypertensives", True, False, 8.0),
    ("00000-0302-01", "Amlodipine 5 mg", "Antihypertensives", True, False, 10.0),
    ("00000-0401-01", "Sertraline 50 mg", "Antidepressants", True, False, 11.0),
    ("00000-0402-01", "Escitalopram 10 mg", "Antidepressants", True, False, 14.0),
    ("00000-0501-01", "Albuterol inhaler", "Respiratory", True, False, 35.0),
    ("00000-0502-01", "Fluticasone-salmeterol inhaler", "Respiratory", False, False, 290.0),
    ("00000-0601-01", "Semaglutide pen", "GLP-1 agonists", False, True, 980.0),
    ("00000-0701-01", "Adalimumab pen", "Immunology (specialty)", False, True, 6900.0),
    ("00000-0801-01", "Amoxicillin 500 mg", "Anti-infectives", True, False, 7.0),
    ("00000-0802-01", "Azithromycin 250 mg", "Anti-infectives", True, False, 9.0),
)
ADULT_RATES = {"Statins": 0.22, "Antidiabetics": 0.11, "Antihypertensives": 0.26, "Antidepressants": 0.13, "Respiratory": 0.09}
CHILD_RATES = {"Respiratory": 0.10, "Antidepressants": 0.04}
QUOTAS = {"00000-0601-01": {"SPN-ALDER": 14, "SPN-BIRCH": 6, "SPN-CEDAR": 5},
          "00000-0701-01": {"SPN-ALDER": 4, "SPN-BIRCH": 2, "SPN-CEDAR": 1}}
PERSONA_MEMBERS = (  # member_id, subscriber_id, relationship, first, last, dob, sponsor, pinned NDCs
    ("M-1001", "M-1001", "subscriber", "Ana", "Ferreira", date(1985, 2, 14), "SPN-BIRCH", ("00000-0101-01", "00000-0301-01")),
    ("M-1002", "M-1001", "spouse", "Marco", "Ferreira", date(1983, 8, 30), "SPN-BIRCH", ("00000-0402-01", "00000-0202-01")),
    ("M-1003", "M-1001", "child", "Lily", "Ferreira", date(2014, 5, 1), "SPN-BIRCH", ("00000-0502-01",)),
    ("M-1004", "M-1001", "child", "Noah", "Ferreira", date(2007, 3, 15), "SPN-BIRCH", ("00000-0501-01",)),
    ("M-2001", "M-2001", "subscriber", "Dana", "Whitaker", date(1980, 10, 10), "SPN-ALDER", ("00000-0201-01", "00000-0102-01")),
)
PERSONA_PHARMACY = "PH-0007"
FIRST = ("Alex", "Bea", "Cyrus", "Dalia", "Emil", "Fern", "Grace", "Hugo", "Iris", "Jonah", "Kira", "Leo", "Mira", "Nils",
         "Opal", "Pavel", "Rhea", "Silas", "Talia", "Umar", "Vera", "Wynn", "Yara", "Zane")
LAST = ("Adair", "Bishop", "Calloway", "Delgado", "Ellison", "Forsythe", "Gallo", "Hale", "Ingram", "Joyce", "Keller",
        "Lowell", "Mercer", "Nakamura", "Oakes", "Pryor", "Quinlan", "Rowan", "Serrano", "Thorne", "Vance", "Whitlock")


def _money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _age(dob: date, on: date = AS_OF) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _plan_id(sponsor_id: str) -> str:
    return f"RXP-{sponsor_id.split('-', 1)[1]}-{PLAN_YEAR}"


def _member(mid, sub, rel, first, last, dob, sponsor):
    return {"member_id": mid, "subscriber_id": sub, "relationship": rel, "first_name": first, "last_name": last,
            "date_of_birth": dob, "sponsor_id": sponsor, "plan_id": _plan_id(sponsor)}


def _claim(rng, n, member, drug, pharmacy, fill_date, days):
    ndc, _, _, generic, specialty, cost = drug
    ingredient = _money(cost * days / 30 * rng.uniform(0.92, 1.08))
    fee = Decimal("0.00") if pharmacy == "PH-0001" else (Decimal("2.50") if specialty else Decimal("1.75"))
    total = ingredient + fee
    if generic:
        member_paid = Decimal("25.00") if days == 90 else Decimal("10.00")
    elif specialty:
        member_paid = min(_money(float(total) * 0.20), Decimal("250.00"))
    else:
        member_paid = min(_money(float(total) * 0.25), Decimal("150.00"))
    member_paid = min(member_paid, total)
    roll = rng.random()
    status = "paid" if roll < 0.96 else ("reversed" if roll < 0.985 else "rejected")
    plan_paid = total - member_paid
    if status == "rejected":
        plan_paid = member_paid = Decimal("0.00")
    return {"claim_id": f"C-{n:06d}", "member_id": member["member_id"], "sponsor_id": member["sponsor_id"], "plan_id": member["plan_id"],
            "pharmacy_id": pharmacy, "ndc": ndc, "fill_date": fill_date, "quantity": Decimal(days), "days_supply": days,
            "ingredient_cost": ingredient, "dispensing_fee": fee, "plan_paid": plan_paid, "member_paid": member_paid,
            "claim_status": status}


def generate(seed: int = 20261019) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    by_ndc = {d[0]: d for d in DRUGS}
    by_class = defaultdict(list)
    for d in DRUGS:
        by_class[d[2]].append(d)
    members, therapy, home = [], {}, {}
    persona_ids = {p[0] for p in PERSONA_MEMBERS}
    for mid, sub, rel, first, last, dob, sponsor, ndcs in PERSONA_MEMBERS:
        members.append(_member(mid, sub, rel, first, last, dob, sponsor))
        therapy[mid] = [by_ndc[n] for n in ndcs]
        home[mid] = PERSONA_PHARMACY
    n = 1
    for sponsor, count in HOUSEHOLDS.items():
        for _ in range(count):
            sub_id, last, pharmacy = f"M-{n:04d}", rng.choice(LAST), rng.choice(RETAIL)
            n += 1
            people = [(sub_id, "subscriber", date(rng.randint(1962, 2000), rng.randint(1, 12), rng.randint(1, 28)))]
            if rng.random() < 0.55:
                people.append((f"M-{n:04d}", "spouse", date(rng.randint(1962, 2000), rng.randint(1, 12), rng.randint(1, 28))))
                n += 1
            for _ in range(rng.choice((0, 0, 1, 1, 2))):
                people.append((f"M-{n:04d}", "child", date(rng.randint(2002, 2024), rng.randint(1, 12), rng.randint(1, 28))))
                n += 1
            for mid, rel, dob in people:
                members.append(_member(mid, sub_id, rel, rng.choice(FIRST), last, dob, sponsor))
                home[mid] = pharmacy
                rates = CHILD_RATES if _age(dob) < 18 else ADULT_RATES
                therapy[mid] = [rng.choice(by_class[cls]) for cls, rate in rates.items() if rng.random() < rate]
    for ndc, per_sponsor in QUOTAS.items():
        for sponsor, k in per_sponsor.items():
            adults = sorted(m["member_id"] for m in members
                            if m["sponsor_id"] == sponsor and m["member_id"] not in persona_ids and _age(m["date_of_birth"]) >= 25)
            for mid in rng.sample(adults, k):
                therapy[mid].append(by_ndc[ndc])
    claims, cid = [], 1
    for m in members:
        mid = m["member_id"]
        for drug in therapy[mid]:
            specialty = drug[4]
            mail = not specialty and mid not in persona_ids and rng.random() < 0.25
            pharmacy = "PH-0002" if specialty else ("PH-0001" if mail else home[mid])
            for month in ((1, 4, 7) if mail else FILL_MONTHS):
                claims.append(_claim(rng, cid, m, drug, pharmacy, date(PLAN_YEAR, month, rng.randint(1, 28)), 90 if mail else 30))
                cid += 1
        for month in FILL_MONTHS:
            if rng.random() < 0.035 or (mid == "M-1004" and month == 3):
                claims.append(_claim(rng, cid, m, rng.choice(by_class["Anti-infectives"]), home[mid],
                                     date(PLAN_YEAR, month, rng.randint(1, 28)), 10))
                cid += 1
    spent = defaultdict(Decimal)
    for c in claims:
        if c["claim_status"] == "paid":
            spent[c["member_id"]] += c["member_paid"]
    accumulators = []
    for m in members:
        deductible, oop_max = (_money(v) for v in PLAN_TERMS[m["sponsor_id"]])
        s = spent[m["member_id"]]
        accumulators.append({"member_id": m["member_id"], "plan_year": PLAN_YEAR, "deductible": deductible,
                             "deductible_met": min(s, deductible), "oop_max": oop_max, "oop_met": min(s, oop_max)})
    return {
        "sponsors": [{"sponsor_id": a, "sponsor_name": b, "industry": c} for a, b, c in SPONSORS],
        "plans": [{"plan_id": _plan_id(s), "sponsor_id": s, "plan_name": f"{name} Rx Plan", "plan_year": PLAN_YEAR,
                   "deductible": _money(PLAN_TERMS[s][0]), "oop_max": _money(PLAN_TERMS[s][1])} for s, name, _ in SPONSORS],
        "members": members,
        "pharmacies": [{"pharmacy_id": a, "pharmacy_name": b, "city": c, "state": d, "network_type": e} for a, b, c, d, e in PHARMACIES],
        "drugs": [{"ndc": a, "drug_name": b, "drug_class": c, "generic_flag": d, "specialty_flag": e} for a, b, c, d, e, _ in DRUGS],
        "pharmacy_claims": claims,
        "accumulators": accumulators,
    }
