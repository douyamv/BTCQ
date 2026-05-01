"""出块人（Proposer）：PoQ-Stake 共识下的区块生产逻辑。

流程：
  1. 检查 wallet 抵押额是否 >= MIN_STAKE
  2. 用 prev_hash + height + proposer_addr 派生确定性电路 seed
  3. 调用量子机执行 RCS 电路（≈1 秒接口）
  4. 经典验证 XEB ≥ 当前阈值
  5. 从 mempool 选合法交易
  6. 组装并签名区块
"""

from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Optional, List

import numpy as np

from .constants import (
    PROTOCOL_VERSION, CIRCUIT_N_QUBITS, CIRCUIT_DEPTH, CIRCUIT_N_SAMPLES,
    MIN_STAKE, BOOTSTRAP_OPEN_BLOCKS, BOOTSTRAP_PER_ADDR_CAP,
    slot_at, slot_start_timestamp, slot_duration_at, GENESIS_TIMESTAMP,
)
from .circuit import build_circuit_description, to_qiskit, simulate_statevector, amplitudes_for_samples
from .xeb import linear_xeb, linear_xeb_from_probs
from .block import Block, compute_samples_root, compute_transactions_root
from .chain import Chain
from .wallet import Wallet, keccak256
from .mempool import Mempool
from .transaction import Transaction
from .stake import (
    STAKE_VAULT, TX_TRANSFER, TX_STAKE, TX_UNSTAKE,
    select_proposer_for_slot, select_bootstrap_proposer,
)


def _circuit_seed(prev_hash: bytes, slot: int, proposer_addr: bytes) -> bytes:
    """每个 slot 的电路 seed = keccak(prev_hash || slot || proposer)。

    用 slot 而非 height：保证空 slot 也产生不同电路，proposer 没有"换 height 重试"自由。
    """
    return keccak256(prev_hash + slot.to_bytes(8, "big") + proposer_addr)


def _samples_from_counts(counts: dict, n_qubits: int, n_samples: int) -> List[int]:
    expanded: List[int] = []
    for bitstr, c in counts.items():
        bitstr = bitstr.replace(" ", "")
        v = int(bitstr, 2)
        expanded.extend([v] * c)
    if len(expanded) > n_samples:
        expanded = expanded[:n_samples]
    elif len(expanded) < n_samples:
        last = expanded[-1] if expanded else 0
        expanded += [last] * (n_samples - len(expanded))
    return expanded


def _check_eligible(chain: Chain, wallet: Wallet, verbose: bool) -> int:
    """检查 wall-clock 当前 slot 我是否能出块。返回该 slot 编号供调用方使用。

    bootstrap 期（前 BOOTSTRAP_OPEN_BLOCKS 块）：开放挖矿 + 每地址有上限
    PoQ-Stake 期：必须是 VRF 选中的 slot proposer
    """
    addr = wallet.address_bytes
    now_ts = int(time.time())
    cur_slot = slot_at(now_ts)
    head = chain.head
    head_slot = head.slot if head else 0

    # slot 必须严格递增
    if cur_slot <= head_slot:
        wait_until = slot_start_timestamp(head_slot + 1)
        raise RuntimeError(
            f"当前 slot {cur_slot} ≤ 上一区块 slot {head_slot}，需等 {wait_until-now_ts}s "
            f"到下个 slot 才能出块"
        )

    if chain.height + 1 <= BOOTSTRAP_OPEN_BLOCKS:
        # bootstrap：单地址出块上限
        mined = chain.bootstrap_blocks_by(addr)
        if mined >= BOOTSTRAP_PER_ADDR_CAP:
            raise RuntimeError(
                f"bootstrap：地址 {wallet.address_hex()} 已挖 {mined} 块，达到 "
                f"{BOOTSTRAP_PER_ADDR_CAP} 上限。等转入 PoQ-Stake 后再挖（先抵押）。"
            )
        # Issue 4：bootstrap 期也走 VRF（如果候选集非空）
        miners_map = chain.bootstrap_miners_map()
        stake_map = chain.stake_map()
        expected = select_bootstrap_proposer(
            cur_slot, miners_map, BOOTSTRAP_PER_ADDR_CAP, stake_map
        )
        if expected is not None and expected != addr:
            raise RuntimeError(
                f"bootstrap slot {cur_slot} VRF 选中的是 0x{expected.hex()}，不是你。"
                f"等下一个 slot（候选集 {len(miners_map) + len(stake_map)} 个地址）。"
            )
        if verbose:
            if expected is None:
                print(f"[propose] bootstrap slot {cur_slot}：候选集为空（首次挖矿期），开放抢占")
            else:
                print(f"[propose] bootstrap slot {cur_slot}：VRF 选中你（候选 "
                      f"{len(miners_map) + len(stake_map)} 个地址中）")
            print(f"  高度 {chain.height+1}/{BOOTSTRAP_OPEN_BLOCKS}, 你已挖 {mined}/{BOOTSTRAP_PER_ADDR_CAP}")
        return cur_slot

    # PoQ-Stake 期
    s = chain.staked_of(addr)
    if s < MIN_STAKE:
        raise RuntimeError(
            f"抵押 {s/10**8:.4f} BTCQ < 最低 {MIN_STAKE/10**8:.4f} BTCQ。先用 scripts/stake.py 抵押。"
        )
    stake_map = chain.stake_map()
    expected = select_proposer_for_slot(cur_slot, stake_map)
    if expected is None:
        raise RuntimeError("全网无合格 staker（不应发生）")
    if expected != addr:
        next_my_slot = _next_my_slot(cur_slot, addr, stake_map)
        wait = slot_start_timestamp(next_my_slot) - now_ts if next_my_slot else None
        raise RuntimeError(
            f"slot {cur_slot} 选中的是 0x{expected.hex()}，不是你。"
            + (f" 你下一个 slot 估计是 {next_my_slot}（约 {wait}s 后）。" if next_my_slot else "")
        )
    if verbose:
        print(f"[propose] ✓ slot {cur_slot}: 你被 VRF 选中（抵押 {s/10**8:.4f} BTCQ）")
    return cur_slot


def _next_my_slot(cur_slot: int, addr: bytes, stake_map: dict, lookahead: int = 200) -> int | None:
    """前瞻 lookahead 个 slot，返回下一个属于我的 slot 编号；找不到返回 None。"""
    for s in range(cur_slot + 1, cur_slot + 1 + lookahead):
        if select_proposer_for_slot(s, stake_map) == addr:
            return s
    return None


def propose_classical_simulator(
    chain_dir: str | Path,
    wallet: Wallet,
    n_qubits: int = CIRCUIT_N_QUBITS,
    depth: int = CIRCUIT_DEPTH,
    n_samples: int = CIRCUIT_N_SAMPLES,
    verbose: bool = True,
    mempool: Optional[Mempool] = None,
    skip_stake_check: bool = False,
):
    """经典模拟出块（dev 用，不连量子机）。"""
    chain = Chain(chain_dir)
    head = chain.head
    assert head is not None
    cur_slot = _check_eligible(chain, wallet, verbose) if not skip_stake_check else slot_at(int(time.time()))
    prev_hash = head.block_hash()
    height = head.height + 1
    difficulty = chain.next_difficulty()
    if verbose:
        print(f"[propose] head={head.height}, slot {cur_slot}, prev={prev_hash.hex()[:16]}...")
        print(f"[propose] difficulty target = {difficulty:.4f}")

    seed = _circuit_seed(prev_hash, cur_slot, wallet.address_bytes)
    desc = build_circuit_description(seed, n_qubits, depth)
    state = simulate_statevector(desc)
    rng = np.random.default_rng(int.from_bytes(os.urandom(8), "big"))
    probs = np.abs(state)**2
    samples = rng.choice(2**n_qubits, size=n_samples, replace=True, p=probs / probs.sum())
    samples = [int(x) for x in samples]
    f_xeb = linear_xeb(state, samples, n_qubits)
    if verbose:
        print(f"[propose] simulator XEB = {f_xeb:.4f} (need ≥ {difficulty:.4f})")
    if f_xeb < difficulty:
        raise RuntimeError(f"模拟 XEB={f_xeb:.4f} 未达阈值，难度过高？")
    return _finalize_block(chain, wallet, prev_hash, head, height, cur_slot,
                            n_qubits, depth, n_samples, samples, f_xeb,
                            difficulty, verbose, mempool=mempool)


def propose_ibm_quantum(
    chain_dir: str | Path,
    wallet: Wallet,
    backend_name: str = "ibm_marrakesh",
    shots: int = CIRCUIT_N_SAMPLES,
    n_qubits: int = CIRCUIT_N_QUBITS,
    depth: int = CIRCUIT_DEPTH,
    verbose: bool = True,
    mempool: Optional[Mempool] = None,
    skip_stake_check: bool = False,
):
    """真量子机出块。每次烧 ~1 秒配额。"""
    from qiskit import transpile
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

    chain = Chain(chain_dir)
    head = chain.head
    assert head is not None
    cur_slot = _check_eligible(chain, wallet, verbose) if not skip_stake_check else slot_at(int(time.time()))
    prev_hash = head.block_hash()
    height = head.height + 1
    difficulty = chain.next_difficulty()

    if verbose:
        print(f"[propose] connecting to {backend_name}...")
    svc = QiskitRuntimeService()
    backend = svc.backend(backend_name)
    if verbose:
        print(f"[propose] backend ready, queue={backend.status().pending_jobs}")
        print(f"[propose] slot {cur_slot}, difficulty target = {difficulty:.4f}")

    seed = _circuit_seed(prev_hash, cur_slot, wallet.address_bytes)
    desc = build_circuit_description(seed, n_qubits, depth)
    qc = to_qiskit(desc, measure=True)

    if verbose:
        print(f"[propose] transpiling 量子证明电路 (n={n_qubits}, depth={depth})...")
    trans = transpile(qc, backend=backend, optimization_level=3, seed_transpiler=42)
    n_2q = sum(1 for g in trans.data if g.operation.num_qubits == 2)
    if verbose:
        print(f"  transpiled depth={trans.depth()}, 2q gates={n_2q}")

    sampler = Sampler(mode=backend)
    t0 = time.time()
    job = sampler.run([trans], shots=shots)
    if verbose:
        print(f"  job_id={job.job_id()}, waiting...")
    result = job.result()
    interface_time = time.time() - t0
    data = result[0].data
    reg_name = list(data.keys())[0]
    counts = getattr(data, reg_name).get_counts()
    samples = _samples_from_counts(counts, n_qubits, shots)
    if verbose:
        print(f"  量子接口总耗时: {interface_time:.1f}s（含队列+网络+执行）")

    if verbose:
        print(f"  classical-verifying XEB on n={n_qubits}...")
    t0 = time.time()
    probs = amplitudes_for_samples(desc, samples)
    f_xeb = linear_xeb_from_probs(probs, n_qubits)
    verify_time = time.time() - t0
    if verbose:
        print(f"  XEB = {f_xeb:.4f}  (need ≥ {difficulty:.4f})  [verify {verify_time:.1f}s]")
    if f_xeb < difficulty:
        raise RuntimeError(f"量子证明 XEB={f_xeb:.4f} 未达阈值，硬件保真度问题？")
    return _finalize_block(chain, wallet, prev_hash, head, height, cur_slot,
                            n_qubits, depth, shots, samples, f_xeb,
                            difficulty, verbose, mempool=mempool)


def _select_valid_transactions(chain: Chain, mempool: Optional[Mempool],
                                max_count: int = 1000) -> List[Transaction]:
    """从 mempool 选出可被合法打包的交易（同时支持 transfer/stake/unstake）。"""
    if mempool is None or len(mempool) == 0:
        return []
    selected: List[Transaction] = []
    pending_balance: dict = {}
    pending_nonce: dict = {}
    pending_stake: dict = {}

    def _bal(addr):
        return pending_balance.get(addr, chain.balance_of(addr))
    def _nonce(addr):
        return pending_nonce.get(addr, chain.nonce_of(addr))
    def _stake(addr):
        return pending_stake.get(addr, chain.staked_of(addr))

    for tx in mempool.take(max_count * 4):
        if not tx.verify_signature():
            continue
        if tx.nonce != _nonce(tx.sender):
            continue
        if tx.amount < 0:
            continue

        if tx.kind == TX_TRANSFER:
            if _bal(tx.sender) < tx.amount: continue
            pending_balance[tx.sender] = _bal(tx.sender) - tx.amount
            pending_balance[tx.recipient] = _bal(tx.recipient) + tx.amount
        elif tx.kind == TX_STAKE:
            if tx.recipient != STAKE_VAULT: continue
            if _bal(tx.sender) < tx.amount: continue
            pending_balance[tx.sender] = _bal(tx.sender) - tx.amount
            pending_stake[tx.sender] = _stake(tx.sender) + tx.amount
        elif tx.kind == TX_UNSTAKE:
            if tx.recipient != STAKE_VAULT: continue
            if _stake(tx.sender) < tx.amount: continue
            pending_stake[tx.sender] = _stake(tx.sender) - tx.amount
            # 余额不立即增加（冷却期）
        else:
            continue   # 未知 kind 拒收

        pending_nonce[tx.sender] = tx.nonce + 1
        selected.append(tx)
        if len(selected) >= max_count:
            break
    return selected


def _finalize_block(chain, wallet, prev_hash, head, height, slot, n_qubits, depth,
                    n_samples, samples, f_xeb, difficulty, verbose,
                    mempool: Optional[Mempool] = None):
    samples_root = compute_samples_root(samples, n_qubits)
    txs = _select_valid_transactions(chain, mempool)
    tx_root = compute_transactions_root(txs)
    block = Block(
        version           = PROTOCOL_VERSION,
        height            = height,
        slot              = slot,
        prev_hash         = prev_hash,
        timestamp         = int(time.time()),
        proposer_address  = wallet.address_bytes,
        n_qubits          = n_qubits,
        depth             = depth,
        n_samples         = n_samples,
        difficulty        = difficulty,
        samples_root      = samples_root,
        xeb_score         = f_xeb,
        samples           = samples,
        transactions      = txs,
        transactions_root = tx_root,
    )
    block.proposer_signature = wallet.sign(block.block_hash())
    chain.append(block)
    if mempool is not None and txs:
        mempool.remove_included(txs)
    if verbose:
        from .block import block_reward
        print(f"\n✅ 区块出块成功！")
        print(f"   高度:    {block.height}    slot: {block.slot}")
        print(f"   哈希:    0x{block.block_hash().hex()}")
        print(f"   出块人:  {wallet.address_hex()}")
        print(f"   XEB:     {f_xeb:.4f}")
        print(f"   奖励:    {block_reward(block.height)/10**8:.0f} BTCQ")
        print(f"   交易:    {len(txs)} 笔已打包")
    return block
