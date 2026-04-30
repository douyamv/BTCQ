# CHANGELOG

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
