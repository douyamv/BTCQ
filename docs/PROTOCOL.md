# BTCQ 协议技术规范 v0.1

本文件是 BTCQ（Bitcoin Quantum）协议的规范级描述。任何独立实现必须严格遵循以下规则才能与参考实现互操作。

---

## 1. 常量

```
PROTOCOL_VERSION       = 1
TICKER                 = "BTCQ"
GENESIS_TIMESTAMP      = 1777507200     # 2026-04-30 00:00:00 UTC
GENESIS_PREV_HASH      = 0x00..00 (32 bytes)
GENESIS_MESSAGE        = "BTCQ Genesis: 量子时代的第一枚比特币 — 2026-04-30"
TOTAL_SUPPLY           = 21_000_000 * 10^8
INITIAL_BLOCK_REWARD   = 50 * 10^8
HALVING_INTERVAL       = 210_000

# 出块节奏
TARGET_BLOCK_TIME_BOOTSTRAP = 60        # 头 15 天每块 60 秒
TARGET_BLOCK_TIME_FINAL     = 600       # 45 天后稳态每块 600 秒
BOOTSTRAP_FAST_DURATION     = 15 * 86400
BOOTSTRAP_RAMP_DURATION     = 30 * 86400

# 共识
MIN_STAKE              = 1 * 10^8       # 最低抵押 1 BTCQ
UNSTAKE_DELAY_BLOCKS   = 100
SLASH_RATIO            = 0.1
BOOTSTRAP_OPEN_BLOCKS  = 144            # 头 144 块开放挖矿（无需抵押）

# 量子证明电路
CIRCUIT_N_QUBITS       = 24
CIRCUIT_DEPTH          = 8
CIRCUIT_N_SAMPLES      = 1024
CIRCUIT_SINGLE_GATES   = ("h", "s", "t")

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
  proposer_address  : bytes20         # PoQ-Stake 出块人地址
  n_qubits          : uint8
  depth             : uint8
  n_samples         : uint32
  difficulty        : float64 (IEEE-754 binary64)
  nonce             : uint64           # 保留字段（PoQ-Stake 中固定为 0）
  samples_root      : bytes32
  xeb_score         : float64
  transactions_root : bytes32
  tx_count          : uint32
  proposer_signature: bytes65
]
```

区块体（block body）另含 `samples: List[int]` 与 `transactions: List[Transaction]`，长度由 `n_samples` 与 `tx_count` 字段决定。

### 2.2 Transaction 字段

```
Transaction {
  sender    : bytes20
  recipient : bytes20
  amount    : uint128
  nonce     : uint64
  kind      : string         # "transfer" | "stake" | "unstake"
  signature : bytes65
}
tx_hash := keccak256(unsigned_bytes)
```

`unsigned_bytes` 序列化顺序：
```
sender || recipient || u128(amount, big) || u64(nonce, big) || u8(len(kind)) || kind_utf8
```

### 2.3 区块哈希

```python
header_bytes = serialize([version, height, prev_hash, timestamp, proposer_address,
                           n_qubits, depth, n_samples, difficulty, nonce,
                           samples_root, xeb_score, transactions_root, tx_count])
block_hash = keccak256(header_bytes)
```

`proposer_signature = secp256k1.sign(block_hash, proposer_private_key)`。

### 2.4 samples 编码

每个 sample 是 `n_qubits` 比特的位串，按大端字节序打包，向上取整到字节边界。n_qubits=24 时每个 sample 占 3 字节。

```
samples_root = merkle_root([keccak256(s_i) for s_i in samples])
```

---

## 3. 电路生成（确定性）

输入：`circuit_seed = keccak256(prev_hash || height_le_8 || proposer_address)`。

注意 PoQ-Stake 下电路 seed **由 height 决定，不再有矿工 nonce**——出块人没有"调整 nonce 反复试"的余地，只能"做或不做"。

### 3.1 PRG

```
key   = circuit_seed[:32]
nonce = b"\x00" * 12
prg   = ChaCha20(key, nonce).keystream()
```

### 3.2 电路构造

```
for layer in range(depth):                       # depth = 8
    for q in range(n_qubits):                    # n_qubits = 24
        gate_idx = read_byte(prg) % 3
        apply [H, S, T][gate_idx] on qubit q
    if layer % 2 == 0:
        for q in range(0, n_qubits - 1, 2):
            apply CZ on (q, q+1)
    else:
        for q in range(1, n_qubits - 1, 2):
            apply CZ on (q, q+1)
# 最终测量所有比特
```

---

## 4. XEB 计算

### 4.1 定义（Linear XEB）

```
F_xeb = 2^n * mean_{x in samples} [ p_U(x) ] - 1
```

* `p_U(x) = |⟨x|U|0⟩|²`，是 U 作用于全 0 初态后量子态在比特串 x 上的精确概率
* `mean` 对 `n_samples` 个采样位串平均

### 4.2 取值参考

| 采样源 | 期望 F_xeb |
|---|---|
| 完美量子电路（无噪声） | ≈ 1.0 |
| 实际 NISQ（IBM Heron r2, depth 8 转译后 ~50 个 RZZ）| ≈ 0.5 – 0.8 |
| 经典均匀采样 | ≈ 0.0 |
| 经典从 p_U 直接采样 | ≈ 1.0（但要 5–10 秒模拟） |

---

## 5. 难度调整

```python
def target_block_time_at(seconds_since_genesis):
    if seconds_since_genesis < BOOTSTRAP_FAST_DURATION:        # 0–15 天
        return TARGET_BLOCK_TIME_BOOTSTRAP                      # 60
    if seconds_since_genesis < BOOTSTRAP_FAST_DURATION + BOOTSTRAP_RAMP_DURATION:
        progress = (seconds_since_genesis - BOOTSTRAP_FAST_DURATION) / BOOTSTRAP_RAMP_DURATION
        return TARGET_BLOCK_TIME_BOOTSTRAP + (TARGET_BLOCK_TIME_FINAL - TARGET_BLOCK_TIME_BOOTSTRAP) * progress
    return TARGET_BLOCK_TIME_FINAL                              # 600

def difficulty_window_at(seconds_since_genesis):
    return 144 if seconds_since_genesis < (BOOTSTRAP_FAST_DURATION + BOOTSTRAP_RAMP_DURATION) else 2016

def compute_difficulty_at(height):
    if height == 0: return INITIAL_XEB_THRESHOLD
    prev = blocks[height - 1]
    secs = max(0, prev.timestamp - GENESIS_TIMESTAMP)
    window_size = difficulty_window_at(secs)
    if height % window_size != 0:
        return prev.difficulty
    window = blocks[height - window_size : height]
    actual = window[-1].timestamp - window[0].timestamp
    expected = sum(target_block_time_at(b.timestamp - GENESIS_TIMESTAMP) for b in window)
    factor = clip(actual / max(expected, 1), 0.25, 4.0)
    new_D = prev.difficulty / factor    # 时间越短 → factor 小 → 难度越高
    return clip(new_D, 0.01, 0.95)
```

---

## 6. PoQ-Stake 共识

### 6.1 抵押状态

抵押状态由历史交易确定：

```python
def stake_state_at(blocks):
    active = {}            # address -> staked amount
    cooling = []           # (release_height, address, amount)
    for blk in blocks:
        cooling = [(h, a, amt) for (h, a, amt) in cooling if h > blk.height]
        for tx in blk.transactions:
            if tx.kind == "stake":
                active[tx.sender] = active.get(tx.sender, 0) + tx.amount
            elif tx.kind == "unstake":
                if active.get(tx.sender, 0) >= tx.amount:
                    active[tx.sender] -= tx.amount
                    cooling.append((blk.height + UNSTAKE_DELAY_BLOCKS, tx.sender, tx.amount))
    return active
```

### 6.2 出块人选举（VRF）

```python
def select_proposer(prev_hash, height, stake_map):
    eligible = [(a, s) for a, s in stake_map.items() if s >= MIN_STAKE]
    if not eligible: return None
    total = sum(s for _, s in eligible)
    seed = keccak256(prev_hash || u64(height, big))
    rnd = uint64(seed[:8]) % total
    cum = 0
    for addr, s in eligible:
        cum += s
        if rnd < cum: return addr
```

v0.1 的 VRF 是 keccak 派生的伪随机；v0.5 升级为 Schnorr-VRF。

### 6.3 区块验证流程

```python
def verify_block(block, prev, expected_difficulty, chain_state):
    # 1. 协议版本 / 高度 / prev_hash / 时间戳 / 难度 / 电路参数（与 v0.5 之前一致）
    ...
    # 2. samples_root / transactions_root
    ...
    # 3. 出块人签名
    assert verify_sig(block.block_hash(), block.proposer_signature, block.proposer_address)
    # 4. PoQ-Stake：出块人抵押 ≥ MIN_STAKE（bootstrap 期除外）
    if block.height > BOOTSTRAP_OPEN_BLOCKS:
        stake = stake_state_at(blocks_before(block.height))
        assert stake.get(block.proposer_address, 0) >= MIN_STAKE
        # v0.5 起：还需检查 VRF 选举结果与 proposer_address 一致
    # 5. 量子证明：重算电路 + XEB
    seed = keccak256(block.prev_hash || u64(block.height) || block.proposer_address)
    desc = build_circuit(seed, n_qubits, depth)
    state = simulate(desc)
    F_xeb = 2^n * mean(|state[x_i]|² for x_i in block.samples) - 1
    assert |F_xeb - block.xeb_score| < tol
    assert F_xeb >= block.difficulty
    # 6. 交易合法性
    verify_transactions(block.transactions, chain_state)
```

### 6.4 交易验证规则

```
transfer:  sender 余额 ≥ amount, nonce 严格递增
stake:     sender 余额 ≥ amount, recipient == STAKE_VAULT, nonce 严格递增
unstake:   sender 抵押 ≥ amount, recipient == STAKE_VAULT, nonce 严格递增
任何: signature 通过 secp256k1 + recipient address 校验
```

---

## 7. 经济学规则

### 7.1 区块奖励

```python
def block_reward(height):
    halvings = height // HALVING_INTERVAL
    if halvings >= 64: return 0
    return INITIAL_BLOCK_REWARD >> halvings
```

### 7.2 创世区块

```
height       = 0
prev_hash    = 0x00..00
timestamp    = GENESIS_TIMESTAMP (1777507200)
proposer_address = 0x00..00
nonce        = 0
samples      = []
xeb_score    = 0.0
transactions = []
```

### 7.3 Coinbase 规则

每个区块的 Coinbase 隐式将 `block_reward(height)` 个原子单位发往 `proposer_address`。
区块通过 `transactions` 字段携带普通交易、抵押与解抵押。

### 7.4 解抵押冷却

`unstake` 交易在 H 高度上链后，资金从 `staked` 移到 `cooling`。等到当前链高度 ≥ H + UNSTAKE_DELAY_BLOCKS 时，资金回到 sender 的流动余额。

---

## 8. P2P 协议（v0.5+）

v0.1 暂不规定网络协议（单节点）。v0.5 引入 TCP/QUIC 节点发现 + 区块/交易广播。

---

## 9. 钱包与地址

* 私钥：32 字节 secp256k1 标量
* 公钥：64 字节未压缩
* 地址：keccak256(public_key)[12:]，0x 前缀十六进制（20 字节）

完全兼容 Ethereum 地址格式。

---

## 10. 升级路径

协议参数（n_qubits, depth, n_samples, MIN_STAKE 等）可通过硬分叉升级。每次升级 `version` 字段递增并在共识层激活。

v1.0 计划：n=36, depth=14, samples=4096, MIN_STAKE=10 BTCQ。

---

*Last updated: 2026-05-01.*
