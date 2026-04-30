#!/usr/bin/env python3
"""挖一个区块。

用法:
    python scripts/mine.py --classical                  # 经典模拟（不烧配额，dev 用）
    python scripts/mine.py --quantum                    # 真量子机
    python scripts/mine.py --quantum --backend ibm_fez  # 指定后端
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qxeb.wallet import Wallet
from qxeb.miner import mine_classical_simulator, mine_ibm_quantum
from qxeb.mempool import Mempool


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--classical", action="store_true", help="经典模拟挖矿（dev 用）")
    parser.add_argument("--quantum", action="store_true", help="真量子机挖矿")
    parser.add_argument("--backend", default="ibm_marrakesh", help="IBM 后端名")
    parser.add_argument("--wallet", default="wallet.json", help="钱包文件路径")
    parser.add_argument("--chain", default="./chain_data", help="链数据目录")
    parser.add_argument("--max-attempts", type=int, default=20)
    parser.add_argument("--shots", type=int, default=4096)
    args = parser.parse_args()

    if not (args.classical ^ args.quantum):
        print("请指定 --classical 或 --quantum (二选一)")
        sys.exit(1)

    wallet_path = Path(args.wallet)
    if not wallet_path.exists():
        print(f"⚠️  钱包不存在：{wallet_path}。请先 python scripts/new_wallet.py")
        sys.exit(1)
    wallet = Wallet.load(wallet_path)
    print(f"矿工地址: {wallet.address_hex()}")

    mempool = Mempool(Path(args.chain) / "mempool.json")
    if len(mempool) > 0:
        print(f"mempool 有 {len(mempool)} 笔交易待打包")

    if args.classical:
        block = mine_classical_simulator(
            args.chain, wallet, max_attempts=args.max_attempts, mempool=mempool)
    else:
        block = mine_ibm_quantum(
            args.chain, wallet, backend_name=args.backend,
            max_attempts=args.max_attempts, shots=args.shots, mempool=mempool)

    print(f"\n区块文件: {args.chain}/blocks/{block.height:08d}.json")


if __name__ == "__main__":
    main()
