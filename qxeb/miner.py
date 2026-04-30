"""量子矿工：从 IBM Quantum 取真实采样，组装合法区块。

也支持经典模拟模式（--classical），用于 dev / 验证流程不烧配额。
"""

from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Optional, List

import numpy as np

from .constants import (
    PROTOCOL_VERSION, CIRCUIT_N_QUBITS, CIRCUIT_DEPTH, CIRCUIT_N_SAMPLES,
)
from .circuit import build_circuit_description, to_qiskit, simulate_statevector, amplitudes_for_samples
from .xeb import linear_xeb, linear_xeb_from_probs
from .block import Block, compute_samples_root, compute_transactions_root
from .chain import Chain
from .wallet import Wallet, keccak256
from .mempool import Mempool
from .transaction import Transaction


def _circuit_seed(prev_hash: bytes, nonce: int, miner_addr: bytes) -> bytes:
    return keccak256(prev_hash + nonce.to_bytes(8, "big") + miner_addr)


def _samples_from_counts(counts: dict, n_qubits: int, n_samples: int) -> List[int]:
    """把 Qiskit 的 counts 字典展开成长度为 n_samples 的整数列表。

    Qiskit 约定：counts 中的 bitstring 最左字符对应最高编号比特 q_{n-1}，
    最右字符对应 q_0。状态向量索引 k 的第 j 位也对应 q_j。
    所以 int(bitstr, 2) 直接得到与状态向量索引一致的整数。
    """
    expanded: List[int] = []
    for bitstr, c in counts.items():
        bitstr = bitstr.replace(" ", "")
        v = int(bitstr, 2)
        expanded.extend([v] * c)
    if len(expanded) > n_samples:
        expanded = expanded[:n_samples]
    elif len(expanded) < n_samples:
        # 极少出现：shots 对齐
        last = expanded[-1] if expanded else 0
        expanded += [last] * (n_samples - len(expanded))
    return expanded


def mine_classical_simulator(
    chain_dir: str | Path,
    wallet: Wallet,
    max_attempts: int = 1000,
    n_qubits: int = CIRCUIT_N_QUBITS,
    depth: int = CIRCUIT_DEPTH,
    n_samples: int = CIRCUIT_N_SAMPLES,
    verbose: bool = True,
    mempool: Optional[Mempool] = None,
):
    """
    经典模拟挖矿（用于本地开发，不连量子机）。
    通过对完美状态向量直接采样模拟"理想量子矿工"。

    n>31 在常规机器上会 OOM —— 这正是 QXEB 设计目的（经典挖不动）。
    """
    if n_qubits > 31:
        raise MemoryError(
            f"n={n_qubits} 状态向量需 {(1 << n_qubits) * 16 // 1024**3} GB 内存，"
            f"远超常规机器。这正是 QXEB 设计目的——n>31 必须用量子机挖矿（--quantum）。"
        )
    chain = Chain(chain_dir)
    head = chain.head
    assert head is not None, "请先初始化链：python -m scripts.init_chain"
    prev_hash = head.block_hash()
    difficulty = chain.next_difficulty()

    if verbose:
        print(f"[mine] head height={head.height} prev_hash={prev_hash.hex()[:16]}...")
        print(f"[mine] difficulty target = {difficulty:.4f}")

    rng = np.random.default_rng(int.from_bytes(os.urandom(8), "big"))

    for attempt in range(max_attempts):
        nonce = rng.integers(0, 2**63)
        seed = _circuit_seed(prev_hash, int(nonce), wallet.address_bytes)
        desc = build_circuit_description(seed, n_qubits, depth)
        state = simulate_statevector(desc)
        probs = np.abs(state)**2
        # 从理想分布采样（这是"理想量子矿工"的对照）
        samples = rng.choice(2**n_qubits, size=n_samples, replace=True, p=probs / probs.sum())
        samples = [int(x) for x in samples]
        f_xeb = linear_xeb(state, samples, n_qubits)
        if verbose and attempt % 10 == 0:
            print(f"  attempt {attempt}: nonce={nonce} XEB={f_xeb:.4f}")
        if f_xeb >= difficulty:
            return _finalize_block(chain, wallet, prev_hash, head, int(nonce),
                                    n_qubits, depth, n_samples, samples, f_xeb,
                                    difficulty, verbose, mempool=mempool)
    raise RuntimeError(f"经典模拟挖矿 {max_attempts} 次未达到难度，请重试")


def mine_ibm_quantum(
    chain_dir: str | Path,
    wallet: Wallet,
    backend_name: str = "ibm_marrakesh",
    max_attempts: int = 5,
    shots: int = CIRCUIT_N_SAMPLES,
    n_qubits: int = CIRCUIT_N_QUBITS,
    depth: int = CIRCUIT_DEPTH,
    verbose: bool = True,
    mempool: Optional[Mempool] = None,
):
    """真量子机挖矿。每次 attempt 烧一次量子作业（约 0.5–1 秒配额）。"""
    from qiskit import transpile
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

    chain = Chain(chain_dir)
    head = chain.head
    assert head is not None
    prev_hash = head.block_hash()
    difficulty = chain.next_difficulty()

    if verbose:
        print(f"[mine] connecting to {backend_name}...")
    svc = QiskitRuntimeService()
    backend = svc.backend(backend_name)
    if verbose:
        print(f"[mine] backend ready, queue={backend.status().pending_jobs}")
        print(f"[mine] difficulty target = {difficulty:.4f}")

    for attempt in range(max_attempts):
        nonce = int.from_bytes(os.urandom(8), "big") % (2**63)
        seed = _circuit_seed(prev_hash, nonce, wallet.address_bytes)
        desc = build_circuit_description(seed, n_qubits, depth)
        qc = to_qiskit(desc, measure=True)

        if verbose:
            print(f"  attempt {attempt}: nonce={nonce}, transpiling...")
        trans = transpile(qc, backend=backend, optimization_level=3, seed_transpiler=42)
        n_2q = sum(1 for g in trans.data if g.operation.num_qubits == 2)
        if verbose:
            print(f"    transpiled depth={trans.depth()}, 2q gates={n_2q}")

        sampler = Sampler(mode=backend)
        job = sampler.run([trans], shots=shots)
        if verbose:
            print(f"    job_id={job.job_id()}, waiting...")
        result = job.result()
        counts = result[0].data.meas.get_counts()
        samples = _samples_from_counts(counts, n_qubits, shots)

        # 经典验证 XEB
        if verbose:
            print(f"    classical-verifying XEB on n={n_qubits} (可能数十秒到数分钟)...")
        probs = amplitudes_for_samples(desc, samples)
        f_xeb = linear_xeb_from_probs(probs, n_qubits)
        if verbose:
            print(f"    XEB = {f_xeb:.4f}  (need ≥ {difficulty:.4f})")
        if f_xeb >= difficulty:
            return _finalize_block(chain, wallet, prev_hash, head, nonce,
                                    n_qubits, depth, shots, samples, f_xeb,
                                    difficulty, verbose)
    raise RuntimeError(f"量子挖矿 {max_attempts} 次未达难度，请重试")


def _select_valid_transactions(chain: Chain, mempool: Optional[Mempool],
                                max_count: int = 1000) -> List[Transaction]:
    """从 mempool 选出可被合法打包的交易。

    校验：
      - 签名合法
      - sender nonce 严格等于当前账户 nonce + 同 sender 已选交易数
      - sender 余额扣减后仍 ≥ 0
    """
    if mempool is None or len(mempool) == 0:
        return []
    selected: List[Transaction] = []
    # 跟踪每个 sender 在本批次中的临时余额与 nonce
    pending_balance: dict = {}
    pending_nonce: dict = {}
    for tx in mempool.take(max_count * 4):  # 多取一些再筛
        if not tx.verify_signature():
            continue
        cur_nonce = pending_nonce.get(tx.sender, chain.nonce_of(tx.sender))
        if tx.nonce != cur_nonce:
            continue
        cur_bal = pending_balance.get(tx.sender, chain.balance_of(tx.sender))
        if cur_bal < tx.amount:
            continue
        # 接受
        selected.append(tx)
        pending_balance[tx.sender] = cur_bal - tx.amount
        pending_balance[tx.recipient] = pending_balance.get(
            tx.recipient, chain.balance_of(tx.recipient)) + tx.amount
        pending_nonce[tx.sender] = cur_nonce + 1
        if len(selected) >= max_count:
            break
    return selected


def _finalize_block(chain, wallet, prev_hash, head, nonce, n_qubits, depth,
                    n_samples, samples, f_xeb, difficulty, verbose,
                    mempool: Optional[Mempool] = None):
    samples_root = compute_samples_root(samples, n_qubits)
    txs = _select_valid_transactions(chain, mempool)
    tx_root = compute_transactions_root(txs)
    block = Block(
        version         = PROTOCOL_VERSION,
        height          = head.height + 1,
        prev_hash       = prev_hash,
        timestamp       = int(time.time()),
        miner_address   = wallet.address_bytes,
        n_qubits        = n_qubits,
        depth           = depth,
        n_samples       = n_samples,
        difficulty      = difficulty,
        nonce           = nonce,
        samples_root    = samples_root,
        xeb_score       = f_xeb,
        samples         = samples,
        transactions    = txs,
        transactions_root = tx_root,
    )
    block.miner_signature = wallet.sign(block.block_hash())
    chain.append(block)
    if mempool is not None and txs:
        mempool.remove_included(txs)
    if verbose:
        print(f"\n✅ 区块挖出！")
        print(f"   高度: {block.height}")
        print(f"   哈希: 0x{block.block_hash().hex()}")
        print(f"   XEB:  {f_xeb:.4f}")
        print(f"   奖励: 50 QXEB → {wallet.address_hex()}")
        print(f"   交易: {len(txs)} 笔已打包")
    return block
