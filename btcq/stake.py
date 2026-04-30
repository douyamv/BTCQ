"""抵押（Stake）与抵押状态计算。

设计：
    * 抵押通过特殊地址实现：发送到 STAKE_VAULT (`0x0000...01`) 视为抵押
    * 解抵押：sender = STAKE_VAULT 的反向交易（必须由账户本人发起，签名 + nonce 防伪）
      实际实现：用 tx_kind 标记区分（普通转账 / 抵押 / 解抵押）
    * 解抵押有 UNSTAKE_DELAY_BLOCKS 延迟：交易上链后 100 块才能真正取出（领取交易）
    * 投票权重 = 当前 active_stake，与抵押时长无关（v0.5 可改为时长加权）

为简化 v0.1，我们扩展 Transaction 的 kind 字段：
    * "transfer"  — 普通转账
    * "stake"     — 抵押（recipient 必须是 STAKE_VAULT）
    * "unstake"   — 解抵押申请（recipient 必须是 STAKE_VAULT；amount 为申请取出额）
"""

from __future__ import annotations
from typing import Dict, List, Tuple

from .constants import MIN_STAKE, UNSTAKE_DELAY_BLOCKS


STAKE_VAULT = bytes.fromhex("00" * 19 + "01")    # 0x000...001 — 抵押"金库"伪地址
TX_TRANSFER = "transfer"
TX_STAKE    = "stake"
TX_UNSTAKE  = "unstake"


def stake_state_at(blocks) -> Dict[bytes, int]:
    """根据已上链区块计算每个地址当前的活跃抵押额。

    一个 unstake 在 H 高度提交后，从 H+UNSTAKE_DELAY_BLOCKS 开始释放（资金回到 sender 余额）。
    在 [H, H+delay) 区间内，资金既不算 staked 也不算 liquid（处于"冷却"）。
    """
    active: Dict[bytes, int] = {}
    cooling: List[Tuple[int, bytes, int]] = []  # (release_height, address, amount)

    for blk in blocks:
        # 先处理这一块释放的冷却资金
        cooling = [(h, a, amt) for (h, a, amt) in cooling if h > blk.height]

        for tx in blk.transactions:
            if tx.kind == TX_STAKE:
                active[tx.sender] = active.get(tx.sender, 0) + tx.amount
            elif tx.kind == TX_UNSTAKE:
                avail = active.get(tx.sender, 0)
                if tx.amount > avail:
                    continue   # 协议层不应让此交易上链；此处保险
                active[tx.sender] = avail - tx.amount
                if active[tx.sender] == 0:
                    del active[tx.sender]
                cooling.append((blk.height + UNSTAKE_DELAY_BLOCKS,
                                tx.sender, tx.amount))
    return active


def cooling_returns_at(blocks, address: bytes, current_height: int) -> int:
    """计算 address 已经度过冷却期、可取出的金额（未来变成普通余额）。

    v0.1 设计：冷却期结束后金额自动加回 balance_of（在 chain.py 里实现）。
    """
    total = 0
    for blk in blocks:
        for tx in blk.transactions:
            if tx.kind == TX_UNSTAKE and tx.sender == address:
                if blk.height + UNSTAKE_DELAY_BLOCKS <= current_height:
                    total += tx.amount
    return total


def is_eligible_proposer(address: bytes, stake_map: Dict[bytes, int]) -> bool:
    """是否有资格出块（抵押额 ≥ MIN_STAKE）。"""
    return stake_map.get(address, 0) >= MIN_STAKE


def select_proposer(prev_hash: bytes, height: int, stake_map: Dict[bytes, int]) -> bytes | None:
    """VRF-style 出块人选举：基于 prev_hash + height 派生伪随机数，按抵押权重抽签。

    v0.1 用 keccak 当 VRF（足够确定 + 无偏见，但不是真 VRF — 缺少不可预测性证明）。
    v0.5 会换成 Schnorr-VRF。
    """
    from .wallet import keccak256
    eligible = [(a, s) for a, s in stake_map.items() if s >= MIN_STAKE]
    if not eligible:
        return None
    total = sum(s for _, s in eligible)
    seed = keccak256(prev_hash + height.to_bytes(8, "big"))
    rnd = int.from_bytes(seed[:8], "big") % total
    cum = 0
    for addr, s in eligible:
        cum += s
        if rnd < cum:
            return addr
    return eligible[-1][0]
