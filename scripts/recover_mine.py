#!/usr/bin/env python3
"""从已完成但未被打包的 IBM 作业 ID 恢复挖矿。

用法: python scripts/recover_mine.py <job_id> <nonce>
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qxeb.wallet import Wallet, keccak256
from qxeb.chain import Chain
from qxeb.mempool import Mempool
from qxeb.circuit import build_circuit_description, amplitudes_for_samples
from qxeb.xeb import linear_xeb_from_probs
from qxeb.miner import _finalize_block
from qxeb.constants import CIRCUIT_N_QUBITS, CIRCUIT_DEPTH, CIRCUIT_N_SAMPLES, PROTOCOL_VERSION

from qiskit_ibm_runtime import QiskitRuntimeService


def main():
    if len(sys.argv) < 3:
        print("用法: python scripts/recover_mine.py <job_id> <nonce>")
        sys.exit(1)
    job_id = sys.argv[1]
    nonce = int(sys.argv[2])

    wallet = Wallet.load("wallet.json")
    chain = Chain("./chain_data")
    mempool = Mempool("./chain_data/mempool.json")
    head = chain.head
    prev_hash = head.block_hash()
    difficulty = chain.next_difficulty()

    print(f"恢复作业 {job_id}, nonce={nonce}")
    svc = QiskitRuntimeService()
    job = svc.job(job_id)
    print(f"  status: {job.status()}")
    result = job.result()
    data = result[0].data
    # 自动找到经典寄存器（无论叫 meas / c / 啥）
    regs = list(data.keys())
    print(f"  classical regs: {regs}")
    counts = getattr(data, regs[0]).get_counts()

    # 展开成样本
    samples = []
    for bitstr, c in counts.items():
        bitstr = bitstr.replace(" ", "")
        v = int(bitstr, 2)
        samples.extend([v] * c)
    if len(samples) > CIRCUIT_N_SAMPLES:
        samples = samples[:CIRCUIT_N_SAMPLES]
    print(f"  samples: {len(samples)}")

    # 构造同样的电路并经典验证 XEB
    seed = keccak256(prev_hash + nonce.to_bytes(8, "big") + wallet.address_bytes)
    desc = build_circuit_description(seed, CIRCUIT_N_QUBITS, CIRCUIT_DEPTH)
    print(f"  classical-verifying XEB on n={CIRCUIT_N_QUBITS}（Aer MPS, 可能数分钟）...")
    t0 = time.time()
    probs = amplitudes_for_samples(desc, samples)
    f_xeb = linear_xeb_from_probs(probs, CIRCUIT_N_QUBITS)
    print(f"  XEB = {f_xeb:.4f}  (need ≥ {difficulty:.4f})  ({time.time()-t0:.1f}s)")

    if f_xeb < difficulty:
        print(f"❌ XEB 未达难度，作废")
        sys.exit(1)

    block = _finalize_block(chain, wallet, prev_hash, head, nonce,
                            CIRCUIT_N_QUBITS, CIRCUIT_DEPTH, len(samples),
                            samples, f_xeb, difficulty, verbose=True,
                            mempool=mempool)
    print(f"\n区块文件: chain_data/blocks/{block.height:08d}.json")


if __name__ == "__main__":
    main()
