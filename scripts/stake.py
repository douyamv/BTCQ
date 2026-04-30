#!/usr/bin/env python3
"""抵押 BTCQ：发起 stake / unstake 交易并写入 mempool。

用法:
    python scripts/stake.py --amount 5            # 抵押 5 BTCQ
    python scripts/stake.py --unstake --amount 5  # 申请解抵押 5 BTCQ
    python scripts/stake.py --status              # 查看自己的抵押状态
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcq.wallet import Wallet
from btcq.chain import Chain
from btcq.mempool import Mempool
from btcq.transaction import sign_transaction
from btcq.constants import COIN, MIN_STAKE, UNSTAKE_DELAY_BLOCKS
from btcq.stake import STAKE_VAULT, TX_STAKE, TX_UNSTAKE


def parse_amount(s: str) -> int:
    if "." in s:
        whole, frac = s.split(".")
        frac = (frac + "0" * 8)[:8]
        return int(whole) * COIN + int(frac)
    return int(s) * COIN


def show_status(chain: Chain, wallet: Wallet):
    addr = wallet.address_bytes
    print(f"地址:      {wallet.address_hex()}")
    print(f"流动余额:  {chain.balance_of(addr)/COIN:.8f} BTCQ")
    print(f"已抵押:    {chain.staked_of(addr)/COIN:.8f} BTCQ")
    print(f"冷却中:    {chain.cooling_of(addr)/COIN:.8f} BTCQ  (解抵押后 {UNSTAKE_DELAY_BLOCKS} 块释放)")
    print(f"总资产:    {chain.total_balance_of(addr)/COIN:.8f} BTCQ")
    print(f"出块资格:  {'✅' if chain.staked_of(addr) >= MIN_STAKE else '❌（需 ' + str(MIN_STAKE/COIN) + ' BTCQ）'}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--amount", help="金额（BTCQ）")
    p.add_argument("--unstake", action="store_true", help="申请解抵押（默认是抵押）")
    p.add_argument("--status", action="store_true", help="查看抵押状态")
    p.add_argument("--wallet", default="wallet.json")
    p.add_argument("--chain", default="./chain_data")
    p.add_argument("--mempool", default="./chain_data/mempool.json")
    args = p.parse_args()

    wallet = Wallet.load(args.wallet)
    chain = Chain(args.chain)
    mempool = Mempool(args.mempool)

    if args.status or not args.amount:
        show_status(chain, wallet)
        return

    amount = parse_amount(args.amount)
    nonce = chain.nonce_of(wallet.address_bytes) + sum(
        1 for t in mempool.all() if t.sender == wallet.address_bytes
    )

    if args.unstake:
        s = chain.staked_of(wallet.address_bytes)
        if s < amount:
            print(f"❌ 抵押不足：你抵押了 {s/COIN} BTCQ，要解 {amount/COIN}")
            sys.exit(1)
        tx = sign_transaction(wallet, STAKE_VAULT, amount, nonce, kind=TX_UNSTAKE)
        action = "解抵押"
    else:
        bal = chain.balance_of(wallet.address_bytes)
        if bal < amount:
            print(f"❌ 余额不足：你有 {bal/COIN} BTCQ，要抵押 {amount/COIN}")
            sys.exit(1)
        tx = sign_transaction(wallet, STAKE_VAULT, amount, nonce, kind=TX_STAKE)
        action = "抵押"

    mempool.add(tx)
    print(f"✅ {action}交易已写入 mempool")
    print(f"   tx_hash: 0x{tx.tx_hash().hex()}")
    print(f"   amount:  {amount/COIN} BTCQ")
    print(f"   nonce:   {nonce}")
    print(f"\n下一个区块出块时，矿工会将此交易打包上链。")
    if args.unstake:
        print(f"⏳ 解抵押需等 {UNSTAKE_DELAY_BLOCKS} 块（≈ {UNSTAKE_DELAY_BLOCKS*60//60} 分钟@bootstrap）冷却才回到流动余额")


if __name__ == "__main__":
    main()
