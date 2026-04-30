#!/usr/bin/env python3
"""查询地址余额。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qxeb.chain import Chain
from qxeb.constants import COIN


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/balance.py <地址>")
        sys.exit(1)
    addr = sys.argv[1]
    if addr.startswith("0x"):
        addr = addr[2:]
    addr_bytes = bytes.fromhex(addr)
    chain = Chain("./chain_data")
    bal = chain.balance_of(addr_bytes)
    print(f"地址:    0x{addr}")
    print(f"余额:    {bal / COIN:.8f} QXEB")
    print(f"已挖出:  {chain.total_supply_so_far() / COIN:.8f} / 21,000,000 QXEB")
    print(f"链高度:  {chain.height}")


if __name__ == "__main__":
    main()
