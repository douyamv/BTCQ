"""区块验证器。任何节点都可独立运行验证一条链是否合法。

v0.1.1 修复：
* Bug 1：强制 VRF 选举的出块人才有效
* Bug 2：交易按 kind 分支校验（transfer/stake/unstake 各自余额逻辑）
* Bug 7：bootstrap 期单地址出块上限
"""

from __future__ import annotations
import time
from pathlib import Path
from typing import Tuple, Optional

from .block import Block, compute_samples_root, compute_transactions_root
from .chain import Chain
from .circuit import build_circuit_description, simulate_statevector, amplitudes_for_samples
from .xeb import linear_xeb, linear_xeb_from_probs
from .wallet import Wallet, keccak256
from .transaction import Transaction
from .stake import (
    STAKE_VAULT, TX_TRANSFER, TX_STAKE, TX_UNSTAKE,
    select_proposer_for_slot, select_bootstrap_proposer,
)
from .constants import (
    PROTOCOL_VERSION, CIRCUIT_N_QUBITS, CIRCUIT_DEPTH,
    XEB_FLOAT_TOL, TIMESTAMP_FUTURE_TOL,
    BOOTSTRAP_OPEN_BLOCKS, BOOTSTRAP_PER_ADDR_CAP, MIN_STAKE,
    SLOT_FUTURE_TOL, SLOT_TIMESTAMP_TOL,
    slot_at, slot_start_timestamp,
)


class VerificationError(Exception):
    pass


def _verify_transactions(txs, chain_state) -> Tuple[bool, str]:
    """按 kind 分支校验交易：transfer / stake / unstake 各自语义。

    chain_state: 当前已上链状态（不含本块）。
    """
    if not txs:
        return True, ""
    pending_balance: dict = {}
    pending_nonce: dict = {}
    pending_stake: dict = {}

    def _bal(a):    return pending_balance.get(a, chain_state.balance_of(a))
    def _nonce(a):  return pending_nonce.get(a, chain_state.nonce_of(a))
    def _stake(a):  return pending_stake.get(a, chain_state.staked_of(a))

    for i, tx in enumerate(txs):
        if not tx.verify_signature():
            return False, f"交易 #{i} 签名无效"
        if _nonce(tx.sender) != tx.nonce:
            return False, f"交易 #{i} nonce 错误: {tx.nonce} != {_nonce(tx.sender)}"
        if tx.amount < 0:
            return False, f"交易 #{i} 金额为负"

        if tx.kind == TX_TRANSFER:
            if _bal(tx.sender) < tx.amount:
                return False, f"交易 #{i} (transfer) 余额不足: {_bal(tx.sender)} < {tx.amount}"
            pending_balance[tx.sender] = _bal(tx.sender) - tx.amount
            pending_balance[tx.recipient] = _bal(tx.recipient) + tx.amount
        elif tx.kind == TX_STAKE:
            if tx.recipient != STAKE_VAULT:
                return False, f"交易 #{i} (stake) recipient 必须是 STAKE_VAULT"
            if _bal(tx.sender) < tx.amount:
                return False, f"交易 #{i} (stake) 流动余额不足: {_bal(tx.sender)} < {tx.amount}"
            pending_balance[tx.sender] = _bal(tx.sender) - tx.amount
            pending_stake[tx.sender] = _stake(tx.sender) + tx.amount
        elif tx.kind == TX_UNSTAKE:
            if tx.recipient != STAKE_VAULT:
                return False, f"交易 #{i} (unstake) recipient 必须是 STAKE_VAULT"
            if _stake(tx.sender) < tx.amount:
                return False, f"交易 #{i} (unstake) 抵押不足: {_stake(tx.sender)} < {tx.amount}"
            pending_stake[tx.sender] = _stake(tx.sender) - tx.amount
            # 余额不立即增加（冷却期）
        else:
            return False, f"交易 #{i} 未知 kind: {tx.kind}"

        pending_nonce[tx.sender] = tx.nonce + 1
    return True, ""


def verify_block(block: Block, prev: Block, expected_difficulty: float, *,
                 chain_state: Optional["Chain"] = None,
                 recompute_xeb: bool = True) -> Tuple[bool, str]:
    """验证单个区块。返回 (是否合法, 信息)。

    chain_state: 已上链状态（不含本块）。强烈建议提供，否则跳过共识层校验。
    """
    # 1. 协议版本
    if block.version != PROTOCOL_VERSION:
        return False, f"协议版本不匹配: {block.version} != {PROTOCOL_VERSION}"
    # 2. 高度连续
    if block.height != prev.height + 1:
        return False, f"高度不连续: {block.height} != {prev.height + 1}"
    # 3. 链接
    if block.prev_hash != prev.block_hash():
        return False, "prev_hash 与上一区块哈希不匹配"
    # 4. 时间戳：单调递增 + 不超本地钟太多（三道防线之三）
    if block.timestamp <= prev.timestamp:
        return False, "时间戳早于上一区块"
    if block.timestamp > int(time.time()) + TIMESTAMP_FUTURE_TOL:
        return False, "时间戳超前过多（>2 小时）"

    # 4b. Slot 严格递增（防止同一 slot 多区块）—— 这是 slot 设计的核心不变量
    #     允许跳号（空 slot），但绝对不能并列或倒退
    if block.slot <= prev.slot:
        return False, f"slot {block.slot} ≤ 上一区块 slot {prev.slot}（slot 必须严格递增）"
    # 4c. block.slot 与 timestamp 大致一致（允许 SLOT_FUTURE_TOL 个 slot 漂移）
    derived_slot = slot_at(block.timestamp)
    if abs(block.slot - derived_slot) > SLOT_FUTURE_TOL:
        return False, (f"block.slot={block.slot} 与 timestamp 算出的 slot={derived_slot} 偏差超 "
                       f"{SLOT_FUTURE_TOL} 个 slot")
    # 4d. block.timestamp 落在 slot 时间窗 ± 容差（loose 容差兼容慢链/慢算）
    slot_start = slot_start_timestamp(block.slot)
    slot_end = slot_start_timestamp(block.slot + 1)
    if not (slot_start - SLOT_TIMESTAMP_TOL <= block.timestamp <= slot_end + SLOT_TIMESTAMP_TOL):
        return False, (f"block.timestamp={block.timestamp} 距 slot {block.slot} 时间窗 "
                       f"[{slot_start}, {slot_end}] 偏差超 {SLOT_TIMESTAMP_TOL}s")
    # 5. 难度
    if abs(block.difficulty - expected_difficulty) > 1e-9:
        return False, f"难度不匹配: {block.difficulty} != {expected_difficulty}"
    # 6. 电路参数（v0.1 固定）
    if block.n_qubits != CIRCUIT_N_QUBITS:
        return False, f"n_qubits != {CIRCUIT_N_QUBITS}"
    if block.depth != CIRCUIT_DEPTH:
        return False, f"depth != {CIRCUIT_DEPTH}"
    if block.n_samples != len(block.samples):
        return False, "n_samples 字段与 samples 长度不一致"
    # 7. samples_root
    if compute_samples_root(block.samples, block.n_qubits) != block.samples_root:
        return False, "samples_root 错误"
    # 7b. transactions_root
    if compute_transactions_root(block.transactions) != block.transactions_root:
        return False, "transactions_root 错误"
    # 7c. 交易合法性（按 kind 分支校验）
    if chain_state is not None:
        ok, msg = _verify_transactions(block.transactions, chain_state)
        if not ok:
            return False, msg
    # 7d. C1: state_root 一致性（账户模型必须）
    if chain_state is not None:
        expected_state_root = chain_state.preview_state_root(block)
        if block.state_root != expected_state_root:
            return False, (f"state_root 不一致：链上 0x{block.state_root.hex()[:16]}... "
                           f"vs 期望 0x{expected_state_root.hex()[:16]}...")
    # 8. 出块人签名
    if not Wallet.verify(block.block_hash(), block.proposer_signature, block.proposer_address):
        return False, "出块人签名无效"

    # 8b. 共识层资格检查（PoQ-Stake 核心，第二道防线）
    if chain_state is not None:
        if block.height <= BOOTSTRAP_OPEN_BLOCKS:
            # bootstrap 期：单地址 cap + 已注册集合 VRF
            mined_so_far = chain_state.bootstrap_blocks_by(block.proposer_address)
            if mined_so_far >= BOOTSTRAP_PER_ADDR_CAP:
                return False, (f"bootstrap 期 0x{block.proposer_address.hex()} 已挖 "
                               f"{mined_so_far} 块，达到 {BOOTSTRAP_PER_ADDR_CAP} 上限")
            # Issue 4 修复：bootstrap 期也走 VRF（如果候选集非空）
            miners_map = chain_state.bootstrap_miners_map()
            stake_map = chain_state.stake_map()
            expected = select_bootstrap_proposer(
                block.slot, miners_map, BOOTSTRAP_PER_ADDR_CAP, stake_map
            )
            if expected is not None and block.proposer_address != expected:
                return False, (f"bootstrap slot {block.slot} VRF 选中的是 "
                               f"0x{expected.hex()}，不是 0x{block.proposer_address.hex()}")
            # expected is None 时（创世后第 1 块或所有人都达上限）→ 开放挖矿
        else:
            # PoQ-Stake 期：必须是当前 slot 的 VRF proposer
            stake_map = chain_state.stake_map()
            if stake_map.get(block.proposer_address, 0) < MIN_STAKE:
                return False, f"出块人 0x{block.proposer_address.hex()} 抵押不足"
            expected = select_proposer_for_slot(block.slot, stake_map)
            if expected is None:
                return False, "全网无合格 staker"
            if block.proposer_address != expected:
                return False, (f"slot {block.slot} 提议人不匹配："
                               f"期望 0x{expected.hex()}，实际 0x{block.proposer_address.hex()}")

    # 9. 重算电路 + XEB（最贵的一步，可选）
    if recompute_xeb:
        # seed 现在用 slot（不是 height），与 proposer 端一致
        seed = keccak256(block.prev_hash + block.slot.to_bytes(8, "big") + block.proposer_address)
        desc = build_circuit_description(seed, block.n_qubits, block.depth)
        probs = amplitudes_for_samples(desc, block.samples)
        f_xeb = linear_xeb_from_probs(probs, block.n_qubits)
        tol = 0.02 if block.n_qubits > 31 else XEB_FLOAT_TOL * 100
        if abs(f_xeb - block.xeb_score) > tol:
            return False, f"XEB 重算不一致: 链上 {block.xeb_score:.6f} vs 实测 {f_xeb:.6f}"
        if f_xeb < block.difficulty:
            return False, f"XEB 低于难度: {f_xeb:.4f} < {block.difficulty:.4f}"
    return True, "OK"


def verify_chain(chain_dir: str | Path, *, recompute_xeb: bool = True) -> Tuple[bool, str]:
    """全链顺序验证。用"截至 h-1 的子链"作为状态来校验交易。"""
    full_chain = Chain(chain_dir)
    if full_chain.head is None:
        return False, "链为空"
    if full_chain.height < 0:
        return False, "无创世"

    import tempfile, shutil
    tmpdir = Path(tempfile.mkdtemp(prefix="btcq-verify-"))
    try:
        shadow = Chain(tmpdir)
        shadow.append(full_chain.get(0))

        for h in range(1, full_chain.height + 1):
            block = full_chain.get(h)
            prev = shadow.get(h - 1)
            expected = shadow.difficulty_at(h)
            ok, msg = verify_block(block, prev, expected,
                                   chain_state=shadow, recompute_xeb=recompute_xeb)
            if not ok:
                return False, f"区块 #{h}: {msg}"
            shadow.append(block)
        return True, f"全链 {full_chain.height + 1} 个区块全部合法（含 {full_chain.total_tx_count()} 笔交易）"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
