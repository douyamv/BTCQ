"""链状态管理：从磁盘加载区块、追加、查询余额。

设计要点（v0.1.1）：
* **增量 stake_map 缓存**：append 时同步更新，查询 O(1)
* **per-address bootstrap 计数**：限制单地址在 bootstrap 期最多挖几块
* **slash_records**：罚没历史，可被 verifier 查询
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import json

from .block import Block, block_reward
from .constants import (
    DIFFICULTY_MIN_FACTOR, DIFFICULTY_MAX_FACTOR,
    DIFFICULTY_MIN, DIFFICULTY_MAX, GENESIS_TIMESTAMP,
    INITIAL_XEB_THRESHOLD, POQSTAKE_XEB_THRESHOLD_FLOOR,
    BOOTSTRAP_OPEN_BLOCKS, BOOTSTRAP_PER_ADDR_CAP,
    UNSTAKE_DELAY_BLOCKS, SLASH_RATIO, COIN,
    target_block_time_at, difficulty_window_at,
)


class Chain:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        (self.dir / "blocks").mkdir(parents=True, exist_ok=True)
        self._blocks: List[Block] = []
        # === 增量缓存 ===
        # 抵押映射：address -> currently active stake (atomic)
        self._stake_map: Dict[bytes, int] = {}
        # 待释放冷却：[(release_height, address, amount)]
        self._cooling: List[Tuple[int, bytes, int]] = []
        # 每个地址的 bootstrap 期出块数（防垄断）
        self._bootstrap_blocks_by_addr: Dict[bytes, int] = {}
        # 罚没历史：[(height, address, amount, reason)]
        self._slash_records: List[Tuple[int, bytes, int, str]] = []
        self._load()

    def _load(self):
        blocks_dir = self.dir / "blocks"
        files = sorted(
            (p for p in blocks_dir.glob("*.json") if p.stem.isdigit()),
            key=lambda p: int(p.stem),
        )
        for f in files:
            block = Block.load(f)
            self._blocks.append(block)
            self._update_state_caches(block)

    def _update_state_caches(self, block: Block):
        """append/load 时增量更新所有状态缓存。O(交易数)。"""
        # 1. 释放已到期的冷却
        self._cooling = [(h, a, amt) for (h, a, amt) in self._cooling if h > block.height]
        # 2. 处理交易对 stake_map 的影响
        for tx in block.transactions:
            if tx.kind == "stake":
                self._stake_map[tx.sender] = self._stake_map.get(tx.sender, 0) + tx.amount
            elif tx.kind == "unstake":
                cur = self._stake_map.get(tx.sender, 0)
                if tx.amount <= cur:
                    self._stake_map[tx.sender] = cur - tx.amount
                    if self._stake_map[tx.sender] == 0:
                        del self._stake_map[tx.sender]
                    self._cooling.append((block.height + UNSTAKE_DELAY_BLOCKS, tx.sender, tx.amount))
        # 3. bootstrap 期 per-address 出块数
        if block.height > 0 and block.height <= BOOTSTRAP_OPEN_BLOCKS:
            self._bootstrap_blocks_by_addr[block.proposer_address] = \
                self._bootstrap_blocks_by_addr.get(block.proposer_address, 0) + 1

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
        self._update_state_caches(block)
        block.save(self.dir / "blocks" / f"{block.height:08d}.json")
        # 同步刷新 latest 软链快照
        (self.dir / "blocks" / "latest.json").write_text(
            json.dumps(block.to_dict(), indent=2, ensure_ascii=False))

    # ====== 经济 ======
    def balance_of(self, address_bytes: bytes) -> int:
        """流动余额（不含正在抵押与冷却中的金额）。

        转账：sender -= amount, recipient += amount
        抵押 (stake)：sender -= amount（钱被锁进金库；记入 staked_of）
        解抵押 (unstake)：发起当下不影响余额；
            等到 height + UNSTAKE_DELAY_BLOCKS 时金额回到 sender 的流动余额
        出块奖励：proposer += block_reward
        """
        from .constants import UNSTAKE_DELAY_BLOCKS
        total = 0
        current_h = self.height
        for b in self._blocks:
            if b.proposer_address == address_bytes:
                total += block_reward(b.height)
            for tx in b.transactions:
                if tx.kind == "transfer":
                    if tx.sender == address_bytes:
                        total -= tx.amount
                    if tx.recipient == address_bytes:
                        total += tx.amount
                elif tx.kind == "stake":
                    if tx.sender == address_bytes:
                        total -= tx.amount    # 锁进抵押池
                elif tx.kind == "unstake":
                    if tx.sender == address_bytes:
                        # 已度过冷却期？
                        if b.height + UNSTAKE_DELAY_BLOCKS <= current_h:
                            total += tx.amount
        return total

    def staked_of(self, address_bytes: bytes) -> int:
        """O(1)：从增量缓存读取当前活跃抵押额。"""
        return self._stake_map.get(address_bytes, 0)

    def cooling_of(self, address_bytes: bytes) -> int:
        """O(冷却记录数)：未到期冷却金额。"""
        return sum(amt for (h, a, amt) in self._cooling if a == address_bytes)

    def total_balance_of(self, address_bytes: bytes) -> int:
        """流动 + 抵押 + 冷却（用户的全部资产）。"""
        return self.balance_of(address_bytes) + self.staked_of(address_bytes) + self.cooling_of(address_bytes)

    def stake_map(self) -> Dict[bytes, int]:
        """全网当前抵押映射 {address: stake_amount}。O(1) 直接返回缓存副本。"""
        return dict(self._stake_map)

    def total_stake(self) -> int:
        return sum(self._stake_map.values())

    def bootstrap_blocks_by(self, address_bytes: bytes) -> int:
        """该地址在 bootstrap 期已经挖了多少块。"""
        return self._bootstrap_blocks_by_addr.get(address_bytes, 0)

    def slash(self, address: bytes, height: int, reason: str) -> int:
        """对违规出块人执行罚没。返回扣除的金额（atomic）。"""
        cur = self._stake_map.get(address, 0)
        if cur <= 0:
            return 0
        amount = max(int(0.001 * COIN), int(cur * SLASH_RATIO))   # 最少 0.001 BTCQ
        amount = min(amount, cur)
        self._stake_map[address] = cur - amount
        if self._stake_map[address] == 0:
            del self._stake_map[address]
        self._slash_records.append((height, address, amount, reason))
        return amount

    def slash_records(self) -> list:
        return list(self._slash_records)

    def nonce_of(self, address_bytes: bytes) -> int:
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
