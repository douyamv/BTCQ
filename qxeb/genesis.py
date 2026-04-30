"""创世区块 — 协议预定义、不可篡改、无人挖出。"""

from .block import Block
from .constants import (
    PROTOCOL_VERSION, GENESIS_TIMESTAMP, GENESIS_PREV_HASH, GENESIS_MESSAGE,
    CIRCUIT_N_QUBITS, CIRCUIT_DEPTH, CIRCUIT_N_SAMPLES, INITIAL_XEB_THRESHOLD,
)


def make_genesis() -> Block:
    g = Block(
        version         = PROTOCOL_VERSION,
        height          = 0,
        prev_hash       = GENESIS_PREV_HASH,
        timestamp       = GENESIS_TIMESTAMP,
        miner_address   = b"\x00" * 20,
        n_qubits        = CIRCUIT_N_QUBITS,
        depth           = CIRCUIT_DEPTH,
        n_samples       = 0,                  # 创世不含样本
        difficulty      = INITIAL_XEB_THRESHOLD,
        nonce           = 0,
        samples_root    = b"\x00" * 32,
        xeb_score       = 0.0,
        samples         = [],
        miner_signature = b"\x00" * 65,
    )
    return g


# 创世铭文（写在哈希里也可，但这里作为元数据保存）
def genesis_message() -> str:
    return GENESIS_MESSAGE
