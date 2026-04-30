"""确定性随机电路生成。给定 32 字节 seed，产出唯一的电路描述与 Qiskit 实例。"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Iterator

from Crypto.Cipher import ChaCha20

from .constants import CIRCUIT_SINGLE_GATES


def _chacha_stream(seed: bytes) -> Iterator[int]:
    """从 seed 派生无尽伪随机字节流（ChaCha20 keystream）。"""
    assert len(seed) == 32
    cipher = ChaCha20.new(key=seed, nonce=b"\x00" * 8)
    while True:
        chunk = cipher.encrypt(b"\x00" * 4096)
        for b in chunk:
            yield b


@dataclass
class Gate:
    name: str                  # 'h','s','t','cz'
    qubits: Tuple[int, ...]    # 作用量子比特

    def to_tuple(self):
        return (self.name, tuple(self.qubits))


@dataclass
class CircuitDescription:
    n_qubits: int
    depth: int
    gates: List[Gate] = field(default_factory=list)

    def gate_count(self):
        return len(self.gates)

    def two_qubit_count(self):
        return sum(1 for g in self.gates if len(g.qubits) == 2)


def build_circuit_description(seed: bytes, n_qubits: int, depth: int) -> CircuitDescription:
    """从 seed 确定性派生电路描述。CPU only，不依赖 Qiskit。"""
    desc = CircuitDescription(n_qubits=n_qubits, depth=depth)
    rng = _chacha_stream(seed)
    for layer in range(depth):
        # 单比特门层
        for q in range(n_qubits):
            idx = next(rng) % len(CIRCUIT_SINGLE_GATES)
            desc.gates.append(Gate(CIRCUIT_SINGLE_GATES[idx], (q,)))
        # 双比特门 CZ 砖墙
        if layer % 2 == 0:
            for q in range(0, n_qubits - 1, 2):
                desc.gates.append(Gate("cz", (q, q + 1)))
        else:
            for q in range(1, n_qubits - 1, 2):
                desc.gates.append(Gate("cz", (q, q + 1)))
    return desc


def to_qiskit(desc: CircuitDescription, measure: bool = True):
    """将电路描述编译为 Qiskit QuantumCircuit。延迟导入避免无需量子时也强制依赖。"""
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(desc.n_qubits)
    for g in desc.gates:
        if g.name == "h":
            qc.h(g.qubits[0])
        elif g.name == "s":
            qc.s(g.qubits[0])
        elif g.name == "t":
            qc.t(g.qubits[0])
        elif g.name == "cz":
            qc.cz(g.qubits[0], g.qubits[1])
        else:
            raise ValueError(f"未知门 {g.name}")
    if measure:
        qc.measure_all()    # 添加名为 'meas' 的经典寄存器
    return qc


def simulate_statevector(desc: CircuitDescription):
    """经典状态向量模拟。优先使用 Qiskit Aer（C++）加速。

    返回 numpy.ndarray[complex128]，长度 2**n_qubits，下标使用 Qiskit 大端约定
    （最高位 == qubit n-1）。

    n > 31 时不会调用此函数（状态向量内存超出常规机器），用 amplitudes_for_samples 代替。
    """
    import numpy as np
    try:
        from qiskit_aer import AerSimulator
        from qiskit import transpile
        qc = to_qiskit(desc, measure=False)
        qc.save_statevector()
        sim = AerSimulator(method="statevector")
        tqc = transpile(qc, sim, optimization_level=0)
        result = sim.run(tqc).result()
        sv = result.get_statevector(tqc)
        return np.asarray(sv).astype(np.complex128)
    except ImportError:
        return _simulate_statevector_numpy(desc)


def amplitudes_for_samples(desc: CircuitDescription, samples, *, max_bond_dim: int = 4096):
    """对每个 sample 计算 p_U(x_i) = |⟨x_i|U|0⟩|²，返回与 samples 等长的 numpy 数组。

    n ≤ 31 时直接走精确状态向量。
    n > 31 时使用 Aer 的 matrix_product_state 方法 + 大 bond_dim。
    对我们的 1D 砖墙 RCS 电路，d=14 时 bond_dim ≈ 1024–4096 足以接近精确。
    """
    import numpy as np
    from .constants import STATEVECTOR_MAX_N

    if desc.n_qubits <= STATEVECTOR_MAX_N:
        state = simulate_statevector(desc)
        probs = np.abs(state)**2
        return np.array([probs[int(x)] for x in samples])

    # 大 n 路径：Aer MPS
    from qiskit_aer import AerSimulator
    from qiskit import transpile
    qc = to_qiskit(desc, measure=False)
    qc.save_statevector()
    sim = AerSimulator(method="matrix_product_state",
                       matrix_product_state_max_bond_dimension=max_bond_dim)
    tqc = transpile(qc, sim, optimization_level=0)
    result = sim.run(tqc).result()
    sv = result.get_statevector(tqc)
    probs = np.abs(np.asarray(sv).astype(np.complex128))**2
    return np.array([probs[int(x)] for x in samples])


def _simulate_statevector_numpy(desc: CircuitDescription):
    import numpy as np
    n = desc.n_qubits
    state = np.zeros(2**n, dtype=np.complex128)
    state[0] = 1.0
    H = (1 / np.sqrt(2)) * np.array([[1, 1], [1, -1]], dtype=np.complex128)
    S = np.array([[1, 0], [0, 1j]], dtype=np.complex128)
    T = np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=np.complex128)
    GATES_1Q = {"h": H, "s": S, "t": T}
    indices = np.arange(2**n, dtype=np.int64)

    def apply_1q(state, gate, q):
        shape = (1 << (n - q - 1), 2, 1 << q)
        s = state.reshape(shape)
        return np.einsum("ij,ajb->aib", gate, s).reshape(-1)

    def apply_cz(state, q1, q2):
        mask = (((indices >> q1) & 1) & ((indices >> q2) & 1)).astype(bool)
        state[mask] *= -1
        return state

    for g in desc.gates:
        if g.name in GATES_1Q:
            state = apply_1q(state, GATES_1Q[g.name], g.qubits[0])
        elif g.name == "cz":
            state = apply_cz(state, g.qubits[0], g.qubits[1])
    return state
