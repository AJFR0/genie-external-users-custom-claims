This guide builds the pattern from the [Overview](overview.html) end to end, using the two fictional companies in this repo: **Northwind Retirement Services**, a 401(k) recordkeeper, and **Larkspur Pharmacy Benefits**, a pharmacy benefit manager. Every SQL block below is the real file the bundle deploys, and every trace card and result table comes from a live run of the isolation suite.

## Before you start

- A Unity Catalog workspace and a serverless or pro SQL warehouse.
- A workspace admin for the one-time bootstrap step (it creates service principals and their OAuth secrets).
- The `CREATE CATALOG` privilege, or an existing catalog you can create schemas in.
- The Databricks CLI with bundle support, and Python 3.10 or later for the local app and the command-line tools.

## Step 1: Check availability

OAuth custom identity claims are announced on the Databricks *What's coming?* page ([AWS](https://docs.databricks.com/aws/en/release-notes/whats-coming), [Azure](https://learn.microsoft.com/en-us/azure/databricks/release-notes/whats-coming)). There is no workspace setting to turn on. Three checks tell you whether your workspace has them.

**Check 1 and 2, in the SQL editor.** These are in `sql/check_availability.sql`.

```sql
DESCRIBE FUNCTION current_oauth_custom_identity_claim;
SELECT current_oauth_custom_identity_claim() AS claim;
```

| Result | Meaning |
|---|---|
| `DESCRIBE` returns a description | The function exists in this workspace |
| `SELECT` returns `NULL` | Available. Claim-keyed views can be created by any identity. |
| `SELECT` raises `OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED` | Available. Claim-keyed views must be created from a session that carries a claim; the bundle does this for you. |
| Either raises `UNRESOLVED_ROUTINE` | Not available in this workspace yet |

**Check 3, with a service principal token.** Request a token with `custom_claim` set, then read it back through the Statement Execution API:

```bash
TOKEN=$(curl -s -X POST "https://<workspace-host>/oidc/v1/token" \
  -u "<client-id>:<client-secret>" \
  -d grant_type=client_credentials -d scope=all-apis \
  -d custom_claim=availability-probe | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST "https://<workspace-host>/api/2.0/sql/statements" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"warehouse_id": "<warehouse-id>", "wait_timeout": "30s",
       "statement": "SELECT current_oauth_custom_identity_claim() AS claim, session_user() AS caller"}'
```

The result must contain `availability-probe` and the service principal's application id. If the token request returns HTTP 403 with `custom_claim is not enabled for account`, ask your Databricks account team. Notebook 01 and `python -m claims_kit.availability` run all three checks and report which deploy mode the workspace needs.

## Architecture

[[ diagram("object-map", "Who owns what, and who can read what.") ]]

| Identity | May do |
|---|---|
| Pipelines and internal users | Write and read the base tables as usual. Base tables carry no claim logic. |
| View owner (you, or an account group in production) | Owns the claim-keyed views. Views read the base and governance tables with the owner's rights. |
| Portal service principal, one per application | `USE CATALOG`, `USE SCHEMA` on its portal schema, `SELECT` on its portal views. Nothing else. |
| Genie Agent | Attached to the portal views only. The portal service principal has Can Run. |
| Operators | Change entitlements with their own identity, through your admin tooling (the local app's admin tab in this repo). |

## Step 2: Deploy with the bundle

```bash
databricks bundle deploy -p <profile> --var warehouse_id=<warehouse-id>
databricks bundle run bootstrap -p <profile> --var warehouse_id=<warehouse-id>
databricks bundle run northwind_deploy -p <profile> --var warehouse_id=<warehouse-id>
databricks bundle run larkspur_deploy -p <profile> --var warehouse_id=<warehouse-id>
```

| Variable | Default | Meaning |
|---|---|---|
| `catalog` | `genie_claims_ref` | Catalog for both examples |
| `create_catalog` | `true` | Create the catalog if it is missing. Use `false` with an existing catalog. |
| `warehouse_id` | (required) | SQL warehouse for the service principals, the Statement API and Genie |
| `secret_scope` | `genie-claims-ref` | Where bootstrap stores each service principal's client id and secret |
| `view_owner` | the deploying user | Owner of the claim-keyed views. Use an account group in production. |

If you can't create catalogs, point the bundle at one you can use: `--var catalog=<existing catalog> --var create_catalog=false`.

[[ diagram("deploy-flow", "Step 04 adapts to how the workspace treats a missing claim.") ]]

| Notebook | What it does |
|---|---|
| `00_bootstrap_service_principals` | One service principal per application, an OAuth secret in the secret scope, Can Use on the warehouse |
| `01_check_availability` | The three checks above, and the deploy mode |
| `02_create_data` | Catalog (optional), three schemas per example, deterministic synthetic data |
| `03_entitlements` | Per-user grants and per-role policies, with CHECK constraints |
| `04_claim_views` | The claim-keyed views, in either deploy mode |
| `05_runtime_grants` | `SELECT` on portal views for the portal service principal, nothing else |
| `06_genie_agent` | The Genie Agent over the portal views, with Can Run for the service principal |
| `07_validate_isolation` | The isolation suite; the task fails if any check fails |

## Step 3: Understand each object (Northwind)

Three schemas per application keep pipelines, policy and the portal apart: `northwind_base`, `northwind_governance` and `northwind_portal`.

### Entitlements

Per-user grants and per-role policies, with constraints that reject malformed claims and unknown roles:

[[ sql("northwind", "governance") ]]

The seed rows. Linda holds two roles, so she has two rows:

[[ sql("northwind", "seed_entitlements") ]]

### The policy view

This is the only object that reads the claim. A grant counts only when it belongs to the user named in the token, the caller is this application's service principal, today is inside the grant's dates, and the role has a policy.

[[ sql("northwind", "policy_views") ]]

### The portal views

None of these mentions the claim. Each joins to `my_effective_grants`, groups the user's scope first so several grants never duplicate rows, and applies the role policy.

[[ sql("northwind", "portal_views") ]]

### Runtime grants

[[ sql("northwind", "runtime_grants") ]]

## Step 4: Configure the Genie Agent

- **Attach the portal views only.** Never attach base tables, entitlement tables or the policy view.
- **Turn prompt matching off on claim-keyed views.** Prompt matching samples column values with the author's permissions and shares them with every user. Leave it on only for public reference views such as the fund lineup.
- **Compensate in the instructions.** With prompt matching off, Genie can't look up values, so tell it how users name things. Northwind's instructions map "Plan A" to `plan_id = 'PLAN-A'`; without that line Genie filtered on the plan name and found nothing.
- **Queries run as the caller**, which is the default. Every query then carries the user's claim.
- **Can Run for the portal service principal. Can Manage for a small admin group only.** Managers can read every conversation and its stored results.
- **Say how to answer about other people.** Northwind's instructions include: "If a question names a person who does not appear in the data, say that you can't see information about that person. Never answer with the signed-in user's own data instead."

## Entitlement pattern catalog

Each pattern below is live in one of the two examples, and the trace cards show what a real token resolved to.

### 1. Per-user rows

One row per user, role and scope. Onboarding a user is an insert.

```sql
INSERT INTO <catalog>.northwind_governance.portal_user_grants
VALUES ('pu-1001', 'participant', 'participant', 'P-1001', DATE '2026-01-01', NULL, 'provisioning job', current_timestamp());
```

### 2. Role policies

What a role may see lives in one row. Turning off `mask_dob` for advisors changes every advisor on their next question.

```sql
UPDATE <catalog>.northwind_governance.role_policies SET mask_dob = false WHERE role = 'advisor';
```

### 3. Several roles per user

Linda sponsors Plan A and is a participant in Plan B. Two rows, one session, both views answer:

[[ trace_card("northwind", "linda") ]]

### 4. Masking by role

Raj is an advisor. The roster view hides dates of birth because his role policy says so:

```sql
CASE WHEN r.mask_dob THEN NULL ELSE p.date_of_birth END AS date_of_birth
```

[[ trace_card("northwind", "raj") ]]

When grants disagree, the least restrictive one wins (`bool_and(mask_dob)` across the user's grants for a plan). Change that to `bool_or` if you want the most restrictive grant to win.

### 5. Relationship rules derived from data

Larkspur subscribers whose role includes minor dependents also see their children under 18. No grant rows are needed for the children, and adult dependents stay private:

```sql
SELECT m.member_id, 'minor dependent' AS visible_as
FROM <catalog>.larkspur_governance.my_effective_grants AS e
JOIN <catalog>.larkspur_base.members AS m ON m.subscriber_id = e.scope_id
WHERE e.include_minor_dependents AND m.relationship = 'child'
  AND m.date_of_birth > add_months(current_date(), -216)
```

[[ trace_card("larkspur", "ana") ]]

### 6. Aggregates with a minimum group size

Benefits administrators see spend by quarter and drug class, never member rows. Groups with fewer distinct members than the role's `min_cell_size` disappear:

```sql
HAVING COUNT(DISTINCT c.member_id) >= ms.min_cell_size
```

[[ trace_card("larkspur", "dana") ]]

Totals then cover the visible groups only, so the Genie instructions tell it to say so.

### 7. Time-bound grants

Theo's consulting engagement with Cedar Logistics ended on June 30, so that grant no longer matches. His consultant role also uses a larger minimum group size (20) than Dana's administrator role (11), so he sees fewer Alder groups than she does:

[[ trace_card("larkspur", "theo") ]]

### 8. Masking identity for a partner

Pharmacy staff reconcile claims filled at their pharmacy. The member id becomes a one-way reference:

```sql
CASE WHEN mp.mask_identity THEN substr(sha2(concat('larkspur-demo:', c.member_id), 256), 1, 16) ELSE c.member_id END
```

[[ trace_card("larkspur", "priya") ]]

This hash is demo grade. In production use a keyed hash or a token vault so a reference can't be reversed by hashing every member id.

### 9. Fail closed, and one service principal per application

A user who signs in but has no grants sees nothing:

[[ trace_card("northwind", "unknown") ]]

Each application's views also check `session_user()`, so a Larkspur token carrying a Northwind user's claim is denied by grants and, even with a mistaken grant, returns no rows.

## Step 5: Integrate your backend

The local app in `app/` is a working reference. The parts that matter in production:

- **Take the user id from your server-side session.** Never from the browser, the chat or a URL. Validate its format before minting: Unity Catalog trims surrounding spaces from the claim and keeps its case, so `" pu-1001 "` matches `pu-1001` and `PU-1001` matches nothing. See `src/claims_kit/claims.py`.
- **Mint and cache one token per user.** `client_credentials` with `custom_claim`, cached until a few minutes before it expires, never sent to the browser. To avoid storing a client secret, use the `urn:ietf:params:oauth:grant-type:token-exchange` grant (workload identity federation) with the same `custom_claim` parameter. See `src/claims_kit/tokens.py`.
- **Bind conversations to users.** Genie conversations belong to the service principal, and any token from that service principal can read them. Keep your own map of user to conversation id, never accept a conversation id from the client, start a new conversation per session, delete it at sign-out, and delete old conversations on a schedule. See `app/conversations.py`.
- **Write your own audit log.** Query history attributes every query to the service principal, so Databricks audit data can't tell you which end user asked. Log the user id, conversation id, message id and statement ids, and join to query history on statement id. See `app/audit.py`.
- **Retry transient warehouse errors** and nothing else. See `StatementRunner.execute`.
- **Trace each request while you build.** `app/ask_flow.py` records every step a question takes, from session to audit record, which makes isolation easy to explain and to debug.

## Security model and best practices

- The user id comes only from your authenticated session.
- Treat the service principal credential as a master key: it can mint a token for any user. Keep it in a vault, rotate it, restrict where it can be used, or use workload identity federation and store no secret.
- Keep tokens short-lived and on the server.
- Keep base tables free of claim logic so pipelines and administrators keep working on them.
- Grant the portal service principal `SELECT` on portal views and nothing else. The isolation suite proves it can't read base or governance objects, change entitlements or create objects.
- One service principal per application, and every view checks `session_user()`.
- Keep prompt matching off on claim-keyed views, and keep Can Manage on the Genie Agent to a small group.
- Run the isolation suite after every change to views, entitlements or the Genie Agent, and keep the results as evidence.

## Behavior notes

- **No claim.** Depending on the workspace's current release, `current_oauth_custom_identity_claim()` either returns `NULL` or raises `OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED` when the token carries no claim. The function is evaluated when a statement is analyzed, so in the second case even `CREATE VIEW` needs a claim-carrying session. Notebook 04 detects which case applies.
- **Trimming and case.** Surrounding spaces are trimmed; case is kept.
- **Conversations** belong to the service principal (see Step 5).
- **Attribution.** Query history shows the service principal.
- **Surfaces.** The announcement lists the Genie Conversation API, the SQL Statement Execution API and the JDBC driver. Jobs, notebooks, the SQL editor and dashboards run without a claim, and multi-agent supervisors are not listed, so design for one Genie Agent per request.

## Step 6: Validate

`notebooks/07_validate_isolation.py` (task 07 of each deploy job) and `python -m claims_kit.validate --example <name>` mint real tokens for every persona and check each layer:

| Category | What it proves |
|---|---|
| visibility | Each persona sees exactly the ids its grants allow, in every portal view, with no duplicated rows |
| role_effect | Masking rules from role policies hold |
| constraint | The entitlements table rejects malformed claims (trailing newline, uppercase, leading space) |
| attack | No claim, injection strings, wildcards, uppercase and control characters see nothing; an admin session without a claim sees nothing |
| privilege | The portal service principal can't read base or governance objects, change entitlements or create a view |
| cross_app | Another application's service principal is denied |
| binding | Even with a mistaken grant, the view answers only for its own service principal |
| token | Edited, unsigned and corrupted tokens are rejected |
| genie | Answers contain the persona's own numbers and nobody else's |
| documented | Platform behaviors your backend must handle (trimming, conversation ownership); never fails the run |

Results from the live runs behind this guide:

[[ validation_summary("northwind") ]]

[[ validation_summary("larkspur") ]]

A case is inconclusive, never passed, when the evidence is ambiguous: Genie doesn't finish or doesn't state the expected number, a transient warehouse error interrupts a check, or an object is hidden instead of explicitly denied. Only a leaked number or a wrong row fails a case, and every result records the reason it passed.

## Production checklist

1. One service principal per application; its credential in a vault with rotation, or workload identity federation.
2. User id from the authenticated session only, validated against your canonical format.
3. Tokens minted on the server, cached per user, never sent to the browser.
4. Portal service principal: `USE CATALOG`, `USE SCHEMA` and `SELECT` on portal views only.
5. Claim-keyed views owned by an account group, with explicit column lists and comments on every column.
6. Base tables without claim logic; entitlement tables with CHECK constraints.
7. Genie Agent on portal views only, prompt matching off on claim-keyed views, Can Manage limited, instructions for naming and for other people.
8. Conversation ids bound to users on the server; deleted at sign-out and on a schedule.
9. Per-user audit log joined to query history on statement id.
10. Transient errors retried; Genie polling with backoff and a timeout.
11. Isolation suite run on every change, with results kept as evidence.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Token request returns 403 `custom_claim is not enabled for account` | Custom identity claims are not available for this account yet. Ask your Databricks account team. |
| `OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED` while creating a view | The workspace evaluates the function without a claim. Create claim-keyed views from a claim-carrying session (notebook 04 does). |
| The portal service principal gets `INSUFFICIENT_PERMISSIONS` on the warehouse | Grant it Can Use on the warehouse (bootstrap does). |
| Genie reports "Failed to fetch tables" when creating the agent | The views don't exist yet. Create the agent after the views (task 06 runs after 04 and 05). |
| `ALTER VIEW ... OWNER TO` is denied | The deploying user needs ownership or MANAGE on the catalog or schema, or metastore admin. |
| The admin console rejects a grant with a CHECK constraint error | The console checks ids, roles and scope types itself, so this is usually an end date before the start date. Jobs that write grants directly also hit the claim, role and scope constraints. |
| Statements fail with "catalog not found" for an unqualified name | Fully qualify every name. The workspace's default catalog may not be the one you expect. |
| Genie answers with zero for a plan or sponsor | It filtered on a display name. Add the naming rule to the instructions (prompt matching is off on claim-keyed views). |
