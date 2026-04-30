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
MIN_STAKE              = 1 * COIN          # 最低抵押 1 BTCQ 才能参与出块
UNSTAKE_DELAY_BLOCKS   = 100               # 解抵押延迟：100 块后才能取出
SLASH_RATIO            = 0.1               # 提交无效证明被罚没的比例
BOOTSTRAP_OPEN_BLOCKS  = 1000              # 头 1000 块开放挖矿（解决鸡生蛋）
BOOTSTRAP_PER_ADDR_CAP = 20                # bootstrap 期同一地址最多挖 20 块（防垄断）

# === 量子证明电路（n=30 + depth=12，真量子优势） ===
# n=30 + depth=12：
#   - 状态向量 16 GB（笔记本/工作站 OK，但单机 GPU 模拟 5–30 秒）
#   - 量子 Heron r2 上 ~0.5 秒电路 + 网络往返 ≈ 1–2 秒接口
#   - 经典模拟（含状态向量构造 + 取概率分布 + 采样）：30–60 秒
#   - 真量子优势：30–60×，且经典+GPU 也追不上 1 秒块响应窗口
#   - 4096 shots：XEB 统计标准差 ~0.016，远低于 0.10 阈值
CIRCUIT_N_QUBITS       = 30
CIRCUIT_DEPTH          = 12
CIRCUIT_N_SAMPLES      = 4096
CIRCUIT_SINGLE_GATES   = ("h", "s", "t")   # 单比特门候选

# === XEB 阈值（远高于经典随机噪声底） ===
# 24q + 1024 shots 经典随机 σ ≈ 0.031；30q + 4096 shots 经典随机 σ ≈ 0.016
# 0.10 阈值 = 6σ，bootstrap 期足够；正式 PoQ-Stake 期升到 0.15 (≈ 9σ)
INITIAL_XEB_THRESHOLD       = 0.10
POQSTAKE_XEB_THRESHOLD_FLOOR= 0.15         # 进入 PoQ-Stake 后地板阈值

# === 验证宽容 ===
TIMESTAMP_FUTURE_TOL   = 7200              # 秒，区块时间最多超前 2 小时
XEB_FLOAT_TOL          = 1e-3

# === 经典验证内存阈值 ===
STATEVECTOR_MAX_N      = 31
