from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
    from PySide6.QtCore import QEvent
    from PySide6.QtSvgWidgets import QSvgWidget
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QHeaderView,
        QListWidget,
        QListWidgetItem,
        QScrollArea,
        QSplitter,
        QStyle,
        QSizePolicy,
        QSpacerItem,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtGui import QIcon, QKeySequence, QShortcut
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget
    PYSIDE_AVAILABLE = True
    PYQTGRAPH_AVAILABLE = True
else:
    PYSIDE_AVAILABLE = False
    PYQTGRAPH_AVAILABLE = False
    try:
        from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
        from PySide6.QtCore import QEvent
        from PySide6.QtSvgWidgets import QSvgWidget
        from PySide6.QtWidgets import (
            QApplication,
            QAbstractItemView,
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPlainTextEdit,
            QProgressBar,
            QPushButton,
            QHeaderView,
            QListWidget,
            QListWidgetItem,
            QScrollArea,
            QSplitter,
            QStyle,
            QSizePolicy,
            QSpacerItem,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
        from PySide6.QtGui import QIcon, QKeySequence, QShortcut
        PYSIDE_AVAILABLE = True
        try:
            import pyqtgraph as pg
            from pyqtgraph import PlotWidget
            PYQTGRAPH_AVAILABLE = True
        except Exception:
            pg = None
            PYQTGRAPH_AVAILABLE = False
    except ImportError:
        class _SignalPlaceholder:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def connect(self, *args, **kwargs) -> None:
                pass

            def emit(self, *args, **kwargs) -> None:
                pass

        class _QObjectPlaceholder:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def moveToThread(self, thread: object) -> None:
                pass

            def deleteLater(self) -> None:
                pass

        class _QThreadPlaceholder:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def start(self) -> None:
                pass

            def quit(self) -> None:
                pass

            def wait(self) -> None:
                pass

            def isRunning(self) -> bool:
                return False

            @property
            def started(self):
                return self

            def connect(self, *args, **kwargs) -> None:
                pass

        class _QTimerPlaceholder:
            def __init__(self, *args, **kwargs) -> None:
                self.timeout = _SignalLikePlaceholder()

            def setInterval(self, *args, **kwargs) -> None:
                pass

            def start(self, *args, **kwargs) -> None:
                pass

            def stop(self, *args, **kwargs) -> None:
                pass

        class _SignalLikePlaceholder:
            def connect(self, *args, **kwargs) -> None:
                pass

        class _QKeySequencePlaceholder:
            def __init__(self, *args, **kwargs) -> None:
                self.sequence = args[0] if args else ""

        class _QShortcutPlaceholder:
            def __init__(self, *args, **kwargs) -> None:
                self.activated = _SignalLikePlaceholder()

            def setContext(self, *args, **kwargs) -> None:
                pass

        Signal = _SignalPlaceholder  # type: ignore
        QObject = _QObjectPlaceholder  # type: ignore
        QThread = _QThreadPlaceholder  # type: ignore
        QTimer = _QTimerPlaceholder  # type: ignore
        QEvent = type(
            "QEvent",
            (),
            {"Type": type("Type", (), {"MouseButtonDblClick": 0, "WindowStateChange": 1})},
        )  # type: ignore
        QShortcut = _QShortcutPlaceholder  # type: ignore
        QKeySequence = _QKeySequencePlaceholder  # type: ignore

        class _TextCursorPlaceholder:
            End = 0

            def movePosition(self, *args, **kwargs) -> None:
                pass

        class _QtWidgetPlaceholder:
            def __init__(self, *args, **kwargs) -> None:
                self.clicked = _SignalLikePlaceholder()
                self.stateChanged = _SignalLikePlaceholder()
                self.currentIndexChanged = _SignalLikePlaceholder()
                self._items = []
                self._current_index = 0
                self._checked = False
                self._row_count = 0
                self._cell_widgets = {}
                self._tabs = []

            def setRange(self, *args, **kwargs) -> None:
                pass

            def setDecimals(self, *args, **kwargs) -> None:
                pass

            def setValue(self, *args, **kwargs) -> None:
                pass

            def setSuffix(self, *args, **kwargs) -> None:
                pass

            def setReadOnly(self, *args, **kwargs) -> None:
                pass

            def setMinimumHeight(self, *args, **kwargs) -> None:
                pass

            def setEnabled(self, *args, **kwargs) -> None:
                pass

            def setText(self, *args, **kwargs) -> None:
                pass

            def setAlignment(self, *args, **kwargs) -> None:
                pass

            def setIcon(self, *args, **kwargs) -> None:
                pass

            def setVisible(self, *args, **kwargs) -> None:
                pass

            def setChecked(self, checked: bool) -> None:
                self._checked = checked

            def isChecked(self) -> bool:
                return self._checked

            def addItems(self, items: list[str]) -> None:
                self._items.extend(items)

            def addItem(self, item: str) -> None:
                self._items.append(item)

            def count(self) -> int:
                return len(self._items)

            def itemText(self, index: int) -> str:
                if 0 <= index < len(self._items):
                    return self._items[index]
                return ""

            def setCurrentIndex(self, index: int) -> None:
                self._current_index = index

            def currentIndex(self) -> int:
                return self._current_index

            def currentText(self) -> str:
                if 0 <= self._current_index < len(self._items):
                    return self._items[self._current_index]
                return ""

            def setRowCount(self, count: int) -> None:
                self._row_count = count

            def rowCount(self) -> int:
                return self._row_count

            def setCellWidget(self, row: int, column: int, widget: object) -> None:
                self._cell_widgets[(row, column)] = widget

            def cellWidget(self, row: int, column: int):
                return self._cell_widgets.get((row, column))

            def addTab(self, widget: object, title: str) -> None:
                self._tabs.append(widget)

            def setTabEnabled(self, index: int, enabled: bool) -> None:
                pass

            def indexOf(self, widget: object) -> int:
                try:
                    return self._tabs.index(widget)
                except ValueError:
                    return -1

            def setCurrentIndex(self, index: int) -> None:
                self._current_index = index

            def currentWidget(self):
                if 0 <= self._current_index < len(self._tabs):
                    return self._tabs[self._current_index]
                return None

            def appendPlainText(self, *args, **kwargs) -> None:
                pass

            def setPlainText(self, *args, **kwargs) -> None:
                pass

            def toPlainText(self, *args, **kwargs) -> str:
                return ""

            def setItem(self, *args, **kwargs) -> None:
                pass

            def horizontalHeader(self) -> "_QtWidgetPlaceholder":
                return self

            def setStretchLastSection(self, *args, **kwargs) -> None:
                pass

            def setSectionResizeMode(self, *args, **kwargs) -> None:
                pass

            def setColumnWidth(self, *args, **kwargs) -> None:
                pass

            def setSizePolicy(self, *args, **kwargs) -> None:
                pass

            def setDragDropMode(self, *args, **kwargs) -> None:
                pass

            def setDefaultDropAction(self, *args, **kwargs) -> None:
                pass

            def setDragEnabled(self, *args, **kwargs) -> None:
                pass

            def setAcceptDrops(self, *args, **kwargs) -> None:
                pass

            def setDropIndicatorShown(self, *args, **kwargs) -> None:
                pass

            def setSelectionMode(self, *args, **kwargs) -> None:
                pass

            def addItem(self, item: object) -> None:
                self._items.append(item)

            def setTextCursor(self, *args, **kwargs) -> None:
                pass

            def textCursor(self) -> "_TextCursorPlaceholder":
                return _TextCursorPlaceholder()

            def ensureCursorVisible(self) -> None:
                pass

            def setHeaderLabels(self, *args, **kwargs) -> None:
                pass

        class _QApplicationPlaceholder(_QtWidgetPlaceholder):
            @staticmethod
            def instance():
                return None

            def exec(self) -> int:
                return 0

        class QWidget(_QtWidgetPlaceholder):
            pass

        class QLayoutPlaceholder(_QtWidgetPlaceholder):
            def addLayout(self, *args, **kwargs) -> None:
                pass

            def addWidget(self, *args, **kwargs) -> None:
                pass

            def setContentsMargins(self, *args, **kwargs) -> None:
                pass

            def setSpacing(self, *args, **kwargs) -> None:
                pass

            def addRow(self, *args, **kwargs) -> None:
                pass

        class QSizePolicy(_QtWidgetPlaceholder):
            class Policy:
                Expanding = 0
                Minimum = 0
                Preferred = 0

        class _QtPlaceholder:
            class AlignmentFlag:
                AlignCenter = 0
            class MouseButton:
                LeftButton = 1
            class Orientation:
                Horizontal = 0
                Vertical = 1
            class DropAction:
                MoveAction = 0

        class QStyle:
            class StandardPixmap:
                SP_DesktopIcon = 0
                SP_DialogOpenButton = 0
                SP_DialogSaveButton = 0
                SP_DialogApplyButton = 0
                SP_DialogCancelButton = 0
                SP_DialogYesButton = 0
                SP_DirIcon = 0
                SP_DirOpenIcon = 0
                SP_FileIcon = 0
                SP_FileDialogContentsView = 0
                SP_FileDialogStart = 0
                SP_BrowserReload = 0
                SP_MediaPlay = 0
                SP_FileDialogDetailedView = 0
                SP_MessageBoxInformation = 0
                SP_MessageBoxWarning = 0

        class QHeaderView(_QtWidgetPlaceholder):
            class ResizeMode:
                Stretch = 0

        class QAbstractItemView:
            class DragDropMode:
                InternalMove = 0
            class SelectionMode:
                SingleSelection = 0

        class QListWidgetItem:
            def __init__(self, *args, **kwargs) -> None:
                pass

        QCheckBox = QComboBox = QDoubleSpinBox = QFileDialog = QLabel = QLineEdit = QMessageBox = QPlainTextEdit = QProgressBar = QPushButton = QSpacerItem = QTabWidget = QTableWidget = QTableWidgetItem = QListWidget = _QtWidgetPlaceholder  # type: ignore
        QFormLayout = QHBoxLayout = QVBoxLayout = QLayoutPlaceholder  # type: ignore
        QSvgWidget = _QtWidgetPlaceholder  # type: ignore
        QGroupBox = QFrame = QSplitter = QScrollArea = _QtWidgetPlaceholder  # type: ignore
        QIcon = _QtWidgetPlaceholder  # type: ignore
        Qt = _QtPlaceholder  # type: ignore
        QApplication = _QApplicationPlaceholder  # type: ignore
        PlotWidget = _QtWidgetPlaceholder  # type: ignore
        pg = None
        PYSIDE_AVAILABLE = False
        PYQTGRAPH_AVAILABLE = False
