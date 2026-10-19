const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
// Genie answers use **bold**; render only that, after escaping everything else.
const md = (v) => esc(v).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");

function table(columns, rows) {
  if (!columns || !columns.length) return "";
  const head = columns.map((c) => `<th>${esc(c)}</th>`).join("");
  const body = (rows || []).map((r) => `<tr>${r.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("");
  return `<div class="tbl"><table><thead><tr>${head}</tr></thead><tbody>${body || `<tr><td colspan="${columns.length}" class="dim">no rows</td></tr>`}</tbody></table></div>`;
}

function renderValue(v) {
  if (Array.isArray(v) && v.every((x) => typeof x === "string")) return v.map((x) => `<pre>${esc(x)}</pre>`).join("");
  if (Array.isArray(v)) return v.map(renderValue).join("");
  if (v && typeof v === "object" && Array.isArray(v.columns)) return table(v.columns, v.rows) + (v.row_count !== undefined ? `<div class="dim">${v.row_count} rows · statement ${esc(v.statement_id)}</div>` : "");
  if (v && typeof v === "object") return `<pre>${esc(JSON.stringify(v, null, 2))}</pre>`;
  return `<span>${esc(v)}</span>`;
}

function renderTrace(steps) {
  $("#trace").innerHTML = steps.map((s) => `
    <li class="step ${esc(s.status)}">
      <div class="head"><span class="n">${s.n}</span><span class="title">${esc(s.title)}</span><span class="ms">${s.ms} ms</span></div>
      ${Object.entries(s.detail || {}).map(([k, v]) => `<div class="kv"><div class="k">${esc(k.replaceAll("_", " "))}</div><div class="v">${renderValue(v)}</div></div>`).join("")}
    </li>`).join("");
}

function renderAnswer(question, data) {
  const turn = document.createElement("div");
  turn.className = "turn";
  let html = `<div class="q">${esc(question)}</div>`;
  if (data.error) html += `<div class="a error">${esc(data.error)}</div>`;
  else if (data.answer) {
    const a = data.answer;
    html += `<div class="a ${a.status === "COMPLETED" ? "" : "warn"}">${a.text.map(md).join("<br>") || esc(a.error || a.status)}`;
    for (const q of a.queries) html += table(q.columns, q.rows);
    html += `</div>`;
  }
  turn.innerHTML = html;
  $("#messages").appendChild(turn);
  turn.scrollIntoView({behavior: "smooth", block: "end"});
}

async function ask(question) {
  const button = $("#ask button");
  button.disabled = true;
  button.textContent = "Asking…";
  try {
    const res = await fetch("/portal/api/ask", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question, new_conversation: $("#new_conversation").checked})});
    const data = await res.json();
    renderAnswer(question, res.ok ? data : {error: data.detail || res.statusText});
    if (data.trace) renderTrace(data.trace);
  } finally {
    button.disabled = false;
    button.textContent = "Ask";
    $("#new_conversation").checked = false;
  }
}

$("#ask")?.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#question").value.trim();
  if (q) { $("#question").value = ""; ask(q); }
});
document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => ask(b.dataset.q)));
