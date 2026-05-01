#!/usr/bin/env python3
"""极简区块浏览器：打印链关键状态与最近区块。

用法:
    python scripts/explorer.py
    python scripts/explorer.py --tail 10        # 最近 10 块详情
    python scripts/explorer.py --remote http://43.136.28.125:8333  # 远程节点
"""

import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def from_local(args):
    from btcq.chain import Chain
    from btcq.constants import (
        COIN, TOTAL_SUPPLY, GENESIS_TIMESTAMP, BOOTSTRAP_OPEN_BLOCKS,
        target_block_time_at, slot_at,
    )
    chain = Chain(args.chain)
    head = chain.head
    if head is None:
        print("链未初始化")
        return
    secs = max(0, head.timestamp - GENESIS_TIMESTAMP)
    print("=" * 60)
    print(f" BTCQ 区块浏览器 · 高度 {chain.height}")
    print("=" * 60)
    print(f"  当前 slot:        {slot_at(int(time.time()))}")
    print(f"  最新区块 slot:    {head.slot}")
    print(f"  最新哈希:          0x{head.block_hash().hex()[:32]}...")
    print(f"  state_root:       0x{head.state_root.hex()[:32]}...")
    print(f"  距创世:            {secs/86400:.2f} 天")
    print(f"  目标出块时间:      {target_block_time_at(secs):.0f} 秒")
    print()
    print(f"  下一区块奖励:      {chain.head.height < BOOTSTRAP_OPEN_BLOCKS and 50 or '...'} BTCQ")
    print(f"  总供应:            {chain.total_supply_so_far()/COIN:,.4f} / {TOTAL_SUPPLY/COIN:,.0f} BTCQ")
    print(f"  总抵押:            {chain.total_stake()/COIN:,.4f} BTCQ")
    print(f"  总交易数:          {chain.total_tx_count()}")
    print(f"  Mempool:           （需查节点）")
    print(f"  罚没记录:          {len(chain.slash_records())} 条 / 共 {chain.total_slashed()/COIN:,.4f} BTCQ")
    print()
    print(f"=== 最近 {args.tail} 块 ===")
    for h in range(max(0, chain.height - args.tail + 1), chain.height + 1):
        b = chain.get(h)
        ts = time.strftime('%m-%d %H:%M:%S', time.localtime(b.timestamp))
        print(f"  #{h:>4d}  slot {b.slot:>6d}  {ts}  XEB {b.xeb_score:>6.2f}  "
              f"{len(b.transactions):>2d} tx  proposer 0x{b.proposer_address.hex()[:8]}...")


def from_remote(args):
    import requests
    base = args.remote.rstrip('/')
    info = requests.get(f"{base}/info", timeout=8).json()
    print("=" * 60)
    print(f" BTCQ 区块浏览器 · {args.remote} · 高度 {info['height']}")
    print("=" * 60)
    print(f"  user_agent:       {info.get('user_agent', '')}")
    print(f"  最新哈希:          {info['head_hash'][:48]}...")
    print(f"  最新 slot:        {info.get('head_slot', '?')}")
    print(f"  总供应:            {info['total_supply']/COIN:,.4f} BTCQ")
    print(f"  总抵押:            {info['total_stake']/COIN:,.4f} BTCQ")
    print(f"  Mempool:           {info.get('mempool_size', '?')} 笔待打包")
    print(f"  Peer 数:           {len(info.get('peers', []))}")
    print(f"  罚没:              {info.get('slash_count', 0)} 条 / {info.get('total_slashed', 0)/COIN:,.4f} BTCQ")
    print()
    end = info['height']
    start = max(0, end - args.tail + 1)
    blocks = requests.get(f"{base}/blocks/range/{start}/{end}", timeout=15).json()
    print(f"=== 最近 {len(blocks)} 块 ===")
    for b in blocks:
        ts = time.strftime('%m-%d %H:%M:%S', time.localtime(b['timestamp']))
        print(f"  #{b['height']:>4d}  slot {b['slot']:>6d}  {ts}  XEB {b['xeb_score']:>6.2f}  "
              f"{len(b['transactions']):>2d} tx  proposer {b['proposer_address'][:10]}...")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chain", default="./chain_data")
    p.add_argument("--remote", help="远端节点 URL，例如 http://43.136.28.125:8333")
    p.add_argument("--tail", type=int, default=10)
    args = p.parse_args()
    if args.remote:
        from_remote(args)
    else:
        from_local(args)


if __name__ == "__main__":
    main()
