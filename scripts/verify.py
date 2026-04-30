#!/usr/bin/env python3
"""验证整条链。"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcq.verifier import verify_chain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", default="./chain_data")
    parser.add_argument("--no-xeb", action="store_true",
                        help="跳过 XEB 重计算（只验签名/结构，快但不安全）")
    args = parser.parse_args()
    ok, msg = verify_chain(args.chain, recompute_xeb=not args.no_xeb)
    print(("✅ " if ok else "❌ ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
