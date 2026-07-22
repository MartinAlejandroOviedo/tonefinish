"""Widget mejorado para orden de procesos con estado visual."""
from __future__ import annotations

from typing import Dict, List, Optional, Callable

from ui.qt_compat import (
    QApplication, QLabel, QVBoxLayout, QHBoxLayout, QWidget, Qt, 
    Signal, PYSIDE_AVAILABLE, QCheckBox, QFrame
)

try:
    if PYSIDE_AVAILABLE:
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag, QPixmap
    else:
        QMimeData = None
        QDrag = None
        QPixmap = None
except Exception:
    QMimeData = None
    QDrag = None
    QPixmap = None


# Configuración de procesos con iconos y categorías
PROCESS_CONFIG = {
    "repair": {"name": "Reparación", "icon": "🔧", "category": "repair"},
    "deesser": {"name": "De-Esser", "icon": "🔊", "category": "mix"},
    "tone_eq": {"name": "EQ Tonal", "icon": "🎚️", "category": "mix"},
    "dynamic_eq": {"name": "EQ Dinámica IA", "icon": "〰️", "category": "mix"},
    "vocal": {"name": "Naturalizador Vocal IA", "icon": "🎙️", "category": "mix"},
    "low_end": {"name": "Balance Dinámico de Graves", "icon": "🔉", "category": "mix"},
    "spectral": {"name": "Control Espectral IA", "icon": "🌈", "category": "mix"},
    "transient": {"name": "Control de Transientes", "icon": "⚡", "category": "mix"},
    "stereo_guard": {"name": "Guardia de Correlación", "icon": "↔️", "category": "mix"},
    "glue": {"name": "Glue Comp", "icon": "🔗", "category": "mix"},
    "stereo_dynamic": {"name": "Stereo Dyn", "icon": "🔄", "category": "mix"},
    "saturation": {"name": "Saturación", "icon": "🔥", "category": "mix"},
    "loudness": {"name": "Loudness", "icon": "📢", "category": "master"},
    "master_limiter": {"name": "Limitador", "icon": "🧱", "category": "master"},
}

# Colores por categoría
CATEGORY_COLORS = {
    "io": "#3a5f8a",      # Azul - entrada/salida
    "repair": "#5a8a5a",  # Verde - reparación
    "mix": "#8a6a3a",     # Naranja - mezcla
    "master": "#6a3a8a",  # Púrpura - mastering
}


class ProcessItem(QFrame):
    """Item de proceso con checkbox, icono y nombre."""
    activated = Signal(str)
    stateChanged = Signal(str, bool)
    
    def __init__(self, key: str, config: dict) -> None:
        super().__init__()
        self.key = key
        self.config = config
        self._drag_start_pos = None
        self._enabled = True
        self._index = 0
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # Índice
        self.index_label = QLabel("01")
        self.index_label.setFixedWidth(24)
        self.index_label.setStyleSheet("font-weight: bold; color: #fff;")
        layout.addWidget(self.index_label)
        
        # Checkbox (oculto para items fijos)
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.stateChanged.connect(self._on_checkbox_changed)
        if config.get("fixed"):
            self.checkbox.hide()
        layout.addWidget(self.checkbox)
        
        # Icono
        icon = QLabel(config.get("icon", "⚙️"))
        icon.setFixedWidth(20)
        layout.addWidget(icon)
        
        # Nombre
        self.name_label = QLabel(config.get("name", key))
        self.name_label.setStyleSheet("font-weight: 500;")
        layout.addWidget(self.name_label, 1)
        
        # Indicador de arrastre
        drag_hint = QLabel("⋮⋮")
        drag_hint.setStyleSheet("color: #fff;")
        if not config.get("fixed"):
            layout.addWidget(drag_hint)
        
        self.setLayout(layout)
        self._update_style()
    
    def _on_checkbox_changed(self, state: int) -> None:
        self._enabled = state == 2  # Qt.CheckState.Checked
        self._update_style()
        self.stateChanged.emit(self.key, self._enabled)
    
    def set_enabled_state(self, enabled: bool) -> None:
        """Establece el estado sin emitir señal."""
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(enabled)
        self._enabled = enabled
        self._update_style()
        self.checkbox.blockSignals(False)
    
    def is_process_enabled(self) -> bool:
        return self._enabled or self.config.get("fixed", False)
    
    def update_index(self, index: int) -> None:
        self._index = index
        self.index_label.setText(f"{index:02d}")
    
    def _update_style(self) -> None:
        category = self.config.get("category", "mix")
        base_color = CATEGORY_COLORS.get(category, "#555")
        
        if self._enabled or self.config.get("fixed"):
            self.setStyleSheet(f"""
                ProcessItem {{
                    background: {base_color};
                    border: 1px solid #444;
                    border-radius: 4px;
                    color: #fff;
                }}
                ProcessItem:hover {{
                    border: 1px solid #888;
                    background: {base_color}cc;
                }}
            """)
            self.name_label.setStyleSheet("font-weight: 500; color: #fff;")
        else:
            self.setStyleSheet("""
                ProcessItem {
                    background: #2a2a2a;
                    border: 1px dashed #444;
                    border-radius: 4px;
                    color: #fff;
                }
            """)
            self.name_label.setStyleSheet("font-weight: 400; color: #fff; text-decoration: line-through;")
    
    def mousePressEvent(self, e) -> None:
        if self.config.get("fixed"):
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = e.position()
        super().mousePressEvent(e)
    
    def mouseMoveEvent(self, e) -> None:
        if self.config.get("fixed"):
            return
        if not QDrag or not QMimeData or not QPixmap:
            return
        if e.buttons() == Qt.MouseButton.LeftButton:
            if self._drag_start_pos is None:
                return
            if QApplication is not None:
                distance = (e.position() - self._drag_start_pos).manhattanLength()
                if distance < QApplication.startDragDistance():
                    return
            drag = QDrag(self)
            mime = QMimeData()
            drag.setMimeData(mime)
            pixmap = QPixmap(1, 1)
            pixmap.fill(Qt.GlobalColor.transparent)
            drag.setPixmap(pixmap)
            drag.exec(Qt.DropAction.MoveAction)
            self.show()
    
    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.key)
        super().mouseDoubleClickEvent(e)


class DragTargetIndicator(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(4)
        self.setStyleSheet("background: #4a9eff; border-radius: 2px;")


class ProcessOrderWidget(QWidget):
    """Widget de orden de procesos con estado visual y drag & drop."""
    orderChanged = Signal(list)
    processStateChanged = Signal(str, bool)
    
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        
        self._items: Dict[str, ProcessItem] = {}
        self._checkbox_callbacks: Dict[str, tuple] = {}
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)
        
        # Leyenda de colores
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for cat, color in CATEGORY_COLORS.items():
            cat_names = {"io": "E/S", "repair": "Reparación", "mix": "Mezcla", "master": "Master"}
            dot = QLabel(f"● {cat_names.get(cat, cat)}")
            dot.setStyleSheet(f"color: {color}; font-size: 11px;")
            legend.addWidget(dot)
        legend.addStretch()
        main_layout.addLayout(legend)
        
        # Contenedor de items
        self.items_layout = QVBoxLayout()
        self.items_layout.setSpacing(3)
        self._drag_target_indicator = DragTargetIndicator()
        self.items_layout.addWidget(self._drag_target_indicator)
        self._drag_target_indicator.hide()
        main_layout.addLayout(self.items_layout)
        
        # Info
        info = QLabel("💡 Arrastra para reordenar • Doble-click para ir al proceso")
        info.setStyleSheet("color: #fff; font-size: 11px; margin-top: 8px;")
        main_layout.addWidget(info)
        
        main_layout.addStretch()
        self.setLayout(main_layout)
    
    def add_process(self, key: str) -> None:
        """Agrega un proceso a la lista."""
        if key not in PROCESS_CONFIG:
            return
        if key in self._items:
            return
        
        config = PROCESS_CONFIG[key]
        item = ProcessItem(key, config)
        item.activated.connect(lambda k: self._on_item_activated(k))
        item.stateChanged.connect(self._on_item_state_changed)
        
        self._items[key] = item
        self.items_layout.addWidget(item)
        self._update_indices()
    
    def bind_checkbox(self, key: str, checkbox: QCheckBox) -> None:
        """Vincula un checkbox externo con el estado del proceso."""
        if key not in self._items:
            return
        
        item = self._items[key]
        
        # Sincronizar estado inicial
        item.set_enabled_state(checkbox.isChecked())
        
        # Conectar cambios del checkbox externo
        def on_external_change(state: int) -> None:
            item.set_enabled_state(state == 2)
        
        checkbox.stateChanged.connect(on_external_change)
        self._checkbox_callbacks[key] = (checkbox, on_external_change)
    
    def _on_item_activated(self, key: str) -> None:
        # Reemitir para navegación externa
        pass
    
    def _on_item_state_changed(self, key: str, enabled: bool) -> None:
        # Sincronizar con checkbox externo
        if key in self._checkbox_callbacks:
            checkbox, _ = self._checkbox_callbacks[key]
            checkbox.blockSignals(True)
            checkbox.setChecked(enabled)
            checkbox.blockSignals(False)
        self.processStateChanged.emit(key, enabled)
    
    def dragEnterEvent(self, e) -> None:
        e.accept()
    
    def dragLeaveEvent(self, e) -> None:
        self._drag_target_indicator.hide()
        source = e.source()
        if source is not None:
            source.show()
        e.accept()
    
    def dragMoveEvent(self, e) -> None:
        index = self._find_drop_location(e)
        if index is not None:
            self.items_layout.insertWidget(index, self._drag_target_indicator)
            source = e.source()
            if source is not None:
                source.hide()
            self._drag_target_indicator.show()
        e.accept()
    
    def dropEvent(self, e) -> None:
        widget = e.source()
        self._drag_target_indicator.hide()
        index = self.items_layout.indexOf(self._drag_target_indicator)
        if index is not None and widget is not None:
            # No permitir mover antes de "input" o después de "output"
            input_idx = self._get_item_index("input")
            output_idx = self._get_item_index("output")
            
            if input_idx is not None and index <= input_idx:
                index = input_idx + 1
            if output_idx is not None and index >= output_idx:
                index = output_idx
            
            self.items_layout.insertWidget(index, widget)
            widget.show()
            self._update_indices()
            self.orderChanged.emit(self.get_order())
            self.items_layout.activate()
        e.accept()
    
    def _get_item_index(self, key: str) -> Optional[int]:
        if key not in self._items:
            return None
        return self.items_layout.indexOf(self._items[key])
    
    def _find_drop_location(self, e) -> int:
        pos = e.position()
        spacing = self.items_layout.spacing() / 2
        widgets = [
            self.items_layout.itemAt(n).widget()
            for n in range(self.items_layout.count())
            if self.items_layout.itemAt(n).widget() is not self._drag_target_indicator
        ]
        if not widgets:
            return 0
        for n in range(self.items_layout.count()):
            w = self.items_layout.itemAt(n).widget()
            if w is None or w is self._drag_target_indicator:
                continue
            drop_here = (
                pos.y() >= w.y() - spacing
                and pos.y() <= w.y() + w.size().height() + spacing
            )
            if drop_here:
                return n
        first = widgets[0]
        last = widgets[-1]
        if first is not None and pos.y() < first.y():
            # Buscar índice del primer widget
            for i in range(self.items_layout.count()):
                if self.items_layout.itemAt(i).widget() is first:
                    return i
        # Buscar índice del último widget
        for i in range(self.items_layout.count()):
            if self.items_layout.itemAt(i).widget() is last:
                return i
        return self.items_layout.count() - 1
    
    def _update_indices(self) -> None:
        index = 1
        for n in range(self.items_layout.count()):
            w = self.items_layout.itemAt(n).widget()
            if isinstance(w, ProcessItem):
                w.update_index(index)
                index += 1
    
    def get_order(self) -> List[str]:
        """Retorna la lista de keys en orden actual."""
        result: List[str] = []
        for n in range(self.items_layout.count()):
            w = self.items_layout.itemAt(n).widget()
            if isinstance(w, ProcessItem):
                result.append(w.key)
        return result
    
    def get_enabled_order(self) -> List[str]:
        """Retorna solo los procesos habilitados en orden."""
        result: List[str] = []
        for n in range(self.items_layout.count()):
            w = self.items_layout.itemAt(n).widget()
            if isinstance(w, ProcessItem) and w.is_process_enabled():
                result.append(w.key)
        return result
    
    def update_all_states(self, enabled_map: Dict[str, bool]) -> None:
        """Actualiza el estado de todos los items según un diccionario {key: enabled}."""
        for key, item in self._items.items():
            # Por defecto habilitado si no está en el mapa
            enabled = enabled_map.get(key, True)
            item.set_enabled_state(enabled)
    
    def set_item_enabled(self, key: str, enabled: bool) -> None:
        """Actualiza el estado habilitado de un item por su key."""
        if key in self._items:
            self._items[key].set_enabled_state(enabled)
