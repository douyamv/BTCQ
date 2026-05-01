"""交易池（mempool）：本地 JSON 文件存储待打包交易。

v0.1 是单节点本地池。v0.5 引入 P2P 后会广播。
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional, Union

from .transaction import Transaction


class Mempool:
    def __init__(self, path: Union[str, Path]):
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

    def add(self, tx: Transaction, chain=None):
        if not tx.verify_signature():
            raise ValueError("交易签名无效")
        # 业务校验（防止 mempool 塞满废 tx）
        if chain is not None:
            self._validate_against_chain(tx, chain)
        # 简单去重：相同 sender+nonce 替换
        self._txs = [t for t in self._txs if not (t.sender == tx.sender and t.nonce == tx.nonce)]
        self._txs.append(tx)
        self._save()

    def _validate_against_chain(self, tx: Transaction, chain):
        """根据当前链状态校验 tx 业务规则。任何不通过抛 ValueError。

        - amount > 0
        - 转账/抵押 sender ≠ recipient（防自转）
        - nonce 必须 == 链上 nonce（不超前不滞后）
        - 转账：sender liquid >= amount
        - 抵押：sender liquid >= amount（且 amount ≥ 单位配置）
        - 解抵押：sender staked >= amount
        - mempool 大小硬上限（防 DoS）
        """
        from .constants import MIN_STAKE
        if tx.amount <= 0:
            raise ValueError("amount 必须 > 0")

        # 当前 mempool 已 pending 的同 sender 交易消耗
        pending_out = sum(
            t.amount for t in self._txs
            if t.sender == tx.sender and t.kind in ("transfer", "stake")
        )
        pending_unstake = sum(
            t.amount for t in self._txs
            if t.sender == tx.sender and t.kind == "unstake"
        )

        # nonce: 必须严格等于 链上 nonce + mempool 中同 sender 已有 tx 数 - (重复 nonce 跳过)
        on_chain_nonce = chain.nonce_of(tx.sender)
        # 算 sender 在 mempool 已有的最大 nonce + 1（替换重复 nonce 不算）
        existing_same = [t for t in self._txs if t.sender == tx.sender and t.nonce != tx.nonce]
        expected_nonce = on_chain_nonce + len(existing_same)
        if tx.nonce != expected_nonce:
            raise ValueError(f"nonce 不匹配，期望 {expected_nonce}，收到 {tx.nonce}")

        liquid = chain.balance_of(tx.sender)
        staked = chain.staked_of(tx.sender)

        if tx.kind == "transfer":
            if tx.sender == tx.recipient:
                raise ValueError("不能转给自己")
            if tx.amount + pending_out > liquid:
                raise ValueError(f"余额不足（流通={liquid}, 待打包占用={pending_out}, 本笔={tx.amount}）")
        elif tx.kind == "stake":
            if tx.amount < MIN_STAKE and (staked + tx.amount) < MIN_STAKE:
                # 允许追加，但首次抵押必须 ≥ MIN_STAKE
                if staked == 0:
                    raise ValueError(f"首次抵押至少 {MIN_STAKE} 原子单位")
            if tx.amount + pending_out > liquid:
                raise ValueError(f"流通余额不足（liquid={liquid}, 待打包占用={pending_out}, 本笔={tx.amount}）")
        elif tx.kind == "unstake":
            if tx.amount + pending_unstake > staked:
                raise ValueError(f"抵押不足（staked={staked}, 待打包解抵押={pending_unstake}, 本笔={tx.amount}）")

        # 防 DoS：mempool 硬上限
        MAX_MEMPOOL = 50_000
        if len(self._txs) >= MAX_MEMPOOL:
            raise ValueError("mempool 已满")

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
