# BTCQ 节点部署指南

从零部署一个 BTCQ 测试网节点 / 矿工 / 全节点。

---

## 1. 系统要求

| 角色 | 最低配置 |
|---|---|
| **轻量节点（仅同步与转账）** | 4 核 CPU / 8 GB RAM / 10 GB 磁盘 / 公网 |
| **挖矿节点（含量子证明）** | 4 核 CPU / 16 GB RAM / 量子机访问（IBM Quantum 免费即可）/ 公网 |
| **全节点 + 验证（n=30 XEB 重算）** | 8 核 CPU / 32 GB RAM / 100 GB 磁盘 / GPU 推荐 |

**操作系统**：Linux / macOS（推荐）/ Windows WSL

**Python**：3.10+（推荐 3.11）

---

## 2. 安装

```bash
git clone https://github.com/douyamv/BTCQ.git
cd BTCQ
pip install -r requirements.txt
```

依赖（关键）：
- `qiskit >= 2.0` 与 `qiskit-ibm-runtime >= 0.35` — 量子证明
- `qiskit-aer >= 0.17` — 经典 XEB 验证
- `flask >= 3.0` 与 `requests >= 2.32` — P2P 节点
- `eth-keys >= 0.4` — secp256k1 + Ethereum 兼容地址
- `pycryptodome >= 3.18` — keccak256 + ChaCha20

---

## 3. 配置 IBM Quantum 访问（挖矿者必读）

### 3.1 注册免费账号

1. 浏览器打开 https://quantum.ibm.com
2. 用邮箱注册（推荐 Gmail）— 5 分钟完成验证
3. **免费每月 600 秒配额** — BTCQ 单块约 1 秒，足够挖 600+ 块

### 3.2 获取 API Token

登录后 → 右上角头像 → **API Token** → 复制（一长串字符）

### 3.3 一次性写入凭据

```python
from qiskit_ibm_runtime import QiskitRuntimeService
QiskitRuntimeService.save_account(
    channel="ibm_quantum_platform",
    token="你的_token",
    overwrite=True,
)
```

### 3.4 验证

```python
from qiskit_ibm_runtime import QiskitRuntimeService
print([b.name for b in QiskitRuntimeService().backends(simulator=False, operational=True)])
# 期望输出: ['ibm_fez', 'ibm_marrakesh', 'ibm_kingston'] 或类似
```

---

## 4. 初始化 + 创建钱包

```bash
# 4a. 初始化创世（每个节点本地都跑一次；创世由协议固化，所有节点结果一致）
python scripts/init_chain.py

# 4b. 生成出块钱包（私钥保存在 wallet.json，请备份！）
python scripts/new_wallet.py
# → 输出地址 0x...
```

> **重要**：`wallet.json` 存放你的私钥，丢失等于丢币。
> 推荐：复制到 USB 离线保存；不要提交到 git；不要分享。

---

## 5. 启动 P2P 节点

### 5.1 单机启动

```bash
python scripts/node.py --port 8333
```

输出 `BTCQ 节点启动 :8333` 表示成功。其他用户可通过 `http://你的IP:8333` 连接你。

### 5.2 加入种子节点（推荐）

```bash
python scripts/node.py --port 8333 \
  --peers http://seed1.btcq.network:8333,http://seed2.btcq.network:8333
```

> **当前种子节点**（v0.1.4 测试网）：
> - 待社区运营者部署。临时方案：你自己跑节点 + 把 IP 分享到 BTCQ Discord/Telegram

### 5.3 公网部署（让别人能连你）

```bash
# Linux 防火墙
sudo ufw allow 8333/tcp

# 启动时自报公网 URL
python scripts/node.py --port 8333 --public-url http://your.public.ip:8333
```

### 5.4 systemd 服务（生产环境推荐）

```ini
# /etc/systemd/system/btcq-node.service
[Unit]
Description=BTCQ Node
After=network.target

[Service]
Type=simple
User=btcq
WorkingDirectory=/home/btcq/BTCQ
ExecStart=/usr/bin/python3 scripts/node.py --port 8333 --public-url http://your.host:8333
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable btcq-node
sudo systemctl start btcq-node
sudo systemctl status btcq-node
```

---

## 6. 开始挖矿

### 6.1 Bootstrap 期（创世后头 1000 块，无需抵押）

```bash
python scripts/propose.py --quantum --backend ibm_marrakesh
```

每挖出一块得 50 BTCQ。**单地址 bootstrap 期最多挖 20 块**（防垄断）。

### 6.2 持续挖矿循环

```bash
# 简易循环（slot 60s，每分钟尝试一次）
while true; do
    python scripts/propose.py --quantum --backend ibm_marrakesh || true
    sleep 60
done
```

或者用 `tmux`/`screen` 长期挂着。

### 6.3 PoQ-Stake 期（区块 1000+，需抵押）

```bash
# 抵押 5 BTCQ 进入 staker 集合
python scripts/stake.py --amount 5

# 等下一 slot 是你（VRF 选）
python scripts/propose.py --quantum --backend ibm_marrakesh
# 如果不是你的 slot，会提示等下次
```

---

## 7. 查询状态

```bash
# 链整体
python scripts/stats.py

# 余额（流动 + 抵押 + 冷却 + 总）
python scripts/stake.py --status

# 任意地址余额
python scripts/balance.py 0xABC...

# 整链验证（完整重算 XEB，慢但严格）
python scripts/verify.py

# 跳过 XEB（仅查签名/结构，快）
python scripts/verify.py --no-xeb

# 看 mempool 待打包交易
python scripts/mempool.py
```

### HTTP API（节点运行时）

```bash
curl http://localhost:8333/info             # 节点状态
curl http://localhost:8333/blocks/0         # 创世
curl http://localhost:8333/blocks/range/1/10 # 一段区块
curl http://localhost:8333/peers            # 已知 peer
curl http://localhost:8333/slashes          # 罚没历史
```

---

## 8. 转账

```bash
# 创建一笔签名交易（自动写入本地 mempool）
python scripts/send.py --to 0xRECIPIENT_ADDR --amount 5

# 此交易会在下次出块时被打包（任意节点的 mempool）
```

---

## 9. 故障排查

### "RuntimeError: 量子证明 XEB 未达阈值"

* 检查后端在线：`curl https://api.quantum.ibm.com/...` 或 Qiskit `backend.status()`
* Heron r2 在 n=30 d=12 应该轻松达 XEB > 1
* 检查 difficulty target 是否过高（链状态查 `curl localhost:8333/info`）

### "RuntimeError: slot S 选中的是 0x...，不是你"

* PoQ-Stake 期间，每个 slot 唯一 proposer。等下一个属于你的 slot
* 或：增加抵押额，提高被选中频率

### "RuntimeError: bootstrap：地址 已挖 20 块，达到上限"

* bootstrap 期单地址最多挖 20 块。继续 → 抵押后转 PoQ-Stake 模式

### "拒绝来自 X 的区块：state_root 不一致"

* 客户端版本不一致或本地状态损坏
* 删除 `chain_data/`，从种子节点全量重同步
* 或检查 git 是否最新

### 节点启动 "Address already in use"

```bash
lsof -ti :8333 | xargs kill -9   # 杀掉占用端口的进程
```

### 钱包私钥丢了

挖出的币无法找回。**务必备份 `wallet.json`**。

---

## 10. 升级到新版本

```bash
git pull
pip install -r requirements.txt --upgrade

# 协议版本升级时，可能需要重置链
# 检查 BLOCK_VERSION 是否变化：
python -c "from btcq.constants import PROTOCOL_VERSION; print(PROTOCOL_VERSION)"

# 如果协议变了：
rm -rf chain_data
python scripts/init_chain.py
# 重新 sync
```

---

## 11. 安全建议

* `wallet.json` 不要提交到 git（已在 `.gitignore`）
* 长期持币用冷钱包：导出私钥 → 物理隔离设备保存
* 节点公网部署：仅开放 8333；其他端口防火墙阻断
* 不要在公网节点上放置大量 staked 钱包；分离"出块钱包"和"持币钱包"
* 监控双签：`curl localhost:8333/slashes` 看是否有自家地址被罚没

---

## 12. 进阶

* [WHITEPAPER.md](WHITEPAPER.md) — 协议设计与经济模型
* [PROTOCOL.md](PROTOCOL.md) — 字段级技术规范
* [FAQ.md](FAQ.md) — 常见疑问
* [CLASSICAL_ATTACK_ANALYSIS.md](CLASSICAL_ATTACK_ANALYSIS.md) — 经典攻击成本分析
* GUI 客户端：https://github.com/douyamv/BTCQ-Miner
