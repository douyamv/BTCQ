#!/usr/bin/env python3
"""自动挖矿守护进程：固定间隔挖矿，崩溃自动重试。

用法:
    python scripts/auto_mine.py                  # 默认 180 秒一块
    python scripts/auto_mine.py --interval 60    # 自定义间隔
    python scripts/auto_mine.py --interval 180 --backend ibm_marrakesh

按 Ctrl+C 停止。
"""

import sys
import argparse
import time
import subprocess
import urllib.request
import urllib.error
import json as _json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _notify_nodes(ports=(8333, 8334)):
    """挖矿完成后让本地节点重新读盘。"""
    for port in ports:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/reload", timeout=2)
        except Exception:
            pass    # 节点可能未运行


def _push_block_to_remotes(chain_dir: Path, urls):
    """挖矿成功后把最新区块直接 POST 给远程节点。

    本机 NAT 下后台广播触不到 push 路径（远程不会主动连本机）。
    所以挖完直接 POST，确保远程链同步。
    """
    if not urls:
        return
    latest = chain_dir / "blocks" / "latest.json"
    if not latest.exists():
        return
    try:
        block_data = _json.loads(latest.read_text())
    except Exception as e:
        print(f"  ⚠️ 读取 latest.json 失败: {e}")
        return
    payload = _json.dumps(block_data).encode()
    for url in urls:
        url = url.rstrip("/")
        try:
            req = urllib.request.Request(
                f"{url}/block",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                if '"ok": true' in body or '"ok":true' in body:
                    print(f"  → 已推送到 {url}")
                else:
                    print(f"  ⚠️ {url} 拒绝: {body[:150]}")
        except Exception as e:
            print(f"  ⚠️ 推送 {url} 失败: {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=180, help="挖矿间隔秒数（默认 180 = 3 分钟）")
    p.add_argument("--backend", default="ibm_marrakesh")
    p.add_argument("--wallet", default="wallet.json",
                   help="钱包文件路径（多个用逗号分隔，会按顺序轮换）")
    p.add_argument("--shots", type=int, default=4096)
    p.add_argument("--mode", choices=["quantum", "classical"], default="quantum")
    p.add_argument("--push-to", default="",
                   help="挖矿成功后把新区块推送到这些节点，逗号分隔（例：http://43.136.28.125:8333）")
    p.add_argument("--chain", default="./chain_data", help="链数据目录")
    args = p.parse_args()
    push_urls = [u.strip() for u in args.push_to.split(",") if u.strip()]
    chain_dir = Path(args.chain).resolve()

    # 多钱包轮换：每次挖矿用一个，按数组顺序循环
    wallets = [w.strip() for w in args.wallet.split(",") if w.strip()]
    if not wallets:
        wallets = ["wallet.json"]

    print(f"=" * 60)
    print(f" BTCQ 自动挖矿 · {args.mode} · 后端 {args.backend}")
    print(f" 间隔 {args.interval} 秒  钱包数 {len(wallets)}（轮换）")
    for i, w in enumerate(wallets):
        print(f"   [{i}] {w}")
    if push_urls:
        print(f" 出块后推送到：")
        for u in push_urls:
            print(f"   → {u}")
    print(f"=" * 60)
    print(" 按 Ctrl+C 停止\n")

    blocks_mined = 0
    failures = 0
    started_at = time.time()
    cycle = 0

    while True:
        loop_start = time.time()
        ts = datetime.now().strftime("%H:%M:%S")
        wallet = wallets[cycle % len(wallets)]
        cycle += 1
        print(f"[{ts}] 第 {blocks_mined + failures + 1} 次尝试 · 钱包 {Path(wallet).name}")
        try:
            cmd = ["python3", "scripts/propose.py",
                   f"--{args.mode}",
                   "--wallet", wallet,
                   "--shots", str(args.shots)]
            if args.mode == "quantum":
                cmd.extend(["--backend", args.backend])
            # IBM Quantum 队列可能排几分钟到几十分钟，不要太短
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if r.returncode == 0 and "区块出块成功" in r.stdout:
                blocks_mined += 1
                for line in r.stdout.splitlines():
                    if "高度" in line or "XEB" in line:
                        print(f"  {line.strip()}")
                # 挖矿写在 chain_data，但节点内存缓存不会自动刷新——通知本地节点重读
                _notify_nodes()
                # 直接推送到远程节点（本机 NAT 后无法被回连）
                _push_block_to_remotes(chain_dir, push_urls)
                runtime = (time.time() - started_at) / 60
                print(f"[{ts}] ✅ 累计 {blocks_mined} 块，运行 {runtime:.1f} 分钟，失败 {failures} 次\n")
            else:
                failures += 1
                # 提取错误信息
                err_line = r.stderr.strip().split('\n')[-1] if r.stderr else r.stdout.strip().split('\n')[-1]
                print(f"[{ts}] ⚠️  失败：{err_line[:200]}")
                # 如果是 slot 不到，等下个 slot
                if "slot" in err_line.lower() and "等" in err_line:
                    print(f"  → 等待节奏中，30 秒后再尝试")
                    time.sleep(30)
                    continue
        except subprocess.TimeoutExpired:
            failures += 1
            print(f"[{ts}] ⚠️  超时（5 分钟），重启")
        except KeyboardInterrupt:
            print(f"\n\n停止。共挖出 {blocks_mined} 块，失败 {failures} 次。")
            return
        except Exception as e:
            failures += 1
            print(f"[{ts}] ⚠️  异常：{e}")

        # 等下次
        elapsed = time.time() - loop_start
        wait = max(args.interval - elapsed, 5)
        print(f"  等待 {wait:.0f} 秒后继续...\n")
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            print(f"\n停止。共挖出 {blocks_mined} 块。")
            return


if __name__ == "__main__":
    main()
