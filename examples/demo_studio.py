"""End-to-end demo of genlayer-doctor against the hosted GenLayer Studio network (free, no GEN).

1. deploys a contract with a floating `py-genlayer:test` header -> consensus says FINALIZED,
   `gldoctor explain` shows the deployment actually failed;
2. shows `gldoctor check --network studionet` would have caught it before sending a tx;
3. fixes the header with `fix_source`, redeploys, writes, reads back and explains both txs.

Credentials (never printed):
  GENLAYER_PRIVATE_KEY=0x...            or
  GENLAYER_MNEMONIC_FILE=path [GENLAYER_HD_PATH="m/44'/60'/0'/0/0"]

Requires: pip install genlayer-py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from eth_account import Account
from genlayer_py import create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

from genlayer_doctor.check import check_file
from genlayer_doctor.explain import explain_transaction
from genlayer_doctor.header import fix_source
from genlayer_doctor.rpc import RpcClient

HERE = Path(__file__).parent
RPC = "https://studio.genlayer.com/api"
EXPLORER = "https://explorer-studio.genlayer.com"


def load_account():
    key = os.environ.get("GENLAYER_PRIVATE_KEY")
    if key:
        return Account.from_key(key)
    mfile = os.environ.get("GENLAYER_MNEMONIC_FILE")
    if not mfile:
        sys.exit("set GENLAYER_PRIVATE_KEY or GENLAYER_MNEMONIC_FILE")
    Account.enable_unaudited_hdwallet_features()
    phrase = Path(os.path.expanduser(mfile)).read_text().strip()
    return Account.from_mnemonic(phrase, account_path=os.environ.get("GENLAYER_HD_PATH", "m/44'/60'/0'/0/0"))


def show(title: str, obj) -> None:
    print(f"\n=== {title} ===")
    print(obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str))


def deploy(client, account, source: str, args: list):
    tx_hash = client.deploy_contract(code=source, account=account, args=args)
    client.wait_for_transaction_receipt(transaction_hash=tx_hash, status=TransactionStatus.ACCEPTED, retries=100)
    return tx_hash if isinstance(tx_hash, str) else "0x" + bytes(tx_hash).hex().removeprefix("0x")


def explain(rpc: RpcClient, tx_hash: str) -> dict:
    rep = explain_transaction(rpc.get_transaction(tx_hash))
    return {"verdict": rep.verdict, "status": rep.status, "result_name": rep.result_name,
            "leader_execution": rep.leader_execution, "result": f"{rep.result_kind}: {rep.result_payload}",
            "contract": rep.contract_address,
            "findings": [f"{f.code} {f.severity}: {f.message}" for f in rep.findings]}


def main() -> None:
    account = load_account()
    print("deployer:", account.address)
    client = create_client(chain=studionet, account=account)
    rpc = RpcClient(RPC)
    results: dict = {"deployer": account.address}

    broken_path = HERE / "contracts" / "bad_floating_runner.py"
    broken = broken_path.read_text()

    # 1) the silent failure ---------------------------------------------------
    tx_bad = deploy(client, account, broken, ["deployed with a floating runner"])
    show("1. deploy with py-genlayer:test -> explain", rep := explain(rpc, tx_bad))
    results["broken_deploy"] = {"tx": tx_bad, **rep}

    # 2) caught before deploying ------------------------------------------------
    res = check_file(str(broken_path), client=rpc)
    show("2. gldoctor check --network studionet (gasless dry run)",
         [f"{f.code} {f.severity}: {f.message}" for f in res.findings])

    # 3) fix, redeploy, use ---------------------------------------------------
    fixed = fix_source(broken)
    tx_ok = deploy(client, account, fixed, ["Hello from genlayer-doctor"])
    rep_ok = explain(rpc, tx_ok)
    show("3. fixed header -> deploy -> explain", rep_ok)
    contract = rep_ok["contract"]
    tx_w = client.write_contract(address=contract, function_name="set_greeting",
                                 args=["checked by gldoctor before deploy"], account=account)
    client.wait_for_transaction_receipt(transaction_hash=tx_w, status=TransactionStatus.ACCEPTED, retries=100)
    tx_w = tx_w if isinstance(tx_w, str) else "0x" + bytes(tx_w).hex().removeprefix("0x")
    rep_w = explain(rpc, tx_w)
    show("4. write set_greeting -> explain", rep_w)
    reads = {fn: client.read_contract(address=contract, function_name=fn) for fn in ("get_greeting", "get_updates", "get_owner")}
    show("5. read back", reads)

    results.update({"fixed_deploy": {"tx": tx_ok, **rep_ok}, "write": {"tx": tx_w, **rep_w}, "reads": reads,
                    "explorer": f"{EXPLORER}/address/{contract}"})
    out = HERE / "demo_result.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
