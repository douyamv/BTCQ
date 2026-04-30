#!/usr/bin/env python3
"""生成一个新钱包。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qxeb.wallet import Wallet


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "wallet.json")
    if out.exists():
        print(f"⚠️  {out} 已存在，覆盖请先手动删除。")
        sys.exit(1)
    w = Wallet.generate()
    w.save(out)
    print(f"✅ 新钱包已保存到 {out}")
    print(f"   地址: {w.address_hex()}")
    print(f"   ⚠️ 私钥保存在文件中，请妥善备份！")


if __name__ == "__main__":
    main()
