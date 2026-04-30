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
from .stake import STAKE_VAULT, TX_TRANSFER, TX_STAKE, TX_UNSTAKE, select_proposer
from .constants import (
    PROTOCOL_VERSION, CIRCUIT_N_QUBITS, CIRCUIT_DEPTH,
    XEB_FLOAT_TOL, TIMESTAMP_FUTURE_TOL,
    BOOTSTRAP_OPEN_BLOCKS, BOOTSTRAP_PER_ADDR_CAP, MIN_STAKE,
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
    # 4. 时间戳
    if block.timestamp <= prev.timestamp:
        return False, "时间戳早于上一区块"
    if block.timestamp > int(time.time()) + TIMESTAMP_FUTURE_TOL:
        return False, "时间戳超前过多"
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
    # 8. 出块人签名
    if not Wallet.verify(block.block_hash(), block.proposer_signature, block.proposer_address):
        return False, "出块人签名无效"

    # 8b. 共识层资格检查（PoQ-Stake 核心）
    if chain_state is not None:
        if block.height <= BOOTSTRAP_OPEN_BLOCKS:
            # bootstrap 期：开放挖矿，但单地址有上限
            mined_so_far = chain_state.bootstrap_blocks_by(block.proposer_address)
            if mined_so_far >= BOOTSTRAP_PER_ADDR_CAP:
                return False, (f"bootstrap 期 {block.proposer_address.hex()} 已挖 "
                               f"{mined_so_far} 块，达到 {BOOTSTRAP_PER_ADDR_CAP} 上限")
        else:
            # PoQ-Stake 期：必须是 VRF 选中的出块人
            stake_map = chain_state.stake_map()
            if stake_map.get(block.proposer_address, 0) < MIN_STAKE:
                return False, f"出块人 {block.proposer_address.hex()} 抵押不足"
            expected = select_proposer(block.prev_hash, block.height, stake_map)
            if expected is None:
                return False, "全网无合格 staker，链卡死"
            if block.proposer_address != expected:
                return False, (f"非本 slot 选中的出块人：期望 0x{expected.hex()}，"
                               f"实际 0x{block.proposer_address.hex()}")

    # 9. 重算电路 + XEB（最贵的一步，可选）
    if recompute_xeb:
        seed = keccak256(block.prev_hash + block.height.to_bytes(8, "big") + block.proposer_address)
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
