"""链状态管理：从磁盘加载区块、追加、查询余额。"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict
import json

from .block import Block, block_reward
from .constants import (
    INITIAL_XEB_THRESHOLD, DIFFICULTY_MIN_FACTOR, DIFFICULTY_MAX_FACTOR,
    DIFFICULTY_MIN, DIFFICULTY_MAX, GENESIS_TIMESTAMP,
    target_block_time_at, difficulty_window_at,
)


class Chain:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        (self.dir / "blocks").mkdir(parents=True, exist_ok=True)
        self._blocks: List[Block] = []
        self._load()

    def _load(self):
        blocks_dir = self.dir / "blocks"
        files = sorted(
            (p for p in blocks_dir.glob("*.json") if p.stem.isdigit()),
            key=lambda p: int(p.stem),
        )
        for f in files:
            self._blocks.append(Block.load(f))

    @property
    def height(self) -> int:
        return len(self._blocks) - 1 if self._blocks else -1

    @property
    def head(self) -> Optional[Block]:
        return self._blocks[-1] if self._blocks else None

    def get(self, height: int) -> Block:
        return self._blocks[height]

    def append(self, block: Block):
        assert block.height == self.height + 1, f"高度不连续 {block.height} vs {self.height + 1}"
        self._blocks.append(block)
        block.save(self.dir / "blocks" / f"{block.height:08d}.json")
        # 同步刷新 latest 软链快照
        (self.dir / "blocks" / "latest.json").write_text(
            json.dumps(block.to_dict(), indent=2, ensure_ascii=False))

    # ====== 经济 ======
    def balance_of(self, address_bytes: bytes) -> int:
        total = 0
        for b in self._blocks:
            # 挖矿奖励
            if b.miner_address == address_bytes:
                total += block_reward(b.height)
            # 转账影响
            for tx in b.transactions:
                if tx.sender == address_bytes:
                    total -= tx.amount
                if tx.recipient == address_bytes:
                    total += tx.amount
        return total

    def nonce_of(self, address_bytes: bytes) -> int:
        """返回地址下一笔交易应使用的 nonce（已上链交易数）。"""
        n = 0
        for b in self._blocks:
            for tx in b.transactions:
                if tx.sender == address_bytes:
                    n += 1
        return n

    def total_supply_so_far(self) -> int:
        return sum(block_reward(b.height) for b in self._blocks)

    def total_tx_count(self) -> int:
        return sum(len(b.transactions) for b in self._blocks)

    # ====== 难度 ======
    def difficulty_at(self, height: int) -> float:
        """计算给定高度的难度（XEB 阈值）。

        难度调整窗口随 bootstrap 阶段动态变化：
          - 头 45 天（bootstrap）：每 144 块调整一次
          - 之后：每 2016 块调整一次（BTC 节奏）
        预期出块间隔也是时间相关的（60 秒 → 600 秒）。
        """
        if height == 0:
            return INITIAL_XEB_THRESHOLD
        # 决定本次是否是调整点：用 prev 区块的时间判断当前所处阶段
        prev = self._blocks[height - 1]
        seconds_since_genesis = max(0, prev.timestamp - GENESIS_TIMESTAMP)
        window_size = difficulty_window_at(seconds_since_genesis)

        if height % window_size != 0:
            return prev.difficulty
        # 调整点：取最近 window_size 块
        window = self._blocks[height - window_size : height]
        actual_time = max(window[-1].timestamp - window[0].timestamp, 1)
        # 期望时间 = 窗口内每块当时的目标间隔之和
        expected = 0.0
        for b in window:
            t = max(0, b.timestamp - GENESIS_TIMESTAMP)
            expected += target_block_time_at(t)
        expected = max(expected, 1.0)
        factor = max(DIFFICULTY_MIN_FACTOR, min(DIFFICULTY_MAX_FACTOR, actual_time / expected))
        # 时间越短 → factor 越小 → 难度越高（除以 factor）
        new_D = prev.difficulty / factor
        return max(DIFFICULTY_MIN, min(DIFFICULTY_MAX, new_D))

    def next_difficulty(self) -> float:
        return self.difficulty_at(self.height + 1)

    def expected_block_time(self) -> float:
        """当前阶段的期望出块时间。"""
        head = self.head
        if head is None:
            return target_block_time_at(0)
        t = max(0, head.timestamp - GENESIS_TIMESTAMP)
        return target_block_time_at(t)
