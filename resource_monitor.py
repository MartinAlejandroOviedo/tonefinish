from __future__ import annotations

import csv
import os
import pathlib
import subprocess
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResourceProfile:
    name: str
    max_ffmpeg_workers: int
    max_parallel_analysis: int
    max_secondary_tasks: int
    cpu_soft_limit: float
    memory_soft_limit: float
    min_free_ram_gb: float

    def format_summary(self) -> str:
        return (
            f"{self.name} | workers={self.max_ffmpeg_workers} | "
            f"análisis={self.max_parallel_analysis} | secundarios={self.max_secondary_tasks} | "
            f"CPU≤{self.cpu_soft_limit:.0f}% | RAM≤{self.memory_soft_limit:.0f}% | "
            f"RAM libre≥{self.min_free_ram_gb:.1f} GB"
        )


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float | None
    memory_percent: float | None
    memory_available_gb: float | None
    ffmpeg_processes: int | None
    cpu_count: int

    def format_summary(self) -> str:
        parts: list[str] = [f"CPU {self.cpu_count} cores"]
        if self.cpu_percent is not None:
            parts.append(f"CPU {self.cpu_percent:.0f}%")
        if self.memory_percent is not None:
            parts.append(f"RAM {self.memory_percent:.0f}%")
        if self.memory_available_gb is not None:
            parts.append(f"RAM libre {self.memory_available_gb:.1f} GB")
        if self.ffmpeg_processes is not None:
            parts.append(f"FFmpeg {self.ffmpeg_processes}")
        return " | ".join(parts)


@dataclass(frozen=True)
class GpuSnapshot:
    backend: str
    device_count: int
    name: str | None = None
    driver_version: str | None = None
    utilization_percent: float | None = None
    memory_total_mb: float | None = None
    memory_used_mb: float | None = None
    memory_free_mb: float | None = None

    def format_summary(self) -> str:
        parts = [self.backend, f"devices={self.device_count}"]
        if self.name:
            parts.append(self.name)
        if self.utilization_percent is not None:
            parts.append(f"GPU {self.utilization_percent:.0f}%")
        if self.memory_total_mb is not None and self.memory_used_mb is not None:
            parts.append(f"VRAM {self.memory_used_mb:.0f}/{self.memory_total_mb:.0f} MB")
        if self.memory_free_mb is not None:
            parts.append(f"VRAM libre {self.memory_free_mb:.0f} MB")
        return " | ".join(parts)


class ResourceMonitor:
    def __init__(self) -> None:
        self._psutil = self._load_psutil()

    @staticmethod
    def _load_psutil():
        try:
            import psutil  # type: ignore

            return psutil
        except Exception:
            return None

    def snapshot(self) -> ResourceSnapshot:
        cpu_count = max(1, os.cpu_count() or 1)
        cpu_percent: float | None = None
        memory_percent: float | None = None
        memory_available_gb: float | None = None
        ffmpeg_processes: int | None = None

        if self._psutil is not None:
            try:
                cpu_percent = float(self._psutil.cpu_percent(interval=None))
            except Exception:
                cpu_percent = None
            try:
                mem = self._psutil.virtual_memory()
                memory_percent = float(mem.percent)
                memory_available_gb = float(mem.available) / (1024.0**3)
            except Exception:
                memory_percent = None
                memory_available_gb = None
            try:
                ffmpeg_processes = sum(
                    1
                    for proc in self._psutil.process_iter(["name"])
                    if (proc.info.get("name") or "").lower().startswith("ffmpeg")
                )
            except Exception:
                ffmpeg_processes = None
            return ResourceSnapshot(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_available_gb=memory_available_gb,
                ffmpeg_processes=ffmpeg_processes,
                cpu_count=cpu_count,
            )

        cpu_percent = self._read_cpu_percent_linux()
        memory_percent, memory_available_gb = self._read_memory_linux()
        ffmpeg_processes = self._count_ffmpeg_processes()
        return ResourceSnapshot(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_available_gb=memory_available_gb,
            ffmpeg_processes=ffmpeg_processes,
            cpu_count=cpu_count,
        )

    def gpu_snapshot(self) -> GpuSnapshot | None:
        """Detecta una GPU disponible usando utilidades del sistema cuando existen."""
        snapshot = self._gpu_snapshot_nvidia_smi()
        if snapshot is not None:
            return snapshot
        snapshot = self._gpu_snapshot_drm()
        if snapshot is not None:
            return snapshot
        snapshot = self._gpu_snapshot_lspci()
        if snapshot is not None:
            return snapshot
        return None

    def has_gpu(self) -> bool:
        return self.gpu_snapshot() is not None

    def format_gpu_summary(self) -> str:
        snapshot = self.gpu_snapshot()
        if snapshot is None:
            return "GPU no disponible"
        return snapshot.format_summary()

    def classify(self, snapshot: ResourceSnapshot) -> ResourceProfile:
        cpu_count = snapshot.cpu_count
        memory_gb = snapshot.memory_available_gb or 0.0

        if cpu_count <= 4 or memory_gb < 8.0:
            return ResourceProfile(
                name="Baja",
                max_ffmpeg_workers=1,
                max_parallel_analysis=1,
                max_secondary_tasks=1,
                cpu_soft_limit=65.0,
                memory_soft_limit=75.0,
                min_free_ram_gb=2.0,
            )
        if cpu_count <= 8 or memory_gb < 16.0:
            return ResourceProfile(
                name="Media",
                max_ffmpeg_workers=1,
                max_parallel_analysis=1,
                max_secondary_tasks=2,
                cpu_soft_limit=75.0,
                memory_soft_limit=80.0,
                min_free_ram_gb=3.0,
            )
        if cpu_count <= 12 or memory_gb < 32.0:
            return ResourceProfile(
                name="Alta",
                max_ffmpeg_workers=2,
                max_parallel_analysis=2,
                max_secondary_tasks=2,
                cpu_soft_limit=80.0,
                memory_soft_limit=85.0,
                min_free_ram_gb=4.0,
            )
        return ResourceProfile(
            name="Muy alta",
            max_ffmpeg_workers=3,
            max_parallel_analysis=2,
            max_secondary_tasks=3,
            cpu_soft_limit=85.0,
            memory_soft_limit=90.0,
            min_free_ram_gb=6.0,
        )

    @staticmethod
    def profile_by_name(name: str | None) -> ResourceProfile | None:
        if not name:
            return None
        normalized = name.strip().lower()
        profiles = {
            "baja": ResourceProfile("Baja", 1, 1, 1, 65.0, 75.0, 2.0),
            "media": ResourceProfile("Media", 1, 1, 2, 75.0, 80.0, 3.0),
            "alta": ResourceProfile("Alta", 2, 2, 2, 80.0, 85.0, 4.0),
            "muy alta": ResourceProfile("Muy alta", 3, 2, 3, 85.0, 90.0, 6.0),
        }
        return profiles.get(normalized)

    def _read_cpu_percent_linux(self) -> float | None:
        try:
            load1 = os.getloadavg()[0]
            cpu_count = max(1, os.cpu_count() or 1)
            return min(100.0, max(0.0, (load1 / cpu_count) * 100.0))
        except Exception:
            return None

    def _read_memory_linux(self) -> tuple[float | None, float | None]:
        meminfo = pathlib.Path("/proc/meminfo")
        if not meminfo.exists():
            return None, None
        try:
            values: dict[str, int] = {}
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, _, rest = line.partition(":")
                if not rest:
                    continue
                number = rest.strip().split()[0]
                values[key] = int(number) * 1024
            total = values.get("MemTotal")
            available = values.get("MemAvailable")
            if not total or not available:
                return None, None
            percent = 100.0 - (available / total * 100.0)
            return percent, available / (1024.0**3)
        except Exception:
            return None, None

    def _count_ffmpeg_processes(self) -> int | None:
        try:
            out = subprocess.run(
                ["ps", "-A", "-o", "comm="],
                capture_output=True,
                text=True,
                check=False,
            )
            if out.returncode != 0:
                return None
            return sum(1 for line in out.stdout.splitlines() if line.strip().startswith("ffmpeg"))
        except Exception:
            return None

    def _gpu_snapshot_nvidia_smi(self) -> GpuSnapshot | None:
        if shutil.which("nvidia-smi") is None:
            return None
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,driver_version,utilization.gpu,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None

        rows = [row for row in csv.reader(line for line in result.stdout.splitlines() if line.strip())]
        if not rows:
            return None

        total_devices = len(rows)
        names = [row[0].strip() for row in rows if len(row) > 0 and row[0].strip()]
        driver_versions = [row[1].strip() for row in rows if len(row) > 1 and row[1].strip()]

        utils: list[float] = []
        total_mb = 0.0
        used_mb = 0.0
        free_mb = 0.0
        for row in rows:
            if len(row) >= 6:
                try:
                    utils.append(float(row[2]))
                except Exception:
                    pass
                try:
                    total_mb += float(row[3])
                except Exception:
                    pass
                try:
                    used_mb += float(row[4])
                except Exception:
                    pass
                try:
                    free_mb += float(row[5])
                except Exception:
                    pass

        return GpuSnapshot(
            backend="nvidia-smi",
            device_count=total_devices,
            name=names[0] if names else None,
            driver_version=driver_versions[0] if driver_versions else None,
            utilization_percent=(sum(utils) / len(utils)) if utils else None,
            memory_total_mb=total_mb if total_mb > 0 else None,
            memory_used_mb=used_mb if used_mb > 0 else None,
            memory_free_mb=free_mb if free_mb > 0 else None,
        )

    def _gpu_snapshot_drm(self) -> GpuSnapshot | None:
        """
        Detección genérica de GPU por nodos DRM en Linux.
        No aporta telemetría de uso/VRAM, pero confirma hardware visible.
        """
        try:
            dri = pathlib.Path("/dev/dri")
            if not dri.exists():
                return None
            render_nodes = sorted(dri.glob("renderD*"))
            card_nodes = sorted(dri.glob("card*"))
            device_count = len(render_nodes) if render_nodes else len(card_nodes)
            if device_count <= 0:
                return None
            return GpuSnapshot(
                backend="drm",
                device_count=device_count,
                name="GPU detectada por /dev/dri",
            )
        except Exception:
            return None

    def _gpu_snapshot_lspci(self) -> GpuSnapshot | None:
        """
        Fallback por lspci para entornos donde /dev/dri no está montado
        pero el dispositivo PCI sí está visible.
        """
        if shutil.which("lspci") is None:
            return None
        try:
            result = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None

        lines = []
        for raw in result.stdout.splitlines():
            text = raw.strip()
            lower = text.lower()
            if " vga " in f" {lower} " or "3d controller" in lower or "display controller" in lower:
                if any(vendor in lower for vendor in ("nvidia", "amd", "advanced micro devices", "intel", "radeon", "geforce", "arc")):
                    lines.append(text)
        if not lines:
            return None

        return GpuSnapshot(
            backend="lspci",
            device_count=len(lines),
            name=lines[0],
        )
