#!/usr/bin/env python3
"""启动 BTCQ P2P 节点。

用法:
    python scripts/node.py                          # 默认端口 8333
    python scripts/node.py --port 8334
    python scripts/node.py --peers http://1.2.3.4:8333,http://5.6.7.8:8333
    python scripts/node.py --port 8333 --public-url http://my.host:8333
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcq.node import Node, DEFAULT_PORT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--chain", default="./chain_data")
    p.add_argument("--peers", default="", help="逗号分隔的对等节点 URL")
    p.add_argument("--public-url", default=None, help="本节点对外可访问的 URL（让 peer 反向连接）")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    seeds = [s.strip() for s in args.peers.split(",") if s.strip()]
    node = Node(
        chain_dir=args.chain,
        port=args.port,
        seeds=seeds,
        public_url=args.public_url,
        verbose=not args.quiet,
    )
    node.start()


if __name__ == "__main__":
    main()
