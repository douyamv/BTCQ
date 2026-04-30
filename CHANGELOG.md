# CHANGELOG

## v0.1.0 — 2026-05-01

第一个公开版本。

* 创世区块协议固化（`GENESIS_TIMESTAMP=1777507200`，2026-04-30 00:00 UTC）
* 电路参数 `(n=36, depth=14, samples=8192)` — 经典笔记本和工作站完全无法参与挖矿
* XEB 阈值 `0.10` 起步
* **Bootstrap 加速期**：头 15 天 60 秒/块、之后 30 天线性升至 600 秒/块、再之后稳态 600 秒/块
* 难度调整：bootstrap 期 144 块/次，稳态 2016 块/次
* 区块奖励 50 QXEB / 块，每 210000 块减半（首次因 bootstrap 提前约 5 个月）
* 总量上限 21,000,000 枚
* 经典模拟 + IBM Quantum 双矿工实现
* 验证器：n≤31 用精确状态向量；n>31 用 Aer MPS（高 bond_dim）
* 钱包：secp256k1 + Ethereum 地址格式
* **转账系统已上线**：Transaction（账户模型）+ Mempool + scripts/send.py + scripts/mempool.py
  - 签名：secp256k1 over keccak256
  - nonce 防重放
  - balance_of/nonce_of 同时考虑挖矿奖励与转账收支
  - block 携带 transactions_root 与 tx 列表，验证器全程校验
* 完整中文白皮书 + 协议规范 + 挖矿指南 + FAQ + 经典攻击成本分析
