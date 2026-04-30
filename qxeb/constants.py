"""协议常量。所有数值与 docs/PROTOCOL.md 严格一致。修改前请先升级协议版本。"""

PROTOCOL_VERSION       = 1

# 创世
GENESIS_TIMESTAMP      = 1777507200        # 2026-04-30 00:00:00 UTC
GENESIS_PREV_HASH      = b"\x00" * 32
GENESIS_MESSAGE        = "QXEB Genesis: 量子算力第一次有了价格 — 2026-04-30"

# === 经济模型（完全照搬 Bitcoin） ===
COIN                   = 10**8             # 1 QXEB = 10^8 atomic units (sat-like)
TOTAL_SUPPLY           = 21_000_000 * COIN # 总量上限：21,000,000 QXEB
INITIAL_BLOCK_REWARD   = 50 * COIN         # 创世后第 1 块奖励：50 QXEB
HALVING_INTERVAL       = 210_000           # 每 210,000 块减半一次（≈ 4 年）

# === 出块节奏（参照 Bitcoin，但前期有 bootstrap 加速） ===
# Bootstrap 调度：让早期矿工有较高出块频率，加速冷启动与参与
#   第   0–15 天：目标 60 秒/块（密集出块期）
#   第  15–45 天：60 → 600 线性升（30 天平滑过渡）
#   第    45 天+：600 秒/块（BTC 标准节奏）
# 减半仍按 BTC 规则：每 210,000 块减半一次（首次因 bootstrap 提前约 5 个月）
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
INITIAL_XEB_THRESHOLD  = 0.10              # 创世后第 1 块的 XEB 阈值


def target_block_time_at(seconds_since_genesis: int) -> float:
    """
    给定自创世以来的秒数，返回当前期望出块间隔（秒）。
    """
    if seconds_since_genesis < BOOTSTRAP_FAST_DURATION:
        return float(TARGET_BLOCK_TIME_BOOTSTRAP)
    if seconds_since_genesis < BOOTSTRAP_TOTAL_DURATION:
        elapsed = seconds_since_genesis - BOOTSTRAP_FAST_DURATION
        progress = elapsed / BOOTSTRAP_RAMP_DURATION
        return TARGET_BLOCK_TIME_BOOTSTRAP + (TARGET_BLOCK_TIME_FINAL - TARGET_BLOCK_TIME_BOOTSTRAP) * progress
    return float(TARGET_BLOCK_TIME_FINAL)


def difficulty_window_at(seconds_since_genesis: int) -> int:
    """难度调整窗口：bootstrap 期 144 块（响应快），稳态 2016 块（BTC 节奏）。"""
    if seconds_since_genesis < BOOTSTRAP_TOTAL_DURATION:
        return DIFFICULTY_WINDOW
    return DIFFICULTY_WINDOW_FINAL

# === v0.1 电路参数 ===
# n=36 让经典从根本上失去公平参与挖矿的机会：
#   - 状态向量需 1 TB（双精度）/ 512 GB（单精度），笔记本和工作站都过不去
#   - 即使有服务器，张量网络法验证一块也要数十分钟到数小时
#   - 量子机（IBM Heron 156q、Quantinuum H2 56q、IonQ Tempo）无压力
# 量子优势倍率：~10⁴–10⁵×
CIRCUIT_N_QUBITS       = 36
CIRCUIT_DEPTH          = 14
CIRCUIT_N_SAMPLES      = 8192
CIRCUIT_SINGLE_GATES   = ("h", "s", "t")   # 单比特门候选

# === 验证宽容 ===
TIMESTAMP_FUTURE_TOL   = 7200              # 秒，区块时间最多超前 2 小时
XEB_FLOAT_TOL          = 1e-3              # XEB 比较容差（n>32 用 MPS 时放宽）

# === 经典验证内存阈值 ===
# n ≤ STATEVECTOR_MAX_N: 用精确状态向量
# n  > STATEVECTOR_MAX_N: 用 Aer MPS 近似 + 高 bond_dim
STATEVECTOR_MAX_N      = 31
