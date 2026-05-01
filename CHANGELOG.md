# CHANGELOG

## v0.1.4 — 2026-05-01 · 公开 testnet 就绪

🌍 **正式公开 testnet 版本**。所有 P0/P1 阻塞性问题修复完毕。

### 核心架构（C1 状态根）

* `block.state_root`：账户状态（balance + stake + nonce）的 Merkle 根
* 创世状态根固化（GENESIS_ALLOCATIONS 派生）；任何节点必须算出相同值
* `chain.preview_state_root(block)`：在不修改实际状态的前提下预览
* 验证者：检查 `block.state_root` 匹配本地重算结果，不一致拒绝
* 防御场景：两个独立实现对账户余额计算有平台差异/bug 时静默分裂——现在必然被捕获

### 创世预分配（C4 多地址致敬 + 生态运营）

| 致敬对象 | 地址 | 金额 |
|---|---|---|
| Satoshi Nakamoto | `0xbf0b...48d3` | 50 BTCQ |
| Vitalik Buterin | `0x5008...584f` | 25 BTCQ |
| Hal Finney | `0x0bd9...1699` | 10 BTCQ |
| Nick Szabo | `0x5041...1c51` | 10 BTCQ |
| David Chaum | `0x4694...d2b4` | 10 BTCQ |
| Wei Dai | `0x4da9...f8fe` | 10 BTCQ |
| Peter Shor | `0x9e31...a4d0` | 25 BTCQ |
| John Preskill | `0xf4d2...b21b` | 10 BTCQ |
| Ecosystem Faucet | `0xe642...914b` | 100 BTCQ |
| **总计** | | **250 BTCQ** |

致敬地址私钥不可恢复（永久锁定纪念）；Ecosystem Faucet 由运营方持有用于早期分发。

### 抗 DDoS（C3）

* `/tx` 60/min/IP, `/block` 30/min, `/peers` 10/min, `/blocks/range` 30/min
* `/blocks/range` 单次硬限 100 块（防内存挤爆）
* Peer 池上限 200（防 broadcast 风暴）

### 双签持久化（C2）

* `_seen_proposals` 写入 `chain_data/seen_proposals.json`
* 重启后恢复；自动清理 1000 slot 之前的旧记录

### Reorg 三件（R1+R2+R3）

* **R1**: rewind 时清理 height>target 的 slash 记录 + 重新应用保留的
* **R2**: rewind 把被回滚区块的交易塞回 mempool（不再永久丢失支付）
* **R3**: 等高度不同 hash 的竞争块——lower hash wins（确定性 tie-breaker），触发 reorg

### 工具

* `scripts/explorer.py` — 区块浏览器（本地或 HTTP）
* `scripts/faucet.py` — 生态 faucet 转账（运营方专用）
* `scripts/peer.py` — peer 管理
* `docs/DEPLOY.md` — 完整部署指南

### 测试网现状

* 真量子机已实战出块（IBM Heron r2，slot 1438 + 1441）
* 单节点完整跑通：创世 → 出块 → 抵押 → 转账 → 验证
* 双节点同步通过（等高度时 fork choice tie-breaker）
* 协议参数：n=30 比特，深度 12，每块 4096 采样
* 量子接口耗时：~10 秒/块（IBM 队列+网络+执行），经典验证 ~60 秒/块（Aer 状态向量）

### v1.0 主网剩余工作

* n=36 升级（彻底防本地模拟，需配 sentinel 验证或 ZK proof）
* Schnorr-VRF（不可预测性证明）
* fraud proof 系统（链上 slashing 评议）
* 区块浏览器 Web UI

---

## v0.1.0 — 2026-05-01

第一个公开版本：BTCQ（Bitcoin Quantum）。

### 共识：PoQ-Stake

* **Proof-of-Quantumness Stake**：抵押 + 量子证明双重门槛
* 出块流程：VRF 选举 → 量子机执行 RCS 电路 → 验证 XEB → 上链
* 单块量子时间 ≈ 1 秒，远低于 PoW 矿场的能源消耗
* Bootstrap 开放挖矿期：头 144 块无需抵押（解决鸡生蛋问题）
* MIN_STAKE = 1 BTCQ，UNSTAKE_DELAY = 100 块

### 量子证明电路

* n=24 比特，深度 8，每块 1024 采样
* 经典模拟需 256 MB 状态向量、5–10 秒
* 量子（IBM Heron r2 / Quantinuum H2）约 0.3 秒电路 + 网络往返 ≈ 1 秒接口
* 量子优势倍率：5–30×

### 经济模型（完全照搬 Bitcoin）

* 总量 21,000,000 BTCQ
* 创世第 1 块奖励 50 BTCQ
* 每 210,000 块减半（首次因 bootstrap 提前约 5 个月）
* 创世时间：2026-04-30 00:00 UTC

### 出块节奏（bootstrap → 稳态）

* 头 15 天：60 秒/块
* 第 15–45 天：60 → 600 秒线性
* 之后：600 秒/块（BTC 节奏）
* 难度调整：bootstrap 期 144 块/次，稳态 2016 块/次

### 转账系统（账户模型）

* Transaction 三种 kind：transfer / stake / unstake
* 签名：secp256k1 over keccak256
* nonce 防重放
* balance_of / staked_of / cooling_of 三栏并行

### 工具与脚本

* `scripts/init_chain.py` — 初始化链
* `scripts/new_wallet.py` — 生成钱包
* `scripts/propose.py` — 出块（PoQ-Stake）
* `scripts/stake.py` — 抵押 / 解抵押 / 状态查询
* `scripts/send.py` — 转账
* `scripts/mempool.py` — 查看待打包交易
* `scripts/verify.py` — 验证整条链
* `scripts/balance.py` — 余额查询
* `scripts/stats.py` — 链整体状态

### 文档

* 完整中文白皮书
* 协议技术规范
* 出块指南（PoQ-Stake 流程）
* FAQ
* 经典攻击成本分析

### 历史

本版本之前曾以 "QXEB" 名义发布过纯 PoW 设计。
v0.1.0 重构为 PoQ-Stake 并改名 BTCQ，原因：
* PoW 量子配额成本高（每块数十秒）
* PoS 经济安全 + 量子门槛是更好的组合
* "比特币量子"叙事更直观

旧 QXEB 设计的 commit 历史保留在 git 中可追溯。
