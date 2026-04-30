"""区块验证器。任何节点都可独立运行验证一条链是否合法。"""

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
from .constants import (
    PROTOCOL_VERSION, CIRCUIT_N_QUBITS, CIRCUIT_DEPTH,
    XEB_FLOAT_TOL, TIMESTAMP_FUTURE_TOL,
)


class VerificationError(Exception):
    pass


def _verify_transactions(txs, chain_state) -> Tuple[bool, str]:
    """对一组交易做：签名 + nonce 顺序 + 余额够 三项校验。chain_state 是当前已上链状态（不含本块）。"""
    if not txs:
        return True, ""
    pending_balance = {}
    pending_nonce = {}
    for i, tx in enumerate(txs):
        if not tx.verify_signature():
            return False, f"交易 #{i} 签名无效"
        cur_nonce = pending_nonce.get(tx.sender, chain_state.nonce_of(tx.sender))
        if tx.nonce != cur_nonce:
            return False, f"交易 #{i} nonce 错误: {tx.nonce} != {cur_nonce}"
        cur_bal = pending_balance.get(tx.sender, chain_state.balance_of(tx.sender))
        if cur_bal < tx.amount:
            return False, f"交易 #{i} 余额不足: {cur_bal} < {tx.amount}"
        if tx.amount < 0:
            return False, f"交易 #{i} 金额为负"
        pending_balance[tx.sender] = cur_bal - tx.amount
        pending_balance[tx.recipient] = pending_balance.get(
            tx.recipient, chain_state.balance_of(tx.recipient)) + tx.amount
        pending_nonce[tx.sender] = cur_nonce + 1
    return True, ""


def verify_block(block: Block, prev: Block, expected_difficulty: float, *,
                 chain_state: Optional["Chain"] = None, recompute_xeb: bool = True) -> Tuple[bool, str]:
    """验证单个区块。返回 (是否合法, 信息)。

    chain_state: 若提供则会验证交易余额/nonce 与链状态一致。
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
    # 7c. 每笔交易签名 + 余额 + nonce 校验
    if chain_state is not None:
        ok, msg = _verify_transactions(block.transactions, chain_state)
        if not ok:
            return False, msg
    # 8. 出块人签名
    if not Wallet.verify(block.block_hash(), block.proposer_signature, block.proposer_address):
        return False, "出块人签名无效"
    # 8b. 出块人是否有足够抵押（PoQ-Stake 关键约束）
    # bootstrap 期（前 BOOTSTRAP_OPEN_BLOCKS 块）开放挖矿，无需抵押
    from .constants import BOOTSTRAP_OPEN_BLOCKS, MIN_STAKE
    if chain_state is not None and block.height > BOOTSTRAP_OPEN_BLOCKS:
        from .stake import stake_state_at
        prior_blocks = [chain_state.get(h) for h in range(0, block.height)]
        stake_map = stake_state_at(prior_blocks)
        if stake_map.get(block.proposer_address, 0) < MIN_STAKE:
            return False, f"出块人 {block.proposer_address.hex()} 抵押不足，无资格出块"
    # 9. 重算电路 + XEB（最贵的一步，可选）
    if recompute_xeb:
        # PoQ-Stake：seed 由 prev_hash + height + proposer 决定（不再有矿工 nonce）
        seed = keccak256(block.prev_hash + block.height.to_bytes(8, "big") + block.proposer_address)
        desc = build_circuit_description(seed, block.n_qubits, block.depth)
        probs = amplitudes_for_samples(desc, block.samples)
        f_xeb = linear_xeb_from_probs(probs, block.n_qubits)
        # n>31 用 MPS 近似时容许较大数值漂移
        tol = 0.02 if block.n_qubits > 31 else XEB_FLOAT_TOL * 100
        if abs(f_xeb - block.xeb_score) > tol:
            return False, f"XEB 重算不一致: 链上 {block.xeb_score:.6f} vs 实测 {f_xeb:.6f}"
        if f_xeb < block.difficulty:
            return False, f"XEB 低于难度: {f_xeb:.4f} < {block.difficulty:.4f}"
    return True, "OK"


def verify_chain(chain_dir: str | Path, *, recompute_xeb: bool = True) -> Tuple[bool, str]:
    """全链顺序验证。每一步用"截至 h-1 的子链"作为状态来校验交易。"""
    full_chain = Chain(chain_dir)
    if full_chain.head is None:
        return False, "链为空"
    if full_chain.height < 0:
        return False, "无创世"

    # 用一个"逐步追加"的影子链来代表每个高度时的状态
    import tempfile, shutil
    tmpdir = Path(tempfile.mkdtemp(prefix="btcq-verify-"))
    try:
        shadow = Chain(tmpdir)
        shadow.append(full_chain.get(0))   # 复制创世

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
