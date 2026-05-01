# BTCQ · 比特币量子（Bitcoin Quantum）

> 第一个**只能由量子计算机参与共识**的加密货币——PoQ-Stake 共识，每块约 1 秒量子时间，彻底告别 PoW 矿场的电力浪费。
>
> **创世铭文**：「基于比特币的发现，致敬 Satoshi。我们需要一个量子网络 BTC。Thanks, Satoshi.」

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10+-blue.svg)
![status](https://img.shields.io/badge/status-v0.1.4%20公开%20testnet-green)
![consensus](https://img.shields.io/badge/共识-PoQ--Stake-blueviolet)

---

## 这是什么

BTCQ 把"量子计算优势"——这个被搁置在物理实验室里 7 年的资源——第一次铸成了可以挖、可以持有、可以流通的链上资产。

* **共识** = PoQ-Stake（Proof-of-Quantumness Stake）：抵押 BTCQ + 每块提交 1 秒量子证明
* **量子门槛** = 经典伪造合法证明需要 5–10 秒（量子机 ~1 秒），1 分钟出块时间内经典追不上
* **总量** = 21,000,000 枚（与 BTC 对齐）
* **创世** = 2026-04-30
* **能耗** = PoW 矿场的百万分之一

完整设计请看 [白皮书](docs/WHITEPAPER.md) | [技术规范](docs/PROTOCOL.md) | [挖矿指南](docs/MINING_GUIDE.md) | [FAQ](docs/FAQ.md)

---

## 5 分钟快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化链（写入创世区块）
python scripts/init_chain.py

# 3. 生成钱包
python scripts/new_wallet.py

# 4. 出块（bootstrap 期前 144 块开放挖矿，无需抵押）
python scripts/propose.py --classical                  # 本地经典模拟
python scripts/propose.py --quantum --backend ibm_marrakesh  # 真量子机

# 5. 抵押后正式参与 PoQ-Stake
python scripts/stake.py --amount 5                     # 抵押 5 BTCQ
python scripts/stake.py --status                       # 查看抵押状态

# 6. 转账
python scripts/send.py --to 0xRECIPIENT --amount 3
python scripts/mempool.py                              # 查看待打包交易

# 7. 验证整条链
python scripts/verify.py

# 8. 链状态
python scripts/stats.py
python scripts/balance.py 0x<地址>

# 9. 启动 P2P 节点（与他人组网）
python scripts/node.py --port 8333 --peers http://其他节点:8333
```

---

## 为什么这个设计是"对的"

| 问题 | BTC | BTCQ v0.1 |
|---|---|---|
| 共识算法 | PoW (SHA-256 哈希猜谜) | **PoQ-Stake**（量子证明 + 抵押） |
| 谁有优势 | ASIC 矿场 | **量子计算机持有者 + 抵押人** |
| 单块出块成本 | 数 PWh 全网算力 | **~1 秒量子机时间** |
| 全网年耗电 | 数百 TWh | **微 W–W 量级** |
| 抗 51% 攻击 | 51% 算力 | **51% 量子算力 + 51% 抵押** |
| 难度增长 | 摩尔定律 + ASIC | 量子比特数（缓慢） |
| 早期出块 | 难度自适应 | 头 15 天 1 分钟/块 + 30 天平滑过渡到 10 分钟/块 |

BTCQ 把工作量证明的"量子—经典不对称性"反过来用：经典做困难，量子做轻松，**而且没有 PoW 那种千万矿机的能源浪费**。

---

## 当前状态（v0.1.4 · 公开 testnet）

* **协议版本**: v0.1.4（公开 testnet）
* **共识**: PoQ-Stake（硬时间 slot + VRF 选举 + 双签罚没）
* **量子证明电路**: n=30 比特，深度 12，每块 4096 个采样
* **State Root**: 已上线（账户模型一致性保证）
* **量子接口耗时**: 约 1–10 秒/块（IBM Heron r2 实测）
* **量子优势倍率**: 30×（实测，v1.0 升 n=36 后将达 10⁴–10⁵×）
* **出块节奏**: 头 15 天 60 秒/slot → 30 天线性升至 600 秒/slot → 稳态 600 秒/slot
* **总量上限**: 21,000,000 BTCQ，区块奖励 50 BTCQ，每 210,000 块减半
* **创世预分配**: 250 BTCQ 致敬开拓者（Satoshi/Vitalik/Hal/Nick/David Chaum/Wei Dai/Shor/Preskill）+ 生态运营
* **抵押门槛**: 1 BTCQ
* **Bootstrap 开放挖矿**: 头 1000 块，每地址上限 20 块（防垄断）

完整状态：[CHANGELOG](CHANGELOG.md) | 部署：[DEPLOY](docs/DEPLOY.md)

---

## 谁能挖

任何能访问支持 ≥24 量子比特、深度 ≥8 电路、双比特门保真度 ≥99% 的量子处理器的人。这一门槛在 2026 Q2 全球大约能覆盖几千人。

具体硬件支持：

* ✅ IBM Quantum (Heron r2: ibm_fez, ibm_marrakesh, ibm_kingston)
* ✅ Quantinuum H2 / Helios
* ✅ IonQ Forte / Tempo
* ✅ Atom Computing (中性原子阵列)
* ✅ Google Quantum AI (Willow，需 API 访问)
* ⚠️ 任何 Qiskit/Cirq 兼容的云服务

也支持纯经典模拟（`--classical`），作为对照实验和开发调试。

---

## 不预挖、不 ICO、不私募

BTCQ 没有任何预先分配。第一枚币由第一个出块者获得，**那个人很可能就是你**。

代码 100% 开源（MIT），白皮书 CC-BY-SA。无团队保留份额，无营销预算，无"团队"。

---

## 贡献

欢迎 PR：

* 协议 bug / 安全问题 → 提 issue 或邮件
* P2P 网络层（v0.5 蓝图）
* VRF 严格化、罚没机制实现（v0.5）
* 多硬件矿工后端（IonQ/Quantinuum/Atom 适配器）
* 中文以外的文档翻译

---

## 许可

代码：MIT  ·  白皮书与文档：CC-BY-SA 4.0
