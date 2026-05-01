"""极简钱包：secp256k1 私钥 + Ethereum 风格地址 + 签名。"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional, Union

from eth_keys import keys
from Crypto.Hash import keccak


def keccak256(data: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(data)
    return h.digest()


class Wallet:
    def __init__(self, private_key_bytes: bytes):
        assert len(private_key_bytes) == 32
        self._sk = keys.PrivateKey(private_key_bytes)

    @classmethod
    def generate(cls) -> "Wallet":
        return cls(os.urandom(32))

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Wallet":
        path = Path(path)
        data = json.loads(path.read_text())
        sk = bytes.fromhex(data["private_key"])
        return cls(sk)

    def save(self, path: Union[str, Path]):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "private_key": self._sk.to_bytes().hex(),
            "public_key":  self._sk.public_key.to_hex(),
            "address":     self.address_hex(),
        }, indent=2))

    @property
    def public_key_bytes(self) -> bytes:
        return self._sk.public_key.to_bytes()

    @property
    def address_bytes(self) -> bytes:
        return keccak256(self.public_key_bytes)[-20:]

    def address_hex(self) -> str:
        return "0x" + self.address_bytes.hex()

    def sign(self, message_hash: bytes) -> bytes:
        """Returns 65-byte signature (r || s || v)。"""
        sig = self._sk.sign_msg_hash(message_hash)
        return sig.to_bytes()

    @staticmethod
    def verify(message_hash: bytes, signature: bytes, address_bytes: bytes) -> bool:
        try:
            sig = keys.Signature(signature)
            pk = sig.recover_public_key_from_msg_hash(message_hash)
            return keccak256(pk.to_bytes())[-20:] == address_bytes
        except Exception:
            return False

    def sign_transaction(self, recipient: Union[bytes, str], amount: int, nonce: int):
        """Convenience: 签发一笔交易。"""
        # 延迟导入避免循环
        from .transaction import sign_transaction
        if isinstance(recipient, str):
            recipient = bytes.fromhex(recipient[2:] if recipient.startswith("0x") else recipient)
        return sign_transaction(self, recipient, amount, nonce)
