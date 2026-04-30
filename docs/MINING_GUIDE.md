# QXEB 挖矿指南

完整的从 0 到挖出第一个 QXEB 区块的指南。

---

## 1. 你需要什么

* Python 3.10+
* 一台能联网的电脑（CPU 4 核 + 16 GB 内存即可，验证器需要 GPU 更佳）
* **量子计算资源（任选其一）**：
  - **IBM Quantum 账号**（推荐，免费额度 600 秒/月够挖几百个块）
  - Quantinuum API key
  - IonQ API key
  - 自有量子硬件 + Qiskit/Cirq SDK
* 或者：仅做经典模拟挖矿（`--classical`），用来验证流程，无量子优势

---

## 2. 安装

```bash
git clone https://github.com/douyamv/qxeb.git
cd qxeb
pip install -r requirements.txt
```

---

## 3. 配置 IBM Quantum 访问（推荐路径）

### 3.1 注册免费账号

去 https://quantum.ibm.com 用邮箱注册，获取免费的 600 秒/月配额。

### 3.2 获取 API Token

登录后 → Account → Generate API Token，复制保存。

### 3.3 一次性写入凭据

```python
from qiskit_ibm_runtime import QiskitRuntimeService
QiskitRuntimeService.save_account(
    channel="ibm_quantum_platform",
    token="你的 token",
    overwrite=True,
)
```

### 3.4 验证

```python
from qiskit_ibm_runtime import QiskitRuntimeService
svc = QiskitRuntimeService()
print([b.name for b in svc.backends(simulator=False, operational=True)])
# 应输出 ['ibm_fez', 'ibm_marrakesh', 'ibm_kingston'] 之类
```

---

## 4. 创世 + 钱包

```bash
# 写入创世区块（每个矿工本地都做一次）
python scripts/init_chain.py

# 生成你的矿工钱包（私钥保存在 wallet.json，请备份！）
python scripts/new_wallet.py
# → 输出地址 0x...
```

---

## 5. 挖矿

### 5.1 经典模拟挖矿（先这个）

不烧量子配额，验证一下整条流水线通不通：

```bash
python scripts/mine.py --classical
```

预计 10–60 秒挖出一个区块（v0.1 难度极低）。看到 `✅ 区块挖出！` 就成功了。

### 5.2 真量子机挖矿

```bash
python scripts/mine.py --quantum --backend ibm_marrakesh
```

流程：
1. 客户端连接 ibm_marrakesh
2. 生成本次区块的随机电路（30 比特 / 深度 14）
3. 提交 4096 shots 到量子机
4. 量子机执行（约 0.1 秒），返回采样
5. 客户端经典模拟同一电路，计算 XEB 分数
6. 若 XEB ≥ 当前难度，区块合法 → 写入链

**单次挖矿配额成本**: 约 0.5–1 秒（Open Plan 600 秒/月够挖 600+ 个块）。

**单次挖矿挂钟时间**: 约 30–120 秒，取决于队列。

### 5.3 持续挖矿

```bash
# 简易循环
while true; do
    python scripts/mine.py --quantum --backend ibm_marrakesh
done
```

或者写成系统服务、cron 任务、tmux 持久会话。

---

## 6. 验证你的链

```bash
python scripts/verify.py
```

输出 `✅ 全链 X 个区块全部合法` 表示一切正常。

跳过 XEB 重计算（更快但更弱）：

```bash
python scripts/verify.py --no-xeb
```

---

## 7. 查询余额

```bash
python scripts/balance.py 0x你的地址
python scripts/stats.py            # 链整体状态：高度、阶段、难度、总供应等
```

每挖出一个区块，你的地址会拿到 50 QXEB（v0.1 第一阶段）。

---

## 7b. 转账（v0.1 已支持）

挖到币之后，可以转给别人：

```bash
# 1. 创建一笔交易（金额单位 QXEB，支持小数）
python scripts/send.py --to 0xRECIPIENT_ADDR --amount 5

# 2. 查看待打包交易
python scripts/mempool.py

# 3. 下次挖矿自动打包它（mempool 中的交易会被矿工选入新块）
python scripts/mine.py --quantum
```

设计要点：

* **账户模型**（类 Ethereum）：每个地址有余额 + nonce
* **nonce 防重放**：每笔交易使用 sender 当前 nonce，发出后递增
* **签名**：secp256k1 over keccak256(unsigned_tx)
* **无手续费**（v0.5 引入 gas）
* **本地 mempool**：`chain_data/mempool.json`，单节点本地池
* **多账户场景**：`new_wallet.py alice.json` / `new_wallet.py bob.json` 可生成多个

---

## 8. 故障排查

### "RuntimeError: 量子挖矿 5 次未达难度"

* 检查后端真的在线：`backend.status()`
* 检查电路保真度：Heron r2 在深度 14 应轻松达到 XEB > 0.4
* 难度调整可能过激，用 `--max-attempts 20` 多试几次

### "Qiskit 转译失败 / 拓扑不兼容"

确保 backend.basis_gates 包含 H/S/T/CZ。如果只支持 RZZ/SX 等，转译会自动展开但深度会增加。

### "经典验证 XEB 太慢（>1 分钟）"

* 升级到 GPU：用 `qiskit-aer-gpu` 或 `cuquantum`
* 临时跳过验证：开发期可用 `--no-xeb`

### "私钥丢了怎么办"

挖到的币与 wallet.json 绑定。**丢失即归零**——务必备份。

---

## 9. 安全建议

* `wallet.json` 不要提交到 git（已加入 .gitignore）
* 长期持币用冷钱包：导出私钥 → 物理隔离设备保存
* 链上签名格式与 Ethereum 一致，Metamask 等钱包未来可直接对接

---

## 10. 进阶

* 看 [PROTOCOL.md](PROTOCOL.md) 了解每个字段
* 看 [WHITEPAPER.md](WHITEPAPER.md) 了解经济模型与路线图
* 看 [FAQ.md](FAQ.md) 解答常见疑问

挖矿愉快。
