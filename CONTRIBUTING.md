# 贡献指南

欢迎参与 BTCQ。先看 [白皮书](docs/WHITEPAPER.md) 与 [协议规范](docs/PROTOCOL.md)，再考虑贡献方向。

## 优先方向

1. **GPU/张量网络验证器**（v1.0 关键）
   * 在不损失正确性的前提下把 XEB 验证从 CPU 30 秒压到 GPU 几秒
   * 参考 cuQuantum、qiskit-aer-gpu、quimb 等

2. **多硬件矿工后端**
   * IonQ、Quantinuum、Atom Computing、Google Quantum AI 适配器
   * 接口模式参照 `btcq/miner.py::mine_ibm_quantum`

3. **P2P 网络层**（v0.5 蓝图）
   * 轻量节点发现、区块/交易广播
   * libp2p 或自研，不强求

4. **测试向量与一致性测试**
   * `tests/test_circuit.py`、`tests/test_xeb.py`、`tests/test_block_serialize.py`
   * 任何独立实现需通过

5. **协议 / 安全审计**
   * 找密码学 bug、共识漏洞、序列化歧义

## 贡献流程

1. Fork → branch → 提 PR
2. 协议级修改请先开 Issue 讨论
3. 通过本地 `python scripts/verify.py` 与 pytest

## 行为准则

技术、坦率、就事论事。不接受人身攻击与歧视。
