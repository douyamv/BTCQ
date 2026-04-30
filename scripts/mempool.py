#!/usr/bin/env python3
"""查看本地 mempool 中的待打包交易。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qxeb.mempool import Mempool
from qxeb.constants import COIN


def main():
    mp = Mempool("./chain_data/mempool.json")
    if len(mp) == 0:
        print("mempool 为空")
        return
    print(f"待打包交易：{len(mp)} 笔")
    print("-" * 70)
    for i, tx in enumerate(mp.all()):
        print(f"  [{i}] {tx.amount/COIN:.4f} QXEB")
        print(f"      from:  0x{tx.sender.hex()}")
        print(f"      to:    0x{tx.recipient.hex()}")
        print(f"      nonce: {tx.nonce}")
        print(f"      hash:  0x{tx.tx_hash().hex()[:32]}...")
        print(f"      sig:   {'✓' if tx.verify_signature() else '✗ INVALID'}")


if __name__ == "__main__":
    main()
