"""创世区块 — 协议预定义、不可篡改、无人挖出。"""

from .block import Block
from .constants import (
    PROTOCOL_VERSION, GENESIS_TIMESTAMP, GENESIS_PREV_HASH, GENESIS_MESSAGE,
    CIRCUIT_N_QUBITS, CIRCUIT_DEPTH, INITIAL_XEB_THRESHOLD,
)


def make_genesis() -> Block:
    g = Block(
        version            = PROTOCOL_VERSION,
        height             = 0,
        slot               = 0,                 # 创世位于 slot 0
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
    return g


def genesis_message() -> str:
    return GENESIS_MESSAGE
