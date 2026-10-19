"""Build the seven guide diagrams into docs/assets/diagrams/. Run: .venv/bin/python -m docs.diagrams.build_diagrams"""
from __future__ import annotations

from pathlib import Path

from .svgkit import Svg

OUT = Path(__file__).resolve().parents[1] / "assets" / "diagrams"


def previous_patterns() -> Svg:
    s = Svg(1240, 500)
    s.text(40, 46, "Per-user answers before custom identity claims: every pattern had a cost", size=22, weight="bold")
    cards = [
        ("Provision every user", ["SCIM or token federation makes", "each end user a Databricks", "identity"],
         ["Sync every external user", "Federation needs users that", "already exist", "Account identity limits"], False),
        ("One SP per tenant", ["Views filter on session_user()", "with one service principal", "per customer"],
         ["Access only per tenant", "A secret per tenant", "Identities multiply by role"], False),
        ("Embedded dashboards", ["Signed per-viewer filters", "on published dashboards"], ["No free-form questions"], False),
        ("Tool-only agents", ["An agent calls UC function", "tools with a server-bound id"],
         ["Only the questions the", "tools were built for"], False),
        ("User id in the prompt", ["The id travels as text or", "as a session variable"],
         ["Not secure: users, injected", "text or the model itself", "can change it"], True),
    ]
    for i, (title, how, cost, insecure) in enumerate(cards):
        x = 40 + i * 236
        s.rect(x, 76, 220, 250, fill="deny_bg" if insecure else "white", stroke="deny" if insecure else "soft")
        s.text(x + 14, 104, title, size=15, weight="bold")
        s.text(x + 14, 134, "HOW", size=11, color="muted", weight="bold")
        s.lines(x + 14, 154, how, size=12.5, color="ink")
        s.text(x + 14, 226, "COST", size=11, color="deny", weight="bold")
        s.lines(x + 14, 246, cost, size=12.5, color="deny")
    s.rect(40, 350, 1160, 120, fill="claim_bg", stroke="claim")
    s.text(64, 384, "With custom identity claims", size=18, weight="bold", color="claim")
    s.lines(64, 414, ["One service principal per application. A signed token names the end user on every request.",
                      "Entitlements are rows in a table. Unity Catalog filters every query. Genie stays free-form."], size=14)
    return s


def request_flow() -> Svg:
    s = Svg(1240, 620)
    s.text(40, 40, "How one question flows", size=22, weight="bold")
    lanes = [("User's browser", 130, "white"), ("Your backend", 390, "white"), ("Databricks OAuth", 650, "white"),
             ("Genie Agent", 880, "genie_bg"), ("Unity Catalog", 1110, "claim_bg")]
    for name, cx, fill in lanes:
        s.box(cx - 100, 60, 200, 46, name, fill=fill, center=True, size=14)
        s.arrow([(cx, 106), (cx, 580)], color="soft", dash="4 6", head=False)
    s.arrow([(130, 160), (386, 160)], color="ink", label="sign in with your identity provider", label_pos=(258, 150))
    s.badge(106, 160, 1, color="ink")
    s.text(400, 186, "user id comes from the server-side session", size=12, color="muted")
    s.arrow([(390, 230), (646, 230)], color="claim", label="client_credentials + custom_claim=pu-2001", label_pos=(518, 220))
    s.badge(366, 230, 2)
    s.arrow([(650, 266), (394, 266)], color="claim", dash="6 4", label="signed token: custom.claim = pu-2001", label_pos=(522, 290))
    s.arrow([(390, 340), (876, 340)], color="genie", label="question + that token", label_pos=(640, 330))
    s.badge(366, 340, 3, color="genie")
    s.arrow([(880, 400), (1106, 400)], color="genie", label="SQL, the same for every user", label_pos=(995, 390))
    s.badge(856, 400, 4, color="genie")
    s.rect(990, 456, 240, 70, fill="claim_bg", stroke="claim")
    s.badge(966, 491, 5)
    s.lines(1004, 482, ["claim → entitlements table", "→ only the permitted rows"], size=12.5, color="claim")
    s.arrow([(1110, 560), (134, 560)], color="ok", dash="6 4", label="answer, through Genie and your backend", label_pos=(620, 552))
    s.text(40, 606, "The browser never sees the token, the claim or the Genie conversation id.", size=13, color="muted")
    return s


def layers() -> Svg:
    s = Svg(1240, 590)
    s.text(40, 40, "Four layers, each proved by the isolation suite", size=22, weight="bold")
    rows = [
        ("1  Unity Catalog grants", "Which application's service principal can read which views", "cross_app"),
        ("2  Service principal binding", "session_user() = this application's service principal, inside the view", "binding"),
        ("3  Claim → entitlements", "Grant rows for the user named in the signed token", "visibility · attack"),
        ("4  Role policy", "What that role may see: detail level, masking, minimum group size", "role_effect"),
    ]
    stops = [("Another application's service principal", "PERMISSION_DENIED"), ("A mistaken grant to another application", "0 rows"),
             ("A forged, unknown or malformed claim", "0 rows"), ("An advisor asks for dates of birth", "masked")]
    for i, ((title, body, test), (who, result)) in enumerate(zip(rows, stops)):
        y = 70 + i * 122
        s.rect(40, y, 740, 104, fill="claim_bg" if i < 2 else "white", stroke="claim")
        s.text(62, y + 34, title, size=17, weight="bold", color="claim")
        s.text(62, y + 62, body, size=13.5)
        s.pill(62, y + 74, f"proved by: {test}", color="muted", size=11)
        s.box(860, y + 10, 340, 84, who, [f"stops at layer {i + 1}: {result}"], fill="deny_bg", stroke="deny", size=13.5)
        s.arrow([(856, y + 52), (784, y + 52)], color="deny")
    return s


def entitlement_route() -> Svg:
    s = Svg(1240, 720)
    s.text(40, 40, "Tracing one lookup: Linda (pu-2001), plan sponsor and participant", size=22, weight="bold")
    s.box(40, 70, 260, 100, "Signed token", ['"custom": {"claim": "pu-2001"}', '"sub": <Northwind portal SP>'], fill="claim_bg",
          stroke="claim", mono_body=True, body_size=11.5)
    s.arrow([(300, 120), (995, 120), (995, 196)], color="claim", label="the claim travels inside the signed token", label_pos=(640, 110))
    s.box(330, 200, 410, 150, "portal_user_grants   (per user)", [
        "pu-2001  sponsor      plan         PLAN-A", "pu-2001  participant  participant  P-2001",
        "pu-1001  participant  participant  P-1001  (another user)"], mono_body=True, body_size=11)
    s.box(330, 375, 410, 130, "role_policies   (per role)", [
        "sponsor      aggregates  roster  dob visible", "participant  own accounts", "advisor      aggregates  roster  dob masked"],
        mono_body=True, body_size=11)
    s.rect(770, 200, 450, 280, fill="white", stroke="claim", width=2)
    s.text(790, 230, "governance.my_effective_grants", size=15, weight="bold", color="claim", mono=True)
    conds = ["portal_user_id = current_oauth_custom_identity_claim()", "session_user() = the Northwind portal SP",
             "today is between valid_from and valid_to", "join role_policies on role"]
    for i, c in enumerate(conds):
        s.badge(802, 270 + i * 50, i + 1)
        s.text(824, 275 + i * 50, c, size=11, mono=True)
    s.arrow([(740, 275), (766, 290)], color="line")
    s.arrow([(740, 440), (766, 420)], color="line")
    views = [("portal.my_accounts", ["her own Plan B account: P-2001"]), ("portal.plan_summary", ["Plan A totals by fund"]),
             ("portal.plan_roster", ["Plan A participants,", "dates of birth visible"])]
    for i, (name, body) in enumerate(views):
        x = 40 + i * 400
        s.box(x, 550, 360, 100, name, body, fill="ok_bg", stroke="ok", size=14)
        s.arrow([(995, 480), (x + 180, 546)], color="ok")
    s.text(40, 690, "No matching grant means every portal view returns no rows: the design fails closed.", size=14, color="muted")
    return s


def object_map() -> Svg:
    s = Svg(1240, 640)
    s.text(40, 40, "Who owns what, and who can read what", size=22, weight="bold")
    s.box(40, 70, 340, 80, "Pipelines and internal users", ["write and read base tables as usual"])
    s.box(450, 70, 340, 80, "View owner", ["you, or an account group in production"])
    s.box(860, 70, 340, 80, "Portal service principal", ["one per application"], fill="claim_bg", stroke="claim", title_color="claim")
    schemas = [(40, "<example>_base", ["plans, participants, balances", "no claim logic: pipelines unaffected"]),
               (450, "<example>_governance", ["portal_user_grants", "role_policies", "my_effective_grants (claim)"]),
               (860, "<example>_portal", ["claim-keyed views", "my_access", "public reference views"])]
    for x, name, body in schemas:
        s.box(x, 250, 340, 150, name, body, size=15)
    s.arrow([(210, 150), (210, 246)], color="ok", label="write", label_pos=(236, 205))
    s.arrow([(560, 150), (300, 246)], color="line")
    s.arrow([(620, 150), (620, 246)], color="line")
    s.text(560, 226, "owner's rights", size=12, color="muted", anchor="middle")
    s.arrow([(1030, 150), (1030, 246)], color="ok", label="SELECT on views only", label_pos=(1110, 205))
    s.arrow([(860, 135), (825, 135), (825, 430), (210, 430), (210, 404)], color="deny", dash="6 5")
    s.arrow([(620, 430), (620, 404)], color="deny", dash="6 5")
    s.text(415, 452, "no grants on base or governance", size=12, color="deny", anchor="middle")
    s.box(860, 480, 340, 110, "Genie Agent", ["attached to portal views only", "prompt matching off on claim-keyed views",
                                              "portal SP has Can Run"], fill="genie_bg", stroke="genie", title_color="genie")
    s.arrow([(1030, 476), (1030, 404)], color="genie")
    return s


def deploy_flow() -> Svg:
    s = Svg(1240, 560)
    s.text(40, 40, "What the bundle's deploy job does", size=22, weight="bold")
    steps = ["01 availability", "02 data", "03 entitlements", "04 claim views", "05 runtime grants", "06 Genie Agent", "07 validate"]
    x = 40
    for i, label in enumerate(steps):
        w = s.pill(x, 64, label, color="claim" if i == 3 else "muted", bg="claim_bg" if i == 3 else "white", size=13)
        x += w + 18
    s.box(40, 130, 1160, 130, "Step 04 when the function returns NULL without a claim", [], fill="ok_bg", stroke="ok")
    s.box(70, 176, 330, 64, "Admin creates the views", [], size=14)
    s.box(450, 176, 330, 64, "Ownership set to view_owner", [], size=14)
    s.arrow([(400, 208), (446, 208)], color="ok")
    s.box(40, 290, 1160, 200, "Step 04 when the function raises OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED", [], fill="mask_bg", stroke="mask")
    seq = ["Temporary grants to the portal SP", "Portal SP creates views with a claim-carrying token",
           "Admin takes ownership", "Temporary grants revoked, even on failure"]
    for i, label in enumerate(seq):
        bx = 70 + i * 285
        s.rect(bx, 350, 260, 90, fill="white", stroke="mask")
        s.badge(bx + 22, 372, i + 1, color="mask")
        words, line, out = label.split(), "", []
        for wd in words:
            if len(line) + len(wd) > 26:
                out.append(line.strip())
                line = ""
            line += wd + " "
        out.append(line.strip())
        s.lines(bx + 44, 377, out, size=13)
        if i < 3:
            s.arrow([(bx + 260, 395), (bx + 281, 395)], color="mask")
    s.text(40, 530, "Either way the portal service principal ends with SELECT on portal views and nothing else.", size=14, color="muted")
    return s


def decision_tree() -> Svg:
    s = Svg(1240, 640)
    s.text(40, 40, "Is this the right pattern?", size=22, weight="bold")

    def q(x, y, text):
        s.box(x, y, 330, 76, text[0], text[1:], fill="panel", stroke="line", size=14)

    def outcome(x, y, title, body, color):
        s.box(x, y, 330, 96, title, body, fill=f"{color}_bg", stroke=color, title_color=color, size=14)

    q(40, 70, ["Do users ask free-form questions?"])
    outcome(40, 210, "Use something simpler", ["Embedded dashboards, or an agent", "with UC function tools"], "mask")
    s.arrow([(205, 146), (205, 206)], color="mask", label="no", label_pos=(222, 180))
    q(450, 70, ["Are the users employees already", "synced to Databricks?"])
    s.arrow([(370, 108), (446, 108)], color="ok", label="yes", label_pos=(408, 100))
    outcome(450, 210, "Per-user identities", ["Standard identities with row filters"], "mask")
    s.arrow([(615, 146), (615, 206)], color="mask", label="yes", label_pos=(634, 180))
    q(860, 70, ["Does a multi-agent supervisor", "sit in front of Genie?"])
    s.arrow([(780, 108), (856, 108)], color="ok", label="no", label_pos=(818, 100))
    outcome(860, 210, "Bind the id in tools", ["Pass the user id server-side", "to UC function tools"], "mask")
    s.arrow([(1025, 146), (1025, 206)], color="mask", label="yes", label_pos=(1044, 180))
    q(860, 350, ["Must per-user attribution live in", "Databricks audit tables?"])
    s.arrow([(1200, 108), (1220, 108), (1220, 388), (1194, 388)], color="ok", label="no", label_pos=(1232, 250))
    outcome(450, 350, "Plan the audit trail", ["Queries are attributed to the", "service principal: log users in your app"], "mask")
    s.arrow([(856, 388), (784, 388)], color="mask", label="yes", label_pos=(820, 380))
    outcome(860, 500, "Custom identity claims", ["One service principal per application,", "one Genie Agent: this repo"], "ok")
    s.arrow([(1025, 426), (1025, 496)], color="ok", label="no", label_pos=(1044, 466))
    return s


DIAGRAMS = {"previous-patterns": previous_patterns, "request-flow": request_flow, "layers": layers,
            "entitlement-route": entitlement_route, "object-map": object_map, "deploy-flow": deploy_flow,
            "decision-tree": decision_tree}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in DIAGRAMS.items():
        build().save(OUT / f"{name}.svg")
        print(f"wrote {name}.svg")


if __name__ == "__main__":
    main()
