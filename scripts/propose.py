#!/usr/bin/env python3
"""出块（PoQ-Stake）。

用法:
    python scripts/propose.py --classical                  # 经典模拟（dev，不烧配额）
    python scripts/propose.py --quantum                    # 真量子机
    python scripts/propose.py --quantum --backend ibm_fez

PoQ-Stake 出块前会验证你抵押 ≥ MIN_STAKE，但 bootstrap 期（前 144 块）开放挖矿无需抵押。
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcq.wallet import Wallet
from btcq.proposer import propose_classical_simulator, propose_ibm_quantum
from btcq.mempool import Mempool


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--classical", action="store_true", help="经典模拟（dev 用）")
    parser.add_argument("--quantum", action="store_true", help="真量子机")
    parser.add_argument("--backend", default="ibm_marrakesh", help="IBM 后端名")
    parser.add_argument("--wallet", default="wallet.json")
    parser.add_argument("--chain", default="./chain_data")
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--skip-stake-check", action="store_true",
                        help="跳过抵押检查（仅 dev 用）")
    args = parser.parse_args()

    if not (args.classical ^ args.quantum):
        print("请指定 --classical 或 --quantum (二选一)")
        sys.exit(1)

    wallet_path = Path(args.wallet)
    if not wallet_path.exists():
        print(f"⚠️  钱包不存在：{wallet_path}。请先 python scripts/new_wallet.py")
        sys.exit(1)
    wallet = Wallet.load(wallet_path)
    print(f"出块人地址: {wallet.address_hex()}")

    mempool = Mempool(Path(args.chain) / "mempool.json")
    if len(mempool) > 0:
        print(f"mempool 有 {len(mempool)} 笔交易待打包")

    if args.classical:
        block = propose_classical_simulator(
            args.chain, wallet, mempool=mempool,
            skip_stake_check=args.skip_stake_check)
    else:
        block = propose_ibm_quantum(
            args.chain, wallet, backend_name=args.backend, shots=args.shots,
            mempool=mempool, skip_stake_check=args.skip_stake_check)

    print(f"\n区块文件: {args.chain}/blocks/{block.height:08d}.json")


if __name__ == "__main__":
    main()
