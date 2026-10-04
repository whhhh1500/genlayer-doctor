import * as gd from "./gldoctor.js";
import { EXAMPLES } from "./examples.js";

const $ = (s) => document.querySelector(s);
$("#ver").textContent = "v" + gd.VERSION;

function rpcUrl() {
  const n = $("#net").value;
  return n === "custom" ? $("#custom").value.trim() : gd.NETWORKS[n].rpc;
}
function explorer() {
  const n = $("#net").value;
  return n === "custom" ? null : gd.NETWORKS[n].explorer;
}
$("#net").addEventListener("change", () => { $("#custom-wrap").hidden = $("#net").value !== "custom"; });

// tabs (keyboard accessible)
const tabs = [$("#tab-check"), $("#tab-tx")];
function select(tab) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", on);
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
  }
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => select(t));
  t.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]; select(n); n.focus(); }
  });
});

function el(tag, cls, ...kids) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : String(k));
  return e;
}
function renderFindings(findings) {
  if (!findings.length) return el("p", "ok", "✔ No findings.");
  return el("ul", "findings", findings.map((f) => el("li", `sev-${f.severity}`,
    el("span", "badge", f.severity), " ", el("code", null, f.code), f.line ? ` line ${f.line}: ` : ": ", f.message,
    f.hint ? el("div", "hint", "hint: ", f.hint) : null,
    f.details?.length ? el("pre", null, f.details.join("\n")) : null)));
}
function verdict(kind, text) { return el("p", `verdict v-${kind}`, text); }

// ---- check
$("#src").value = EXAMPLES["bad_floating_runner.py"];
document.querySelectorAll("[data-ex]").forEach((b) => b.addEventListener("click", () => { $("#src").value = EXAMPLES[b.dataset.ex]; $("#check-out").replaceChildren(); }));

async function runCheck(dry) {
  const out = $("#check-out");
  out.replaceChildren(el("p", "muted", dry ? `Dry run on ${rpcUrl()}…` : "Linting…"));
  const { findings } = await gd.checkSource($("#src").value, dry ? rpcUrl() : null);
  const bad = findings.some((f) => f.severity === "error");
  out.replaceChildren(
    verdict(bad ? "bad" : "ok", bad ? "FAIL: this contract would not deploy/run correctly." : dry ? "PASS: the node loaded the contract." : "PASS (offline lint only)."),
    renderFindings(findings),
  );
}
$("#run-check").addEventListener("click", () => runCheck(true));
$("#run-lint").addEventListener("click", () => runCheck(false));
$("#run-fix").addEventListener("click", () => {
  const before = $("#src").value;
  const after = gd.fixSource(before);
  $("#src").value = after;
  $("#check-out").replaceChildren(el("p", "muted", before === after ? "Header already pinned." : "Header pinned to the recommended py-genlayer runner. Run the check again."));
});

// ---- explain
document.querySelectorAll("[data-tx]").forEach((b) => b.addEventListener("click", () => { $("#tx").value = b.dataset.tx; $("#net").value = "studionet"; explain(); }));
$("#tx-form").addEventListener("submit", (e) => { e.preventDefault(); explain(); });

async function explain() {
  const hash = $("#tx").value.trim();
  const out = $("#tx-out");
  history.replaceState(null, "", `#tx=${hash}&net=${$("#net").value}`);
  out.replaceChildren(el("p", "muted", `Fetching ${hash.slice(0, 10)}… from ${rpcUrl()}`));
  try {
    const r = await gd.explainHash(hash, rpcUrl());
    const ex = explorer();
    const link = (p, t) => { if (!ex) return t; const a = el("a", null, t); a.href = `${ex}/${p}`; a.target = "_blank"; a.rel = "noopener"; return a; };
    const dl = el("dl", "kv");
    const row = (k, v) => dl.append(el("dt", null, k), el("dd", null, v));
    row("type", r.type);
    row("status", `${r.status}${r.resultName ? " / " + r.resultName : ""}`);
    row("leader execution", r.leaderExecution || "—");
    row("result", `${r.resultKind || "—"}${r.resultPayload ? ": " + r.resultPayload : ""}`);
    row("votes", Object.entries(r.votes).map(([k, v]) => `${k}×${v}`).join(", ") || "—");
    if (r.sender) row("from", link(`address/${r.sender}`, r.sender));
    if (r.contractAddress) row("contract", link(`address/${r.contractAddress}`, r.contractAddress));
    else if (r.to) row("to", link(`address/${r.to}`, r.to));
    if (r.messages) row("emitted messages", `${r.messages} (e.g. value transfers, executed on finalization)`);
    row("explorer", link(`tx/${r.hash}`, "open"));
    const msg = { OK: "OK: consensus reached and the code really executed.", FAILED: "FAILED: see findings below.", PENDING: "PENDING: not decided yet.", UNKNOWN: "UNKNOWN" }[r.verdict];
    out.replaceChildren(verdict(r.verdict === "OK" ? "ok" : r.verdict === "PENDING" ? "warn" : "bad", msg), dl, renderFindings(r.findings));
  } catch (e) {
    out.replaceChildren(verdict("bad", `Could not explain: ${e.message}`));
  }
}

// deep links: #tx=0x..&net=studionet
const h = new URLSearchParams(location.hash.slice(1));
if (h.get("net") && [...$("#net").options].some((o) => o.value === h.get("net"))) $("#net").value = h.get("net");
if (h.get("tx")) { select($("#tab-tx")); $("#tx").value = h.get("tx"); explain(); }
