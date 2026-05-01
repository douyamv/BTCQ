#!/usr/bin/env python3
"""发起一笔转账：签名后写入本地 mempool，等待矿工打包。

用法:
    python scripts/send.py --to 0xRECIPIENT --amount 5
    python scripts/send.py --to 0xRECIPIENT --amount 0.5 --wallet alice.json

amount 单位是 BTCQ（小数允许，最多 8 位）。
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcq.wallet import Wallet
from btcq.chain import Chain
from btcq.mempool import Mempool
from btcq.constants import COIN


def parse_amount(s: str) -> int:
    """'5' 或 '0.5' → 原子单位整数（按 COIN 精度补齐）。"""
    decimals = len(str(COIN)) - 1
    if "." in s:
        whole, frac = s.split(".")
        frac = (frac + "0" * decimals)[:decimals]
        return int(whole or "0") * COIN + int(frac or "0")
    return int(s) * COIN


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True, help="收款方地址 (0x...)")
    p.add_argument("--amount", required=True, help="金额（BTCQ）")
    p.add_argument("--wallet", default="wallet.json")
    p.add_argument("--chain", default="./chain_data")
    p.add_argument("--mempool", default="./chain_data/mempool.json")
    args = p.parse_args()

    wallet = Wallet.load(args.wallet)
    chain = Chain(args.chain)
    mempool = Mempool(args.mempool)

    to_addr = args.to
    if to_addr.startswith("0x"):
        to_addr = to_addr[2:]
    recipient = bytes.fromhex(to_addr)
    if len(recipient) != 20:
        print("❌ 收款地址必须是 20 字节十六进制")
        sys.exit(1)

    amount = parse_amount(args.amount)
    bal = chain.balance_of(wallet.address_bytes)
    if bal < amount:
        print(f"❌ 余额不足：你有 {bal/COIN} BTCQ，要发 {amount/COIN} BTCQ")
        sys.exit(1)

    nonce = chain.nonce_of(wallet.address_bytes) + sum(
        1 for t in mempool.all() if t.sender == wallet.address_bytes
    )
    tx = wallet.sign_transaction(recipient, amount, nonce)
    mempool.add(tx)

    print(f"✅ 交易已签名并写入 mempool")
    print(f"   tx_hash:   0x{tx.tx_hash().hex()}")
    print(f"   from:      {wallet.address_hex()}")
    print(f"   to:        0x{recipient.hex()}")
    print(f"   amount:    {amount/COIN} BTCQ")
    print(f"   nonce:     {nonce}")
    print(f"   mempool 中待打包交易数: {len(mempool)}")
    print()
    print("   等下一个区块被挖出时矿工会自动打包它（如果你自己挖，运行 mine.py）")


if __name__ == "__main__":
    main()
