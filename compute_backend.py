from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from resource_monitor import GpuSnapshot, ResourceMonitor, ResourceSnapshot


class BackendKind(str, Enum):
    CPU = "cpu"
    GPU = "gpu"


@dataclass(frozen=True)
class StagePolicy:
    allow_gpu: bool = False
    prefer_gpu: bool = False
    require_gpu: bool = False
    min_free_vram_mb: float = 1024.0
    max_gpu_utilization_percent: float = 85.0


@dataclass(frozen=True)
class BackendDecision:
    stage: str
    backend: Literal["cpu", "gpu"]
    requested_backend: Literal["cpu", "gpu"]
    fallback_used: bool
    reason: str
    cpu_snapshot: ResourceSnapshot | None = None
    gpu_snapshot: GpuSnapshot | None = None

    def format_summary(self) -> str:
        fallback = "fallback" if self.fallback_used else "direct"
        return f"{self.stage}: {self.requested_backend}->{self.backend} ({fallback}) - {self.reason}"


DEFAULT_STAGE_POLICIES: dict[str, StagePolicy] = {
    # Etapas que deben permanecer en CPU por estabilidad y consistencia.
    "analysis.loudness": StagePolicy(allow_gpu=False),
    "analysis.validation": StagePolicy(allow_gpu=False),
    "render.mastering": StagePolicy(allow_gpu=False),
    "render.normalization": StagePolicy(allow_gpu=False),
    "render.limiter": StagePolicy(allow_gpu=False),
    "output.write": StagePolicy(allow_gpu=False),
    "output.report": StagePolicy(allow_gpu=False),
    # Etapas candidatas a GPU.
    "analysis.spectrum": StagePolicy(allow_gpu=True, prefer_gpu=True),
    "analysis.features": StagePolicy(allow_gpu=True, prefer_gpu=True),
    "analysis.deep": StagePolicy(allow_gpu=True, prefer_gpu=True),
    "analysis.batch": StagePolicy(allow_gpu=True, prefer_gpu=True),
}


class ComputeBackend:
    """
    Selector simple de backend de cómputo.

    Por ahora no ejecuta nada: solo decide si una etapa debería correr en CPU,
    GPU o volver a CPU por fallback.
    """

    def __init__(self, monitor: ResourceMonitor | None = None) -> None:
        self.monitor = monitor or ResourceMonitor()
        self._last_cpu_snapshot: ResourceSnapshot | None = None
        self._last_gpu_snapshot: GpuSnapshot | None = None
        self.refresh()

    def refresh(self) -> tuple[ResourceSnapshot, GpuSnapshot | None]:
        self._last_cpu_snapshot = self.monitor.snapshot()
        self._last_gpu_snapshot = self.monitor.gpu_snapshot()
        return self._last_cpu_snapshot, self._last_gpu_snapshot

    @property
    def cpu_snapshot(self) -> ResourceSnapshot | None:
        return self._last_cpu_snapshot

    @property
    def gpu_snapshot(self) -> GpuSnapshot | None:
        return self._last_gpu_snapshot

    def policy_for_stage(self, stage: str) -> StagePolicy:
        normalized = self.normalize_stage(stage)
        return DEFAULT_STAGE_POLICIES.get(normalized, StagePolicy())

    @staticmethod
    def normalize_stage(stage: str) -> str:
        normalized = stage.strip().lower().replace(" ", "_")
        normalized = normalized.replace(":", ".")
        while ".." in normalized:
            normalized = normalized.replace("..", ".")
        return normalized

    def decide(
        self,
        stage: str,
        policy: StagePolicy | None = None,
    ) -> BackendDecision:
        cpu_snapshot, gpu_snapshot = self.refresh()
        normalized_stage = self.normalize_stage(stage)
        effective_policy = policy or self.policy_for_stage(normalized_stage)

        if not effective_policy.allow_gpu:
            return BackendDecision(
                stage=normalized_stage,
                backend=BackendKind.CPU.value,
                requested_backend=BackendKind.CPU.value,
                fallback_used=False,
                reason="stage locked to CPU",
                cpu_snapshot=cpu_snapshot,
                gpu_snapshot=gpu_snapshot,
            )

        if gpu_snapshot is None:
            reason = "no GPU detected"
            if effective_policy.require_gpu:
                reason = "GPU required but not available"
            return BackendDecision(
                stage=normalized_stage,
                backend=BackendKind.CPU.value,
                requested_backend=BackendKind.GPU.value,
                fallback_used=True,
                reason=reason,
                cpu_snapshot=cpu_snapshot,
                gpu_snapshot=None,
            )

        if (
            gpu_snapshot.memory_free_mb is not None
            and gpu_snapshot.memory_free_mb < effective_policy.min_free_vram_mb
        ):
            return BackendDecision(
                stage=normalized_stage,
                backend=BackendKind.CPU.value,
                requested_backend=BackendKind.GPU.value,
                fallback_used=True,
                reason=(
                    f"GPU VRAM below threshold "
                    f"({gpu_snapshot.memory_free_mb:.0f} MB < {effective_policy.min_free_vram_mb:.0f} MB)"
                ),
                cpu_snapshot=cpu_snapshot,
                gpu_snapshot=gpu_snapshot,
            )

        if (
            gpu_snapshot.utilization_percent is not None
            and gpu_snapshot.utilization_percent >= effective_policy.max_gpu_utilization_percent
        ):
            return BackendDecision(
                stage=normalized_stage,
                backend=BackendKind.CPU.value,
                requested_backend=BackendKind.GPU.value,
                fallback_used=True,
                reason=(
                    f"GPU utilization too high "
                    f"({gpu_snapshot.utilization_percent:.0f}% >= {effective_policy.max_gpu_utilization_percent:.0f}%)"
                ),
                cpu_snapshot=cpu_snapshot,
                gpu_snapshot=gpu_snapshot,
            )

        return BackendDecision(
            stage=normalized_stage,
            backend=BackendKind.GPU.value,
            requested_backend=BackendKind.GPU.value,
            fallback_used=False,
            reason="GPU available for optional stage",
            cpu_snapshot=cpu_snapshot,
            gpu_snapshot=gpu_snapshot,
        )

    def decide_many(
        self,
        stages: list[str],
        policies: dict[str, StagePolicy] | None = None,
    ) -> list[BackendDecision]:
        decisions: list[BackendDecision] = []
        for stage in stages:
            policy = None
            if policies is not None:
                policy = policies.get(self.normalize_stage(stage))
            decisions.append(self.decide(stage, policy=policy))
        return decisions

    def summarize_pipeline(
        self,
        stages: list[str],
        policies: dict[str, StagePolicy] | None = None,
    ) -> str:
        decisions = self.decide_many(stages, policies=policies)
        return " | ".join(decision.format_summary() for decision in decisions)
