# QXEB 协议技术规范 v0.1

本文件是 QXEB 协议的规范级描述。任何独立实现必须严格遵循以下规则才能与参考实现互操作。

---

## 1. 常量与参数

```
PROTOCOL_VERSION       = 1
GENESIS_TIMESTAMP      = 1777507200     # 2026-04-30 00:00:00 UTC
GENESIS_PREV_HASH      = 0x00..00 (32 bytes)
TOTAL_SUPPLY           = 21_000_000 * 10^8   # 单位：satoshi-like 原子单位
INITIAL_BLOCK_REWARD   = 50 * 10^8
HALVING_INTERVAL       = 210_000        # 区块数（按块数减半，与 BTC 同）

# 出块节奏（bootstrap 加速 → 稳态）
TARGET_BLOCK_TIME_BOOTSTRAP = 60        # 头 15 天每块 60 秒
TARGET_BLOCK_TIME_FINAL     = 600       # 45 天后稳态每块 600 秒
BOOTSTRAP_FAST_DURATION     = 15 * 86400  # 15 天
BOOTSTRAP_RAMP_DURATION     = 30 * 86400  # 之后 30 天 60→600 线性升

# 难度调整
DIFFICULTY_WINDOW           = 144       # bootstrap 期：每 144 块（≈2.4 小时）调整
DIFFICULTY_WINDOW_FINAL     = 2016      # 稳态期：每 2016 块（≈2 周）调整
DIFFICULTY_MIN_FACTOR       = 0.25
DIFFICULTY_MAX_FACTOR       = 4.0
INITIAL_XEB_THRESHOLD       = 0.10      # F_xeb 阈值

# v0.1 电路参数
CIRCUIT_N_QUBITS       = 36
CIRCUIT_DEPTH          = 14
CIRCUIT_N_SAMPLES      = 8192

# 哈希
ALL_HASHES_USE         = keccak256
ADDRESS_FORMAT         = secp256k1 公钥的 keccak256 后 20 字节（同 Ethereum）
```

---

## 2. 区块格式

### 2.1 字段（按规范序列化顺序）

```
[
  version           : uint16
  height            : uint64
  prev_hash         : bytes32
  timestamp         : uint64
  miner_address     : bytes20
  n_qubits          : uint8
  depth             : uint8
  n_samples         : uint32
  difficulty        : float64 (IEEE-754 binary64)
  nonce             : uint64
  samples_root      : bytes32       # samples 的 keccak256 Merkle 根
  xeb_score         : float64       # 矿工声明值
  transactions_root : bytes32       # transactions 的 keccak256 Merkle 根，无交易为 0
  tx_count          : uint32        # 交易数量
  miner_signature   : bytes65       # secp256k1 签名 (r || s || v)
]
```

区块体（block body）另含 `samples: List[int]` 与 `transactions: List[Transaction]`，长度分别由 `n_samples` 和 `tx_count` 字段决定。

### 2.1.1 Transaction 字段

```
Transaction {
  sender    : bytes20      # 发送方地址
  recipient : bytes20      # 接收方地址
  amount    : uint128      # 原子单位（10^-8 QXEB）
  nonce     : uint64       # 发送方账户 nonce（必须严格等于其当前 nonce）
  signature : bytes65      # secp256k1(keccak256(sender||recipient||amount||nonce))
}
tx_hash := keccak256(unsigned_bytes)
```

**验证规则**：

1. signature 由 sender 私钥对 tx_hash 签名
2. nonce 必须等于 sender 在前序链 + 本块前序交易后的 nonce
3. amount ≥ 0
4. sender 余额（在前序状态 + 本块前序交易扣减后）≥ amount
5. 同一区块内不允许同一 (sender, nonce) 重复

samples 不直接进入区块头，而通过 `samples_root` 承诺，单独以列表形式附加在区块体（block body）。

### 2.2 区块哈希

```python
header_bytes = rlp_encode([
    version, height, prev_hash, timestamp, miner_address,
    n_qubits, depth, n_samples, difficulty, nonce,
    samples_root, xeb_score
])  # 不含 miner_signature
block_hash = keccak256(header_bytes)
```

`miner_signature` = secp256k1.sign(`block_hash`, miner_private_key)。

### 2.3 samples 编码

每个 sample 是长度为 `n_qubits` 比特的位串，按 little-endian 字节序打包，向上取整到字节边界。即 n_qubits=30 时每个 sample 占 4 字节。

```
samples_root = merkle_root( [keccak256(s_i) for s_i in samples] )
```

---

## 3. 电路生成（确定性）

输入：`circuit_seed` (bytes32)。
输出：一个 `n_qubits`-比特、`depth`-层的随机电路 U。

### 3.1 PRG

使用 ChaCha20 流密码作为伪随机源：

```
key   = circuit_seed[:32]
nonce = b"\x00" * 12
prg   = ChaCha20(key, nonce).keystream()
```

每次需要随机字节时从 `prg` 顺序读取。

### 3.2 电路构造

```
for layer in range(depth):
    # 单比特门层
    for q in range(n_qubits):
        gate_idx = read_byte(prg) % 3
        apply [H, S, T][gate_idx] on qubit q
    # 双比特门层（CZ 砖墙模式）
    if layer % 2 == 0:
        for q in range(0, n_qubits - 1, 2):
            apply CZ on (q, q+1)
    else:
        for q in range(1, n_qubits - 1, 2):
            apply CZ on (q, q+1)
# 最终测量所有比特
```

此电路具备 BFNV19 论证所需的"反集中（anti-concentration）"性质，且经典模拟代价随 n 指数增长。

### 3.3 circuit_seed 计算

```
preimage = prev_hash || nonce_le_8bytes || miner_address
circuit_seed = keccak256(preimage)
```

---

## 4. XEB 计算

### 4.1 定义（Linear XEB）

```
F_xeb = 2^n * mean_{x in samples} [ p_U(x) ] - 1
```

其中：
* `p_U(x) = |⟨x|U|0⟩|^2`，是 U 作用于全 0 初态后量子态在比特串 x 上的精确概率
* `mean` 是对 `n_samples` 个采样位串的平均

### 4.2 取值参考

| 采样源 | 期望 F_xeb |
|---|---|
| 完美量子电路（无噪声） | ≈ 1.0 |
| 实际 NISQ 量子机（IBM Heron r2, depth 14, n=36 转译后 ~163 个 RZZ） | ≈ 0.20 – 0.40 |
| 经典均匀采样 | ≈ 0.0 |
| 经典从 p_U 直接采样（"作弊"） | ≈ 1.0 |

**注**：经典作弊需要先经典模拟 U，时间已经超过量子矿工。

### 4.3 验证流程

```python
def verify_block(block, prev_block):
    # 1. 结构与签名
    assert verify_signature(block.miner_signature, header_hash(block), block.miner_address)
    # 2. 链接
    assert block.prev_hash == hash(prev_block)
    assert block.height == prev_block.height + 1
    # 3. 时间戳合理（不超过当前时间 + 2小时，不早于 prev）
    assert prev_block.timestamp < block.timestamp <= now() + 7200
    # 4. 难度
    expected_D = compute_difficulty_at(block.height)
    assert abs(block.difficulty - expected_D) < 1e-9
    # 5. 电路参数符合协议（v0.1 固定）
    assert block.n_qubits == 30 and block.depth == 14 and block.n_samples == 4096
    # 6. samples merkle root
    assert merkle_root(block.samples) == block.samples_root
    # 7. 重新生成电路
    seed = keccak256(block.prev_hash + nonce_bytes(block.nonce) + block.miner_address)
    U = build_circuit(seed, block.n_qubits, block.depth)
    # 8. 经典模拟（v0.1 在 GPU 上 < 30 秒）
    state = simulate(U, n_qubits=block.n_qubits)
    # 9. 计算每个 sample 的 p_U(x)
    probs = [abs(state[bitstring_to_int(x)])**2 for x in block.samples]
    F_xeb = 2**block.n_qubits * np.mean(probs) - 1
    # 10. 与声明对比
    assert abs(F_xeb - block.xeb_score) < 1e-6
    # 11. 工作量
    assert F_xeb >= block.difficulty
```

---

## 5. 难度调整

调整窗口与期望出块时间在 bootstrap 期和稳态期不同：

```python
def target_block_time_at(seconds_since_genesis):
    if seconds_since_genesis < BOOTSTRAP_FAST_DURATION:        # 0–15 天
        return TARGET_BLOCK_TIME_BOOTSTRAP                      # 60
    if seconds_since_genesis < BOOTSTRAP_FAST_DURATION + BOOTSTRAP_RAMP_DURATION:  # 15–45 天
        progress = (seconds_since_genesis - BOOTSTRAP_FAST_DURATION) / BOOTSTRAP_RAMP_DURATION
        return TARGET_BLOCK_TIME_BOOTSTRAP + (TARGET_BLOCK_TIME_FINAL - TARGET_BLOCK_TIME_BOOTSTRAP) * progress
    return TARGET_BLOCK_TIME_FINAL                              # 600

def difficulty_window_at(seconds_since_genesis):
    return DIFFICULTY_WINDOW if seconds_since_genesis < (BOOTSTRAP_FAST_DURATION + BOOTSTRAP_RAMP_DURATION) else DIFFICULTY_WINDOW_FINAL

def compute_difficulty_at(height):
    if height == 0:
        return INITIAL_XEB_THRESHOLD
    prev = blocks[height - 1]
    seconds_since_genesis = max(0, prev.timestamp - GENESIS_TIMESTAMP)
    window_size = difficulty_window_at(seconds_since_genesis)
    if height % window_size != 0:
        return prev.difficulty
    # 调整点
    window = blocks[height - window_size : height]
    actual_time = window[-1].timestamp - window[0].timestamp
    # 期望时间：把窗口内每块"当时应有的"目标间隔加起来
    expected_time = sum(target_block_time_at(b.timestamp - GENESIS_TIMESTAMP) for b in window)
    factor = clip(actual_time / max(expected_time, 1), 0.25, 4.0)
    new_D = prev.difficulty / factor   # 时间越短 → factor 小 → 难度越高
    return clip(new_D, 0.01, 0.95)
```

**为什么 bootstrap 期需要更短的窗口**: 60 秒/块下，2016 块 = 33.6 小时——发现"挖太快"已经过了一天多。改用 144 块 = 2.4 小时，能在小时级响应矿工人数变化。

---

## 6. 经济学规则

### 6.1 区块奖励

```python
def block_reward(height):
    halvings = height // HALVING_INTERVAL
    if halvings >= 64:
        return 0
    return INITIAL_BLOCK_REWARD >> halvings
```

### 6.2 创世区块

创世区块是协议预定义、无人挖出，包含一段不可篡改的"创世铭文"：

```
height       = 0
prev_hash    = 0x00..00
timestamp    = GENESIS_TIMESTAMP
miner_address= 0x00..00
nonce        = 0
samples      = []
xeb_score    = 0.0
miner_signature = 0x00..00
genesis_message = "QXEB Genesis: 量子算力第一次有了价格 — 2026-04-30"
```

参考实现已在 `data/genesis.json` 中固化。

### 6.3 Coinbase

每个区块的 Coinbase 交易隐式将 `block_reward(height)` 个原子单位发往 `miner_address`。
v0.1 已支持普通转账交易；区块通过 `transactions` 字段携带它们。
v0.5 将引入手续费机制（gas）和 P2P 广播。

---

## 7. P2P 协议（v0.5+ 引入）

v0.1 暂不规定网络协议。各矿工运行本地链。
v0.5 将引入：
- TCP/QUIC 节点发现
- 区块/交易广播 protobuf 消息
- 最长合法链共识规则

---

## 8. 钱包与地址

* 私钥：32 字节 secp256k1 标量
* 公钥：64 字节未压缩
* 地址：keccak256(public_key)[12:]，0x 前缀十六进制（20 字节）

完全兼容 Ethereum 地址格式，方便用户使用现有钱包基础设施。

---

## 9. 测试向量

参考实现 `qxeb/tests/` 含以下测试向量：

* `test_circuit_seed.json`: 给定 (prev_hash, nonce, miner) → circuit_seed
* `test_circuit_build.json`: 给定 seed → 电路门序列
* `test_xeb.json`: 给定 (U, samples) → F_xeb
* `test_block_serialize.json`: 区块 RLP 编码 round-trip

任何 QXEB 实现必须通过全部测试向量才被认为兼容。

---

## 10. 升级路径

协议参数（`CIRCUIT_N_QUBITS`、`CIRCUIT_DEPTH`、`CIRCUIT_N_SAMPLES` 等）可通过硬分叉升级。每次升级需在区块头 `version` 字段递增并在共识层激活。

v1.0 计划升级到 (n=40, d=20, samples=8192)，预计 2026 Q4 通过社区投票确定激活高度。

---

*Last updated: 2026-04-30. 任何修改通过 git 历史可追溯。*
