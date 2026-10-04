// genlayer-doctor in the browser: a dependency-free port of the CLI's checks.
// Mirrors src/genlayer_doctor/{header,diagnose,explain,check}.py. Same finding codes.

export const VERSION = "0.2.0";
export const NETWORKS = {
  studionet: { rpc: "https://studio.genlayer.com/api", explorer: "https://explorer-studio.genlayer.com", note: "Hosted GenLayer Studio (free)" },
  localnet: { rpc: "http://127.0.0.1:4000/api", explorer: null, note: "Local Studio / GLSim on port 4000" },
};
export const RECOMMENDED_RUNNERS = { "py-genlayer": "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" };
const KNOWN_RUNNER_NAMES = new Set(["py-genlayer", "py-genlayer-multi", "py-lib-genlayer-embeddings", "py-lib-genlayer-std"]);
const FLOATING = new Set(["test", "latest"]);
const NIX32 = /^[0123456789abcdfghijklmnpqrsvwxyz]{52}$/;
const HEADER_LINE = /^\s*#\s*(\{.*\})\s*$/;
const F = (code, severity, message, extra = {}) => ({ code, severity, message, ...extra });

// ------------------------------------------------------------------ header
function collectDepends(node, out) {
  if (Array.isArray(node)) node.forEach((n) => collectDepends(n, out));
  else if (node && typeof node === "object")
    for (const [k, v] of Object.entries(node)) {
      if (k === "Depends" && typeof v === "string") out.push(v);
      else collectDepends(v, out);
    }
}

export function lintHeader(source) {
  const findings = [];
  const lines = source.split(/\r?\n/);
  const firstIdx = lines.findIndex((l) => l.trim());
  let idx = -1;
  for (let i = 0; i < Math.min(20, lines.length); i++) {
    if (HEADER_LINE.test(lines[i]) && (lines[i].includes("Depends") || lines[i].includes("Seq"))) { idx = i; break; }
  }
  const fixHint = "Use “Fix header” to insert the recommended header.";
  const rec = RECOMMENDED_RUNNERS["py-genlayer"];
  if (idx < 0) {
    findings.push(F("GLD001", "error", `Missing GenVM runner header. Line 1 must be a JSON comment such as # { "Depends": "py-genlayer:${rec}" }`, { line: 1, hint: fixHint }));
    return findings;
  }
  const line = idx + 1;
  if (idx !== 0 || firstIdx !== idx)
    findings.push(F("GLD007", "warning", `Runner header found on line ${line}; GenVM expects it on line 1 (no shebang, blank line or docstring before it).`, { line, hint: "Move the header to the very first line." }));
  let data;
  try { data = JSON.parse(lines[idx].match(HEADER_LINE)[1]); } catch (e) {
    findings.push(F("GLD002", "error", `Runner header is not valid JSON: ${e.message}.`, { line, hint: 'Use double quotes, e.g. # { "Depends": "py-genlayer:<hash>" }' }));
    return findings;
  }
  const deps = [];
  collectDepends(data, deps);
  if (!deps.length) { findings.push(F("GLD003", "error", 'Runner header has no "Depends" entry.', { line, hint: fixHint })); return findings; }
  for (const raw of deps) {
    if (!raw.includes(":")) { findings.push(F("GLD005", "error", `Dependency "${raw}" is not in "<runner>:<hash>" form.`, { line, hint: fixHint })); continue; }
    const [runner, ...rest] = raw.split(":");
    const ref = rest.join(":");
    if (!KNOWN_RUNNER_NAMES.has(runner)) findings.push(F("GLD008", "warning", `Unknown runner "${runner}" (typo?). Known: ${[...KNOWN_RUNNER_NAMES].sort().join(", ")}.`, { line }));
    if (FLOATING.has(ref)) {
      findings.push(F("GLD004", "error", `Runner "${raw}" uses the floating ref ":${ref}". GenVM rejects :test/:latest outside debug mode (Studio, testnets): the deploy is ACCEPTED/FINALIZED but execution fails with \`invalid_contract\`.`, { line, hint: `Pin a runner hash, e.g. py-genlayer:${rec}.` }));
      continue;
    }
    if (!NIX32.test(ref)) { findings.push(F("GLD005", "error", `Runner ref "${ref}" is not a 52-character GenVM hash.`, { line, hint: fixHint })); continue; }
    const want = RECOMMENDED_RUNNERS[runner];
    if (want && ref !== want)
      findings.push(F("GLD006", "warning", `"${runner}" is pinned to ${ref.slice(0, 10)}…, the current docs use ${want.slice(0, 10)}…. Older runners may lack APIs or be unsupported on the target network.`, { line, hint: "The dry run below tells you whether the node accepts it." }));
  }
  return findings;
}

export function fixSource(source, runnerHash = RECOMMENDED_RUNNERS["py-genlayer"]) {
  const lines = source.split(/(?<=\n)/);
  let header = null;
  for (let i = 0; i < Math.min(20, lines.length); i++) {
    const l = lines[i].replace(/\r?\n$/, "");
    if (HEADER_LINE.test(l) && (l.includes("Depends") || l.includes("Seq"))) { header = l; lines.splice(i, 1); break; }
  }
  let valid = false;
  if (header) { try { JSON.parse(header.match(HEADER_LINE)[1]); valid = true; } catch {} }
  if (!header || !valid || !header.includes("py-genlayer:")) header = `# { "Depends": "py-genlayer:${runnerHash}" }`;
  else header = header.replace(/py-genlayer:[^"'\s}]*/g, `py-genlayer:${runnerHash}`);
  while (lines.length && !lines[0].trim()) lines.shift();
  return header + "\n" + lines.join("");
}

// ------------------------------------------------- python-literal parsing
// Studio returns dry-run failures as the Python repr of ('execution failed', {...}).
export function parsePyLiteral(text) {
  let i = 0;
  const ws = () => { while (i < text.length && /\s/.test(text[i])) i++; };
  const fail = (m) => { throw new Error(`py-literal: ${m} at ${i}`); };
  function str() {
    const q = text[i++];
    let out = "";
    while (i < text.length && text[i] !== q) {
      if (text[i] === "\\") {
        const c = text[i + 1];
        const map = { n: "\n", t: "\t", r: "\r", "\\": "\\", "'": "'", '"': '"', "0": "\0" };
        if (c in map) { out += map[c]; i += 2; }
        else if (c === "x") { out += String.fromCharCode(parseInt(text.substr(i + 2, 2), 16)); i += 4; }
        else if (c === "u") { out += String.fromCharCode(parseInt(text.substr(i + 2, 4), 16)); i += 6; }
        else { out += c; i += 2; }
      } else out += text[i++];
    }
    if (text[i] !== q) fail("unterminated string");
    i++;
    return out;
  }
  function seq(close) {
    const items = [];
    ws();
    while (text[i] !== close) {
      items.push(val()); ws();
      if (text[i] === ",") { i++; ws(); } else if (text[i] !== close) fail("expected , or " + close);
    }
    i++;
    return items;
  }
  function val() {
    ws();
    const c = text[i];
    if (c === "'" || c === '"') return str();
    if (c === "(") { i++; return seq(")"); }
    if (c === "[") { i++; return seq("]"); }
    if (c === "{") {
      i++; const o = {}; ws();
      while (text[i] !== "}") {
        const k = val(); ws(); if (text[i] !== ":") fail("expected :"); i++;
        o[k] = val(); ws();
        if (text[i] === ",") { i++; ws(); } else if (text[i] !== "}") fail("expected , or }");
      }
      i++; return o;
    }
    for (const [w, v] of [["None", null], ["True", true], ["False", false]]) if (text.startsWith(w, i)) { i += w.length; return v; }
    const m = /^-?\d+(\.\d+)?([eE][-+]?\d+)?/.exec(text.slice(i));
    if (m) { i += m[0].length; return Number(m[0]); }
    fail("unexpected " + JSON.stringify(c));
  }
  const v = val(); ws();
  if (i !== text.length) fail("trailing data");
  return v;
}

// ------------------------------------------------------------- diagnose
const KNOWN_ERRORS = [
  [/:test\/ :latest runner used in non-debug mode/, "GLD004", "The runner header uses py-genlayer:test or :latest, which GenVM only accepts in debug mode. Pin a runner hash."],
  [/SyntaxError|IndentationError/, "GLD210", "Python syntax error in the contract (see traceback)."],
  [/ModuleNotFoundError|ImportError/, "GLD211", "An import is not available inside the GenVM runner. Only the bundled stdlib subset and `genlayer` are available."],
  [/NameError/, "GLD212", "A name is undefined at module load time (missing `from genlayer import *`?)."],
  [/TypeError|ValueError|AttributeError|KeyError|AssertionError/, "GLD213", "The contract raised an exception while loading or building its schema (see traceback)."],
  [/invalid_contract/, "GLD201", "GenVM refused to load the contract before running any code: usually the runner header is missing, malformed, floating (:test/:latest) or points at a runner the node does not have."],
  [/exit_code \d+/, "GLD214", "The contract process exited with an error (see stderr)."],
];
const BENIGN = [/VALIDATOR_QUORUM_REACHED/, /Validator execution cancelled after quorum/, /runner comment does not start with version/, /no backtrace attached/, /no memories attached/];

export function classify(blob) {
  for (const [re, code, why] of KNOWN_ERRORS) if (re.test(blob)) return [code, why];
  return null;
}

export function tracebackTail(stderr, n = 6) {
  const lines = String(stderr || "").trim().split("\n").filter((l) => l.trim());
  let out = [];
  lines.forEach((l, i) => { if (l.includes('"/contract.py"')) out = lines.slice(i); });
  return (out.length ? out : lines).slice(-n);
}

export function parseGenvmError(message) {
  const err = { summary: "", stderr: "", resultKind: "", resultMessage: "", warnings: [], version: "" };
  let parsed = null;
  try { parsed = parsePyLiteral(message); } catch { parsed = null; }
  const payload = Array.isArray(parsed) ? (err.summary = String(parsed[0]), parsed[1]) : parsed;
  if (payload && typeof payload === "object") {
    err.stderr = payload.stderr || "";
    for (const e of payload.genvm_log || []) {
      if (e.version && !err.version) err.version = String(e.version);
      if ((e.level === "warn" || e.level === "error") && !BENIGN.some((b) => b.test(e.message))) err.warnings.push(String(e.message));
    }
    let r = payload.result;
    if (typeof r === "string") { try { r = JSON.parse(r); } catch { r = { message: r }; } }
    if (r && typeof r === "object") { err.resultKind = String(r.kind || ""); err.resultMessage = String(r.message || ""); }
  } else {
    err.summary = message.split(",")[0].replace(/^[(' ]+|[' ]+$/g, "");
    const m = /"kind": "([^"]+)", "message": "([^"]+)"/.exec(message.replace(/\\"/g, '"'));
    if (m) [, err.resultKind, err.resultMessage] = m;
    for (const w of message.matchAll(/'message': '([^']*)'[^}]*'level': '(warn|error)'/g)) if (!BENIGN.some((b) => b.test(w[1]))) err.warnings.push(w[1]);
  }
  return err;
}

export function findingsFromGenvmError(err, context) {
  const blob = [err.summary, err.stderr, err.resultMessage, ...err.warnings].join("\n");
  const [code, why] = classify(blob) || ["GLD299", "Unrecognised GenVM error."];
  const details = [];
  if (err.resultKind || err.resultMessage) details.push(`result: ${err.resultKind} ${err.resultMessage}`.trim());
  err.warnings.forEach((w) => details.push(`genvm: ${w}`));
  tracebackTail(err.stderr).forEach((l) => details.push(`stderr: ${l}`));
  if (err.version) details.push(`genvm version: ${err.version}`);
  return [F(code, "error", `${context}: ${why}`, { details })];
}

export function summarizeSchema(schema) {
  const t = (x) => (typeof x === "string" ? x : JSON.stringify(x));
  const out = [];
  const ctor = schema?.ctor || {};
  out.push(`constructor(${(ctor.params || []).map(([n, ty]) => `${n}: ${t(ty)}`).join(", ")})`);
  for (const [name, m] of Object.entries(schema?.methods || {}).sort(([a], [b]) => a.localeCompare(b))) {
    let kind = m.readonly ? "view" : "write";
    if (m.payable) kind += ", payable";
    out.push(`${name}(${(m.params || []).map(([n, ty]) => `${n}: ${t(ty)}`).join(", ")}) -> ${t(m.ret ?? "null")}  [${kind}]`);
  }
  return out;
}

// ------------------------------------------------------------------- rpc
export async function rpc(url, method, params) {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method, params }) });
  if (!r.ok) throw Object.assign(new Error(`HTTP ${r.status} from ${url}`), { code: null });
  const j = await r.json();
  if (j.error) throw Object.assign(new Error(String(j.error.message ?? JSON.stringify(j.error))), { code: j.error.code ?? -1 });
  return j.result;
}

const toHex = (s) => "0x" + Array.from(new TextEncoder().encode(s), (b) => b.toString(16).padStart(2, "0")).join("");

export async function checkSource(source, url) {
  const findings = lintHeader(source);
  let schema = null;
  if (url) {
    try {
      schema = await rpc(url, "gen_getContractSchemaForCode", [toHex(source)]);
      findings.push(F("GLD200", "info", "Dry run OK: the node loaded the contract and produced its ABI.", { details: summarizeSchema(schema) }));
    } catch (e) {
      if (e.code === -32601) findings.push(F("GLD202", "warning", `${url} does not support gen_getContractSchemaForCode; dry run skipped (use studionet or localnet).`));
      else if (e.code === null || e.code === undefined) findings.push(F("GLD203", "warning", `dry run skipped: ${e.message} (network or CORS problem?)`));
      else findings.push(...findingsFromGenvmError(parseGenvmError(e.message), "Dry run on node failed"));
    }
  }
  return { findings, schema };
}

// --------------------------------------------------------------- explain
const TX_TYPES = { 0: "send", 1: "deploy", 2: "call", 3: "upgrade" };
const RESULT_CODES = { 0: "return", 1: "user_error (rollback)", 2: "vm_error" };
const STATUS_NAMES = { 0: "UNINITIALIZED", 1: "PENDING", 2: "PROPOSING", 3: "COMMITTING", 4: "REVEALING", 5: "ACCEPTED", 6: "UNDETERMINED", 7: "FINALIZED", 8: "CANCELED", 9: "APPEAL_REVEALING", 10: "APPEAL_COMMITTING", 11: "READY_TO_FINALIZE", 12: "VALIDATORS_TIMEOUT", 13: "LEADER_TIMEOUT" };
const OK = new Set(["ACCEPTED", "FINALIZED"]);
const BAD = new Set(["CANCELED", "UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT"]);

function b64bytes(s) {
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(s) || s.length % 4) return null;
  try { return Uint8Array.from(atob(s), (c) => c.charCodeAt(0)); } catch { return null; }
}

export function decodeResult(raw) {
  if (raw && typeof raw === "object") {
    const p = raw.payload;
    return [String(raw.status ?? ""), typeof p === "string" ? p : p?.readable ?? JSON.stringify(p ?? "")];
  }
  if (typeof raw !== "string" || !raw) return ["", ""];
  const blob = b64bytes(raw);
  if (!blob) return ["", raw];
  if (!blob.length) return ["", ""];
  const kind = RESULT_CODES[blob[0]] ?? `code_${blob[0]}`;
  const body = blob.slice(1);
  if (blob[0] === 0) return [kind, body.length === 1 && body[0] === 0 ? "null" : `<${body.length} bytes calldata>`];
  return [kind, new TextDecoder().decode(body)];
}

export function explainTransaction(tx) {
  const rep = { hash: String(tx.hash || ""), findings: [] };
  const t = tx.type;
  rep.type = typeof t === "number" ? TX_TYPES[t] ?? String(t) : String(t ?? "?");
  const s = tx.status_name ?? tx.statusName ?? tx.status;
  rep.status = typeof s === "number" ? STATUS_NAMES[s] ?? String(s) : String(s ?? "?").toUpperCase();
  rep.resultName = String(tx.result_name || "");
  rep.sender = String(tx.from_address || tx.sender || "");
  rep.to = String(tx.to_address || tx.recipient || "");
  const data = tx.data || {};
  rep.contractAddress = String(data.contract_address || (rep.type === "deploy" ? rep.to : ""));
  let leaders = tx.consensus_data?.leader_receipt || [];
  if (!Array.isArray(leaders)) leaders = [leaders];
  const leader = leaders[0] || {};
  rep.leaderExecution = String(leader.execution_result || "");
  [rep.resultKind, rep.resultPayload] = decodeResult(leader.result);
  rep.stderr = tracebackTail(leader.genvm_result?.stderr || "");
  const names = tx.last_round?.validator_votes_name;
  rep.votes = {};
  for (const v of names || (tx.consensus_data?.validators || []).map((x) => String(x.vote))) rep.votes[v] = (rep.votes[v] || 0) + 1;
  rep.messages = (tx.messages || leader.pending_transactions || []).length;

  if (BAD.has(rep.status)) { rep.verdict = "FAILED"; rep.findings.push(F("GLD102", "error", `Transaction ended with status ${rep.status}.`)); }
  else if (!OK.has(rep.status)) { rep.verdict = "PENDING"; rep.findings.push(F("GLD103", "info", `Transaction is still ${rep.status}; check again later.`)); }
  else if (rep.leaderExecution && rep.leaderExecution !== "SUCCESS") {
    rep.verdict = "FAILED";
    const hit = classify([rep.resultKind, rep.resultPayload, ...rep.stderr].join(" "));
    const details = rep.stderr.map((l) => `stderr: ${l}`);
    if (rep.type === "deploy") details.push(`contract at ${rep.contractAddress} is NOT usable; fix the code and redeploy.`);
    rep.findings.push(F("GLD101", "error", `Status is ${rep.status}${rep.resultName ? " / " + rep.resultName : ""}, but the leader's execution result is ${rep.leaderExecution} (${rep.resultKind || "error"}: ${rep.resultPayload || "n/a"}). Consensus only means validators agreed on the outcome — the outcome was an error.`, { hint: hit?.[1], details }));
  } else rep.verdict = "OK";

  if (rep.type === "deploy" && typeof data.contract_code === "string" && data.contract_code) {
    let src = "";
    try { src = new TextDecoder().decode(Uint8Array.from(atob(data.contract_code), (c) => c.charCodeAt(0))); } catch {}
    if (src) for (const f of lintHeader(src)) rep.findings.push({ ...f, message: "deployed code: " + f.message });
  }
  return rep;
}

export async function explainHash(hash, url) {
  const tx = await rpc(url, "eth_getTransactionByHash", [hash]);
  if (!tx) throw new Error("transaction not found on this network");
  return explainTransaction(tx);
}
