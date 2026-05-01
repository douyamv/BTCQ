"""创世区块 — 协议预定义、不可篡改、无人挖出。"""

from .block import Block
from .constants import (
    PROTOCOL_VERSION, GENESIS_TIMESTAMP, GENESIS_PREV_HASH, GENESIS_MESSAGE,
    CIRCUIT_N_QUBITS, CIRCUIT_DEPTH, INITIAL_XEB_THRESHOLD,
)


def make_genesis() -> Block:
    """创世区块。state_root 反映 GENESIS_ALLOCATIONS 的预分配状态。"""
    g = Block(
        version            = PROTOCOL_VERSION,
        height             = 0,
        slot               = 0,
        prev_hash          = GENESIS_PREV_HASH,
        timestamp          = GENESIS_TIMESTAMP,
        proposer_address   = b"\x00" * 20,
        n_qubits           = CIRCUIT_N_QUBITS,
        depth              = CIRCUIT_DEPTH,
        n_samples          = 0,
        difficulty         = INITIAL_XEB_THRESHOLD,
        samples_root       = b"\x00" * 32,
        xeb_score          = 0.0,
        samples            = [],
        proposer_signature = b"\x00" * 65,
        transactions       = [],
        transactions_root  = b"\x00" * 32,
    )
    # 计算创世 state_root
    g.state_root = _compute_genesis_state_root()
    return g


def _compute_genesis_state_root() -> bytes:
    """从 GENESIS_ALLOCATIONS 派生创世 state_root。所有节点必须算出相同值。"""
    from .constants import GENESIS_ALLOCATIONS
    from .wallet import keccak256
    from .block import merkle_root
    sorted_addrs = sorted(GENESIS_ALLOCATIONS.keys())
    leaves = []
    for addr in sorted_addrs:
        payload = (
            addr +
            GENESIS_ALLOCATIONS[addr].to_bytes(16, "big") +
            (0).to_bytes(16, "big") +    # 创世无 stake
            (0).to_bytes(8, "big")       # 创世无 nonce
        )
        leaves.append(keccak256(payload))
    return merkle_root(leaves)


def genesis_message() -> str:
    return GENESIS_MESSAGE
