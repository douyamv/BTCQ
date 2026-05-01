"""协议常量。所有数值与 docs/PROTOCOL.md 严格一致。修改前请先升级协议版本。"""

PROTOCOL_VERSION       = 1
TICKER                 = "BTCQ"            # 比特币量子（Bitcoin Quantum）

# 创世
GENESIS_TIMESTAMP      = 1777507200        # 2026-04-30 00:00:00 UTC
GENESIS_PREV_HASH      = b"\x00" * 32
GENESIS_MESSAGE        = (
    "基于比特币的发现，致敬 Satoshi。"
    "我们需要一个量子网络 BTC。"
    "Thanks, Satoshi."
)

# === 创世致敬：Satoshi Nakamoto 永久纪念地址 ===
# 地址由确定性短语派生，私钥不可恢复（实际等同烧毁地址，作为永久纪念物）
# 50 BTCQ 永远锁在这个地址，纪念中本聪 2008 年的发现
def _satoshi_tribute_addr() -> bytes:
    from Crypto.Hash import keccak as _keccak
    h = _keccak.new(digest_bits=256)
    h.update(b"Satoshi Nakamoto - thank you for Bitcoin. From the quantum frontier.")
    return h.digest()[-20:]

SATOSHI_TRIBUTE_ADDR    = _satoshi_tribute_addr()  # bytes20
SATOSHI_TRIBUTE_AMOUNT  = 50 * 10**8                # 50 BTCQ

# === 创世预分配（GENESIS_ALLOCATIONS） ===
# 在创世状态中，下列地址持有指定数量的 BTCQ。验证者必须知道这一映射。
# v0.1.x 仅纪念 Satoshi；未来可加入早期生态地址（公开募资）
GENESIS_ALLOCATIONS = {
    SATOSHI_TRIBUTE_ADDR: SATOSHI_TRIBUTE_AMOUNT,
}

# === 经济模型（完全照搬 Bitcoin） ===
COIN                   = 10**8             # 1 BTCQ = 10^8 atomic units (sat-like)
TOTAL_SUPPLY           = 21_000_000 * COIN # 总量上限：21,000,000 BTCQ
INITIAL_BLOCK_REWARD   = 50 * COIN         # 创世后第 1 块奖励：50 BTCQ
HALVING_INTERVAL       = 210_000           # 每 210,000 块减半一次（≈ 4 年）

# === 出块节奏：硬时间 slot（Ethereum 式） ===
# Slot 是协议级"出块时机"概念：
#   每个 slot 对应一个固定的 wall-clock 窗口（bootstrap 60s / 稳态 600s）
#   每个 slot 唯一一个 proposer（VRF 选举）
#   该 proposer 在 slot 期间提交合法区块 → 成功；否则 slot 空，下一个 slot 别人
#   block.height 与 slot 解耦：高度只在出块成功时才递增，空 slot 不计高度
# 这从根本上消除：① 多个 staker 抢同一 height ② 单 staker 刷 XEB ③ 链卡死
SLOT_DURATION_BOOTSTRAP    = 60            # 启动期：60 秒一个 slot
SLOT_DURATION_FINAL        = 600           # 稳态：10 分钟一个 slot（同 BTC 出块时间）
BOOTSTRAP_DURATION         = 45 * 86400    # 创世后 45 天 bootstrap 期（之后转稳态）
SLOT_FUTURE_TOL            = 2             # 允许 ±2 slot 时钟漂移（节点间时钟有偏差）
SLOT_TIMESTAMP_TOL         = 600           # 允许时间戳 ±600 秒漂移（很宽松，留足空 slot + 慢链）
                                           # 关键不变量：block.slot > prev.slot 严格递增

DIFFICULTY_MIN_FACTOR  = 0.25
DIFFICULTY_MAX_FACTOR  = 4.0
DIFFICULTY_MIN         = 0.01
DIFFICULTY_MAX         = 0.95
DIFFICULTY_WINDOW_SLOTS= 144               # 每 144 个 slot 调整一次（不论是否被填）


def slot_duration_at(seconds_since_genesis: int) -> int:
    """给定从创世以来的秒数，返回当前 slot 时长（秒）。"""
    if seconds_since_genesis < BOOTSTRAP_DURATION:
        return SLOT_DURATION_BOOTSTRAP
    return SLOT_DURATION_FINAL


def slot_at(timestamp: int) -> int:
    """给定 wall-clock 时间戳，返回 slot 编号（从 0 开始单调递增）。"""
    secs = max(0, timestamp - GENESIS_TIMESTAMP)
    if secs < BOOTSTRAP_DURATION:
        return secs // SLOT_DURATION_BOOTSTRAP
    bootstrap_slots = BOOTSTRAP_DURATION // SLOT_DURATION_BOOTSTRAP
    return bootstrap_slots + (secs - BOOTSTRAP_DURATION) // SLOT_DURATION_FINAL


def slot_start_timestamp(slot: int) -> int:
    """给定 slot 编号，返回该 slot 开始的 wall-clock 时间戳。"""
    bootstrap_slots = BOOTSTRAP_DURATION // SLOT_DURATION_BOOTSTRAP
    if slot < bootstrap_slots:
        return GENESIS_TIMESTAMP + slot * SLOT_DURATION_BOOTSTRAP
    extra = slot - bootstrap_slots
    return GENESIS_TIMESTAMP + BOOTSTRAP_DURATION + extra * SLOT_DURATION_FINAL


# 兼容旧名字：保留 target_block_time_at 但等价于 slot_duration_at
def target_block_time_at(seconds_since_genesis: int) -> float:
    return float(slot_duration_at(seconds_since_genesis))


def difficulty_window_at(seconds_since_genesis: int) -> int:
    return DIFFICULTY_WINDOW_SLOTS


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
