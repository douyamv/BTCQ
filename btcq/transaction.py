"""转账与抵押交易（账户模型，类 Ethereum 风格）。

v0.1 设计：
* 五字段 + 一个 kind 标记区分用途
* nonce 是发送方账户的单调递增计数器，防重放
* 无手续费（v0.5 引入 gas）
* 签名格式：secp256k1 over keccak256(serialize_unsigned)

kind 取值：
* "transfer" — 普通转账
* "stake"    — 抵押 BTCQ（recipient 必须是 STAKE_VAULT）
* "unstake"  — 解抵押申请（recipient 必须是 STAKE_VAULT）
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .wallet import keccak256, Wallet


@dataclass
class Transaction:
    sender:    bytes        # 20 字节地址
    recipient: bytes        # 20 字节地址
    amount:    int          # 原子单位（10⁻⁸ BTCQ）
    nonce:     int          # 发送方账户 nonce
    kind:      str = "transfer"   # 'transfer' / 'stake' / 'unstake'
    signature: bytes = b""  # 65 字节 (r || s || v)，签名前为空

    # ===== 序列化 =====
    def unsigned_bytes(self) -> bytes:
        """规范化字节串，用于 hash + 签名。不含 signature。"""
        kind_bytes = self.kind.encode()
        return b"".join([
            self.sender,
            self.recipient,
            self.amount.to_bytes(16, "big"),    # 最多 2^128
            self.nonce.to_bytes(8, "big"),
            len(kind_bytes).to_bytes(1, "big"),
            kind_bytes,
        ])

    def tx_hash(self) -> bytes:
        return keccak256(self.unsigned_bytes())

    def is_signed(self) -> bool:
        return len(self.signature) == 65

    def verify_signature(self) -> bool:
        if not self.is_signed():
            return False
        return Wallet.verify(self.tx_hash(), self.signature, self.sender)

    # ===== JSON 互操作 =====
    def to_dict(self) -> dict:
        return {
            "sender":    "0x" + self.sender.hex(),
            "recipient": "0x" + self.recipient.hex(),
            "amount":    self.amount,
            "nonce":     self.nonce,
            "kind":      self.kind,
            "signature": "0x" + self.signature.hex(),
            "tx_hash":   "0x" + self.tx_hash().hex(),
        }

    @staticmethod
    def from_dict(d: dict) -> "Transaction":
        def hx(s):
            return bytes.fromhex(s[2:] if isinstance(s, str) and s.startswith("0x") else s)
        return Transaction(
            sender    = hx(d["sender"]),
            recipient = hx(d["recipient"]),
            amount    = int(d["amount"]),
            nonce     = int(d["nonce"]),
            kind      = d.get("kind", "transfer"),
            signature = hx(d.get("signature", "0x" + "00" * 65)),
        )


def sign_transaction(wallet: Wallet, recipient_bytes: bytes, amount: int, nonce: int,
                     kind: str = "transfer") -> Transaction:
    """用 wallet 私钥构造并签名一笔交易。"""
    tx = Transaction(
        sender    = wallet.address_bytes,
        recipient = recipient_bytes,
        amount    = int(amount),
        nonce     = int(nonce),
        kind      = kind,
    )
    tx.signature = wallet.sign(tx.tx_hash())
    return tx
