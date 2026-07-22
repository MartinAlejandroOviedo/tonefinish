from __future__ import annotations

from dataclasses import dataclass

from audio_tools import set_processing_limits
from resource_monitor import GpuSnapshot, ResourceMonitor, ResourceProfile, ResourceSnapshot


@dataclass(frozen=True)
class CpuBudget:
    max_ffmpeg_processes: int
    ffmpeg_threads_per_process: int
    max_parallel_analysis: int
    max_secondary_tasks: int
    cpu_soft_limit: float
    memory_soft_limit: float
    min_free_ram_gb: float

    def format_summary(self) -> str:
        return (
            f"CPU {self.max_ffmpeg_processes}x{self.ffmpeg_threads_per_process} | "
            f"análisis={self.max_parallel_analysis} | secundarios={self.max_secondary_tasks} | "
            f"CPU≤{self.cpu_soft_limit:.0f}% | RAM≤{self.memory_soft_limit:.0f}% | "
            f"RAM libre≥{self.min_free_ram_gb:.1f} GB"
        )


@dataclass(frozen=True)
class GpuBudget:
    available: bool
    max_gpu_jobs: int
    min_free_vram_mb: float
    max_gpu_utilization_percent: float
    device_count: int = 0
    name: str | None = None
    utilization_percent: float | None = None
    memory_free_mb: float | None = None

    def format_summary(self) -> str:
        if not self.available:
            return "GPU no disponible"
        parts = [f"GPU jobs={self.max_gpu_jobs}", f"VRAM≥{self.min_free_vram_mb:.0f} MB"]
        if self.name:
            parts.append(self.name)
        if self.utilization_percent is not None:
            parts.append(f"GPU {self.utilization_percent:.0f}%")
        if self.memory_free_mb is not None:
            parts.append(f"VRAM libre {self.memory_free_mb:.0f} MB")
        return " | ".join(parts)


@dataclass(frozen=True)
class ProcessingBudget:
    snapshot: ResourceSnapshot
    profile: ResourceProfile
    cpu: CpuBudget
    gpu: GpuBudget

    def format_summary(self) -> str:
        return f"{self.profile.name} | {self.cpu.format_summary()} | {self.gpu.format_summary()}"


class ResourceGovernor:
    """
    Calcula un presupuesto de recursos combinado para CPU y GPU.

    No ejecuta tareas. Solo traduce el estado del sistema a límites de trabajo
    para la sesión actual.
    """

    def __init__(self, monitor: ResourceMonitor | None = None) -> None:
        self.monitor = monitor or ResourceMonitor()

    def build(self, profile_override: str | None = None) -> ProcessingBudget:
        snapshot = self.monitor.snapshot()
        profile = self.monitor.classify(snapshot)
        override = self.monitor.profile_by_name(profile_override)
        if override is not None:
            profile = override

        cpu_threads = max(1, min(profile.max_ffmpeg_workers, profile.max_secondary_tasks))
        cpu_budget = CpuBudget(
            max_ffmpeg_processes=profile.max_ffmpeg_workers,
            ffmpeg_threads_per_process=cpu_threads,
            max_parallel_analysis=profile.max_parallel_analysis,
            max_secondary_tasks=profile.max_secondary_tasks,
            cpu_soft_limit=profile.cpu_soft_limit,
            memory_soft_limit=profile.memory_soft_limit,
            min_free_ram_gb=profile.min_free_ram_gb,
        )

        gpu_snapshot = self.monitor.gpu_snapshot()
        gpu_budget = self._build_gpu_budget(gpu_snapshot, profile)
        return ProcessingBudget(
            snapshot=snapshot,
            profile=profile,
            cpu=cpu_budget,
            gpu=gpu_budget,
        )

    def apply(self, profile_override: str | None = None) -> ProcessingBudget:
        budget = self.build(profile_override=profile_override)
        set_processing_limits(
            max_ffmpeg_processes=budget.cpu.max_ffmpeg_processes,
            ffmpeg_threads_per_process=budget.cpu.ffmpeg_threads_per_process,
        )
        return budget

    def _build_gpu_budget(
        self,
        gpu_snapshot: GpuSnapshot | None,
        profile: ResourceProfile,
    ) -> GpuBudget:
        if gpu_snapshot is None:
            return GpuBudget(
                available=False,
                max_gpu_jobs=0,
                min_free_vram_mb=0.0,
                max_gpu_utilization_percent=0.0,
            )

        free_vram = gpu_snapshot.memory_free_mb or 0.0
        if free_vram >= 8192.0:
            max_gpu_jobs = 3
        elif free_vram >= 4096.0:
            max_gpu_jobs = 2
        elif free_vram >= 2048.0:
            max_gpu_jobs = 1
        else:
            max_gpu_jobs = 0

        # No permitir que la GPU planifique más trabajo del que el perfil
        # de CPU sugiere como paralelo secundario.
        max_gpu_jobs = min(max_gpu_jobs, max(0, profile.max_secondary_tasks - 1))

        return GpuBudget(
            available=True,
            max_gpu_jobs=max_gpu_jobs,
            min_free_vram_mb=2048.0 if max_gpu_jobs > 0 else 0.0,
            max_gpu_utilization_percent=85.0,
            device_count=gpu_snapshot.device_count,
            name=gpu_snapshot.name,
            utilization_percent=gpu_snapshot.utilization_percent,
            memory_free_mb=gpu_snapshot.memory_free_mb,
        )
