# BTCQ 出块指南（PoQ-Stake）

完整的从 0 到出第一个 BTCQ 区块的指南。

---

## 1. 你需要什么

* Python 3.10+
* 一台能联网的电脑（CPU 4 核 + 16 GB 内存即可）
* **量子计算资源（任选其一）**：
  - **IBM Quantum 账号**（推荐，免费 600 秒/月，每块约 1 秒，够出几百个块）
  - Quantinuum API key
  - IonQ API key
  - 自有量子硬件 + Qiskit/Cirq SDK
* 或者：仅做经典模拟（`--classical`），用来验证流程

---

## 2. 安装

```bash
git clone https://github.com/douyamv/btcq.git
cd btcq
pip install -r requirements.txt
```

---

## 3. 配置 IBM Quantum 访问（推荐路径）

### 3.1 注册免费账号

去 https://quantum.ibm.com 用邮箱注册，获取免费 600 秒/月配额。

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
# 写入创世区块
python scripts/init_chain.py

# 生成出块钱包（私钥保存在 wallet.json，请备份！）
python scripts/new_wallet.py
# → 输出地址 0x...
```

---

## 5. 出块（Bootstrap 开放挖矿期，前 144 块）

创世后头 144 个区块为"bootstrap 开放挖矿"，**任何持有量子机的人都能出块，无需抵押**。这是为了解决"鸡生蛋"问题——必须先有人挖到币才能抵押。

### 5.1 经典模拟出块（先这个，验证流程）

```bash
python scripts/propose.py --classical
```

预计 1–10 秒出一个块（电路 n=24 经典模拟很快）。

### 5.2 真量子机出块

```bash
python scripts/propose.py --quantum --backend ibm_marrakesh
```

流程：
1. 客户端连接 ibm_marrakesh
2. 生成本块的确定性 RCS 电路（n=24, depth=8）
3. 提交 1024 shots 到量子机
4. 量子机执行（~0.3 秒），返回采样
5. 客户端经典验证 XEB（~1 秒）
6. 若 XEB ≥ 当前阈值，区块上链

**单次出块配额成本**: 约 1 秒（IBM Open Plan 600 秒/月够 600+ 块）。

**单次出块挂钟时间**: 约 5–60 秒（取决于队列）。

### 5.3 持续出块

```bash
while true; do
    python scripts/propose.py --quantum --backend ibm_marrakesh
    sleep 60   # 等下一个 1 分钟出块时间
done
```

或写成系统服务、cron 任务、tmux 持久会话。

---

## 6. 抵押（出第 145 块及之后必须）

```bash
# 抵押 5 BTCQ（需有 ≥ 5 BTCQ 流动余额）
python scripts/stake.py --amount 5

# 查看抵押状态
python scripts/stake.py --status

# 申请解抵押 5 BTCQ（需冷却 100 块后才回到流动余额）
python scripts/stake.py --unstake --amount 5
```

抵押交易通过 STAKE_VAULT (`0x000...0001`) 完成。出块时矿工会自动从 mempool 选合法 stake/unstake 打包。

---

## 7. 转账

```bash
# 创建一笔转账
python scripts/send.py --to 0xRECIPIENT --amount 5

# 查看待打包交易
python scripts/mempool.py

# 下次出块自动打包
python scripts/propose.py --quantum
```

设计要点：
* **账户模型**（类 Ethereum）：每个地址有余额 + nonce
* **三种 kind**：transfer、stake、unstake
* **nonce 防重放**：每笔交易使用 sender 当前 nonce
* **签名**：secp256k1 over keccak256(unsigned_tx)
* **无手续费**（v0.5 引入 gas）
* **本地 mempool**：`chain_data/mempool.json`

---

## 8. 验证你的链

```bash
python scripts/verify.py            # 完整验证（含 XEB 重算）
python scripts/verify.py --no-xeb   # 仅验签名/结构（更快但更弱）
```

输出 `✅ 全链 X 个区块全部合法` 表示一切正常。

---

## 9. 查询余额与状态

```bash
python scripts/balance.py 0x你的地址
python scripts/stake.py --status     # 抵押 + 冷却 + 流动余额一起看
python scripts/stats.py              # 链整体状态
```

---

## 10. 故障排查

### "RuntimeError: 量子证明 XEB 未达阈值"

* 检查后端在线：`backend.status()`
* 检查电路保真度：Heron r2 在 n=24/depth=8 应轻松达 XEB > 0.6
* 检查难度阈值是否过高（极不可能）

### "RuntimeError: 抵押不足，无资格出块"

* 头 144 块是开放期，按理不会触发
* 之后必须先 stake：`python scripts/stake.py --amount 1`

### "Qiskit 转译失败 / 拓扑不兼容"

确保 backend.basis_gates 包含 H/S/T/CZ。如果只支持 RZZ/SX 等，转译会自动展开。

### "私钥丢了怎么办"

币与 wallet.json 绑定。**丢失即归零**——务必备份。

---

## 11. 安全建议

* `wallet.json` 不要提交到 git（已加入 .gitignore）
* 长期持币用冷钱包：导出私钥 → 物理隔离设备保存
* 链上签名格式与 Ethereum 一致

---

## 12. 进阶

* [PROTOCOL.md](PROTOCOL.md) — 协议字段细节
* [WHITEPAPER.md](WHITEPAPER.md) — 经济模型与路线图
* [FAQ.md](FAQ.md) — 常见疑问
* [CLASSICAL_ATTACK_ANALYSIS.md](CLASSICAL_ATTACK_ANALYSIS.md) — 量子优势数据

出块愉快。
