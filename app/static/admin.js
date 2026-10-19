const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const EXAMPLES = JSON.parse($(".admin").dataset.examples);
let current = Object.keys(EXAMPLES)[0];

async function api(method, path, body) {
  const res = await fetch(path, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { alert(data.detail || res.statusText); throw new Error(data.detail || res.statusText); }
  return data;
}

const head = (cols, extra = "") => `<thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}${extra}</tr></thead>`;

async function loadGrants() {
  const data = await api("GET", `/admin/api/${current}/grants`);
  const at = Object.fromEntries(data.columns.map((c, i) => [c, i]));
  $("#grants").innerHTML = `<table>${head(data.columns, "<th></th>")}<tbody>${data.rows.map((r) => {
    const key = esc(JSON.stringify({portal_user_id: r[at.portal_user_id], role: r[at.role], scope_type: r[at.scope_type], scope_id: r[at.scope_id]}));
    const active = String(r[at.active]) === "true";
    return `<tr class="${active ? "" : "inactive"}">${r.map((v) => `<td>${esc(v)}</td>`).join("")}<td>
      <button class="ghost" data-act="expire" data-key="${key}" ${active ? "" : "disabled"}>Expire</button>
      <button class="ghost" data-act="delete" data-key="${key}">Delete</button></td></tr>`;
  }).join("")}</tbody></table>`;
  $("#grants").querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
    const key = JSON.parse(b.dataset.key);
    if (b.dataset.act === "expire") await api("POST", `/admin/api/${current}/grants/expire`, key);
    else await api("DELETE", `/admin/api/${current}/grants`, key);
    refresh();
  }));
}

async function loadPolicies() {
  const data = await api("GET", `/admin/api/${current}/role-policies`);
  const fields = EXAMPLES[current].role_policy_fields;
  $("#policies").innerHTML = `<table>${head(data.columns)}<tbody>${data.rows.map((r) => `<tr>${r.map((v, i) => {
    const col = data.columns[i], role = esc(r[0]);
    if (!(col in fields)) return `<td>${esc(v)}</td>`;
    if (fields[col] === "boolean") return `<td><input type="checkbox" data-role="${role}" data-field="${esc(col)}" ${String(v) === "true" ? "checked" : ""}></td>`;
    return `<td><input type="number" min="0" value="${esc(v)}" data-role="${role}" data-field="${esc(col)}"></td>`;
  }).join("")}</tr>`).join("")}</tbody></table>`;
  $("#policies").querySelectorAll("input").forEach((inp) => inp.addEventListener("change", async () => {
    const value = inp.type === "checkbox" ? inp.checked : parseInt(inp.value, 10);
    await api("PUT", `/admin/api/${current}/role-policies/${encodeURIComponent(inp.dataset.role)}`, {field: inp.dataset.field, value});
    refresh();
  }));
}

async function loadAudit() {
  const data = await api("GET", "/admin/api/audit");
  $("#audit").innerHTML = `<ul class="audit">${data.records.slice().reverse().map((r) =>
    `<li><code>${esc(r.ts)}</code> <b>${esc(r.event)}</b> ${esc(r.example)} <code>${esc(r.portal_user_id)}</code> ${esc(r.question || r.detail || r.error)}</li>`).join("")}</ul>`;
}

function refresh() { return Promise.all([loadGrants(), loadPolicies(), loadAudit()]).catch((e) => console.error(e)); }

function selectExample(name) {
  current = name;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.ex === name));
  $("#add-grant [name=role]").innerHTML = EXAMPLES[name].grant_roles.map((v) => `<option>${esc(v)}</option>`).join("");
  $("#add-grant [name=scope_type]").innerHTML = EXAMPLES[name].scope_types.map((v) => `<option>${esc(v)}</option>`).join("");
  refresh();
}

document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => selectExample(b.dataset.ex)));
$("#add-grant").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const body = {portal_user_id: f.get("portal_user_id"), role: f.get("role"), scope_type: f.get("scope_type"), scope_id: f.get("scope_id")};
  if (f.get("valid_to")) body.valid_to = f.get("valid_to");
  await api("POST", `/admin/api/${current}/grants`, body);
  e.target.reset();
  selectExample(current);
});
if (current) selectExample(current);
