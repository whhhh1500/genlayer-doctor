from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Network:
    name: str
    rpc: str
    chain_id: int
    explorer: str | None = None
    note: str = ""


NETWORKS: dict[str, Network] = {
    "studionet": Network(
        "studionet",
        "https://studio.genlayer.com/api",
        61999,
        "https://explorer-studio.genlayer.com",
        "Hosted GenLayer Studio. Free, no GEN required.",
    ),
    "localnet": Network(
        "localnet",
        "http://127.0.0.1:4000/api",
        61127,
        None,
        "Local Studio (`genlayer up`) or GLSim (`glsim --port 4000`).",
    ),
    "testnet-asimov": Network(
        "testnet-asimov",
        "https://rpc-asimov.genlayer.com",
        4221,
        "https://explorer-asimov.genlayer.com",
        "Public testnet (infrastructure). Some Studio-only RPC methods may be unavailable.",
    ),
    "testnet-bradbury": Network(
        "testnet-bradbury",
        "https://rpc-bradbury.genlayer.com",
        4221,
        "https://explorer-bradbury.genlayer.com",
        "Public testnet (AI validation). Some Studio-only RPC methods may be unavailable.",
    ),
}


def resolve(network: str | None, rpc: str | None) -> tuple[str, str] | None:
    """Return (label, rpc_url) or None when running offline."""
    if rpc:
        return (network or "custom", rpc)
    if network:
        if network not in NETWORKS:
            raise ValueError(f"unknown network '{network}'. Known: {', '.join(NETWORKS)}")
        return (network, NETWORKS[network].rpc)
    return None
