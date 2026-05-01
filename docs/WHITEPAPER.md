# BTCQ 白皮书

**比特币量子（Bitcoin Quantum, BTCQ）**
**v0.1 — 2026 年 5 月**

> "把量子计算优势第一次变成可定价的稀缺资源。"

---

## 摘要

BTCQ 是一种**只能由量子计算机参与共识**的加密货币。它采用 **PoQ-Stake**（Proof-of-Quantumness Stake）共识机制——抵押 BTCQ 获得出块权利的同时，**每个区块的产生都需要一段真实的量子计算证明**。

* **总量上限**：21,000,000 枚（与 Bitcoin 一致）
* **区块奖励**：50 BTCQ，每 210,000 个区块减半（≈ 4 年）
* **出块时间**：bootstrap 期 1 分钟，过渡 30 天后稳态 10 分钟
* **量子证明成本**：每块约 1 秒量子机接口时间（远低于 PoW 矿场的能源消耗）
* **抵押门槛**：1 BTCQ 可参与共识

BTCQ 的存在意义：**第一次为已经存在的量子计算优势设计了一个市场可定价、可被持有、可被流通的承载物**——而且不是通过浪费电力（PoW）实现的。

---

## 1. 引言：被搁置的量子计算优势

2019 年 10 月，Google 用 Sycamore 处理器在 200 秒内完成了一项被估计需要顶级超级计算机运算 10,000 年的随机电路采样任务（[Arute2019]）。其后，IBM、Quantinuum、QuEra、Atom Computing 在不同物理体系上反复重现并强化了这一"量子计算优势"。

到 2026 年，全球可云端访问的高保真度量子处理器超过 30 台，但**量子算力除了用于物理模拟、化学计算和论文之外，没有任何加密金融意义上的价值捕获机制**。

这就是 BTCQ 解决的具体问题：**让一台量子计算机的算力，可以直接转化为可在公开市场流通的资产，且不需要 BTC 那样的能源浪费**。

---

## 2. 为什么是 PoQ-Stake，不是 PoW？

我们最初考虑过纯 PoW 设计（每块需要量子机花数十秒到几分钟去找合格电路）。但很快意识到：

* **量子算力成本高昂**：IBM Open Plan 每月仅 600 秒免费配额；商业付费每秒美元级
* **PoW 浪费**：BTC 矿场年耗电与中等国家相当，社会成本巨大
* **PoQ-Stake 解决两难**：抵押提供经济安全，量子证明提供身份门槛，**每块只需 1 秒量子时间**

### 2.1 PoQ-Stake 共识（硬时间 slot，Ethereum 式）

**核心机制：每个 slot（60 秒/600 秒固定窗口）由 VRF 唯一选出一名 proposer**。proposer 在该 slot 内完成量子证明并提交区块；失败则 slot 空，下个 slot 选别人。

每个区块的产生流程：

```
1. 协议根据 slot 编号 + 全网抵押表计算唯一 proposer（VRF）
2. proposer 用 prev_hash + slot + 自身地址派生确定性电路 seed
3. proposer 在量子机上运行 RCS 电路（n=30, depth=12, 4096 shots, ~1 秒接口）
4. 计算样本的 XEB 分数，必须 ≥ 当前难度阈值
5. proposer 签名并广播区块
6. 验证者：
   ① 用 block.timestamp 反推 slot
   ② 检查 select_proposer_for_slot(slot) == block.proposer_address
   ③ block.slot > prev.slot（严格递增，防同 slot 双块）
   ④ 经典 Aer 模拟核对 XEB
```

**这个设计从根本上消除三大问题**：

| 问题 | 传统 PoW/无 slot 设计 | 硬时间 slot |
|---|---|---|
| 同高度多块（fork） | 多个矿工抢 → 链分叉 | 每 slot 唯一 proposer，分叉风险大幅降低 |
| 单 staker 刷 XEB | 同一 staker 每个 height 都尝试 | proposer 仅在自己 slot 才能尝试，被动等待 |
| 链卡死 | proposer 失败 → 没人能继续 | 失败的 slot 空，下个 slot 别人接力 |

**三道时间防线**（防恶意时钟操纵）：

1. **Proposer 本地钟** 决定"我能不能在该 slot 出块"——但这只是建议，最终决定权在验证者
2. **验证者用 block.timestamp 反推 slot**，再用 slot 反推 proposer，不一致即拒绝
3. **block.timestamp 边界检查**：不能超过本地钟太多（防未来块）、不能早于上一块（防过去时间倒退）

没有"权威时钟"，只有"互相约束的本地钟"——只要诚实节点偏差 < SLOT_DURATION，系统就稳。NTP 同步精度（~100ms）远小于 60 秒 slot，工程上不会出问题。

### 2.2 量子优势倍率（v0.1）

| 角色 | 单块出块耗时 |
|---|---|
| 量子机（IBM Heron r2 / Quantinuum H2 等） | ≈ 1 秒（接口总时间） |
| 经典暴力模拟（Aer 状态向量） | ≈ 5–10 秒 |
| 经典张量网络近似 | ≈ 1–2 秒（精度有损，可能不达 XEB 阈值） |

5–30× 的稳定时间优势，对 60 秒/块的 bootstrap 期足够形成"经典追不上"的局面。

未来（v1.0+）将提升到 n=36+，让经典完全脱离游戏。

---

## 3. 协议设计

### 3.1 区块结构（核心字段）

```
BTCQBlock {
    version            uint16
    height             uint64
    prev_hash          bytes32
    timestamp          uint64
    proposer_address   bytes20         // 出块人地址（替代 PoW 的 miner_address）
    n_qubits           uint8           // = 24
    depth              uint8           // = 8
    n_samples          uint32          // = 1024
    difficulty         float64         // 当前 XEB 阈值
    samples_root       bytes32         // 样本 Merkle 根
    xeb_score          float64         // 出块人声明的 XEB 分数
    transactions_root  bytes32         // 交易 Merkle 根
    transactions       list<Transaction>
    samples            list<bitstring>
    proposer_signature bytes65         // 出块人对区块头的 secp256k1 签名
}
```

### 3.2 交易类型

```
Transaction {
    sender    bytes20
    recipient bytes20
    amount    uint128
    nonce     uint64
    kind      string    // "transfer" | "stake" | "unstake"
    signature bytes65
}
```

* **transfer**：普通转账
* **stake**：抵押到 STAKE_VAULT (`0x000...0001`)，从 sender 余额扣除，加入抵押池
* **unstake**：申请解抵押，需冷却 100 块后金额回到流动余额

### 3.3 出块节奏（bootstrap → 稳态）

| 阶段 | 时间 | 目标出块时间 | 难度调整窗口 |
|---|---|---|---|
| 启动加速期 | 第 0–15 天 | 60 秒/块 | 144 块 |
| 平滑过渡期 | 第 15–45 天 | 60 → 600 线性 | 144 块 |
| 稳态期 | 第 45 天+ | 600 秒/块（同 BTC） | 2016 块 |

### 3.4 减半曲线（完全照搬 BTC）

* 总量上限：21,000,000 BTCQ
* 创世后第 1 块奖励：50 BTCQ
* 每 210,000 个区块减半一次
* 由于 bootstrap 期块更密，第一次减半比 BTC 早约 5 个月（≈ 3 年 7 个月）；之后每次减半依然 4 年

### 3.5 抵押与出块资格

* 最低抵押：**1 BTCQ**
* 解抵押冷却：**100 块**
* Bootstrap 开放期：创世后 **前 144 块**任何持有量子机的人都可出块（无需抵押）——解决"鸡生蛋"问题

### 3.6 出块人选举（VRF）

```python
def select_proposer(prev_hash, height, stake_map):
    seed = keccak256(prev_hash || height)
    rnd = uint64(seed[:8]) % total_stake
    return staker[i] where cumulative_stake[i] crosses rnd
```

v0.1 用 keccak 当 VRF（确定性 + 无偏，但缺少不可预测性证明）。v0.5 升级为 Schnorr-VRF。

---

## 4. 经济模型

| 参数 | 值 |
|---|---|
| 总量上限 | 21,000,000 BTCQ |
| 创世区块奖励 | 50 BTCQ |
| 减半周期 | 210,000 区块（≈ 3.6 年首次，之后每 4 年） |
| 出块时间（稳态） | 600 秒 |
| 出块时间（bootstrap） | 60 秒 |
| 创世日期 | 2026-04-30 |
| 最低抵押 | 1 BTCQ |
| 解抵押冷却 | 100 块 |

### 4.1 矿工/Staker 收益构成

* **区块奖励**：随减半递减
* **交易费**：v1.0 引入 gas 后矿工自由打包

### 4.2 估值逻辑

BTCQ 的内在价值来自三层：

1. **稀缺**：数学上有上限，且必须经过 PoQ-Stake 才能产出
2. **效用**：未来作为去中心化"量子算力市场"的本位币
3. **叙事**：作为"量子计算 × 区块链"交叉点的纪念物

---

## 5. 路线图

| 版本 | 时间 | 关键变化 |
|---|---|---|
| **v0.1（本版本）** | 2026 Q2 | 单节点测试网，PoQ-Stake，n=24，bootstrap 开放挖矿 |
| **v0.5** | 2026 Q3 | P2P 网络、VRF 严格强制、罚没机制、CLI 钱包 |
| **v1.0** | 2026 Q4 | 主网启动，n=36 量子证明（笔记本完全无法挖），区块浏览器 |
| **v1.5** | 2027 Q2 | EVM 兼容侧链、BTCQ ↔ ETH 跨链桥、gas 与手续费 |
| **v2.0** | 2028 | n=55 + 哨兵子电路验证 + ZK proofs |
| **v3.0** | 2030+ | 量子算力市场（DePIN）：以 BTCQ 结算量子时段 |

---

## 6. 风险与限制

### 6.1 技术风险

* **经典算法突破**：未来可能出现 RCS 经典近似算法削弱量子门槛。BTCQ 通过周期性提高 n 缓解
* **量子硬件中心化**：现阶段量子资源集中在 IBM、Google、Quantinuum 等少数公司云端；矿业可能短期集中
* **VRF 不可预测性弱**：v0.1 用 keccak 派生伪随机不是真 VRF；v0.5 升级

### 6.2 经济风险

* BTCQ 没有任何历史价格，早期市值可能为零或剧烈波动
* 监管态度未知
* 无团队预挖、无 ICO、无私募——这是优点也是风险

### 6.3 我们不承诺什么

* 不承诺价格上涨
* 不承诺被任何交易所上市
* 不承诺替代任何现有加密货币
* 仅承诺协议数学正确、代码开源、无预挖、规则不变

---

## 7. 总结

BTCQ 把量子计算优势——这个被搁置在物理实验室里 7 年的资源——第一次铸成可挖、可持有、可流通的链上资产。它不浪费 BTC 那样的电力，不威胁任何现有加密货币，只是在量子时代真正到来之前，**先把第一枚"比特币 × 量子"铸出来，等市场到来**。

代码 100% 开源（MIT），白皮书 CC-BY-SA。无团队保留份额，无预挖，无营销预算，无"团队"。代码是规范，规范是共识，共识是价值。

**第一个 BTCQ 区块由你的量子计算机出块。从你开始。**

---

## 参考文献

[Arute2019] Arute F. et al. "Quantum supremacy using a programmable superconducting processor." *Nature* 574, 505–510 (2019).

[BFNV19] Bouland A., Fefferman B., Nirkhe C., Vazirani U. "On the complexity and verification of quantum random circuit sampling." *Nature Physics* 15, 159–163 (2019).

[Mahadev2018] Mahadev U. "Classical Verification of Quantum Computations." *FOCS* 2018.

[Nakamoto2008] Nakamoto S. "Bitcoin: A Peer-to-Peer Electronic Cash System." (2008).

---

*Github: github.com/douyamv/btcq*
*Released under CC-BY-SA 4.0. 协议代码采用 MIT License.*
