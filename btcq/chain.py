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
    GENESIS_ALLOCATIONS,
    target_block_time_at, difficulty_window_at,
)


class Chain:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        (self.dir / "blocks").mkdir(parents=True, exist_ok=True)
        self._blocks: List[Block] = []
        # === 增量缓存（O(1) 查询） ===
        # 抵押映射：address -> currently active stake (atomic)
        self._stake_map: Dict[bytes, int] = {}
        # 流动余额：address -> liquid balance (atomic)
        self._balance: Dict[bytes, int] = {}
        # 账户 nonce：address -> next nonce
        self._nonce: Dict[bytes, int] = {}
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
        # 重启后恢复 slash 历史（已应用过的扣减不会重复）
        self._load_slash_records()

    def _apply_genesis_allocations(self):
        """创世状态预分配（致敬 Satoshi 等）。仅在创世后立即调用。"""
        for addr, amount in GENESIS_ALLOCATIONS.items():
            self._balance[addr] = self._balance.get(addr, 0) + amount

    def _update_state_caches(self, block: Block):
        """append/load 时增量更新所有状态缓存。O(交易数)。"""
        # 0. 创世块：应用预分配（Satoshi 等）
        if block.height == 0:
            self._apply_genesis_allocations()
            return
        # 1. 释放已到期的冷却（资金回流流动余额）
        still_cooling = []
        for (h, a, amt) in self._cooling:
            if h <= block.height:
                self._balance[a] = self._balance.get(a, 0) + amt
            else:
                still_cooling.append((h, a, amt))
        self._cooling = still_cooling

        # 2. 出块奖励
        if block.height > 0:
            from .block import block_reward
            self._balance[block.proposer_address] = self._balance.get(block.proposer_address, 0) + block_reward(block.height)

        # 3. 交易状态变化
        for tx in block.transactions:
            if tx.kind == "transfer":
                self._balance[tx.sender]    = self._balance.get(tx.sender, 0) - tx.amount
                self._balance[tx.recipient] = self._balance.get(tx.recipient, 0) + tx.amount
            elif tx.kind == "stake":
                self._balance[tx.sender]   = self._balance.get(tx.sender, 0) - tx.amount
                self._stake_map[tx.sender] = self._stake_map.get(tx.sender, 0) + tx.amount
            elif tx.kind == "unstake":
                cur = self._stake_map.get(tx.sender, 0)
                if tx.amount <= cur:
                    self._stake_map[tx.sender] = cur - tx.amount
                    if self._stake_map[tx.sender] == 0:
                        del self._stake_map[tx.sender]
                    self._cooling.append((block.height + UNSTAKE_DELAY_BLOCKS, tx.sender, tx.amount))
            self._nonce[tx.sender] = self._nonce.get(tx.sender, 0) + 1

        # 4. bootstrap 期 per-address 出块数
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

    # ====== 经济（O(1) 增量缓存） ======
    def balance_of(self, address_bytes: bytes) -> int:
        """O(1)：从增量缓存读取流动余额（不含正在抵押与冷却中的金额）。"""
        return self._balance.get(address_bytes, 0)

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

    def bootstrap_miners_map(self) -> Dict[bytes, int]:
        """bootstrap 已注册矿工映射 {address: count}（O(1)，缓存副本）。"""
        return dict(self._bootstrap_blocks_by_addr)

    def slash(self, address: bytes, height: int, reason: str) -> int:
        """对违规出块人执行罚没。返回扣除的金额（atomic）。

        slash 立即从 _stake_map 扣除，并持久化到 slash_records.json。
        持久化让重启后罚没记录不丢失，跨节点观察一致。
        """
        cur = self._stake_map.get(address, 0)
        if cur <= 0:
            # 没抵押也记录违规，方便可观察（amount=0）
            self._slash_records.append((height, address, 0, reason + " [无抵押可罚]"))
            self._save_slash_records()
            return 0
        amount = max(int(0.001 * COIN), int(cur * SLASH_RATIO))   # 最少 0.001 BTCQ
        amount = min(amount, cur)
        self._stake_map[address] = cur - amount
        if self._stake_map[address] == 0:
            del self._stake_map[address]
        self._slash_records.append((height, address, amount, reason))
        self._save_slash_records()
        return amount

    def slash_records(self) -> list:
        return list(self._slash_records)

    def total_slashed(self) -> int:
        """已被罚没的 BTCQ 总额（atomic）。"""
        return sum(amt for (_, _, amt, _) in self._slash_records)

    def _save_slash_records(self):
        path = self.dir / "slash_records.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {"height": h, "address": "0x" + a.hex(), "amount": amt, "reason": r}
            for (h, a, amt, r) in self._slash_records
        ]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _load_slash_records(self):
        path = self.dir / "slash_records.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for r in data:
                addr = bytes.fromhex(r["address"][2:] if r["address"].startswith("0x") else r["address"])
                self._slash_records.append((r["height"], addr, r["amount"], r["reason"]))
                # 重新应用扣减（如果当前还有抵押）
                if r["amount"] > 0 and self._stake_map.get(addr, 0) >= r["amount"]:
                    self._stake_map[addr] -= r["amount"]
                    if self._stake_map[addr] == 0:
                        del self._stake_map[addr]
        except Exception:
            pass

    # ====== Reorg / Fork choice 支持（Issue 3） ======
    def rewind_to(self, target_height: int, mempool=None) -> List["Block"]:
        """回滚链到指定高度，返回被回滚的区块列表（供 reorg 后回流交易用）。

        修复 Bug R1：清理 height > target 的 slash 记录
        修复 Bug R2：被回滚的区块返回，调用方可把其交易塞回 mempool
        """
        if target_height >= self.height:
            return []
        if target_height < 0:
            target_height = 0
        rolled_back: List["Block"] = []
        for h in range(target_height + 1, self.height + 1):
            rolled_back.append(self._blocks[h])
            f = self.dir / "blocks" / f"{h:08d}.json"
            if f.exists():
                f.unlink()
        # 截断 + 重建状态缓存
        self._blocks = self._blocks[:target_height + 1]
        self._stake_map.clear()
        self._balance.clear()
        self._nonce.clear()
        self._cooling.clear()
        self._bootstrap_blocks_by_addr.clear()
        # R1：删除 height > target 的 slash 记录（这些是被回滚那些块时产生的）
        kept_slashes = []
        for (h, addr, amt, reason) in self._slash_records:
            if h <= target_height:
                kept_slashes.append((h, addr, amt, reason))
        self._slash_records = kept_slashes
        self._save_slash_records()
        # 重建经济状态
        for b in self._blocks:
            self._update_state_caches(b)
        # 重新应用保留下来的 slash（在状态重建后）
        for (h, addr, amt, reason) in self._slash_records:
            if amt > 0:
                cur = self._stake_map.get(addr, 0)
                if cur >= amt:
                    self._stake_map[addr] = cur - amt
                    if self._stake_map[addr] == 0:
                        del self._stake_map[addr]
        # R2：把被回滚区块里的合法交易塞回 mempool
        if mempool is not None:
            from .transaction import Transaction
            for blk in rolled_back:
                for tx in blk.transactions:
                    try:
                        mempool.add(tx)
                    except Exception:
                        pass    # 重复或非法的就跳过
        # 刷新 latest 软链
        if self._blocks:
            (self.dir / "blocks" / "latest.json").write_text(
                json.dumps(self._blocks[-1].to_dict(), indent=2, ensure_ascii=False))
        return rolled_back

    def find_common_ancestor_height(self, peer_blocks_by_height: dict) -> int:
        """从顶部向下找与对方链的最高共同祖先。peer_blocks_by_height: {h: hex_hash}"""
        for h in range(min(self.height, max(peer_blocks_by_height.keys() or [0])), -1, -1):
            my_hash = "0x" + self._blocks[h].block_hash().hex()
            if peer_blocks_by_height.get(h) == my_hash:
                return h
        return 0   # 至少创世共同

    def nonce_of(self, address_bytes: bytes) -> int:
        """O(1)：从增量缓存读取地址下一笔交易应使用的 nonce。"""
        return self._nonce.get(address_bytes, 0)

    def total_supply_so_far(self) -> int:
        """全网当前已发行的 BTCQ 总额（出块奖励 + 创世预分配）。"""
        from .constants import GENESIS_ALLOCATIONS
        block_total = sum(block_reward(b.height) for b in self._blocks)
        genesis_total = sum(GENESIS_ALLOCATIONS.values()) if self._blocks else 0
        return block_total + genesis_total

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
