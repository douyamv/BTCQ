#!/usr/bin/env python3
"""极简 faucet：从 ECOSYSTEM_FAUCET_ADDR 给指定地址转 BTCQ。

用法:
    python scripts/faucet.py --to 0xRECIPIENT [--amount 1] [--key faucet.key]

需要 faucet 私钥（由社区运营方持有，不公开）。
私钥派生方式：keccak256("BTCQ ecosystem faucet - early adopters, bounties, community grants.")
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcq.wallet import Wallet
from btcq.chain import Chain
from btcq.mempool import Mempool
from btcq.transaction import sign_transaction
from btcq.constants import COIN, ECOSYSTEM_FAUCET_ADDR


def parse_amount(s: str) -> int:
    if "." in s:
        whole, frac = s.split(".")
        frac = (frac + "0" * 8)[:8]
        return int(whole) * COIN + int(frac)
    return int(s) * COIN


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True, help="收款地址 0x...")
    p.add_argument("--amount", default="1", help="金额（BTCQ，默认 1）")
    p.add_argument("--key", default="faucet.key", help="faucet 私钥文件（hex）")
    p.add_argument("--chain", default="./chain_data")
    args = p.parse_args()

    key_path = Path(args.key)
    if not key_path.exists():
        print(f"⚠️  私钥文件不存在：{key_path}")
        print(f"   faucet 地址应为：0x{ECOSYSTEM_FAUCET_ADDR.hex()}")
        print(f"   运营者从安全位置获取对应私钥后存入 {key_path}")
        sys.exit(1)

    sk_hex = key_path.read_text().strip()
    if sk_hex.startswith("0x"):
        sk_hex = sk_hex[2:]
    wallet = Wallet(bytes.fromhex(sk_hex))

    if wallet.address_bytes != ECOSYSTEM_FAUCET_ADDR:
        print(f"❌ 私钥地址不匹配 ECOSYSTEM_FAUCET_ADDR")
        print(f"   你的私钥地址: {wallet.address_hex()}")
        print(f"   期望地址:     0x{ECOSYSTEM_FAUCET_ADDR.hex()}")
        sys.exit(1)

    chain = Chain(args.chain)
    mempool = Mempool(Path(args.chain) / "mempool.json")

    to_addr = args.to
    if to_addr.startswith("0x"): to_addr = to_addr[2:]
    recipient = bytes.fromhex(to_addr)
    amount = parse_amount(args.amount)
    nonce = chain.nonce_of(wallet.address_bytes)

    bal = chain.balance_of(wallet.address_bytes)
    if bal < amount:
        print(f"❌ Faucet 余额不足：{bal/COIN} BTCQ < {amount/COIN}")
        sys.exit(1)

    tx = sign_transaction(wallet, recipient, amount, nonce, kind="transfer")
    mempool.add(tx)
    print(f"✅ Faucet 转账已写入 mempool")
    print(f"   from:    0x{wallet.address_bytes.hex()}")
    print(f"   to:      0x{recipient.hex()}")
    print(f"   amount:  {amount/COIN} BTCQ")
    print(f"   tx:      0x{tx.tx_hash().hex()}")


if __name__ == "__main__":
    main()
