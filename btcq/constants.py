"""协议常量。所有数值与 docs/PROTOCOL.md 严格一致。修改前请先升级协议版本。"""

PROTOCOL_VERSION       = 1
TICKER                 = "BTCQ"            # 比特币量子（Bitcoin Quantum）

# 创世
GENESIS_TIMESTAMP      = 1777507200        # 2026-04-30 00:00:00 UTC
GENESIS_PREV_HASH      = b"\x00" * 32
GENESIS_MESSAGE        = "BTCQ Genesis: 量子时代的第一枚比特币 — 2026-04-30"

# === 经济模型（完全照搬 Bitcoin） ===
COIN                   = 10**8             # 1 BTCQ = 10^8 atomic units (sat-like)
TOTAL_SUPPLY           = 21_000_000 * COIN # 总量上限：21,000,000 BTCQ
INITIAL_BLOCK_REWARD   = 50 * COIN         # 创世后第 1 块奖励：50 BTCQ
HALVING_INTERVAL       = 210_000           # 每 210,000 块减半一次（≈ 4 年）

# === 出块节奏（参照 Bitcoin，但前期有 bootstrap 加速） ===
TARGET_BLOCK_TIME_FINAL    = 600           # 最终稳态：10 分钟/块
TARGET_BLOCK_TIME_BOOTSTRAP= 60            # 启动期：1 分钟/块
BOOTSTRAP_FAST_DURATION    = 15 * 86400    # 头 15 天保持 60 秒/块
BOOTSTRAP_RAMP_DURATION    = 30 * 86400    # 之后 30 天线性升到 600 秒/块
BOOTSTRAP_TOTAL_DURATION   = BOOTSTRAP_FAST_DURATION + BOOTSTRAP_RAMP_DURATION

DIFFICULTY_WINDOW      = 144               # bootstrap 期 144 块（约 2.4 小时@60s）调整一次
DIFFICULTY_WINDOW_FINAL= 2016              # 稳态后回到 BTC 的 2016 块（≈2 周）
DIFFICULTY_MIN_FACTOR  = 0.25              # 单次最多减为原来的 1/4
DIFFICULTY_MAX_FACTOR  = 4.0               # 单次最多增加 4 倍
DIFFICULTY_MIN         = 0.01
DIFFICULTY_MAX         = 0.95
INITIAL_XEB_THRESHOLD  = 0.05              # 创世后第 1 块的 XEB 阈值（PoQ-Stake 较低）


def target_block_time_at(seconds_since_genesis: int) -> float:
    if seconds_since_genesis < BOOTSTRAP_FAST_DURATION:
        return float(TARGET_BLOCK_TIME_BOOTSTRAP)
    if seconds_since_genesis < BOOTSTRAP_TOTAL_DURATION:
        elapsed = seconds_since_genesis - BOOTSTRAP_FAST_DURATION
        progress = elapsed / BOOTSTRAP_RAMP_DURATION
        return TARGET_BLOCK_TIME_BOOTSTRAP + (TARGET_BLOCK_TIME_FINAL - TARGET_BLOCK_TIME_BOOTSTRAP) * progress
    return float(TARGET_BLOCK_TIME_FINAL)


def difficulty_window_at(seconds_since_genesis: int) -> int:
    if seconds_since_genesis < BOOTSTRAP_TOTAL_DURATION:
        return DIFFICULTY_WINDOW
    return DIFFICULTY_WINDOW_FINAL


# === 共识：PoQ-Stake (Proof-of-Quantumness Stake) ===
# 出块流程：
#   1. 抵押 BTCQ → 成为 staker
#   2. 每个区块由 VRF 选出一个 staker 担任 proposer
#   3. proposer 提交一段量子机执行的 RCS 采样作为"我有量子机"的证明
#   4. 区块上链，proposer 拿区块奖励
#
# 节省成本：每块只需 ~1 秒量子时间（vs PoW 的几分钟）
# 经济安全：抵押额度决定影响力（同 PoS）
# 量子门槛：每块都得过 XEB 阈值，没量子机做不到
MIN_STAKE              = 1 * COIN          # 最低抵押 1 BTCQ 才能参与出块
UNSTAKE_DELAY_BLOCKS   = 100               # 解抵押延迟：100 块后才能取出
SLASH_RATIO            = 0.1               # 提交无效证明被罚没的比例
BOOTSTRAP_OPEN_BLOCKS  = 144               # 头 144 块开放挖矿（无需抵押），之后才进入 PoQ-Stake
                                           # 解决"鸡生蛋"问题：必须先有人挖到币才能抵押

# === 量子证明电路（小规模，每块 ~1 秒） ===
# n=24 + depth=8：
#   - 状态向量 256 MB（任何笔记本都能验证）
#   - 量子 Heron r2 上 ~0.3 秒电路 + 网络往返 ≈ 1 秒接口时间
#   - 经典暴力模拟：约 5–10 秒（quantum 仍有 5–30× 时间优势）
#   - 1024 shots：足够 XEB 统计置信度
CIRCUIT_N_QUBITS       = 24
CIRCUIT_DEPTH          = 8
CIRCUIT_N_SAMPLES      = 1024
CIRCUIT_SINGLE_GATES   = ("h", "s", "t")   # 单比特门候选

# === 验证宽容 ===
TIMESTAMP_FUTURE_TOL   = 7200              # 秒，区块时间最多超前 2 小时
XEB_FLOAT_TOL          = 1e-4

# === 经典验证内存阈值 ===
STATEVECTOR_MAX_N      = 31
