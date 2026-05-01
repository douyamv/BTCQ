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
    """挖矿完成后让节点重新读盘。"""
    for port in ports:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/reload", timeout=2)
        except Exception:
            pass    # 节点可能未运行


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=180, help="挖矿间隔秒数（默认 180 = 3 分钟）")
    p.add_argument("--backend", default="ibm_marrakesh")
    p.add_argument("--wallet", default="wallet.json",
                   help="钱包文件路径（多个用逗号分隔，会按顺序轮换）")
    p.add_argument("--shots", type=int, default=4096)
    p.add_argument("--mode", choices=["quantum", "classical"], default="quantum")
    args = p.parse_args()

    # 多钱包轮换：每次挖矿用一个，按数组顺序循环
    wallets = [w.strip() for w in args.wallet.split(",") if w.strip()]
    if not wallets:
        wallets = ["wallet.json"]

    print(f"=" * 60)
    print(f" BTCQ 自动挖矿 · {args.mode} · 后端 {args.backend}")
    print(f" 间隔 {args.interval} 秒  钱包数 {len(wallets)}（轮换）")
    for i, w in enumerate(wallets):
        print(f"   [{i}] {w}")
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
                # 挖矿写在 chain_data，但节点内存缓存不会自动刷新——通知节点重新加载
                _notify_nodes()
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
