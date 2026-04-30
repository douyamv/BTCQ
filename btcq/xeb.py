"""线性交叉熵基准（Linear XEB）。"""

import numpy as np
from typing import Iterable

from .circuit import CircuitDescription, simulate_statevector, amplitudes_for_samples


def linear_xeb(state: np.ndarray, samples: Iterable[int], n_qubits: int) -> float:
    """
    F_xeb = 2^n * mean(p_U(x)) - 1
    state: 已模拟好的全 0 初态作用 U 后的状态向量
    samples: int 列表，每个表示一个测量得到的比特串
    """
    probs = np.abs(state)**2
    sampled_probs = np.array([probs[int(x)] for x in samples])
    return float((1 << n_qubits) * np.mean(sampled_probs) - 1.0)


def linear_xeb_from_probs(sampled_probs: np.ndarray, n_qubits: int) -> float:
    """直接给定每个 sample 的 p_U(x_i)，计算线性 XEB。"""
    return float((1 << n_qubits) * np.mean(sampled_probs) - 1.0)


def xeb_from_description(desc: CircuitDescription, samples: Iterable[int]) -> float:
    """自动选择最优模拟方法（n≤31 状态向量；n>31 MPS）。"""
    probs = amplitudes_for_samples(desc, samples)
    return linear_xeb_from_probs(probs, desc.n_qubits)


def expected_xeb_perfect_quantum() -> float:
    """无噪声理想量子电路在 Haar 随机电路上的期望 XEB。"""
    return 1.0   # 高深度极限下


def expected_xeb_uniform_classical() -> float:
    """经典均匀随机采样的期望 XEB。"""
    return 0.0
