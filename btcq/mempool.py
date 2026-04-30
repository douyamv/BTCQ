"""交易池（mempool）：本地 JSON 文件存储待打包交易。

v0.1 是单节点本地池。v0.5 引入 P2P 后会广播。
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List

from .transaction import Transaction


class Mempool:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._txs: List[Transaction] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._txs = [Transaction.from_dict(t) for t in data.get("transactions", [])]
            except Exception:
                self._txs = []

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "transactions": [t.to_dict() for t in self._txs],
        }, indent=2, ensure_ascii=False))

    def add(self, tx: Transaction):
        if not tx.verify_signature():
            raise ValueError("交易签名无效")
        # 简单去重：相同 sender+nonce 替换
        self._txs = [t for t in self._txs if not (t.sender == tx.sender and t.nonce == tx.nonce)]
        self._txs.append(tx)
        self._save()

    def all(self) -> List[Transaction]:
        return list(self._txs)

    def take(self, max_count: int = 1000) -> List[Transaction]:
        """取出至多 max_count 个交易（不删除）。矿工打包时调用。"""
        return self._txs[:max_count]

    def remove_included(self, included: List[Transaction]):
        """区块上链后调用：移除已被打包的交易。"""
        included_keys = {(t.sender, t.nonce) for t in included}
        self._txs = [t for t in self._txs
                     if (t.sender, t.nonce) not in included_keys]
        self._save()

    def __len__(self):
        return len(self._txs)
