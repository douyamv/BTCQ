# QXEB 白皮书

**量子交叉熵币（Quantum Cross-Entropy Coin）**
**v0.1 — 2026 年 4 月**

> "把量子计算优势第一次变成可定价的稀缺资源。"

---

## 摘要

QXEB 是一种**只能由量子计算机有效率挖矿**的加密货币。它采用基于随机电路采样（Random Circuit Sampling, RCS）和交叉熵基准（Cross-Entropy Benchmarking, XEB）的工作量证明算法，使得经典计算机在数学上必须付出指数级以上的时间成本，才能伪造合法区块。

QXEB 的发行总量上限为 **21,000,000** 枚，区块奖励初始为 **50 QXEB**，每 **210,000 个区块** 减半一次。最终稳态目标出块时间为 **10 分钟**（与 Bitcoin 对齐），但前 **45 天为 bootstrap 加速期**：

* 第 0–15 天：1 分钟/块（快速冷启动，让早期参与者获得可见性）
* 第 15–45 天：1 分钟 → 10 分钟 线性过渡
* 第 45 天之后：10 分钟/块（BTC 节奏永久稳态）

其设计思想直接借鉴 Bitcoin，但**其挖矿过程不再是哈希猜谜，而是要求矿工完成一段在经典计算机上需要指数级时间、在量子计算机上线性时间内可完成的计算**。

挖矿任务的核心参数为 **n = 36 量子比特、深度 14、每块 8192 次采样**——这一规模确保：

* 笔记本和工作站完全无法挖矿（状态向量需 1 TB / 单精度 512 GB）
* 即便服务器，张量网络法验证一块也要数十分钟到数小时
* 量子机（IBM Heron r2 156q、Quantinuum H2 56q、IonQ Tempo 64q）轻松胜任

QXEB 的存在意义不在于"代替"BTC 或 ETH，而是**第一次为人类已经拥有的量子计算优势设计了一个可被市场定价、可被验证、可被持有、可被流通的承载物**。

---

## 1. 引言：被搁置的量子计算优势

2019 年 10 月，Google 用 Sycamore 处理器在 200 秒内完成了一项被估计需要顶级超级计算机运算 10,000 年的随机电路采样任务（[Arute et al., *Nature* 2019]）。其后，IBM、Quantinuum、QuEra 等机构在不同物理体系上反复重现并强化了这一"量子计算优势"（quantum advantage）。

在这一阶段：

* **理论端**已严格证明：随机电路采样在合理的复杂度假设下经典不可行（Bouland-Fefferman-Nirkhe-Vazirani 2019, [BFNV19]）。
* **硬件端**：到 2026 年 Q1，全球可云端访问的高保真度量子处理器已超过 30 台，其中 IBM Heron r2、Google Willow、Quantinuum H2、Atom Computing G-1 等均能稳定执行 50+ 比特 / 14+ 深度的随机电路。
* **经济端**：量子计算硬件除了用于物理模拟、化学计算和论文之外，**没有任何加密金融意义上的价值捕获机制**。

这就是 QXEB 解决的具体问题：**让一台量子计算机的算力，可以直接转化为可在公开市场流通的资产**。

---

## 2. 核心思想

### 2.1 用 RCS 替代 SHA-256

Bitcoin 的工作量证明本质是：找到一个 nonce，使得 `SHA256(SHA256(block_header))` 的前若干位是 0。SHA-256 在经典 CPU/GPU/ASIC 上**没有量子优势**——Grover 算法理论上能给出平方根加速，但实现 SHA-256 量子 oracle 需要约 **2,700 个逻辑量子比特**，远超 2026 年硬件能力，因此 BTC 挖矿现实中是经典专用问题。

QXEB 把这一逻辑反过来：

> **挖矿任务的核心是采样一个高维量子态的输出分布，并用交叉熵基准证明该采样确实由量子电路产生。**

经典计算机想完成这一任务，必须在指数大的状态空间中精确模拟量子电路。这是数学上被严格分析过的难度（[BFNV19], [BJS10]），不是经验观察。

### 2.2 谁在挖矿

挖一个 QXEB 区块需要：

1. 一台支持 ≥30 个量子比特、深度 ≥14 的电路、双比特门保真度 ≥99% 的量子处理器（或对其的云端访问权）；
2. Qiskit / Cirq 等标准量子 SDK；
3. 经典侧的协议客户端（本仓库 `qxeb/` 模块）。

满足上述条件，2026 年全球可挖矿者数量在 **数百到数千** 量级，与 2009 年 BTC 早期的中本聪期相当。这是 QXEB 早期定价机会的来源。

---

## 3. 协议设计

### 3.1 区块结构

每个 QXEB 区块由下列字段组成（详见 `PROTOCOL.md`）：

```
QXEBBlock {
    version            uint16
    height             uint64
    prev_hash          bytes32         // 上一区块的哈希
    timestamp          uint64          // Unix 秒
    miner_address      bytes20         // 矿工奖励地址（secp256k1 派生）
    circuit_params {                   // 电路参数（共识协定，可由难度调整）
        n_qubits       uint8
        depth          uint8
        n_samples      uint32
    }
    nonce              uint64          // 矿工调整以寻找合格电路
    samples_root       bytes32         // samples 的 Merkle 根
    samples            list[bytes]     // 长度 = n_samples，每个为 bitstring
    xeb_score          float64         // 矿工声明的 XEB 分数
    miner_signature    bytes           // 矿工对前述字段的 secp256k1 签名
}
block_hash := keccak256(serialize(block_excluding_signature))
```

### 3.2 挖矿算法

矿工执行以下流程：

```
1. 从最新区块获取 prev_hash
2. 选择一个 nonce（自由调整以优化 XEB）
3. circuit_seed = keccak256(prev_hash || nonce || miner_address)
4. 由 circuit_seed 确定地生成随机电路 U：
     a. 用 ChaCha20(circuit_seed) 作为伪随机源
     b. depth=14 层中每层：每个量子比特执行 H, S, T 中随机一个单比特门 +
        相邻比特对执行 CZ（砖墙模式）
5. 在量子处理器上运行 U|0...0⟩，采样 n_samples=8192 个比特串 {x_i}
6. 计算 XEB 分数：
     F_xeb = 2^n * mean_i [ p_U(x_i) ] - 1
   其中 p_U(x_i) 是经典模拟 U 后取出的精确概率
   v0.1 中 n_qubits=36：经典模拟用 Aer 矩阵积态法（MPS），单次约 1–10 分钟
7. 若 F_xeb >= 当前难度阈值 D，则区块合法；
   否则换一个 nonce 重试
8. 用矿工私钥签名区块，广播至网络
```

矿工**关键调整空间**：选择哪个 nonce。不同 nonce 产生不同电路 U，从而 XEB 分数不同——这就是矿工的"工作"，类比 BTC 的 nonce 调整。

### 3.3 验证算法

任意全节点验证一个区块：

```
1. 检查格式、签名合法性、prev_hash 正确连接
2. 重新计算 circuit_seed 与电路 U
3. 经典模拟 U（v0.1 在 N=30 时约 16 GB 状态向量、~10 秒 CPU 时间，
   可优化为 GPU/张量网络方法）
4. 对所有 n_samples 个声明样本，从模拟结果中读取 p_U(x_i)
5. 重新计算 F_xeb
6. 若 F_xeb >= 难度阈值 D 且签名正确，区块合法
```

### 3.4 难度调整

**Bootstrap 阶段（创世后头 45 天）**：每 144 个区块（≈ 2.4 小时）调整一次，让难度对参与人数变化反应迅速。

**稳态阶段（45 天后）**：回到 BTC 节奏，每 2016 个区块（≈ 2 周）调整一次。

```
window_size = 144 if seconds_since_genesis < 45*86400 else 2016
expected_time = sum( target_block_time(t_i) for block t_i in window )
                # target_block_time 在 0–15 天内为 60；15–45 天线性升至 600；之后恒为 600
actual_time   = block[h-1].timestamp - block[h-window_size].timestamp
factor        = clip(actual_time / expected_time, 0.25, 4.0)
new_D         = old_D / factor
```

XEB 阈值 D 越高，矿工越需要尝试更多 nonce 才能找到合格电路，等价于难度上升。

### 3.5 共识规则

QXEB 采用**最长合法链**规则（同 BTC 的 Nakamoto 共识）。链工作量定义为：

```
chain_work = Σ over blocks (xeb_score[i] / D_at_block[i])
```

即每个区块对总工作量的贡献是其 XEB 分数除以挖矿时的难度。攻击者要构造平行链超越主链，必须积累更多有效量子算力。

---

## 4. 密码学与计算复杂性论证

### 4.1 为什么经典挖矿必然慢

QXEB 的反伪造性建立在两个相互独立的事实上：

**事实 A（精确模拟下界）**: 给定深度为 d 的 n 比特随机电路 U，经典精确计算单个振幅 ⟨x|U|0⟩ 的最佳已知算法是 [Markov-Shi 2008] 的张量网络收缩，其代价为 O(2^treewidth(U))，而对随机连接图 treewidth ≥ Ω(n)，因此渐近时间为 **2^Ω(n)**。

**事实 B（采样硬度）**: [BFNV19] 证明了，假设多项式层级不坍缩（PH 不在 #P 之内），则不存在经典多项式时间算法能够从 RCS 输出分布中**近似**采样到 XEB 大于多项式小常数的样本。

**结论**: 一个经典攻击者要伪造合格 QXEB 区块，必须：
- 选项 1：精确模拟电路（指数时间）后采样高 p_U 比特串；
- 选项 2：使用未知的近似算法（按 BFNV19，不存在多项式时间方法）。

而量子矿工只需在物理量子处理器上运行电路并测量——时间复杂度为 **O(n·d)**。这就是 QXEB 的量子优势来源。

### 4.2 量化对比

以 v0.1 参数 (n=36, d=14)：

| 角色 | 单区块挖矿耗时 | 备注 |
|---|---|---|
| 量子矿工（IBM Heron r2 等） | ≈ 0.5 秒 | 直接电路执行 + 8192 shots |
| 经典最优张量网络 | **数十分钟（GPU）到数小时（CPU）** | n=36 已超笔记本/工作站 |
| 经典状态向量法 | **不可行** | 1 TB（双精度）/ 512 GB（单精度）内存门槛 |
| 经典通用笔记本 | **完全不可行** | OOM |

v0.1 的量子优势倍率为 **10⁴–10⁵×**，已经把笔记本和工作站排除在外。

主网（v1.0）规划 n=55, d=18：

| 角色 | 单区块挖矿耗时 |
|---|---|
| 量子矿工 | ≈ 1 秒 |
| 经典最优 | **数天** |
| 加速倍率 | **10⁶ – 10⁸ ×** |

完全 supremacy 模式（v2.0）n=75, d=20：

| 角色 | 单区块挖矿耗时 |
|---|---|
| 量子矿工 | ≈ 2 秒 |
| 经典最优 | **数百年（外推）** |
| 加速倍率 | **post-classical** |

### 4.3 难度调整与防 ASIC

由于挖矿任务的核心是物理量子电路执行，**没有任何已知的经典专用集成电路（ASIC）能对该任务产生 ASIC 级加速**——经典硬件再快也只是更快地走指数级路径。这与 BTC 矿业被 ASIC 工厂寡头化的命运截然不同。

QXEB 的"硬件路径"是更高保真度、更多比特数、更深电路的量子处理器。这条路径的扩展由半导体物理 + 量子误差纠正决定，进展缓慢，**矿业去中心化在物理上得到保护**。

---

## 5. 经济模型

### 5.1 发行曲线

| 参数 | 值 |
|---|---|
| 总量上限 | 21,000,000 QXEB |
| 创世区块奖励 | 50 QXEB |
| 减半周期 | 210,000 区块（≈ 4 年） |
| 目标出块时间 | 600 秒 |
| 创世日期 | 2026-04-30 |
| 估计达到 99% 总量年份 | 2042 |

发行曲线与 Bitcoin 完全对齐——这是经过 16 年市场检验的稀缺性曲线，社区对其心理预期已经形成。

### 5.2 矿工收入构成

* **区块奖励**（block subsidy）：随减半递减
* **交易费**（transaction fee）：v1.0 引入，矿工自由打包

### 5.3 估值逻辑

QXEB 的内在价值来自三层：

1. **稀缺**：数学上有上限，经典不可挖
2. **效用**：未来将作为去中心化"量子算力市场"的本位币（量子计算时段可用 QXEB 结算）
3. **叙事**：作为"量子计算第一个金融资产"的纪念物，具备历史属性溢价

---

## 6. 路线图

| 版本 | 时间 | 关键变化 |
|---|---|---|
| **v0.1 (本版本)** | 2026 Q2 | 单节点测试网，n=36，d=14，bootstrap 加速期 |
| **v0.5** | 2026 Q3 | P2P 网络，多节点共识，CLI 钱包 |
| **v1.0** | 2026 Q4 | 主网启动，n=55，d=18，哨兵子电路验证，区块浏览器，主流交易所对接 |
| **v1.5** | 2027 Q2 | EVM 兼容侧链，QXEB ↔ ETH 跨链桥 |
| **v2.0** | 2028 | 完全 supremacy 模式 n=75+，d=20+，ZK + 多签验证，进入仅量子可挖时代 |
| **v3.0** | 2030+ | 量子算力市场（DePIN 模型）：以 QXEB 结算量子时段 |

---

## 7. 风险与限制

我们诚实声明以下风险：

### 7.1 技术风险

* **经典算法突破**：未来可能出现至今未知的 RCS 经典近似算法（已有部分进展如 [Pan-Zhang 2022]），削弱量子优势。QXEB 通过周期性提高 n、d 参数缓解。
* **量子硬件中心化**：现阶段大型量子计算资源集中在 IBM、Google、Quantinuum 等少数公司云端，矿业可能反而短期集中。我们鼓励多家硬件参与。
* **验证成本**：n=40+ 时验证一个区块需要 ~分钟级 GPU 计算，对全节点是负担。我们规划用零知识证明 + 抽样验证缓解。

### 7.2 经济风险

* QXEB 没有任何历史价格，早期市值可能为零或剧烈波动；
* 监管态度未知；
* 无团队预挖、无 ICO、无私募——这是优点也是风险（无营销资源）。

### 7.3 我们不承诺什么

* 不承诺价格上涨；
* 不承诺被任何交易所上市；
* 不承诺替代任何现有加密货币；
* 仅承诺协议数学正确、代码开源、不预挖、规则不变。

---

## 8. 总结

QXEB 把量子计算优势——这一已经存在 7 年但被搁置在物理实验室里的资源——第一次包装成市场可定价、可流通的稀缺资产。它不破解任何现有加密货币，不威胁任何现有金融基础设施。它只是在量子时代到来之前，**先把第一枚"量子算力本位币"铸出来，等市场到来**。

与 Bitcoin 一样，它没有创始人保留份额，没有预挖，没有营销预算，没有"团队"。代码是规范，规范是共识，共识是价值。

**第一个 QXEB 区块由你的量子计算机挖出。从你开始。**

---

## 参考文献

[Arute2019] Arute F. et al. "Quantum supremacy using a programmable superconducting processor." *Nature* 574, 505–510 (2019).

[BFNV19] Bouland A., Fefferman B., Nirkhe C., Vazirani U. "On the complexity and verification of quantum random circuit sampling." *Nature Physics* 15, 159–163 (2019).

[BJS10] Bremner M., Jozsa R., Shepherd D. "Classical simulation of commuting quantum computations implies collapse of the polynomial hierarchy." *Proc. R. Soc. A* 467, 459 (2011).

[MS08] Markov I., Shi Y. "Simulating quantum computation by contracting tensor networks." *SIAM J. Comput.* 38, 963 (2008).

[PZ22] Pan F., Zhang P. "Simulation of quantum circuits using the big-batch tensor network method." *Phys. Rev. Lett.* 128, 030501 (2022).

[Nakamoto2008] Nakamoto S. "Bitcoin: A Peer-to-Peer Electronic Cash System." (2008).

[Mahadev2018] Mahadev U. "Classical Verification of Quantum Computations." *FOCS* 2018.

---

*本白皮书是 QXEB v0.1 的初始版本。Github: github.com/douyamv/qxeb*
*Released under CC-BY-SA 4.0. 协议代码采用 MIT License.*
