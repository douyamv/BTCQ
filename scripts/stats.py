#!/usr/bin/env python3
"""链统计：高度、总供应、当前难度、出块时间等。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qxeb.chain import Chain
from qxeb.constants import (
    COIN, TOTAL_SUPPLY, INITIAL_BLOCK_REWARD, HALVING_INTERVAL,
    GENESIS_TIMESTAMP, target_block_time_at, difficulty_window_at,
)


def main():
    chain = Chain("./chain_data")
    head = chain.head
    if head is None:
        print("链尚未初始化。运行 python scripts/init_chain.py")
        return

    now = int(time.time())
    secs_since_genesis = max(0, head.timestamp - GENESIS_TIMESTAMP)
    target_t = target_block_time_at(secs_since_genesis)
    window = difficulty_window_at(secs_since_genesis)
    next_difficulty = chain.next_difficulty()

    print("=" * 60)
    print("QXEB 链状态")
    print("=" * 60)
    print(f"  链高度:                {chain.height}")
    print(f"  最新区块哈希:          0x{head.block_hash().hex()[:32]}...")
    print(f"  最新区块时间:          {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(head.timestamp))}")
    print(f"  距创世:                {secs_since_genesis / 86400:.2f} 天")
    print()
    print(f"  当前阶段:              " + (
        "Bootstrap 启动期" if secs_since_genesis < 15*86400 else
        "Bootstrap 过渡期" if secs_since_genesis < 45*86400 else
        "稳态期（BTC 节奏）"))
    print(f"  目标出块时间:          {target_t:.0f} 秒")
    print(f"  当前难度调整窗口:      每 {window} 块")
    print(f"  下一区块难度（XEB ≥）: {next_difficulty:.4f}")
    print()
    print(f"  总供应:                {chain.total_supply_so_far() / COIN:,.4f} / {TOTAL_SUPPLY / COIN:,.0f} QXEB")
    print(f"  下一区块奖励:          {(INITIAL_BLOCK_REWARD >> ((chain.height + 1) // HALVING_INTERVAL)) / COIN:.4f} QXEB")
    print(f"  距下次减半:            {HALVING_INTERVAL - (chain.height + 1) % HALVING_INTERVAL} 块")
    print()
    print(f"  电路参数:              n={head.n_qubits}, depth={head.depth}, samples={head.n_samples}")
    print("=" * 60)


if __name__ == "__main__":
    main()
