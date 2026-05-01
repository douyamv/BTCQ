#!/usr/bin/env python3
"""手动管理对等节点 / 查询远端节点。

用法:
    python scripts/peer.py info http://1.2.3.4:8333
    python scripts/peer.py add http://1.2.3.4:8333 http://5.6.7.8:8333
    python scripts/peer.py sync http://1.2.3.4:8333  # 从远端节点全量同步
"""

import sys
import requests


def cmd_info(url):
    r = requests.get(url + "/info", timeout=8)
    print(r.json())


def cmd_add(my_url, peer_url):
    r = requests.post(my_url + "/peers", json={"url": peer_url}, timeout=5)
    print(r.json())


def cmd_sync(remote, local="http://43.136.28.125:8333"):
    rem = requests.get(remote + "/info", timeout=8).json()
    loc = requests.get(local + "/info", timeout=8).json()
    print(f"远端高度 {rem['height']}, 本地高度 {loc['height']}")
    if rem['height'] <= loc['height']:
        print("无需同步")
        return
    # 让本地节点把远端加入 peer 列表，下次自动同步
    requests.post(local + "/peers", json={"url": remote}, timeout=5)
    print(f"已把 {remote} 加入本地节点 peer 列表，等下次同步周期")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "info":
        cmd_info(sys.argv[2])
    elif cmd == "add":
        cmd_add(sys.argv[2], sys.argv[3])
    elif cmd == "sync":
        local = sys.argv[3] if len(sys.argv) > 3 else "http://43.136.28.125:8333"
        cmd_sync(sys.argv[2], local)
    else:
        print("未知命令")


if __name__ == "__main__":
    main()
