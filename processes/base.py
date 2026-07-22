"""
Clase base abstracta para todos los procesos de audio.

Cada proceso debe heredar de BaseProcess e implementar:
- build_filter(): Construye la cadena de filtros ffmpeg
- get_params(): Retorna los parámetros actuales del proceso
- set_params(): Actualiza los parámetros del proceso
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


class ProcessCategory(Enum):
    """Categorías de procesos para organización en la GUI."""
    REPAIR = "repair"       # Reparación: noise, declip, declick, pink_noise
    MIX = "mix"             # Mezcla: deesser, tone_eq, multiband, saturation, stereo, glue
    MASTER = "master"       # Mastering: autogain, loudness, limiter
    OPTIONS = "options"     # Opciones: headroom, normalize


@dataclass
class ProcessConfig:
    """Configuración de un proceso."""
    enabled: bool = True
    order: int = 0          # Orden en la cadena de procesamiento
    params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "order": self.order,
            "params": self.params.copy()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessConfig":
        return cls(
            enabled=data.get("enabled", True),
            order=data.get("order", 0),
            params=data.get("params", {})
        )


class BaseProcess(ABC):
    """
    Clase base para todos los procesos de audio.
    
    Cada proceso debe implementar:
    - build_filter(): Construye la cadena de filtros ffmpeg
    - get_default_params(): Retorna parámetros por defecto
    
    Atributos:
    - id: Identificador único del proceso (ej: "repair", "deesser")
    - name: Nombre legible para la GUI (ej: "Reparación", "De-Esser")
    - description: Descripción del proceso
    - category: Categoría (REPAIR, MIX, MASTER, OPTIONS)
    - config: Configuración actual (enabled, order, params)
    """
    
    def __init__(self):
        self._config = ProcessConfig(
            enabled=True,
            order=self.default_order,
            params=self.get_default_params()
        )
    
    @property
    @abstractmethod
    def id(self) -> str:
        """Identificador único del proceso."""
        pass

    @property
    def plugin_id(self) -> str:
        """ID estable del plugin usado por IA, UI y orquestador nuevo."""
        from processes.catalog import PLUGIN_ID_BY_PROCESS_ID

        try:
            return PLUGIN_ID_BY_PROCESS_ID[self.id]
        except KeyError as exc:
            raise ValueError(f"El proceso {self.id!r} no tiene plugin_id registrado") from exc

    def function_specs(self):
        """Funciones semánticas que este plugin ofrece a la IA."""
        from processes.catalog import function_registry

        return function_registry.for_plugin(self.plugin_id)

    def validate_action(self, action):
        """Valida y normaliza una decisión de IA para este plugin."""
        from processes.catalog import function_registry

        validated = function_registry.validate(action)
        spec = function_registry.get(validated.function_id)
        if spec.plugin_id != self.plugin_id:
            raise ValueError(
                f"{validated.function_id} pertenece a {spec.plugin_id}, no a {self.plugin_id}"
            )
        return validated

    def build_function(self, action, input_label, context, labels):
        """Compila una función validada; cada DSP lo implementará en la Fase 2."""
        self.validate_action(action)
        raise NotImplementedError(
            f"{self.plugin_id} todavía no implementa build_function()"
        )
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre legible para la GUI."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Descripción del proceso."""
        pass
    
    @property
    @abstractmethod
    def category(self) -> ProcessCategory:
        """Categoría del proceso (REPAIR, MIX, MASTER, OPTIONS)."""
        pass
    
    @property
    @abstractmethod
    def default_order(self) -> int:
        """Orden por defecto en la cadena de procesamiento."""
        pass
    
    @property
    def enabled(self) -> bool:
        """Si el proceso está habilitado."""
        return self._config.enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        self._config.enabled = value
    
    @property
    def order(self) -> int:
        """Orden en la cadena de procesamiento."""
        return self._config.order
    
    @order.setter
    def order(self, value: int):
        self._config.order = value
    
    @property
    def config(self) -> ProcessConfig:
        """Configuración actual del proceso."""
        return self._config
    
    @config.setter
    def config(self, value: ProcessConfig):
        self._config = value
    
    @abstractmethod
    def get_default_params(self) -> Dict[str, Any]:
        """Retorna los parámetros por defecto del proceso."""
        pass
    
    def get_params(self) -> Dict[str, Any]:
        """Retorna los parámetros actuales del proceso."""
        return self._config.params.copy()
    
    def set_params(self, params: Dict[str, Any]):
        """Actualiza los parámetros del proceso."""
        self._config.params.update(params)
    
    def set_param(self, key: str, value: Any):
        """Actualiza un parámetro individual."""
        self._config.params[key] = value
    
    def get_param(self, key: str, default: Any = None) -> Any:
        """Obtiene un parámetro individual."""
        return self._config.params.get(key, default)
    
    @abstractmethod
    def build_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye la cadena de filtros ffmpeg para este proceso.
        
        Args:
            input_label: Etiqueta de entrada del flujo de audio
            **kwargs: Parámetros adicionales específicos del proceso
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
            - cadena_filtros: String de filtros ffmpeg (vacío si disabled)
            - etiqueta_salida: Nueva etiqueta de salida
        """
        pass
    
    def is_enabled_with_chain(self, chain_enabled: bool) -> bool:
        """
        Verifica si el proceso está habilitado considerando la cadena.
        
        Args:
            chain_enabled: Si la cadena completa (repair/mix/master) está habilitada
            
        Returns:
            True si ambos (proceso y cadena) están habilitados
        """
        return self.enabled and chain_enabled
    
    def reset_to_defaults(self):
        """Resetea los parámetros a sus valores por defecto."""
        self._config.params = self.get_default_params()
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id='{self.id}', enabled={self.enabled}, order={self.order})"


class ProcessRegistry:
    """
    Registro central de todos los procesos disponibles.
    
    Permite:
    - Registrar procesos
    - Obtener procesos por ID o categoría
    - Reordenar procesos
    - Habilitar/deshabilitar procesos
    """
    
    def __init__(self):
        self._processes: Dict[str, BaseProcess] = {}
        self._order: List[str] = []
    
    def register(self, process: BaseProcess):
        """Registra un proceso."""
        if process.id in self._processes:
            raise ValueError(f"ID de proceso duplicado: {process.id}")
        self._processes[process.id] = process
        if process.id not in self._order:
            self._order.append(process.id)
    
    def unregister(self, process_id: str):
        """Elimina un proceso del registro."""
        if process_id in self._processes:
            del self._processes[process_id]
            self._order.remove(process_id)
    
    def get(self, process_id: str) -> Optional[BaseProcess]:
        """Obtiene un proceso por su ID."""
        return self._processes.get(process_id)
    
    def get_all(self) -> List[BaseProcess]:
        """Retorna todos los procesos en orden."""
        return [self._processes[pid] for pid in self._order if pid in self._processes]
    
    def get_enabled(self) -> List[BaseProcess]:
        """Retorna solo los procesos habilitados en orden."""
        return [p for p in self.get_all() if p.enabled]
    
    def get_by_category(self, category: ProcessCategory) -> List[BaseProcess]:
        """Retorna procesos de una categoría específica."""
        return [p for p in self.get_all() if p.category == category]
    
    def get_enabled_by_category(self, category: ProcessCategory) -> List[BaseProcess]:
        """Retorna procesos habilitados de una categoría."""
        return [p for p in self.get_all() if p.category == category and p.enabled]
    
    def set_order(self, order: List[str]):
        """Establece el orden de los procesos."""
        # Validar que todos los IDs existen
        valid_ids = [pid for pid in order if pid in self._processes]
        # Agregar cualquier proceso faltante al final
        for pid in self._processes:
            if pid not in valid_ids:
                valid_ids.append(pid)
        self._order = valid_ids
    
    def move_up(self, process_id: str) -> bool:
        """Mueve un proceso una posición arriba."""
        if process_id not in self._order:
            return False
        idx = self._order.index(process_id)
        if idx > 0:
            self._order[idx], self._order[idx-1] = self._order[idx-1], self._order[idx]
            return True
        return False
    
    def move_down(self, process_id: str) -> bool:
        """Mueve un proceso una posición abajo."""
        if process_id not in self._order:
            return False
        idx = self._order.index(process_id)
        if idx < len(self._order) - 1:
            self._order[idx], self._order[idx+1] = self._order[idx+1], self._order[idx]
            return True
        return False
    
    def enable(self, process_id: str, enabled: bool = True):
        """Habilita o deshabilita un proceso."""
        if process_id in self._processes:
            self._processes[process_id].enabled = enabled
    
    def enable_category(self, category: ProcessCategory, enabled: bool = True):
        """Habilita o deshabilita todos los procesos de una categoría."""
        for process in self.get_by_category(category):
            process.enabled = enabled
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa el registro a un diccionario."""
        return {
            "order": self._order.copy(),
            "processes": {
                pid: process.config.to_dict()
                for pid, process in self._processes.items()
            }
        }
    
    def from_dict(self, data: Dict[str, Any]):
        """Carga configuración desde un diccionario."""
        if "order" in data:
            self.set_order(data["order"])
        if "processes" in data:
            for pid, config_data in data["processes"].items():
                if pid in self._processes:
                    self._processes[pid].config = ProcessConfig.from_dict(config_data)
    
    def __len__(self) -> int:
        return len(self._processes)
    
    def __iter__(self):
        return iter(self.get_all())
    
    def __contains__(self, process_id: str) -> bool:
        return process_id in self._processes
