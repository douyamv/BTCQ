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


def select_proposer_for_slot(slot: int, stake_map: Dict[bytes, int]) -> bytes | None:
    """硬时间 slot 出块人选举：基于 slot 编号派生伪随机数，按抵押权重抽签。

    每个 slot 唯一确定一个 proposer。slot 与 height 解耦——空 slot 不增高度。
    v0.1 用 keccak 当 VRF（确定性 + 无偏，但不是真 VRF — 缺少不可预测性证明）。
    v0.5 升级 Schnorr-VRF。
    """
    from .wallet import keccak256
    eligible = sorted(
        [(a, s) for a, s in stake_map.items() if s >= MIN_STAKE],
        key=lambda x: x[0],   # 按地址排序，保证所有节点结果一致
    )
    if not eligible:
        return None
    total = sum(s for _, s in eligible)
    seed = keccak256(b"BTCQ-VRF-SLOT" + slot.to_bytes(8, "big"))
    rnd = int.from_bytes(seed[:8], "big") % total
    cum = 0
    for addr, s in eligible:
        cum += s
        if rnd < cum:
            return addr
    return eligible[-1][0]


# 旧 API 兼容（已废弃，仅保留向后兼容）
def select_proposer(prev_hash: bytes, height: int, stake_map: Dict[bytes, int]) -> bytes | None:
    """已废弃：v0.1.2 起 slot 取代 height 作为选举依据。请使用 select_proposer_for_slot。"""
    return select_proposer_for_slot(height, stake_map)


def select_bootstrap_proposer(
    slot: int,
    bootstrap_blocks_by_addr: Dict[bytes, int],
    bootstrap_per_addr_cap: int,
    stake_map: Dict[bytes, int] = None,
) -> bytes | None:
    """Bootstrap 期 slot proposer 选举（Issue 4）。

    候选集合 = (已挖过块且未达上限的矿工) ∪ (已抵押的 stakers)
    若集合非空：用 slot 派生伪随机数选出唯一 proposer
    若集合为空：返回 None，表示该 slot 仍为"开放挖矿"（第一个 valid 块占据）

    这样设计：
      ① 第一位矿工先 free-for-all 出块（集合空 → 开放）
      ② 之后任何已挖过/已抵押的矿工都可参与 VRF
      ③ 同一 slot 唯一 proposer，避免分叉
      ④ per-addr cap 防垄断（达到上限自动出局）
    """
    from .wallet import keccak256
    eligible_addrs: list = []
    for addr, count in bootstrap_blocks_by_addr.items():
        if count < bootstrap_per_addr_cap:
            eligible_addrs.append(addr)
    if stake_map:
        for addr in stake_map:
            if addr not in eligible_addrs:
                eligible_addrs.append(addr)
    if not eligible_addrs:
        return None    # 完全开放：第一个 valid 块抢占
    eligible_addrs.sort()
    seed = keccak256(b"BTCQ-BOOTSTRAP-SLOT" + slot.to_bytes(8, "big"))
    rnd = int.from_bytes(seed[:8], "big") % len(eligible_addrs)
    return eligible_addrs[rnd]
