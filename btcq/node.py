"""BTCQ P2P 节点：HTTP REST + 后台同步线程。

v0.1 网络层最小实现：
* Flask HTTP 服务器，监听端口（默认 8333）
* 端点：/info, /blocks/{h}, /blocks/range/{a}/{b}, /mempool, /tx, /block, /peers
* 后台线程：每 N 秒拉取所有 peer 的最新高度，落后就追同步
* 新区块/交易在收到时主动广播给所有 peer
* 种子节点：硬编码 + 用户可加

后续 (v0.5+)：换 libp2p、断线重连优化、blockchain header-first sync 等。
"""

from __future__ import annotations
import json
import time
import threading
import logging
from pathlib import Path
from typing import List, Set, Optional, Dict
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify

from .block import Block
from .chain import Chain
from .mempool import Mempool
from .transaction import Transaction
from .verifier import verify_block

logger = logging.getLogger("btcq.node")

# 硬编码种子节点（启动时连接发现其他对等节点）
DEFAULT_SEEDS = [
    # "http://seed1.btcq.network:8333",
    # 暂留空。社区运营者可以在此处加入永久种子节点
]

DEFAULT_PORT = 8333
SYNC_INTERVAL_SEC = 15
PEER_TIMEOUT_SEC  = 5
USER_AGENT        = "btcq-node/0.1.1"


class Node:
    def __init__(self, chain_dir: str | Path, port: int = DEFAULT_PORT,
                 seeds: List[str] = None, public_url: Optional[str] = None,
                 verbose: bool = True):
        self.chain_dir = Path(chain_dir)
        self.port = port
        self.public_url = public_url    # 自报的 URL（可被其他 peer 反向连接）
        self.verbose = verbose
        self.chain = Chain(self.chain_dir)
        self.mempool = Mempool(self.chain_dir / "mempool.json")
        self.peers: Set[str] = set(seeds or DEFAULT_SEEDS)
        self.peers_seen: Dict[str, dict] = {}  # url → {last_seen, height}
        self.app = Flask(__name__)
        self._setup_routes()
        self._stop = threading.Event()

    # ============ HTTP routes ============
    def _setup_routes(self):
        a = self.app

        @a.get("/info")
        def info():
            head = self.chain.head
            return jsonify({
                "version":     "v0.1.1",
                "user_agent":  USER_AGENT,
                "chain":       "btcq",
                "height":      self.chain.height,
                "head_hash":   "0x" + (head.block_hash().hex() if head else "0" * 64),
                "n_qubits":    head.n_qubits if head else 0,
                "depth":       head.depth if head else 0,
                "total_supply":self.chain.total_supply_so_far(),
                "total_stake": self.chain.total_stake(),
                "peers":       list(self.peers),
                "mempool_size":len(self.mempool),
                "public_url":  self.public_url,
            })

        @a.get("/blocks/<int:h>")
        def get_block(h):
            if h < 0 or h > self.chain.height:
                return jsonify({"error": "out of range"}), 404
            return jsonify(self.chain.get(h).to_dict())

        @a.get("/blocks/range/<int:a_>/<int:b>")
        def get_range(a_, b):
            b = min(b, self.chain.height)
            if a_ > b:
                return jsonify([])
            blocks = [self.chain.get(h).to_dict() for h in range(a_, b + 1)]
            return jsonify(blocks)

        @a.get("/mempool")
        def get_mempool():
            return jsonify({
                "transactions": [t.to_dict() for t in self.mempool.all()],
            })

        @a.post("/tx")
        def post_tx():
            data = request.get_json()
            try:
                tx = Transaction.from_dict(data)
                self.mempool.add(tx)
                self._broadcast("/tx", data, exclude=request.remote_addr)
                return jsonify({"ok": True, "tx_hash": "0x" + tx.tx_hash().hex()})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

        @a.post("/block")
        def post_block():
            data = request.get_json()
            try:
                block = Block.from_dict(data)
                if block.height <= self.chain.height:
                    return jsonify({"ok": False, "error": "已有该高度区块"}), 409
                if block.height != self.chain.height + 1:
                    return jsonify({"ok": False, "error": "高度不连续，请先同步"}), 409
                prev = self.chain.head
                expected_d = self.chain.next_difficulty()
                ok, msg = verify_block(block, prev, expected_d, chain_state=self.chain)
                if not ok:
                    return jsonify({"ok": False, "error": msg}), 400
                self.chain.append(block)
                if self.verbose:
                    print(f"[node] 收到并接受新区块 #{block.height}")
                self._broadcast("/block", data, exclude=request.remote_addr)
                return jsonify({"ok": True, "height": block.height})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

        @a.get("/peers")
        def get_peers():
            return jsonify({"peers": list(self.peers)})

        @a.post("/peers")
        def add_peer():
            data = request.get_json() or {}
            url = data.get("url")
            if not url or not self._valid_peer_url(url):
                return jsonify({"ok": False, "error": "无效 url"}), 400
            self.peers.add(url)
            return jsonify({"ok": True, "peers": list(self.peers)})

    @staticmethod
    def _valid_peer_url(url: str) -> bool:
        try:
            p = urlparse(url)
            return p.scheme in ("http", "https") and bool(p.netloc)
        except Exception:
            return False

    # ============ 广播 / 同步 ============
    def _broadcast(self, path: str, payload: dict, exclude: Optional[str] = None):
        for url in list(self.peers):
            try:
                requests.post(url + path, json=payload, timeout=PEER_TIMEOUT_SEC,
                              headers={"User-Agent": USER_AGENT})
            except Exception as e:
                if self.verbose:
                    print(f"[node] broadcast → {url} 失败：{e}")

    def _ping_peer(self, url: str) -> Optional[dict]:
        try:
            r = requests.get(url + "/info", timeout=PEER_TIMEOUT_SEC,
                             headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                info = r.json()
                self.peers_seen[url] = {
                    "last_seen": time.time(),
                    "height": info.get("height", -1),
                    "head_hash": info.get("head_hash", ""),
                }
                # 学习对方的 peer 列表（peer exchange）
                for p in info.get("peers", []):
                    if self._valid_peer_url(p) and p != self.public_url:
                        self.peers.add(p)
                return info
        except Exception:
            pass
        return None

    def _sync_from_peer(self, url: str, peer_info: dict) -> int:
        """从 peer 同步缺失的区块。返回拉取并接受的区块数。"""
        peer_h = peer_info.get("height", -1)
        if peer_h <= self.chain.height:
            return 0
        # 拉一段
        start = self.chain.height + 1
        end = min(peer_h, start + 99)   # 一次最多 100 块
        try:
            r = requests.get(f"{url}/blocks/range/{start}/{end}",
                             timeout=PEER_TIMEOUT_SEC * 4,
                             headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                return 0
            count = 0
            for bd in r.json():
                try:
                    block = Block.from_dict(bd)
                    if block.height != self.chain.height + 1:
                        break
                    prev = self.chain.head
                    expected_d = self.chain.next_difficulty()
                    ok, msg = verify_block(block, prev, expected_d,
                                           chain_state=self.chain,
                                           recompute_xeb=False)  # 同步时不重算 XEB（性能）
                    if not ok:
                        if self.verbose:
                            print(f"[node] 拒绝来自 {url} 的区块 #{block.height}：{msg}")
                        break
                    self.chain.append(block)
                    count += 1
                except Exception as e:
                    if self.verbose:
                        print(f"[node] 同步异常：{e}")
                    break
            if count > 0 and self.verbose:
                print(f"[node] 从 {url} 同步了 {count} 块（高度 {start}–{start+count-1}）")
            return count
        except Exception:
            return 0

    def _sync_loop(self):
        if self.verbose:
            print(f"[node] 同步循环启动（每 {SYNC_INTERVAL_SEC} 秒一次）")
        while not self._stop.is_set():
            for url in list(self.peers):
                info = self._ping_peer(url)
                if info:
                    self._sync_from_peer(url, info)
            self._stop.wait(SYNC_INTERVAL_SEC)

    # ============ 启动 ============
    def start(self):
        sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        sync_thread.start()
        # 屏蔽 Flask 的请求日志（噪声）
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        if self.verbose:
            print(f"[node] BTCQ 节点启动 :{self.port}")
            print(f"[node] 链高度: {self.chain.height}")
            print(f"[node] 初始 peers: {len(self.peers)}")
        self.app.run(host="0.0.0.0", port=self.port, threaded=True, use_reloader=False)
