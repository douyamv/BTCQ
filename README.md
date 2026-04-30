# QXEB · 量子交叉熵币

> 第一个**只能由量子计算机有效率挖矿**的加密货币。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10+-blue.svg)
![status](https://img.shields.io/badge/status-v0.1%20testnet-orange)

---

## 这是什么

QXEB 把"量子计算优势"——这个被搁置在物理实验室里 7 年的资源——第一次铸成了可以挖、可以持有、可以流通的链上资产。

* **挖矿** = 跑一段随机量子电路，提交带有交叉熵基准（XEB）证明的样本
* **验证** = 任何人在经典电脑上重算 XEB（v0.1 阶段几秒搞定）
* **量子优势** = 经典伪造合法区块需要指数级时间（数学上严格证明，[BFNV19]）
* **总量** = 21,000,000 枚（与 BTC 对齐）
* **创世** = 2026-04-30

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
python scripts/new_wallet.py bob.json     # 多生成一个用于测试转账

# 4a. 经典模拟挖矿（仅 n≤31 可用，n=36 时会拒绝）
python scripts/mine.py --classical

# 4b. 真量子机挖矿（v0.1 推荐，n=36 唯一可行路径）
python scripts/mine.py --quantum --backend ibm_marrakesh

# 5. 转账（先挖几块拿到余额）
python scripts/send.py --to 0x<bob 地址> --amount 5
python scripts/mempool.py                 # 查看待打包交易
python scripts/mine.py --quantum          # 再挖一块，自动打包 mempool

# 6. 验证整条链
python scripts/verify.py

# 7. 查询余额 / 链状态
python scripts/balance.py 0x<地址>
python scripts/stats.py
```

---

## 为什么这个设计是"对的"

| 问题 | 经典 PoW (BTC) | QXEB |
|---|---|---|
| 挖矿装备 | ASIC 矿场（中心化） | 量子云访问 / 自有量子机 |
| 量子优势 | 反而被 Grover 削弱 | **正向利用**（结构性内置） |
| 能源 | 数 GW 全球电力 | μW–W 级量子处理器 + 制冷 |
| 攻击代价 | 51% 算力 | **指数级经典算力** |
| 难度增长 | 摩尔定律 + ASIC | 量子比特数 + 保真度（缓慢） |
| 早期出块 | 难度自动 | 头 15 天 1 分钟/块 + 30 天平滑过渡到 10 分钟/块 |

QXEB 把工作量证明的"量子—经典不对称性"反过来用：经典做困难，量子做轻松。

---

## 当前状态

* **协议版本**: v0.1（测试网，单节点）
* **电路参数**: **n=36 比特、深度 14、8192 个采样**
* **量子优势倍率**: 当前 **10⁴–10⁵×**（笔记本和工作站完全无法挖矿）
* **出块节奏**: 创世后头 15 天 60 秒/块，再 30 天线性升至 600 秒/块，之后稳态 600 秒/块
* **总量上限**: 21,000,000 QXEB（与 BTC 相同），区块奖励 50 QXEB / 块，每 210000 块减半
* **下一步**: P2P 网络（v0.5）→ 主网（v1.0，n=55，d=18）→ 完全 supremacy 模式（v2.0，n=75+）

详见 [路线图](docs/WHITEPAPER.md#6-路线图)

---

## 谁能挖

任何能访问支持 ≥30 量子比特、深度 ≥14 电路、双比特门保真度 ≥99% 的量子处理器的人。截至 2026 Q2，此条件下的可挖矿者全球大约几千人。

具体硬件支持：

* ✅ IBM Quantum (Heron r2: ibm_fez, ibm_marrakesh, ibm_kingston)
* ✅ Quantinuum H2 / Helios
* ✅ IonQ Forte / Tempo
* ✅ Atom Computing (中性原子阵列)
* ✅ Google Quantum AI (Willow，需 API 访问)
* ⚠️ 任何 Qiskit/Cirq 兼容的云服务

也支持纯经典模拟挖矿（`--classical`），作为对照实验和开发调试。

---

## 不预挖、不 ICO、不私募

QXEB 没有任何预先分配。第一枚币由第一个矿工挖出，**那个人很可能就是你**。

代码 100% 开源（MIT），白皮书 CC-BY-SA。无团队保留份额，无营销预算，无路线图营销。

---

## 贡献

欢迎 PR：

* 协议 bug / 安全问题 → 提 issue 或邮件
* 验证器 GPU 加速（v1.0 关键）
* P2P 网络层（v0.5 蓝图）
* 中文以外的文档翻译
* 多硬件矿工后端（IonQ/Quantinuum/Atom 适配器）

---

## 许可

代码：MIT  ·  白皮书与文档：CC-BY-SA 4.0
