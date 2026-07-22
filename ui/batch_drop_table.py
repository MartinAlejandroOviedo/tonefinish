import pathlib

from ui.qt_compat import PYSIDE_AVAILABLE, QTableWidget, Signal


if PYSIDE_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QDragEnterEvent, QDropEvent


class BatchDropTable(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if PYSIDE_AVAILABLE:
            self.setAcceptDrops(True)
            self.setDragDropOverwriteMode(False)

    def dragEnterEvent(self, event: "QDragEnterEvent") -> None:  # type: ignore[override]
        if not PYSIDE_AVAILABLE:
            return
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if not PYSIDE_AVAILABLE:
            return
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: "QDropEvent") -> None:  # type: ignore[override]
        if not PYSIDE_AVAILABLE:
            return
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            super().dropEvent(event)
            return

        paths: list[pathlib.Path] = []
        for url in mime.urls():
            if url.isLocalFile():
                p = pathlib.Path(url.toLocalFile())
                if p.exists():
                    paths.append(p)

        if paths:
            self.files_dropped.emit(paths)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        super().dropEvent(event)
