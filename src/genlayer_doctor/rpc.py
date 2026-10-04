from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from . import __version__

# Some GenLayer endpoints sit behind Cloudflare, which rejects the default
# "Python-urllib" user agent (error 1010). Always send an explicit one.
USER_AGENT = f"genlayer-doctor/{__version__}"

Transport = Callable[[str, dict, float], dict]


class RpcError(Exception):
    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def http_transport(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode(errors="replace")
        raise RpcError(f"HTTP {e.code} from {url}: {body.strip()}") from e
    except urllib.error.URLError as e:
        raise RpcError(f"cannot reach {url}: {e.reason}") from e


class RpcClient:
    def __init__(self, url: str, timeout: float = 60.0, transport: Optional[Transport] = None):
        self.url = url
        self.timeout = timeout
        self.transport = transport or http_transport
        self._id = 0

    def call(self, method: str, params: list | None = None) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or []}
        resp = self.transport(self.url, payload, self.timeout)
        if "error" in resp and resp["error"]:
            err = resp["error"]
            raise RpcError(str(err.get("message", err)), err.get("code"), err.get("data"))
        return resp.get("result")

    # Convenience wrappers -------------------------------------------------
    def chain_id(self) -> int:
        return int(self.call("eth_chainId"), 16)

    def schema_for_code(self, source: str) -> dict:
        return self.call("gen_getContractSchemaForCode", [source.encode().hex()])

    def get_transaction(self, tx_hash: str) -> dict:
        return self.call("eth_getTransactionByHash", [tx_hash])
