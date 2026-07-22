"""
Módulo de procesos de audio para ToneFinish.

Cada proceso es un módulo independiente con una interfaz común que permite:
- Habilitarlo/deshabilitarlo individualmente
- Reordenarlo en la GUI
- Configurar sus parámetros

Arquitectura:
- BaseProcess: Clase base abstracta para todos los procesos
- ProcessRegistry: Registro central de todos los procesos disponibles
- Cada proceso en su propio archivo (repair.py, deesser.py, etc.)

El pipeline real se construye en audio_processing.build_preprocess_chain().
"""

from processes.base import BaseProcess, ProcessConfig, ProcessCategory, ProcessRegistry
from processes.repair import RepairProcess
from processes.deesser import DeesserProcess
from processes.tone_eq import ToneEQProcess
from processes.dynamic_eq import DynamicEQProcess
from processes.vocal import VocalProcess
from processes.complementary import TransientProcess, StereoGuardProcess, LowEndProcess, SpectralProcess
from processes.multiband import MultibandProcess
from processes.saturation import SaturationProcess
from processes.glue import GlueProcess
from processes.autogain import AutoGainProcess
from processes.loudness import LoudnessProcess
from processes.master_limiter import MasterLimiterProcess
from processes.contracts import (
    AudioFunctionAction,
    AudioFunctionRegistry,
    AudioFunctionSpec,
    AudioProcessContext,
    ContractError,
    FilterLabelFactory,
    ParameterSpec,
)
from processes.catalog import function_registry

# Registro global de procesos
registry = ProcessRegistry()

# Registrar todos los procesos en orden por defecto
registry.register(RepairProcess())
registry.register(DeesserProcess())
registry.register(ToneEQProcess())
registry.register(DynamicEQProcess())
registry.register(VocalProcess())
registry.register(LowEndProcess())
registry.register(SpectralProcess())
registry.register(TransientProcess())
registry.register(StereoGuardProcess())
registry.register(MultibandProcess())
registry.register(SaturationProcess())
registry.register(GlueProcess())
registry.register(AutoGainProcess())
registry.register(MasterLimiterProcess())
registry.register(LoudnessProcess())

# Importar después de crear el registro evita ciclos durante el arranque.
from processes.orchestrator import (
    AudioProcessOrchestrator,
    CompiledAudioGraph,
    migrate_legacy_preprocess_config,
    migrate_legacy_registry_state,
    orchestrator,
)
from processes.audit import (
    build_execution_audit, catalog_fingerprint, effective_execution_actions,
    fingerprint_audio_source, verify_audio_source,
)
from processes.quality import compare_audio_ab, build_catalog_certification, write_catalog_certification

__all__ = [
    "BaseProcess",
    "ProcessConfig", 
    "ProcessCategory",
    "ProcessRegistry",
    "registry",
    "RepairProcess",
    "DeesserProcess",
    "ToneEQProcess",
    "DynamicEQProcess",
    "VocalProcess",
    "TransientProcess", "StereoGuardProcess", "LowEndProcess", "SpectralProcess",
    "MultibandProcess",
    "SaturationProcess",
    "GlueProcess",
    "AutoGainProcess",
    "LoudnessProcess",
    "MasterLimiterProcess",
    "AudioFunctionAction",
    "AudioFunctionRegistry",
    "AudioFunctionSpec",
    "AudioProcessContext",
    "ContractError",
    "FilterLabelFactory",
    "ParameterSpec",
    "function_registry",
    "AudioProcessOrchestrator",
    "CompiledAudioGraph",
    "migrate_legacy_preprocess_config",
    "migrate_legacy_registry_state",
    "orchestrator",
    "build_execution_audit",
    "catalog_fingerprint",
    "effective_execution_actions",
    "fingerprint_audio_source",
    "verify_audio_source",
    "compare_audio_ab", "build_catalog_certification", "write_catalog_certification",
]
