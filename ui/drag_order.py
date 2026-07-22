from __future__ import annotations

from typing import List

from ui.qt_compat import QApplication, QLabel, QVBoxLayout, QWidget, Qt, Signal, PYSIDE_AVAILABLE

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


class DragTargetIndicator(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setContentsMargins(12, 6, 12, 6)
        self.setStyleSheet("QLabel { background-color: #334155; border: 1px dashed #94a3b8; color: #fff; }")


class DragItem(QLabel):
    activated = Signal(str)

    def __init__(self, name: str, key: str) -> None:
        super().__init__(name)
        self.base_name = name
        self.key = key
        self._drag_start_pos = None
        self._enabled = True
        self._index = 0
        self.setContentsMargins(12, 6, 12, 6)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_style()

    def _update_style(self) -> None:
        """Actualiza el estilo visual según el estado habilitado/deshabilitado."""
        if self._enabled:
            self.setStyleSheet(
                "QLabel { border: 1px solid #222; background: #2b2b2b; color: #fff; }"
            )
        else:
            self.setStyleSheet(
                "QLabel { border: 1px dashed #555; background: #1a1a1a; color: #fff; }"
            )

    def set_enabled_state(self, enabled: bool) -> None:
        """Establece si el proceso está habilitado visualmente."""
        self._enabled = enabled
        self._update_style()
        self._update_display()

    def _update_display(self) -> None:
        """Actualiza el texto mostrado con estado e índice."""
        prefix = "✓" if self._enabled else "✗"
        self.setText(f"{self._index:02d} {prefix} {self.base_name}")

    def update_index(self, index: int) -> None:
        self._index = index
        self._update_display()

    def mousePressEvent(self, e) -> None:  # type: ignore[override]
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = e.position()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:  # type: ignore[override]
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

    def mouseDoubleClickEvent(self, e) -> None:  # type: ignore[override]
        if e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.key)
        super().mouseDoubleClickEvent(e)


class DragOrderWidget(QWidget):
    orderChanged = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.blayout = QVBoxLayout()
        self.blayout.setSpacing(6)
        self._drag_target_indicator = DragTargetIndicator()
        self.blayout.addWidget(self._drag_target_indicator)
        self._drag_target_indicator.hide()
        self.setLayout(self.blayout)

    def dragEnterEvent(self, e) -> None:  # type: ignore[override]
        e.accept()

    def dragLeaveEvent(self, e) -> None:  # type: ignore[override]
        self._drag_target_indicator.hide()
        source = e.source()
        if source is not None:
            source.show()
        e.accept()

    def dragMoveEvent(self, e) -> None:  # type: ignore[override]
        index = self._find_drop_location(e)
        if index is not None:
            self.blayout.insertWidget(index, self._drag_target_indicator)
            source = e.source()
            if source is not None:
                source.hide()
            self._drag_target_indicator.show()
        e.accept()

    def dropEvent(self, e) -> None:  # type: ignore[override]
        widget = e.source()
        self._drag_target_indicator.hide()
        index = self.blayout.indexOf(self._drag_target_indicator)
        if index is not None and widget is not None:
            count = self.blayout.count()
            index = max(0, min(index, max(0, count - 1)))
            self.blayout.insertWidget(index, widget)
            widget.show()
            self.update_indices()
            self.orderChanged.emit(self.get_item_keys())
            self.blayout.activate()
        e.accept()

    def _find_drop_location(self, e) -> int:
        pos = e.position()
        spacing = self.blayout.spacing() / 2
        widgets = [
            self.blayout.itemAt(n).widget()
            for n in range(self.blayout.count())
            if self.blayout.itemAt(n).widget() is not self._drag_target_indicator
        ]
        if not widgets:
            return 0
        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
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
        if pos.y() < first.y():
            return self.blayout.indexOf(first)
        return self.blayout.indexOf(last)

    def add_item(self, item: DragItem) -> None:
        self.blayout.addWidget(item)
        self.update_indices()

    def update_indices(self) -> None:
        index = 1
        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
            if isinstance(w, DragItem):
                w.update_index(index)
                index += 1

    def set_item_enabled(self, key: str, enabled: bool) -> None:
        """Actualiza el estado habilitado de un item por su key."""
        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
            if isinstance(w, DragItem) and w.key == key:
                w.set_enabled_state(enabled)
                break

    def update_all_states(self, enabled_map: dict) -> None:
        """Actualiza el estado de todos los items según un diccionario {key: enabled}."""
        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
            if isinstance(w, DragItem):
                # Por defecto habilitado si no está en el mapa
                enabled = enabled_map.get(w.key, True)
                w.set_enabled_state(enabled)

    def get_item_keys(self) -> List[str]:
        data: List[str] = []
        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
            if isinstance(w, DragItem):
                data.append(w.key)
        return data
