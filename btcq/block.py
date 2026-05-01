"""区块结构、序列化、哈希。v0.1 使用 JSON 持久化，区块哈希基于规范字节串 keccak256。"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json
import struct

from .wallet import keccak256
from .transaction import Transaction
from .constants import COIN, INITIAL_BLOCK_REWARD, HALVING_INTERVAL


def block_reward(height: int) -> int:
    """区块奖励（原子单位）。每 HALVING_INTERVAL 减半。

    创世（height=0）无出块奖励（创世铭文 + Satoshi 致敬纯属预分配，不计为挖出）。
    height=1 起每块 INITIAL_BLOCK_REWARD = 50 BTCQ。
    """
    if height == 0:
        return 0
    halvings = (height - 1) // HALVING_INTERVAL
    if halvings >= 64:
        return 0
    return INITIAL_BLOCK_REWARD >> halvings


def merkle_root(leaves: List[bytes]) -> bytes:
    """简单 Merkle 树（双重哈希，BTC 风格但用 keccak256）。空列表返回 0。"""
    if not leaves:
        return b"\x00" * 32
    layer = [keccak256(x) for x in leaves]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [keccak256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


def _u(n: int, b: int) -> bytes:
    """Big-endian 无符号整数编码到固定字节数。"""
    return n.to_bytes(b, "big")


def _f64(x: float) -> bytes:
    return struct.pack(">d", x)


@dataclass
class Block:
    version: int
    height: int
    slot: int                     # v0.1.2+: 硬时间 slot 编号（决定 proposer 选举）
    prev_hash: bytes              # 32
    timestamp: int
    proposer_address: bytes       # 20
    n_qubits: int
    depth: int
    n_samples: int
    difficulty: float
    samples_root: bytes           # 32
    xeb_score: float
    samples: List[int]
    transactions: List[Transaction] = field(default_factory=list)
    transactions_root: bytes = b"\x00" * 32
    proposer_signature: bytes = b""  # 65

    # ===== 序列化 =====
    def header_bytes(self) -> bytes:
        """规范化字节串，用于计算 block_hash 与 proposer_signature。不含签名。"""
        parts = [
            _u(self.version, 2),
            _u(self.height, 8),
            _u(self.slot, 8),
            self.prev_hash,
            _u(self.timestamp, 8),
            self.proposer_address,
            _u(self.n_qubits, 1),
            _u(self.depth, 1),
            _u(self.n_samples, 4),
            _f64(self.difficulty),
            self.samples_root,
            _f64(self.xeb_score),
            self.transactions_root,
            _u(len(self.transactions), 4),
        ]
        return b"".join(parts)

    def block_hash(self) -> bytes:
        return keccak256(self.header_bytes())

    # ===== JSON 持久化 =====
    def to_dict(self) -> dict:
        return {
            "version":          self.version,
            "height":           self.height,
            "slot":             self.slot,
            "prev_hash":        "0x" + self.prev_hash.hex(),
            "timestamp":        self.timestamp,
            "proposer_address": "0x" + self.proposer_address.hex(),
            "n_qubits":         self.n_qubits,
            "depth":             self.depth,
            "n_samples":        self.n_samples,
            "difficulty":       self.difficulty,
            "samples_root":     "0x" + self.samples_root.hex(),
            "xeb_score":        self.xeb_score,
            "samples":          [int(x) for x in self.samples],
            "transactions":     [t.to_dict() for t in self.transactions],
            "transactions_root":"0x" + self.transactions_root.hex(),
            "proposer_signature":"0x" + self.proposer_signature.hex(),
            "block_hash":       "0x" + self.block_hash().hex(),
            "reward":           block_reward(self.height),
        }

    @staticmethod
    def from_dict(d: dict) -> "Block":
        def hx(s):
            return bytes.fromhex(s[2:] if isinstance(s, str) and s.startswith("0x") else s)
        txs = [Transaction.from_dict(t) for t in d.get("transactions", [])]
        return Block(
            version       = d["version"],
            height        = d["height"],
            slot          = d.get("slot", 0),
            prev_hash     = hx(d["prev_hash"]),
            timestamp     = d["timestamp"],
            proposer_address = hx(d["proposer_address"]),
            n_qubits      = d["n_qubits"],
            depth         = d["depth"],
            n_samples     = d["n_samples"],
            difficulty    = d["difficulty"],
            samples_root  = hx(d["samples_root"]),
            xeb_score     = d["xeb_score"],
            samples       = list(d["samples"]),
            transactions  = txs,
            transactions_root = hx(d.get("transactions_root", "0x" + "00" * 32)),
            proposer_signature = hx(d.get("proposer_signature", "0x" + "00" * 65)),
        )

    def save(self, path):
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @staticmethod
    def load(path) -> "Block":
        from pathlib import Path
        return Block.from_dict(json.loads(Path(path).read_text()))


def compute_samples_root(samples: List[int], n_qubits: int) -> bytes:
    """每个 sample 序列化成 ceil(n_qubits/8) 字节大端，然后求 Merkle 根。"""
    nbytes = (n_qubits + 7) // 8
    leaves = [int(x).to_bytes(nbytes, "big") for x in samples]
    return merkle_root(leaves)


def compute_transactions_root(transactions: List[Transaction]) -> bytes:
    """对交易列表求 Merkle 根；空列表返回全 0。"""
    if not transactions:
        return b"\x00" * 32
    leaves = [t.tx_hash() for t in transactions]
    return merkle_root(leaves)
