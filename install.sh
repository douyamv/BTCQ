#!/usr/bin/env bash
# BTCQ 一键安装 · macOS / Linux
# 用法: curl -fsSL https://raw.githubusercontent.com/douyamv/BTCQ/main/install.sh | bash

set -e

INSTALL_DIR="${INSTALL_DIR:-$HOME/.btcq}"
REPO_URL="https://github.com/douyamv/BTCQ.git"

cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

echo ""
cyan "=========================================="
cyan "  ⚛  BTCQ 比特币量子 · 一键安装"
cyan "=========================================="
echo ""

# 1) 系统识别
OS=""
case "$(uname -s)" in
  Darwin*) OS="macOS";;
  Linux*)  OS="Linux";;
  *)       red "不支持的系统：$(uname -s)"; exit 1;;
esac
green "✓ 检测到 $OS"

# 2) Python 3
if command -v python3 >/dev/null 2>&1; then
  green "✓ Python: $(python3 --version 2>&1)"
else
  yellow "⚠ 未检测到 python3，尝试自动安装..."
  if [ "$OS" = "macOS" ]; then
    if ! command -v brew >/dev/null 2>&1; then
      red "请先安装 Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
      exit 1
    fi
    brew install python@3.11
  else
    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
  fi
  green "✓ Python: $(python3 --version 2>&1)"
fi

# 3) pip
if ! python3 -m pip --version >/dev/null 2>&1; then
  yellow "⚠ pip 未就绪，自动安装 ensurepip..."
  python3 -m ensurepip --upgrade || python3 -m pip install --upgrade pip
fi
green "✓ pip $(python3 -m pip --version | awk '{print $2}')"

# 4) Git
if ! command -v git >/dev/null 2>&1; then
  yellow "⚠ 未检测到 git，自动安装..."
  if [ "$OS" = "macOS" ]; then
    xcode-select --install 2>/dev/null || true
  else
    sudo apt-get install -y git
  fi
fi
green "✓ Git: $(git --version | awk '{print $3}')"

# 5) 下载/更新代码
if [ -d "$INSTALL_DIR/.git" ]; then
  cyan "▶ 已安装，更新代码..."
  cd "$INSTALL_DIR" && git pull --rebase --quiet
else
  cyan "▶ 下载 BTCQ 协议代码到 $INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" --quiet
fi
cd "$INSTALL_DIR"

# 6) 依赖
cyan "▶ 安装 Python 依赖（首次约 1–2 分钟）..."
python3 -m pip install --quiet --upgrade pip 2>&1 | tail -3 || true
python3 -m pip install --quiet -r requirements.txt 2>&1 | tail -3
green "✓ 依赖安装完成"

# 7) 初始化链（幂等）
if [ ! -f "$INSTALL_DIR/chain_data/blocks/00000000.json" ]; then
  cyan "▶ 初始化链..."
  python3 scripts/init_chain.py >/dev/null
fi
green "✓ 创世已就位"

# 8) 创建钱包（如果还没有）
if [ ! -f "$INSTALL_DIR/wallet.json" ]; then
  cyan "▶ 生成挖矿钱包..."
  python3 scripts/new_wallet.py >/dev/null
fi
WALLET_ADDR=$(python3 -c "import json; print(json.load(open('wallet.json'))['address'])")
green "✓ 钱包: $WALLET_ADDR"

echo ""
cyan "=========================================="
green "  🎉 BTCQ 已完成自动化安装"
cyan "=========================================="
echo ""
echo "  📍 安装位置:  $INSTALL_DIR"
echo ""
echo "  🚀 下一步（任选其一）："
echo ""
echo "     ① 用 BTCQ Miner GUI 一键挖矿（推荐）"
echo "        下载: https://github.com/douyamv/BTCQ-Miner/releases"
echo ""
echo "     ② 命令行启动节点 + 挖矿"
echo "        cd $INSTALL_DIR"
echo "        python3 scripts/node.py --port 8333 &        # 启动 P2P 节点"
echo "        python3 scripts/auto_mine.py --interval 1200  # 每 20 分钟挖一块"
echo ""
echo "  💡 仅需提供 IBM Quantum API Token（免费每月 600 秒）"
echo "     注册地址: https://quantum.ibm.com"
echo ""
cyan "=========================================="
