// Parity tests for the browser port (docs/gldoctor.js) against the Python fixtures.
// Run: node --test tests/js/
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as gd from "../../docs/gldoctor.js";

const fx = (n) => JSON.parse(readFileSync(new URL(`../fixtures/${n}`, import.meta.url), "utf8"));
const ex = (n) => readFileSync(new URL(`../../examples/contracts/${n}`, import.meta.url), "utf8");
const codes = (fs) => fs.map((f) => f.code);

test("header: ok example has no findings", () => {
  assert.deepEqual(gd.lintHeader(ex("hello_ok.py")), []);
});
test("header: floating :test runner -> GLD004", () => {
  assert.deepEqual(codes(gd.lintHeader(ex("bad_floating_runner.py"))), ["GLD004"]);
});
test("header: missing -> GLD001", () => {
  assert.deepEqual(codes(gd.lintHeader(ex("missing_header.py"))), ["GLD001"]);
});
test("header: other rules", () => {
  assert.deepEqual(codes(gd.lintHeader("# { 'Depends': 'x' }\n")), ["GLD002"]);
  assert.deepEqual(codes(gd.lintHeader('# { "Seq": [] }\n')), ["GLD003"]);
  assert.deepEqual(codes(gd.lintHeader('# { "Depends": "py-genlayer:abc" }\n')), ["GLD005"]);
  assert.deepEqual(codes(gd.lintHeader('# { "Depends": "py-genlayer" }\n')), ["GLD005"]);
  assert.deepEqual(codes(gd.lintHeader('\n# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }\n')), ["GLD007"]);
  assert.deepEqual(codes(gd.lintHeader('# { "Depends": "py-genlayr:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }\n')), ["GLD008"]);
  assert.deepEqual(codes(gd.lintHeader('# { "Depends": "py-genlayer:0000000000000000000000000000000000000000000000000000" }\n')), ["GLD006"]);
});
test("fix: pins, inserts and moves the header", () => {
  const rec = gd.RECOMMENDED_RUNNERS["py-genlayer"];
  assert.ok(gd.fixSource(ex("bad_floating_runner.py")).startsWith(`# { "Depends": "py-genlayer:${rec}" }\n`));
  assert.deepEqual(gd.lintHeader(gd.fixSource(ex("missing_header.py"))), []);
  assert.deepEqual(gd.lintHeader(gd.fixSource('"""doc"""\n# { "Depends": "py-genlayer:test" }\nx = 1\n')), []);
});
test("python literal parser", () => {
  assert.deepEqual(gd.parsePyLiteral("('a', {'b': [1, 2.5, None, True, False], \"c\": 'it\\'s\\n'})"), ["a", { b: [1, 2.5, null, true, false], c: "it's\n" }]);
});
test("dry-run error: floating runner", () => {
  const err = gd.parseGenvmError(fx("schema_bad_header.json").error.message);
  assert.equal(err.summary, "execution failed");
  const f = gd.findingsFromGenvmError(err, "Dry run on node failed");
  assert.equal(f[0].code, "GLD004");
  assert.ok(f[0].details.some((d) => d.includes("invalid_contract")));
});
test("dry-run error: syntax error with traceback", () => {
  const f = gd.findingsFromGenvmError(gd.parseGenvmError(fx("schema_syntax_error.json").error.message), "x");
  assert.equal(f[0].code, "GLD210");
  assert.ok(f[0].details.some((d) => d.includes("SyntaxError")));
  assert.ok(f[0].details.some((d) => d.includes('"/contract.py", line 18')));
});
test("dry-run error: regex fallback for unparsable text", () => {
  const err = gd.parseGenvmError("('execution failed', {'genvm_log': [{'message': ':test/ :latest runner used in non-debug mode, this is not allowed', 'level': 'warn'}], 'broken");
  assert.equal(gd.classify(err.warnings.join(" "))[0], "GLD004");
});
test("schema summary", () => {
  const s = gd.summarizeSchema(fx("schema_ok.json").result);
  assert.equal(s[0], "constructor(greeting: string)");
  assert.ok(s.some((l) => l.startsWith("set_greeting(new_greeting: string) -> null  [write")));
});
test("explain: silent failed deploy", () => {
  const r = gd.explainTransaction(fx("tx_deploy_bad_header.json").result);
  assert.equal(r.verdict, "FAILED");
  assert.equal(r.status, "FINALIZED");
  assert.deepEqual([r.resultKind, r.resultPayload], ["vm_error", "invalid_contract"]);
  assert.deepEqual(codes(r.findings), ["GLD101", "GLD004"]);
});
test("explain: ok deploy and write", () => {
  assert.equal(gd.explainTransaction(fx("tx_deploy_ok.json").result).verdict, "OK");
  const w = gd.explainTransaction(fx("tx_write_ok.json").result);
  assert.equal(w.verdict, "OK");
  assert.equal(Object.values(w.votes).reduce((a, b) => a + b, 0), 5);
});
test("explain: pending, canceled, genlayer-js shape", () => {
  assert.equal(gd.explainTransaction({ hash: "0x1", status: "PENDING" }).verdict, "PENDING");
  assert.equal(gd.explainTransaction({ hash: "0x1", status: "CANCELED" }).verdict, "FAILED");
  const r = gd.explainTransaction({ hash: "0x2", type: 2, status: 5, consensus_data: { leader_receipt: [{ execution_result: "ERROR", result: { status: "rollback", payload: "challenge window still open" } }] } });
  assert.equal(r.status, "ACCEPTED");
  assert.equal(r.verdict, "FAILED");
  assert.match(r.findings[0].message, /challenge window still open/);
});
test("decodeResult variants", () => {
  assert.deepEqual(gd.decodeResult(btoa("\x00\x00")), ["return", "null"]);
  assert.deepEqual(gd.decodeResult(btoa("\x01not enough balance")), ["user_error (rollback)", "not enough balance"]);
  assert.deepEqual(gd.decodeResult(""), ["", ""]);
});
