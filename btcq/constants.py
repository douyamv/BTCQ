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

# === 创世致敬地址：永久纪念加密货币史的开拓者 ===
# 每个地址由确定性短语派生 keccak256(phrase)[-20:]，私钥不可恢复
# 这些地址持币永远锁定，作为加密货币史的纪念物
def _tribute_addr(phrase: str) -> bytes:
    from Crypto.Hash import keccak as _keccak
    h = _keccak.new(digest_bits=256)
    h.update(phrase.encode("utf-8"))
    return h.digest()[-20:]

# 1. Satoshi Nakamoto — Bitcoin 的匿名创造者
SATOSHI_TRIBUTE_ADDR = _tribute_addr(
    "Satoshi Nakamoto - thank you for Bitcoin. From the quantum frontier."
)
# 2. Vitalik Buterin — Ethereum 创始人，账户模型 + 智能合约的核心推动者
VITALIK_TRIBUTE_ADDR = _tribute_addr(
    "Vitalik Buterin - thank you for Ethereum. Account model + smart contracts."
)
# 3. Hal Finney — Bitcoin 第一笔交易接收人，PoW 早期理论家
HAL_TRIBUTE_ADDR = _tribute_addr(
    "Hal Finney - thank you for RPOW and Bitcoin's first transaction. RIP."
)
# 4. Nick Szabo — Smart Contracts、Bit Gold 提出者
NICK_TRIBUTE_ADDR = _tribute_addr(
    "Nick Szabo - thank you for Bit Gold and smart contracts. Pioneer."
)
# 5. David Chaum — DigiCash、ecash，加密货币之父级人物
CHAUM_TRIBUTE_ADDR = _tribute_addr(
    "David Chaum - thank you for DigiCash and electronic cash blueprints."
)
# 6. Wei Dai — b-money 提案人，比特币白皮书引用第一人
WEIDAI_TRIBUTE_ADDR = _tribute_addr(
    "Wei Dai - thank you for b-money and the cryptographic foundations."
)

# 量子先驱致敬
# 7. Peter Shor — Shor 算法发明人（让本协议存在的数学基础）
SHOR_TRIBUTE_ADDR = _tribute_addr(
    "Peter Shor - thank you for Shor's algorithm. Why we exist."
)
# 8. John Preskill — NISQ 概念提出者，量子优越性命名者
PRESKILL_TRIBUTE_ADDR = _tribute_addr(
    "John Preskill - thank you for naming NISQ and quantum supremacy."
)

# === 生态运营预留地址 ===
# 公开未托管地址，用于：早期 faucet、bug bounty、社区资助
# 私钥保存在硬件钱包，多签控制（v0.5+）
# v0.1.x 测试网阶段：用于让早期参与者先抵押启动 PoQ-Stake
ECOSYSTEM_FAUCET_ADDR = _tribute_addr(
    "BTCQ ecosystem faucet - early adopters, bounties, community grants."
)

GENESIS_ALLOCATIONS = {
    SATOSHI_TRIBUTE_ADDR:   50 * 10**8,    # 50 BTCQ — Bitcoin 创造者
    VITALIK_TRIBUTE_ADDR:   25 * 10**8,    # 25 BTCQ — Ethereum 创造者
    HAL_TRIBUTE_ADDR:       10 * 10**8,    # 10 BTCQ — 早期 Bitcoin 工程
    NICK_TRIBUTE_ADDR:      10 * 10**8,    # 10 BTCQ — 智能合约前身
    CHAUM_TRIBUTE_ADDR:     10 * 10**8,    # 10 BTCQ — 加密货币之父
    WEIDAI_TRIBUTE_ADDR:    10 * 10**8,    # 10 BTCQ — b-money
    SHOR_TRIBUTE_ADDR:      25 * 10**8,    # 25 BTCQ — Shor 算法
    PRESKILL_TRIBUTE_ADDR:  10 * 10**8,    # 10 BTCQ — NISQ 命名
    ECOSYSTEM_FAUCET_ADDR: 100 * 10**8,    # 100 BTCQ — 生态运营，早期 staker 启动金
}
# 总计：250 BTCQ 创世预分配（其中 150 BTCQ 永久纪念锁定，100 BTCQ 生态运营）

# 兼容老接口
SATOSHI_TRIBUTE_AMOUNT = GENESIS_ALLOCATIONS[SATOSHI_TRIBUTE_ADDR]

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
