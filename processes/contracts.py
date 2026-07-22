"""Contratos estables entre la IA, los plugins y el pipeline de audio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple
import math
import re


ID_PATTERN = re.compile(r"^audio\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
PLUGIN_ID_PATTERN = re.compile(r"^audio\.[a-z][a-z0-9_]*$")
BAND_IDS = ("sub_bass", "bass", "low_mid", "mid", "high_mid", "air")
ACTION_OPERATIONS = (
    "cut", "boost", "attenuate", "expand", "narrow", "protect", "neutral",
)

_SIGNED_CONTROL_BY_FUNCTION = {
    "audio.tone_eq.band": "gain_db",
    "audio.tone_eq.tilt": "gain_db",
    "audio.multiband.eq": "gain_db",
    "audio.dynamic_eq.motion": "gain_db",
    "audio.transient.dynamic_control": "amount_db",
    "audio.low_end.dynamic_balance": "gain_db",
    "audio.autogain.output_gain": "gain_db",
    "audio.multiband.saturation": "drive_db",
    "audio.saturation.softclip": "drive_db",
}


class ContractError(ValueError):
    """Error de definición o de validación del contrato de procesamiento."""


def infer_action_operation(function_id: str, params: Mapping[str, Any]) -> str:
    """Infiere intención para acciones internas/legacy sin ocultar el signo."""
    if function_id in {"audio.multiband.stereo_width", "audio.stereo.correlation_guard"}:
        width = float(params.get("width", 1.0))
        return "narrow" if width < 1.0 else "expand" if width > 1.0 else "neutral"
    if function_id in {"audio.tone_eq.high_pass", "audio.tone_eq.low_pass"}:
        return "cut"
    if function_id in {"audio.dynamic_eq.resonance", "audio.vocal.resonance_suppressor"}:
        return "attenuate"
    if function_id == "audio.vocal.center_naturalizer":
        return "protect"
    if function_id == "audio.spectral.deharsh": return "attenuate"
    if function_id == "audio.spectral.dullness_recovery": return "boost"
    signed_name = _SIGNED_CONTROL_BY_FUNCTION.get(function_id)
    if signed_name is not None:
        value = float(params.get(signed_name, 0.0))
        return "cut" if value < 0.0 else "boost" if value > 0.0 else "neutral"
    if function_id.startswith("audio.repair.") or function_id in {
        "audio.deesser.sibilance_reduction", "audio.multiband.compressor",
        "audio.multiband.limiter", "audio.glue.bus_compressor",
    }:
        return "attenuate"
    if function_id in {
        "audio.autogain.interstage_limiter", "audio.autogain.final_peak",
        "audio.loudness.normalize", "audio.limiter.true_peak",
    }:
        return "protect"
    if function_id in {"audio.loudness.fade_in", "audio.loudness.fade_out"}:
        return "attenuate"
    if function_id in {"audio.saturation.exciter"}:
        return "boost"
    return "protect"


def supported_operations_for_function(function_id: str) -> Tuple[str, ...]:
    if function_id in _SIGNED_CONTROL_BY_FUNCTION:
        return ("cut", "boost", "attenuate", "neutral")
    if function_id in {"audio.multiband.stereo_width", "audio.stereo.correlation_guard"}:
        return ("narrow", "expand", "neutral")
    if function_id in {"audio.tone_eq.high_pass", "audio.tone_eq.low_pass"}:
        return ("cut",)
    if function_id in {"audio.dynamic_eq.resonance", "audio.vocal.resonance_suppressor"}:
        return ("cut", "attenuate", "protect")
    if function_id == "audio.vocal.center_naturalizer":
        return ("protect", "attenuate")
    if function_id == "audio.spectral.deharsh": return ("cut", "attenuate", "protect")
    if function_id == "audio.spectral.dullness_recovery": return ("boost", "neutral")
    if function_id.startswith("audio.repair.") or function_id in {
        "audio.deesser.sibilance_reduction", "audio.multiband.compressor",
        "audio.multiband.limiter", "audio.glue.bus_compressor",
        "audio.loudness.fade_in", "audio.loudness.fade_out",
    }:
        return ("attenuate", "protect")
    if function_id == "audio.saturation.exciter":
        return ("boost", "neutral")
    return ("protect",)


def validate_operation_semantics(
    function_id: str, operation: str, params: Mapping[str, Any]
) -> None:
    """Impide declarar boost/cut/narrow/expand con parámetros contradictorios."""
    if operation not in ACTION_OPERATIONS:
        raise ContractError(f"operation debe ser uno de {ACTION_OPERATIONS}")
    supported = supported_operations_for_function(function_id)
    if operation not in supported:
        raise ContractError(
            f"operation={operation} no es compatible con {function_id}; permitidas={supported}"
        )
    signed_name = _SIGNED_CONTROL_BY_FUNCTION.get(function_id)
    if signed_name is not None and signed_name in params:
        value = float(params[signed_name])
        if operation == "cut" and value >= 0.0:
            raise ContractError(f"operation=cut requiere {signed_name} negativo")
        if operation == "boost" and value <= 0.0:
            raise ContractError(f"operation=boost requiere {signed_name} positivo")
        if operation == "neutral" and abs(value) > 1e-9:
            raise ContractError(f"operation=neutral requiere {signed_name}=0")
        if operation == "attenuate" and value > 0.0:
            raise ContractError(f"operation=attenuate no admite {signed_name} positivo")
    if function_id in {"audio.multiband.stereo_width", "audio.stereo.correlation_guard"}:
        width = float(params.get("width", 1.0))
        if operation == "narrow" and width >= 1.0:
            raise ContractError("operation=narrow requiere width < 1")
        if operation == "expand" and width <= 1.0:
            raise ContractError("operation=expand requiere width > 1")
        if operation == "neutral" and abs(width - 1.0) > 1e-9:
            raise ContractError("operation=neutral requiere width=1")


def _validate_evidence(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(evidence, Mapping):
        raise ContractError("evidence debe ser un objeto")
    clean: Dict[str, Any] = {}
    for key, value in evidence.items():
        if not isinstance(key, str) or not key.strip():
            raise ContractError("evidence requiere claves de texto no vacías")
        if isinstance(value, float) and not math.isfinite(value):
            raise ContractError(f"evidence.{key} debe ser finito")
        if not isinstance(value, (str, int, float, bool)) or value is None:
            raise ContractError(f"evidence.{key} debe ser escalar")
        clean[key] = value
    return clean


@dataclass(frozen=True)
class ParameterSpec:
    """Esquema compacto, serializable y apto para prompts de un parámetro."""

    value_type: str
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Tuple[Any, ...] = ()
    required: bool = False
    description: str = ""

    def validate(self, name: str, value: Any) -> Any:
        expected = {
            "bool": bool,
            "int": int,
            "float": (int, float),
            "str": str,
        }.get(self.value_type)
        if expected is None:
            raise ContractError(f"Tipo de parámetro no soportado: {self.value_type}")
        if isinstance(value, bool) and self.value_type in ("int", "float"):
            raise ContractError(f"{name} debe ser {self.value_type}, no bool")
        if not isinstance(value, expected):
            raise ContractError(f"{name} debe ser {self.value_type}")
        if self.choices and value not in self.choices:
            raise ContractError(f"{name} debe ser uno de {self.choices}")
        if self.minimum is not None and value < self.minimum:
            raise ContractError(f"{name} debe ser >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ContractError(f"{name} debe ser <= {self.maximum}")
        return float(value) if self.value_type == "float" else value

    def to_dict(self) -> Dict[str, Any]:
        return {
            key: value for key, value in {
                "type": self.value_type, "default": self.default,
                "minimum": self.minimum, "maximum": self.maximum,
                "choices": list(self.choices), "required": self.required,
                "description": self.description,
            }.items() if value not in (None, (), [], "")
        }


@dataclass(frozen=True)
class AudioFunctionSpec:
    """Descripción estable de una capacidad que la IA puede seleccionar."""

    function_id: str
    plugin_id: str
    name: str
    description: str
    parameters: Mapping[str, ParameterSpec] = field(default_factory=dict)
    supported_targets: Tuple[str, ...] = ()
    conflicts_with: Tuple[str, ...] = ()
    requires_analysis: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not ID_PATTERN.fullmatch(self.function_id):
            raise ContractError(f"function_id inválido: {self.function_id}")
        if not PLUGIN_ID_PATTERN.fullmatch(self.plugin_id):
            raise ContractError(f"plugin_id inválido: {self.plugin_id}")

    def validate_action(self, action: "AudioFunctionAction") -> "AudioFunctionAction":
        if action.function_id != self.function_id:
            raise ContractError(f"La acción no corresponde a {self.function_id}")
        unknown = set(action.params) - set(self.parameters)
        if unknown:
            raise ContractError(f"Parámetros desconocidos para {self.function_id}: {sorted(unknown)}")
        missing = [k for k, spec in self.parameters.items() if spec.required and k not in action.params]
        if missing:
            raise ContractError(f"Parámetros requeridos ausentes: {missing}")
        if action.target is not None and action.target not in self.supported_targets:
            raise ContractError(f"Target inválido para {self.function_id}: {action.target}")
        if self.supported_targets and action.target is None:
            raise ContractError(f"{self.function_id} requiere target")
        validated = {k: self.parameters[k].validate(k, v) for k, v in action.params.items()}
        operation = action.operation or infer_action_operation(action.function_id, validated)
        validate_operation_semantics(action.function_id, operation, validated)
        return AudioFunctionAction(
            function_id=action.function_id, enabled=action.enabled,
            params=validated, target=action.target, reason=action.reason,
            confidence=action.confidence, operation=operation,
            evidence=_validate_evidence(action.evidence),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "function_id": self.function_id, "plugin_id": self.plugin_id,
            "name": self.name, "description": self.description,
            "parameters": {k: v.to_dict() for k, v in self.parameters.items()},
            "supported_targets": list(self.supported_targets),
            "supported_operations": list(supported_operations_for_function(self.function_id)),
            "conflicts_with": list(self.conflicts_with),
            "requires_analysis": list(self.requires_analysis),
        }


@dataclass(frozen=True)
class AudioFunctionAction:
    """Decisión de IA ya asociada a una función estable."""

    function_id: str
    enabled: bool = True
    params: Mapping[str, Any] = field(default_factory=dict)
    target: Optional[str] = None
    reason: str = ""
    confidence: Optional[float] = None
    operation: Optional[str] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ContractError("confidence debe estar entre 0 y 1")
        if self.operation is not None and self.operation not in ACTION_OPERATIONS:
            raise ContractError(f"operation debe ser uno de {ACTION_OPERATIONS}")
        _validate_evidence(self.evidence)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AudioFunctionAction":
        allowed = {
            "function_id", "enabled", "params", "target", "reason", "confidence",
            "operation", "evidence",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ContractError(f"Campos desconocidos en acción: {sorted(unknown)}")
        if "function_id" not in data:
            raise ContractError("function_id es obligatorio")
        return cls(
            function_id=data["function_id"], enabled=data.get("enabled", True),
            params=data.get("params", {}), target=data.get("target"),
            reason=data.get("reason", ""), confidence=data.get("confidence"),
            operation=data.get("operation"), evidence=data.get("evidence", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "function_id": self.function_id, "enabled": self.enabled,
            "params": dict(self.params),
        }
        if self.target is not None:
            result["target"] = self.target
        if self.reason:
            result["reason"] = self.reason
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.operation is not None:
            result["operation"] = self.operation
        if self.evidence:
            result["evidence"] = dict(self.evidence)
        return result


@dataclass(frozen=True)
class AudioProcessContext:
    """Datos inmutables del audio disponibles para todos los plugins."""

    audio_id: str
    sample_rate: int
    channels: int
    duration: Optional[float] = None
    analysis: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.audio_id:
            raise ContractError("audio_id es obligatorio")
        if self.sample_rate <= 0 or self.channels <= 0:
            raise ContractError("sample_rate y channels deben ser positivos")


class FilterLabelFactory:
    """Genera labels FFmpeg únicos y deterministas dentro de un grafo."""

    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}

    def new(self, function_id: str, suffix: str = "out") -> str:
        stem = function_id.removeprefix("audio.").replace(".", "_")
        stem = re.sub(r"[^a-zA-Z0-9_]", "_", stem)
        key = f"{stem}_{suffix}"
        self._counters[key] = self._counters.get(key, 0) + 1
        return f"{key}_{self._counters[key]}"


class AudioFunctionRegistry:
    """Catálogo único de funciones, plugins y alias de compatibilidad."""

    def __init__(self, aliases: Optional[Mapping[str, str]] = None) -> None:
        self._specs: Dict[str, AudioFunctionSpec] = {}
        self._aliases = dict(aliases or {})

    def register(self, spec: AudioFunctionSpec) -> None:
        if spec.function_id in self._specs:
            raise ContractError(f"function_id duplicado: {spec.function_id}")
        self._specs[spec.function_id] = spec

    def register_many(self, specs: Iterable[AudioFunctionSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def resolve_id(self, function_id: str) -> str:
        resolved = self._aliases.get(function_id, function_id)
        if resolved not in self._specs:
            raise ContractError(f"function_id desconocido: {function_id}")
        return resolved

    def get(self, function_id: str) -> AudioFunctionSpec:
        return self._specs[self.resolve_id(function_id)]

    def validate(self, action: AudioFunctionAction) -> AudioFunctionAction:
        resolved = self.resolve_id(action.function_id)
        normalized = AudioFunctionAction(
            function_id=resolved, enabled=action.enabled, params=action.params,
            target=action.target, reason=action.reason, confidence=action.confidence,
            operation=action.operation, evidence=action.evidence,
        )
        return self._specs[resolved].validate_action(normalized)

    def validate_plan(
        self,
        actions: Iterable[AudioFunctionAction],
        context: Optional[AudioProcessContext] = None,
    ) -> Tuple[AudioFunctionAction, ...]:
        """Valida una decisión completa, incluidos conflictos y análisis requerido."""
        validated = tuple(self.validate(action) for action in actions)
        enabled_ids = {action.function_id for action in validated if action.enabled}
        for action in validated:
            if not action.enabled:
                continue
            spec = self._specs[action.function_id]
            conflicts = enabled_ids.intersection(spec.conflicts_with)
            if conflicts:
                raise ContractError(
                    f"{action.function_id} entra en conflicto con {sorted(conflicts)}"
                )
            if context is not None:
                missing = [key for key in spec.requires_analysis if key not in context.analysis]
                if missing:
                    raise ContractError(
                        f"{action.function_id} requiere análisis ausente: {missing}"
                    )
        return validated

    def all(self) -> Tuple[AudioFunctionSpec, ...]:
        return tuple(self._specs.values())

    def for_plugin(self, plugin_id: str) -> Tuple[AudioFunctionSpec, ...]:
        return tuple(spec for spec in self._specs.values() if spec.plugin_id == plugin_id)

    def to_dict(self) -> Dict[str, Any]:
        return {"functions": [s.to_dict() for s in self.all()], "aliases": dict(self._aliases)}
