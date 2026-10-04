"""Command line interface: `gldoctor check | explain | fix | networks`."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

from . import __version__
from .check import check_file
from .explain import explain_transaction
from .findings import Finding, has_errors
from .header import RECOMMENDED_RUNNERS, fix_source
from .networks import NETWORKS, resolve
from .rpc import RpcClient, RpcError

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2


class Style:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _c(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.enabled else s

    def red(self, s): return self._c("31", s)
    def yellow(self, s): return self._c("33", s)
    def green(self, s): return self._c("32", s)
    def dim(self, s): return self._c("2", s)
    def bold(self, s): return self._c("1", s)


def _use_color(args) -> bool:
    if getattr(args, "json", False) or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _print_finding(f: Finding, st: Style, path: str | None = None) -> None:
    tag = {"error": st.red("error"), "warning": st.yellow("warn "), "info": st.green("info ")}[f.severity]
    loc = f"{path}:{f.line}: " if path and f.line else (f"{path}: " if path else "")
    print(f"  {tag} {st.bold(f.code)} {loc}{f.message}")
    if f.hint:
        print(f"        {st.dim('hint:')} {f.hint}")
    for d in f.details:
        print(f"        {st.dim('│')} {d}")


def _client(args) -> RpcClient | None:
    target = resolve(args.network, args.rpc)
    if not target:
        return None
    return RpcClient(target[1], timeout=args.timeout)


def cmd_check(args) -> int:
    st = Style(_use_color(args))
    try:
        client = None if args.offline else _client(args)
    except ValueError as e:
        print(f"gldoctor: {e}", file=sys.stderr)
        return EXIT_USAGE
    results = [check_file(p, client=client, with_genvm_lint=args.with_genvm_lint) for p in args.files]
    failed = any(has_errors(r.findings) for r in results)
    warned = any(f.severity == "warning" for r in results for f in r.findings)
    if args.json:
        print(json.dumps({"ok": not failed, "rpc": client.url if client else None,
                          "results": [r.to_dict() for r in results]}, indent=2))
    else:
        where = f"dry run on {client.url}" if client else "offline (add --network studionet for a gasless dry run)"
        print(st.dim(f"gldoctor {__version__} · {where}"))
        for r in results:
            errs = has_errors(r.findings)
            status = st.red("FAIL") if errs else st.green("PASS")
            print(f"{status} {r.path}")
            for f in r.findings:
                _print_finding(f, st, r.path)
    if failed or (args.strict and warned):
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_explain(args) -> int:
    st = Style(_use_color(args))
    try:
        if args.from_file:
            tx = json.loads(Path(args.from_file).read_text())
            tx = tx.get("result", tx)
        else:
            client = _client(args) or RpcClient(NETWORKS["studionet"].rpc, timeout=args.timeout)
            tx = client.get_transaction(args.tx)
    except (RpcError, ValueError, OSError) as e:
        print(f"gldoctor: {e}", file=sys.stderr)
        return EXIT_USAGE
    if not tx:
        print(f"gldoctor: transaction {args.tx} not found", file=sys.stderr)
        return EXIT_USAGE
    rep = explain_transaction(tx)
    if args.json:
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        colour = {"OK": st.green, "FAILED": st.red}.get(rep.verdict, st.yellow)
        print(f"{colour(rep.verdict)}  {rep.type} tx {rep.hash}")
        print(f"  status           {rep.status}" + (f" / {rep.result_name}" if rep.result_name else ""))
        print(f"  leader execution {rep.leader_execution or '?'}"
              + (f"  ({rep.result_kind}: {rep.result_payload})" if rep.result_kind else ""))
        if rep.votes:
            print("  votes            " + ", ".join(f"{k}×{v}" for k, v in rep.votes.items()))
        print(f"  from             {rep.sender}")
        if rep.contract_address:
            print(f"  contract         {rep.contract_address}")
        for f in rep.findings:
            _print_finding(f, st)
    return EXIT_FINDINGS if rep.verdict == "FAILED" or has_errors(rep.findings) else EXIT_OK


def cmd_fix(args) -> int:
    rc = EXIT_OK
    for p in args.files:
        path = Path(p)
        old = path.read_text(encoding="utf-8")
        new = fix_source(old, args.runner)
        if new == old:
            print(f"{p}: header already pinned")
            continue
        if args.write:
            path.write_text(new, encoding="utf-8")
            print(f"{p}: header fixed")
        else:
            sys.stdout.writelines(difflib.unified_diff(
                old.splitlines(keepends=True)[:5], new.splitlines(keepends=True)[:5], f"a/{p}", f"b/{p}"))
            rc = EXIT_FINDINGS
    return rc


def cmd_networks(args) -> int:
    rows = []
    for n in NETWORKS.values():
        row = {"name": n.name, "rpc": n.rpc, "chain_id": n.chain_id, "explorer": n.explorer, "note": n.note}
        if args.ping:
            try:
                got = RpcClient(n.rpc, timeout=args.timeout).chain_id()
                row["reachable"] = True
                row["chain_id_ok"] = got == n.chain_id
            except (RpcError, ValueError, TypeError) as e:
                row["reachable"] = False
                row["error"] = str(e)[:120]
        rows.append(row)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            ping = ""
            if args.ping:
                ping = ("  ✓ reachable" + ("" if r.get("chain_id_ok") else " (chain id mismatch!)")) if r["reachable"] else f"  ✗ {r['error']}"
            print(f"{r['name']:<17} {r['chain_id']:<6} {r['rpc']}{ping}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gldoctor", description="Pre-deploy checks and transaction diagnostics for GenLayer Intelligent Contracts.")
    p.add_argument("--version", action="version", version=f"gldoctor {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def net_opts(sp):
        sp.add_argument("--network", "-n", choices=sorted(NETWORKS), help="target network (enables RPC features)")
        sp.add_argument("--rpc", help="custom JSON-RPC URL (overrides --network)")
        sp.add_argument("--timeout", type=float, default=60.0, help="RPC timeout in seconds (default 60)")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    c = sub.add_parser("check", help="check contract files (header lint + optional gasless dry run)")
    c.add_argument("files", nargs="+")
    net_opts(c)
    c.add_argument("--offline", action="store_true", help="never contact a node")
    c.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")
    c.add_argument("--with-genvm-lint", action="store_true", help="also run `genvm-lint lint` if installed")
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("explain", help="explain whether a transaction really succeeded (default network: studionet)")
    e.add_argument("tx", nargs="?", help="transaction hash")
    e.add_argument("--from-file", help="read a transaction JSON (eth_getTransactionByHash result) instead of RPC")
    net_opts(e)
    e.set_defaults(func=cmd_explain)

    f = sub.add_parser("fix", help="pin the py-genlayer runner header (dry run shows a diff)")
    f.add_argument("files", nargs="+")
    f.add_argument("--runner", default=RECOMMENDED_RUNNERS["py-genlayer"], help="runner hash to pin")
    f.add_argument("--write", action="store_true", help="rewrite files in place")
    f.set_defaults(func=cmd_fix)

    n = sub.add_parser("networks", help="list known networks")
    n.add_argument("--ping", action="store_true", help="check reachability and chain id")
    n.add_argument("--timeout", type=float, default=15.0)
    n.add_argument("--json", action="store_true")
    n.set_defaults(func=cmd_networks)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "explain" and not args.tx and not args.from_file:
        print("gldoctor explain: give a transaction hash or --from-file", file=sys.stderr)
        return EXIT_USAGE
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
