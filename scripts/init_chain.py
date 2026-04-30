#!/usr/bin/env python3
"""初始化链：写入创世区块。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcq.chain import Chain
from btcq.genesis import make_genesis, genesis_message


def main():
    data_dir = Path("./chain_data")
    if (data_dir / "blocks" / "00000000.json").exists():
        print(f"链已存在于 {data_dir}/blocks/，跳过创世。")
        return
    g = make_genesis()
    chain = Chain(data_dir)
    chain.append(g)
    print(f"✅ 创世区块已写入 {data_dir}/blocks/00000000.json")
    print(f"   block_hash = 0x{g.block_hash().hex()}")
    print(f"   message    = {genesis_message()}")


if __name__ == "__main__":
    main()
