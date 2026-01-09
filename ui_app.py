import pathlib
import sys
from typing import Dict, TYPE_CHECKING

from audio_analysis import (
    analyze_audio,
    analyze_audio_with_filter,
    analyze_eq_bands,
    analyze_voice_band,
    evaluate_mix,
    format_analysis_summary,
    write_analysis_toml,
)
from audio_processing import build_preprocess_chain, ensure_output_path, normalize_audio
from audio_tools import ensure_ffmpeg_available
from config import (
    BAND_CONFIG,
    DEFAULT_BAND_RANGE_DB,
    DEFAULT_MAX_ADJUST_DB,
    INPUT_FORMATS,
    LOUDNESS_PRESETS,
    OUTPUT_PRESETS,
    OUTPUT_FORMATS,
    TRANSPARENT_BAND_RANGE_DB,
    TRANSPARENT_MAX_ADJUST_DB,
    VOICE_BAND,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QObject, QThread, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSpacerItem,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    PYSIDE_AVAILABLE = True
else:
    PYSIDE_AVAILABLE = False
    try:
        from PySide6.QtCore import QObject, QThread, Signal
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QFileDialog,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPlainTextEdit,
            QProgressBar,
            QPushButton,
            QSizePolicy,
            QSpacerItem,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
        PYSIDE_AVAILABLE = True
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

            @property
            def started(self):
                return self

            def connect(self, *args, **kwargs) -> None:
                pass

        Signal = _SignalPlaceholder  # type: ignore
        QObject = _QObjectPlaceholder  # type: ignore
        QThread = _QThreadPlaceholder  # type: ignore

        class _SignalLikePlaceholder:
            def connect(self, *args, **kwargs) -> None:
                pass

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

            def text(self) -> str:
                return ""

            def addItems(self, items) -> None:
                self._items.extend(items)

            def setCurrentIndex(self, index: int) -> None:
                self._current_index = index

            def currentText(self) -> str:
                if 0 <= self._current_index < len(self._items):
                    return self._items[self._current_index]
                return ""

            def count(self) -> int:
                return len(self._items)

            def itemText(self, index: int) -> str:
                if 0 <= index < len(self._items):
                    return self._items[index]
                return ""

            def setCurrentText(self, text: str) -> None:
                if text in self._items:
                    self._current_index = self._items.index(text)

            def isChecked(self) -> bool:
                return self._checked

            def setChecked(self, value: bool) -> None:
                self._checked = bool(value)

            def appendPlainText(self, *args, **kwargs) -> None:
                pass

            def textCursor(self) -> _TextCursorPlaceholder:
                return _TextCursorPlaceholder()

            def setTextCursor(self, *args, **kwargs) -> None:
                pass

            def setWindowTitle(self, *args, **kwargs) -> None:
                pass

            def setMinimumWidth(self, *args, **kwargs) -> None:
                pass

            def addWidget(self, *args, **kwargs) -> None:
                pass

            def addLayout(self, *args, **kwargs) -> None:
                pass

            def addRow(self, *args, **kwargs) -> None:
                pass

            def addItem(self, *args, **kwargs) -> None:
                pass

            def setRowCount(self, *args, **kwargs) -> None:
                if args:
                    self._row_count = int(args[0])

            def setColumnCount(self, *args, **kwargs) -> None:
                pass

            def setHorizontalHeaderLabels(self, *args, **kwargs) -> None:
                pass

            def setItem(self, *args, **kwargs) -> None:
                pass

            def addTab(self, widget: object, label: str) -> None:
                self._tabs.append((widget, label))

            def insertTab(self, index: int, widget: object, label: str) -> None:
                self._tabs.insert(index, (widget, label))

            def setTabEnabled(self, index: int, enabled: bool) -> None:
                pass

            def currentWidget(self) -> object | None:
                if 0 <= self._current_index < len(self._tabs):
                    return self._tabs[self._current_index][0]
                return None

            def setCellWidget(self, row: int, column: int, widget: object) -> None:
                self._cell_widgets[(row, column)] = widget

            def cellWidget(self, row: int, column: int) -> object | None:
                return self._cell_widgets.get((row, column))

            def rowCount(self) -> int:
                return self._row_count

        class _QApplicationPlaceholder(_QtWidgetPlaceholder):
            @staticmethod
            def instance():
                return None

            def exec(self) -> int:
                return 0

        class QWidget(_QtWidgetPlaceholder):
            pass

        QApplication = _QApplicationPlaceholder  # type: ignore
        class QLayoutPlaceholder(_QtWidgetPlaceholder):
            pass

        class QSizePolicy(_QtWidgetPlaceholder):
            class Policy:
                Expanding = 0
                Minimum = 0

        QCheckBox = QComboBox = QDoubleSpinBox = QFileDialog = QLabel = QLineEdit = QPlainTextEdit = QProgressBar = QPushButton = QSpacerItem = QTabWidget = QTableWidget = QTableWidgetItem = _QtWidgetPlaceholder  # type: ignore
        QFormLayout = QHBoxLayout = QVBoxLayout = QLayoutPlaceholder  # type: ignore
        PYSIDE_AVAILABLE = False


if PYSIDE_AVAILABLE:
    class AnalyzeWorker(QObject):
        finished = Signal(dict, dict, list, object, str)
        error = Signal(str)

        def __init__(
            self,
            input_path: pathlib.Path,
            target_lufs: float,
            true_peak: float,
            verbose: bool,
            transparent_mode: bool,
        ) -> None:
            super().__init__()
            self.input_path = input_path
            self.target_lufs = target_lufs
            self.true_peak = true_peak
            self.verbose = verbose
            self.transparent_mode = transparent_mode

        def run(self) -> None:
            try:
                ensure_ffmpeg_available()
                band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_mode else DEFAULT_BAND_RANGE_DB
                stats, log = analyze_audio(self.input_path, self.target_lufs, self.true_peak, verbose=self.verbose)
                band_stats, suggestions = analyze_eq_bands(
                    self.input_path,
                    verbose=self.verbose,
                    band_range_db=band_range,
                )
                voice_rms = analyze_voice_band(self.input_path, verbose=self.verbose)
                self.finished.emit(stats, band_stats, suggestions, voice_rms, log)
            except Exception as exc:
                self.error.emit(str(exc))

    class NormalizeWorker(QObject):
        finished = Signal(str, str)
        error = Signal(str)

        def __init__(
            self,
            input_path: pathlib.Path,
            output_path: pathlib.Path,
            stats: Dict[str, float],
            band_stats: Dict[str, float] | None,
            target_lufs: float,
            true_peak: float,
            overwrite: bool,
            verbose: bool,
            dynamic_eq: bool,
            brickwall: bool,
            output_sr: int | None,
            output_bit_depth: str | None,
            output_format: str | None,
            stereo_width: bool,
            deesser: bool,
            fade_in: float,
            fade_out: float,
            transparent_mode: bool,
        ) -> None:
            super().__init__()
            self.input_path = input_path
            self.output_path = output_path
            self.stats = stats
            self.band_stats = band_stats
            self.target_lufs = target_lufs
            self.true_peak = true_peak
            self.overwrite = overwrite
            self.verbose = verbose
            self.dynamic_eq = dynamic_eq
            self.brickwall = brickwall
            self.output_sr = output_sr
            self.output_bit_depth = output_bit_depth
            self.output_format = output_format
            self.stereo_width = stereo_width
            self.deesser = deesser
            self.fade_in = fade_in
            self.fade_out = fade_out
            self.transparent_mode = transparent_mode

        def run(self) -> None:
            try:
                ensure_ffmpeg_available()
                log = normalize_audio(
                    input_path=self.input_path,
                    output_path=self.output_path,
                    stats=self.stats,
                    target_lufs=self.target_lufs,
                    true_peak=self.true_peak,
                    overwrite=self.overwrite,
                    verbose=self.verbose,
                    dynamic_eq=self.dynamic_eq,
                    band_stats=self.band_stats,
                    brickwall=self.brickwall,
                    output_sr=self.output_sr,
                    output_bit_depth=self.output_bit_depth,
                    output_format=self.output_format,
                    stereo_width=self.stereo_width,
                    deesser=self.deesser,
                    fade_in=self.fade_in,
                    fade_out=self.fade_out,
                    transparent_mode=self.transparent_mode,
                )
                self.finished.emit(log, str(self.output_path))
            except Exception as exc:
                self.error.emit(str(exc))

    class ProcessWorker(QObject):
        finished = Signal(dict, dict, list, object, str, str, object, object, object, object, object, object)
        error = Signal(str)
        progress = Signal(str)

        def __init__(
            self,
            input_path: pathlib.Path,
            output_path: pathlib.Path,
            target_lufs: float,
            true_peak: float,
            overwrite: bool,
            verbose: bool,
            dynamic_eq: bool,
            brickwall: bool,
            analyze_only: bool,
            output_sr: int | None,
            output_bit_depth: str | None,
            output_format: str | None,
            stereo_width: bool,
            loudness_preset: str,
            output_preset: str,
            deesser: bool,
            fade_in: float,
            fade_out: float,
            transparent_mode: bool,
        ) -> None:
            super().__init__()
            self.input_path = input_path
            self.output_path = output_path
            self.target_lufs = target_lufs
            self.true_peak = true_peak
            self.overwrite = overwrite
            self.verbose = verbose
            self.dynamic_eq = dynamic_eq
            self.brickwall = brickwall
            self.analyze_only = analyze_only
            self.output_sr = output_sr
            self.output_bit_depth = output_bit_depth
            self.output_format = output_format
            self.stereo_width = stereo_width
            self.loudness_preset = loudness_preset
            self.output_preset = output_preset
            self.deesser = deesser
            self.fade_in = fade_in
            self.fade_out = fade_out
            self.transparent_mode = transparent_mode

        def run(self) -> None:
            try:
                ensure_ffmpeg_available()
                self.progress.emit("Analizando bandas EQ...")
                band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_mode else DEFAULT_BAND_RANGE_DB
                max_adjust = TRANSPARENT_MAX_ADJUST_DB if self.transparent_mode else DEFAULT_MAX_ADJUST_DB
                band_stats, suggestions = analyze_eq_bands(
                    self.input_path,
                    verbose=self.verbose,
                    band_range_db=band_range,
                )
                self.progress.emit("Analizando banda vocal...")
                voice_rms = analyze_voice_band(self.input_path, verbose=self.verbose)
                warning = ""
                dynamic_eq = self.dynamic_eq
                if dynamic_eq and not band_stats:
                    dynamic_eq = False
                    warning = (
                        "Aviso: no se pudo calcular RMS por bandas; "
                        "se desactiva el control dinámico por bandas.\n"
                    )
                self.progress.emit("Calibrando loudness con pre-proceso...")
                pre_chain, pre_output = build_preprocess_chain(
                    input_path=self.input_path,
                    band_stats=band_stats,
                    dynamic_eq=dynamic_eq,
                    stereo_width=self.stereo_width,
                    deesser=self.deesser,
                    band_range_db=band_range,
                    max_adjust_db=max_adjust,
                )
                if pre_chain:
                    stats, log = analyze_audio_with_filter(
                        input_path=self.input_path,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        filter_chain=pre_chain,
                        filter_output=pre_output,
                        verbose=self.verbose,
                    )
                else:
                    stats, log = analyze_audio(self.input_path, self.target_lufs, self.true_peak, verbose=self.verbose)

                normalize_log = ""
                output_path = None
                pre_rating, pre_advice = evaluate_mix(stats, self.target_lufs, self.true_peak)
                pre_summary = format_analysis_summary(
                    "Antes del proceso",
                    stats,
                    band_stats,
                    voice_rms,
                    self.target_lufs,
                    self.true_peak,
                )
                if not self.analyze_only:
                    self.progress.emit("Procesando y normalizando audio...")
                    normalize_log = normalize_audio(
                        input_path=self.input_path,
                        output_path=self.output_path,
                        stats=stats,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        overwrite=self.overwrite,
                        verbose=self.verbose,
                        dynamic_eq=dynamic_eq,
                        band_stats=band_stats,
                        brickwall=self.brickwall,
                        output_sr=self.output_sr,
                        output_bit_depth=self.output_bit_depth,
                        output_format=self.output_format,
                        stereo_width=self.stereo_width,
                        deesser=self.deesser,
                        fade_in=self.fade_in,
                        fade_out=self.fade_out,
                        transparent_mode=self.transparent_mode,
                    )
                    if warning:
                        normalize_log = warning + normalize_log
                    self.progress.emit("Re-analizando salida...")
                    post_stats, _post_log = analyze_audio(self.output_path, self.target_lufs, self.true_peak, verbose=False)
                    post_band_stats, _post_suggestions = analyze_eq_bands(
                        self.output_path,
                        verbose=False,
                        band_range_db=band_range,
                    )
                    post_voice_rms = analyze_voice_band(self.output_path, verbose=False)
                    post_rating, post_advice = evaluate_mix(post_stats, self.target_lufs, self.true_peak)
                    post_summary = format_analysis_summary(
                        "Despues del proceso",
                        post_stats,
                        post_band_stats,
                        post_voice_rms,
                        self.target_lufs,
                        self.true_peak,
                    )
                    normalize_log = "\n".join(
                        part for part in [normalize_log.strip(), pre_summary, post_summary] if part
                    )
                    output_path = str(self.output_path)
                    toml_path = write_analysis_toml(
                        output_path=self.output_path,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        loudness_preset=self.loudness_preset,
                        output_preset=self.output_preset,
                        output_sr=self.output_sr,
                        output_bit_depth=self.output_bit_depth,
                        output_format=self.output_format,
                        dynamic_eq=dynamic_eq,
                        stereo_width=self.stereo_width,
                        brickwall=self.brickwall,
                        analyze_only=self.analyze_only,
                        deesser=self.deesser,
                        fade_in=self.fade_in,
                        fade_out=self.fade_out,
                        before_stats=stats,
                        before_band=band_stats,
                        before_voice=voice_rms,
                        after_stats=post_stats,
                        after_band=post_band_stats,
                        after_voice=post_voice_rms,
                        before_rating=pre_rating,
                        before_advice=pre_advice,
                        after_rating=post_rating,
                        after_advice=post_advice,
                    )
                else:
                    post_stats = None
                    post_voice_rms = None
                    post_rating = None
                    toml_path = write_analysis_toml(
                        output_path=self.output_path,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        loudness_preset=self.loudness_preset,
                        output_preset=self.output_preset,
                        output_sr=self.output_sr,
                        output_bit_depth=self.output_bit_depth,
                        output_format=self.output_format,
                        dynamic_eq=dynamic_eq,
                        stereo_width=self.stereo_width,
                        brickwall=self.brickwall,
                        analyze_only=self.analyze_only,
                        deesser=self.deesser,
                        fade_in=self.fade_in,
                        fade_out=self.fade_out,
                        before_stats=stats,
                        before_band=band_stats,
                        before_voice=voice_rms,
                        after_stats=None,
                        after_band=None,
                        after_voice=None,
                        before_rating=pre_rating,
                        before_advice=pre_advice,
                        after_rating=None,
                        after_advice=None,
                    )
                self.finished.emit(
                    stats,
                    band_stats,
                    suggestions,
                    voice_rms,
                    log,
                    normalize_log,
                    output_path,
                    toml_path,
                    post_stats,
                    post_voice_rms,
                    pre_rating,
                    post_rating,
                )
            except Exception as exc:
                self.error.emit(str(exc))

    class BatchWorker(QObject):
        finished = Signal(str, object)
        error = Signal(str)
        progress = Signal(str, int, int)

        def __init__(
            self,
            files: list[pathlib.Path],
            output_dir: pathlib.Path | None,
            suffix: str,
            target_lufs: float,
            true_peak: float,
            overwrite: bool,
            verbose: bool,
            dynamic_eq: bool,
            brickwall: bool,
            output_sr: int | None,
            output_bit_depth: str | None,
            output_format: str | None,
            stereo_width: bool,
            loudness_preset: str,
            output_preset: str,
            deesser: bool,
            fade_in: float,
            fade_out: float,
            transparent_mode: bool,
        ) -> None:
            super().__init__()
            self.files = files
            self.output_dir = output_dir
            self.suffix = suffix
            self.target_lufs = target_lufs
            self.true_peak = true_peak
            self.overwrite = overwrite
            self.verbose = verbose
            self.dynamic_eq = dynamic_eq
            self.brickwall = brickwall
            self.output_sr = output_sr
            self.output_bit_depth = output_bit_depth
            self.output_format = output_format
            self.stereo_width = stereo_width
            self.loudness_preset = loudness_preset
            self.output_preset = output_preset
            self.deesser = deesser
            self.fade_in = fade_in
            self.fade_out = fade_out
            self.transparent_mode = transparent_mode

        def run(self) -> None:
            try:
                ensure_ffmpeg_available()
                files = [p for p in self.files if p.exists() and p.is_file()]
                if not files:
                    self.error.emit("No se encontraron archivos seleccionados para procesar.")
                    return

                processed = 0
                results: list[dict] = []
                for idx, audio_path in enumerate(files, start=1):
                    self.progress.emit(f"Procesando {idx}/{len(files)}: {audio_path.name}", idx, len(files))

                    out_dir = self.output_dir if self.output_dir else audio_path.parent
                    output_base = out_dir / f"{audio_path.stem}{self.suffix}"
                    fmt = self.output_format or audio_path.suffix.lstrip(".")
                    output_path = ensure_output_path(output_base, fmt)

                    band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_mode else DEFAULT_BAND_RANGE_DB
                    max_adjust = TRANSPARENT_MAX_ADJUST_DB if self.transparent_mode else DEFAULT_MAX_ADJUST_DB
                    band_stats, _suggestions = analyze_eq_bands(
                        audio_path,
                        verbose=self.verbose,
                        band_range_db=band_range,
                    )
                    voice_rms = analyze_voice_band(audio_path, verbose=self.verbose)
                    dynamic_eq = self.dynamic_eq
                    if dynamic_eq and not band_stats:
                        dynamic_eq = False

                    pre_chain, pre_output = build_preprocess_chain(
                        input_path=audio_path,
                        band_stats=band_stats,
                        dynamic_eq=dynamic_eq,
                        stereo_width=self.stereo_width,
                        deesser=self.deesser,
                        band_range_db=band_range,
                        max_adjust_db=max_adjust,
                    )
                    if pre_chain:
                        stats, _log = analyze_audio_with_filter(
                            input_path=audio_path,
                            target_lufs=self.target_lufs,
                            true_peak=self.true_peak,
                            filter_chain=pre_chain,
                            filter_output=pre_output,
                            verbose=self.verbose,
                        )
                    else:
                        stats, _log = analyze_audio(audio_path, self.target_lufs, self.true_peak, verbose=self.verbose)

                    normalize_audio(
                        input_path=audio_path,
                        output_path=output_path,
                        stats=stats,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        overwrite=self.overwrite,
                        verbose=self.verbose,
                        dynamic_eq=dynamic_eq,
                        band_stats=band_stats,
                        brickwall=self.brickwall,
                        output_sr=self.output_sr,
                        output_bit_depth=self.output_bit_depth,
                        output_format=fmt,
                        stereo_width=self.stereo_width,
                        deesser=self.deesser,
                        fade_in=self.fade_in,
                        fade_out=self.fade_out,
                        transparent_mode=self.transparent_mode,
                    )

                    post_stats, _post_log = analyze_audio(output_path, self.target_lufs, self.true_peak, verbose=False)
                    post_band_stats, _post_suggestions = analyze_eq_bands(
                        output_path,
                        verbose=False,
                        band_range_db=band_range,
                    )
                    post_voice_rms = analyze_voice_band(output_path, verbose=False)
                    pre_rating, pre_advice = evaluate_mix(stats, self.target_lufs, self.true_peak)
                    post_rating, post_advice = evaluate_mix(post_stats, self.target_lufs, self.true_peak)

                    write_analysis_toml(
                        output_path=output_path,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        loudness_preset=self.loudness_preset,
                        output_preset=self.output_preset,
                        output_sr=self.output_sr,
                        output_bit_depth=self.output_bit_depth,
                        output_format=fmt,
                        dynamic_eq=dynamic_eq,
                        stereo_width=self.stereo_width,
                        brickwall=self.brickwall,
                        analyze_only=False,
                        deesser=self.deesser,
                        fade_in=self.fade_in,
                        fade_out=self.fade_out,
                        before_stats=stats,
                        before_band=band_stats,
                        before_voice=voice_rms,
                        after_stats=post_stats,
                        after_band=post_band_stats,
                        after_voice=post_voice_rms,
                        before_rating=pre_rating,
                        before_advice=pre_advice,
                        after_rating=post_rating,
                        after_advice=post_advice,
                    )
                    results.append(
                        {
                            "file": audio_path.name,
                            "before": stats,
                            "after": post_stats,
                            "before_rating": pre_rating,
                            "after_rating": post_rating,
                        }
                    )
                    processed += 1

                self.finished.emit(f"Lote completado: {processed} archivos.", results)
            except Exception as exc:
                self.error.emit(str(exc))

    class MainWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("ToneFinish")
            self.setMinimumWidth(480)
            self._current_thread = None
            self._current_worker = None
            self.last_stats: Dict[str, float] | None = None
            self.last_band_stats: Dict[str, float] | None = None
            self.band_labels: Dict[str, QLabel] = {}

            self.input_edit = QLineEdit()
            self.input_button = QPushButton("Abrir...")
            self.input_button.clicked.connect(self.choose_input)

            self.output_edit = QLineEdit()
            self.output_button = QPushButton("Guardar como...")
            self.output_button.clicked.connect(self.choose_output)

            self.target_spin = QDoubleSpinBox()
            self.target_spin.setRange(-60.0, 0.0)
            self.target_spin.setDecimals(1)
            self.target_spin.setValue(-14.0)
            self.target_spin.setSuffix(" LUFS")

            self.true_peak_spin = QDoubleSpinBox()
            self.true_peak_spin.setRange(-20.0, 0.0)
            self.true_peak_spin.setDecimals(1)
            self.true_peak_spin.setValue(-1.5)
            self.true_peak_spin.setSuffix(" dBTP")

            self.preset_combo = QComboBox()
            self.preset_combo.addItems(list(LOUDNESS_PRESETS.keys()))
            self.preset_combo.setCurrentIndex(0)

            self.output_preset_combo = QComboBox()
            self.output_preset_combo.addItems(list(OUTPUT_PRESETS.keys()))
            self.output_preset_combo.setCurrentIndex(0)

            self.output_format_combo = QComboBox()
            self.output_format_combo.addItems(["Auto"] + [fmt.upper() for fmt in OUTPUT_FORMATS])
            self.output_format_combo.setCurrentIndex(0)

            self.mode_combo = QComboBox()
            self.mode_combo.addItems(["Audio unico", "Lote", "Solo analizar"])
            self.mode_combo.setCurrentIndex(0)

            self.batch_preset_combo = QComboBox()
            self.batch_preset_combo.addItems(list(LOUDNESS_PRESETS.keys()))
            self.batch_preset_combo.setCurrentIndex(0)

            self.batch_target_spin = QDoubleSpinBox()
            self.batch_target_spin.setRange(-60.0, 0.0)
            self.batch_target_spin.setDecimals(1)
            self.batch_target_spin.setValue(-14.0)
            self.batch_target_spin.setSuffix(" LUFS")

            self.batch_true_peak_spin = QDoubleSpinBox()
            self.batch_true_peak_spin.setRange(-20.0, 0.0)
            self.batch_true_peak_spin.setDecimals(1)
            self.batch_true_peak_spin.setValue(-1.5)
            self.batch_true_peak_spin.setSuffix(" dBTP")

            self._syncing_lufs = False

            self.sample_rate_combo = QComboBox()
            self.sample_rate_combo.addItems(["Mantener", "44100", "48000", "96000"])
            self.sample_rate_combo.setCurrentIndex(0)

            self.bit_depth_combo = QComboBox()
            self.bit_depth_combo.addItems(["Mantener", "16", "24"])
            self.bit_depth_combo.setCurrentIndex(0)

            self.fade_in_spin = QDoubleSpinBox()
            self.fade_in_spin.setRange(0.0, 30.0)
            self.fade_in_spin.setDecimals(2)
            self.fade_in_spin.setValue(0.0)
            self.fade_in_spin.setSuffix(" s")

            self.fade_out_spin = QDoubleSpinBox()
            self.fade_out_spin.setRange(0.0, 30.0)
            self.fade_out_spin.setDecimals(2)
            self.fade_out_spin.setValue(0.0)
            self.fade_out_spin.setSuffix(" s")

            self.batch_input_edit = QLineEdit()
            self.batch_input_button = QPushButton("Carpeta entrada...")
            self.batch_input_button.clicked.connect(self.choose_batch_input)
            self.batch_refresh_button = QPushButton("Actualizar lista")
            self.batch_refresh_button.clicked.connect(self.refresh_batch_table)

            self.batch_output_edit = QLineEdit()
            self.batch_output_button = QPushButton("Carpeta salida...")
            self.batch_output_button.clicked.connect(self.choose_batch_output)

            self.batch_suffix_edit = QLineEdit()
            self.batch_suffix_edit.setText("_processed")

            self.batch_table = QTableWidget(0, 3)
            self.batch_table.setHorizontalHeaderLabels(["Procesar", "Archivo", "Formato"])
            self.batch_select_all_btn = QPushButton("Seleccionar todo")
            self.batch_select_none_btn = QPushButton("Ninguno")
            self.batch_select_all_btn.clicked.connect(lambda: self._set_batch_selection(True))
            self.batch_select_none_btn.clicked.connect(lambda: self._set_batch_selection(False))

            self.batch_progress_label = QLabel("0/0")
            self.batch_progress_bar = QProgressBar()
            self.batch_progress_bar.setRange(0, 1)
            self.batch_progress_bar.setValue(0)

            self.batch_process_btn = QPushButton("Procesar lote")
            self._batch_files: list[pathlib.Path] = []

            self.overwrite_cb = QCheckBox("Sobrescribir salida si existe")
            self.analyze_only_cb = QCheckBox("Solo analizar (no escribir salida)")
            self.verbose_cb = QCheckBox("Verbose (muestra comandos ffmpeg)")
            self.dynamic_eq_cb = QCheckBox("Control dinámico por bandas")
            self.brickwall_cb = QCheckBox("Brickwall limiter (pico duro)")
            self.stereo_width_cb = QCheckBox("Stereo width por bandas")
            self.deesser_cb = QCheckBox("De-Esser (sibilancia)")
            self.transparent_cb = QCheckBox("Modo transparente")
            self.dynamic_eq_cb.setChecked(True)
            self.brickwall_cb.setChecked(True)
            self.stereo_width_cb.setChecked(True)
            self.deesser_cb.setChecked(False)
            self.transparent_cb.setChecked(True)

            self.analyze_btn = QPushButton("Analizar")
            self.normalize_btn = QPushButton("Normalizar")
            self.process_btn = QPushButton("Procesar audio")

            self.input_i_label = QLabel("-")
            self.input_tp_label = QLabel("-")
            self.input_lra_label = QLabel("-")
            self.threshold_label = QLabel("-")
            self.offset_label = QLabel("-")
            self.voice_band_label = QLabel("-")

            self.eq_suggestions = QPlainTextEdit()
            self.eq_suggestions.setReadOnly(True)
            self.eq_suggestions.setMinimumHeight(120)

            self.results_table = QTableWidget(5, 3)
            self.results_table.setHorizontalHeaderLabels(["Métrica", "Antes", "Después"])

            self.log_view = QPlainTextEdit()
            self.log_view.setReadOnly(True)
            self.log_view.setMinimumHeight(160)

            self._build_layout()
            self._wire_events()

            self.analyze_only_cb.stateChanged.connect(self._on_analyze_only_toggled)
            self._on_analyze_only_toggled(self.analyze_only_cb.isChecked())
            self._on_mode_changed(allow_navigation=False)
            self.tabs.setCurrentIndex(0)

            self.batch_target_spin.valueChanged.connect(self._sync_lufs_from_batch)
            self.batch_true_peak_spin.valueChanged.connect(self._sync_lufs_from_batch)
            self.target_spin.valueChanged.connect(self._sync_lufs_from_main)
            self.true_peak_spin.valueChanged.connect(self._sync_lufs_from_main)

        def _build_layout(self) -> None:
            layout = QVBoxLayout()

            tabs = QTabWidget()
            self.tabs = tabs

            tab_start = QWidget()
            self.tab_start = tab_start
            start_layout = QVBoxLayout()
            start_form = QFormLayout()
            start_form.addRow("Modo de trabajo:", self.mode_combo)
            start_layout.addLayout(start_form)
            start_layout.addWidget(QLabel("Elige Audio unico para un archivo o Lote para procesar varios."))
            tab_start.setLayout(start_layout)

            tab_single = QWidget()
            self.tab_single = tab_single
            tab_single_layout = QVBoxLayout()
            single_input_layout = QHBoxLayout()
            single_input_layout.addWidget(QLabel("Entrada:"))
            single_input_layout.addWidget(self.input_edit)
            single_input_layout.addWidget(self.input_button)
            tab_single_layout.addLayout(single_input_layout)

            single_output_layout = QHBoxLayout()
            single_output_layout.addWidget(QLabel("Salida:"))
            single_output_layout.addWidget(self.output_edit)
            single_output_layout.addWidget(self.output_button)
            tab_single_layout.addLayout(single_output_layout)

            single_form = QFormLayout()
            single_form.addRow("Preset LUFS:", self.preset_combo)
            single_form.addRow("Preset salida:", self.output_preset_combo)
            single_form.addRow("Formato salida:", self.output_format_combo)
            single_form.addRow("Target LUFS:", self.target_spin)
            single_form.addRow("True Peak:", self.true_peak_spin)
            tab_single_layout.addLayout(single_form)

            self.analyze_btn.setVisible(False)
            self.normalize_btn.setVisible(False)
            tab_single_layout.addWidget(self.process_btn)
            tab_single.setLayout(tab_single_layout)

            tab_batch = QWidget()
            self.tab_batch = tab_batch
            batch_layout = QVBoxLayout()
            batch_in_layout = QHBoxLayout()
            batch_in_layout.addWidget(QLabel("Carpeta entrada:"))
            batch_in_layout.addWidget(self.batch_input_edit)
            batch_in_layout.addWidget(self.batch_input_button)
            batch_in_layout.addWidget(self.batch_refresh_button)
            batch_layout.addLayout(batch_in_layout)

            batch_out_layout = QHBoxLayout()
            batch_out_layout.addWidget(QLabel("Carpeta salida:"))
            batch_out_layout.addWidget(self.batch_output_edit)
            batch_out_layout.addWidget(self.batch_output_button)
            batch_layout.addLayout(batch_out_layout)

            batch_form = QFormLayout()
            batch_form.addRow("Preset LUFS:", self.batch_preset_combo)
            batch_form.addRow("Target LUFS:", self.batch_target_spin)
            batch_form.addRow("True Peak:", self.batch_true_peak_spin)
            batch_form.addRow("Formato salida:", self.output_format_combo)
            batch_form.addRow("Sufijo:", self.batch_suffix_edit)
            batch_layout.addLayout(batch_form)
            batch_layout.addWidget(QLabel("Archivos encontrados:"))
            batch_layout.addWidget(self.batch_table)
            batch_select_layout = QHBoxLayout()
            batch_select_layout.addWidget(self.batch_select_all_btn)
            batch_select_layout.addWidget(self.batch_select_none_btn)
            batch_layout.addLayout(batch_select_layout)
            batch_progress_layout = QHBoxLayout()
            batch_progress_layout.addWidget(QLabel("Progreso:"))
            batch_progress_layout.addWidget(self.batch_progress_bar)
            batch_progress_layout.addWidget(self.batch_progress_label)
            batch_layout.addLayout(batch_progress_layout)
            batch_layout.addWidget(self.batch_process_btn)
            tab_batch.setLayout(batch_layout)

            tab_process = QWidget()
            self.tab_process = tab_process
            process_layout = QVBoxLayout()
            settings_form = QFormLayout()
            settings_form.addRow("Sample rate:", self.sample_rate_combo)
            settings_form.addRow("Bit depth:", self.bit_depth_combo)
            settings_form.addRow("Fade in:", self.fade_in_spin)
            settings_form.addRow("Fade out:", self.fade_out_spin)
            process_layout.addLayout(settings_form)

            options_layout = QVBoxLayout()
            options_layout.addWidget(self.analyze_only_cb)
            options_layout.addWidget(self.verbose_cb)
            options_layout.addWidget(self.overwrite_cb)
            options_layout.addWidget(self.dynamic_eq_cb)
            options_layout.addWidget(self.brickwall_cb)
            options_layout.addWidget(self.stereo_width_cb)
            options_layout.addWidget(self.deesser_cb)
            options_layout.addWidget(self.transparent_cb)
            process_layout.addLayout(options_layout)
            tab_process.setLayout(process_layout)

            tab_results = QWidget()
            self.tab_results = tab_results
            results_layout = QVBoxLayout()
            stats_layout = QFormLayout()
            stats_layout.addRow("Input I (LUFS):", self.input_i_label)
            stats_layout.addRow("Input TP (dBTP):", self.input_tp_label)
            stats_layout.addRow("Input LRA (LU):", self.input_lra_label)
            stats_layout.addRow("Threshold (dB):", self.threshold_label)
            stats_layout.addRow("Offset recomendado:", self.offset_label)
            stats_layout.addRow(f"{VOICE_BAND[0]}:", self.voice_band_label)
            results_layout.addLayout(stats_layout)

            eq_layout = QFormLayout()
            for label, _low, _high, _attack, _release, _width in BAND_CONFIG:
                value_label = QLabel("-")
                self.band_labels[label] = value_label
                eq_layout.addRow(label + ":", value_label)
            results_layout.addLayout(eq_layout)

            results_layout.addWidget(QLabel("Sugerencias EQ:"))
            results_layout.addWidget(self.eq_suggestions)
            results_layout.addWidget(QLabel("Resultados (Antes / Después):"))
            results_layout.addWidget(self.results_table)
            self.batch_results_table = QTableWidget(0, 9)
            self.batch_results_table.setHorizontalHeaderLabels(
                [
                    "Archivo",
                    "I antes",
                    "I despues",
                    "TP antes",
                    "TP despues",
                    "LRA antes",
                    "LRA despues",
                    "Rating antes",
                    "Rating despues",
                ]
            )
            results_layout.addWidget(QLabel("Resultados de lote:"))
            results_layout.addWidget(self.batch_results_table)
            results_layout.addWidget(QLabel("Log:"))
            results_layout.addWidget(self.log_view)
            tab_results.setLayout(results_layout)

            tabs.addTab(tab_single, "Audio")
            tabs.addTab(tab_batch, "Lote")
            tabs.addTab(tab_process, "Procesos")
            tabs.addTab(tab_results, "Resultados")
            tabs.insertTab(0, tab_start, "Inicio")
            tabs.setCurrentIndex(0)

            layout.addWidget(tabs)
            self.setLayout(layout)

        def _wire_events(self) -> None:
            self.analyze_btn.clicked.connect(self.start_analyze)
            self.normalize_btn.clicked.connect(self.start_normalize)
            self.process_btn.clicked.connect(self.start_process)
            self.batch_process_btn.clicked.connect(self.start_batch_process)
            self.preset_combo.currentIndexChanged.connect(self._apply_preset)
            self.batch_preset_combo.currentIndexChanged.connect(self._apply_batch_preset)
            self.output_preset_combo.currentIndexChanged.connect(self._apply_output_preset)
            self.output_format_combo.currentIndexChanged.connect(self._apply_output_format)
            self.mode_combo.currentIndexChanged.connect(lambda: self._on_mode_changed(allow_navigation=True))
            self._apply_preset()
            self._apply_batch_preset()
            self._apply_output_preset()
            self._apply_output_format()

        def choose_input(self) -> None:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Seleccionar WAV de entrada", "", "WAV (*.wav);;Todos los archivos (*)"
            )
            if file_path:
                self.input_edit.setText(file_path)
                if not self.output_edit.text():
                    path = pathlib.Path(file_path)
                    self.output_edit.setText(str(path.with_stem(f"{path.stem}_normalized")))

        def choose_output(self) -> None:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Seleccionar salida", "", "WAV (*.wav);;Todos los archivos (*)"
            )
            if file_path:
                self.output_edit.setText(file_path)

        def choose_batch_input(self) -> None:
            folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de entrada")
            if folder:
                self.batch_input_edit.setText(folder)
                self.refresh_batch_table()

        def choose_batch_output(self) -> None:
            folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
            if folder:
                self.batch_output_edit.setText(folder)

        def refresh_batch_table(self) -> None:
            input_dir_text = self.batch_input_edit.text().strip()
            input_dir = pathlib.Path(input_dir_text) if input_dir_text else None
            if not input_dir or not input_dir.exists():
                self.batch_table.setRowCount(0)
                self._batch_files = []
                return
            files = sorted(
                [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in INPUT_FORMATS]
            )
            self._batch_files = files
            self.batch_table.setRowCount(len(files))
            for row, audio_path in enumerate(files):
                checkbox = QCheckBox()
                checkbox.setChecked(True)
                self.batch_table.setCellWidget(row, 0, checkbox)
                self.batch_table.setItem(row, 1, QTableWidgetItem(audio_path.name))
                self.batch_table.setItem(row, 2, QTableWidgetItem(audio_path.suffix.lower().lstrip(".")))

        def _set_batch_selection(self, selected: bool) -> None:
            for row in range(self.batch_table.rowCount()):
                widget = self.batch_table.cellWidget(row, 0)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(selected)

        def _get_selected_batch_files(self) -> list[pathlib.Path]:
            selected: list[pathlib.Path] = []
            for row, audio_path in enumerate(self._batch_files):
                widget = self.batch_table.cellWidget(row, 0)
                if isinstance(widget, QCheckBox) and widget.isChecked():
                    selected.append(audio_path)
            return selected

        def start_analyze(self) -> None:
            input_path = pathlib.Path(self.input_edit.text().strip())
            if not input_path.exists():
                self._show_error("Selecciona un archivo WAV de entrada válido.")
                return
            worker = AnalyzeWorker(
                input_path=input_path,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                verbose=self.verbose_cb.isChecked(),
                transparent_mode=self.transparent_cb.isChecked(),
            )
            self._start_worker(
                worker,
                on_finished=self._handle_analyze_finished,
            )
            self._set_busy(True, "Analizando...")

        def start_normalize(self) -> None:
            input_path = pathlib.Path(self.input_edit.text().strip())
            if not input_path.exists():
                self._show_error("Selecciona un archivo WAV de entrada válido.")
                return
            if self.last_stats is None:
                self._show_error("Primero ejecuta el análisis para obtener las métricas de loudness.")
                return
            if self.dynamic_eq_cb.isChecked() and not self.last_band_stats:
                self._show_error("Primero ejecuta el análisis para obtener métricas por bandas.")
                return
            output_text = self.output_edit.text().strip()
            output_path = pathlib.Path(output_text) if output_text else input_path.with_stem(f"{input_path.stem}_normalized")
            output_format = self._resolve_output_format_for_single()
            output_path = ensure_output_path(output_path, output_format)
            self.output_edit.setText(str(output_path))
            if self.analyze_only_cb.isChecked():
                self.append_log("Modo 'Solo analizar' activo: no se realizará escritura de salida.")
                return

            worker = NormalizeWorker(
                input_path=input_path,
                output_path=output_path,
                stats=self.last_stats,
                band_stats=self.last_band_stats,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                overwrite=self.overwrite_cb.isChecked(),
                verbose=self.verbose_cb.isChecked(),
                dynamic_eq=self.dynamic_eq_cb.isChecked(),
                brickwall=self.brickwall_cb.isChecked(),
                output_sr=self._get_output_sample_rate(),
                output_bit_depth=self._get_output_bit_depth(),
                output_format=output_format,
                stereo_width=self.stereo_width_cb.isChecked(),
                deesser=self.deesser_cb.isChecked(),
                fade_in=self.fade_in_spin.value(),
                fade_out=self.fade_out_spin.value(),
                transparent_mode=self.transparent_cb.isChecked(),
            )
            self._start_worker(
                worker,
                on_finished=self._handle_normalize_finished,
            )
            self._set_busy(True, "Normalizando...")

        def start_process(self) -> None:
            input_path = pathlib.Path(self.input_edit.text().strip())
            if not input_path.exists():
                self._show_error("Selecciona un archivo WAV de entrada válido.")
                return
            if self.dynamic_eq_cb.isChecked() and self.analyze_only_cb.isChecked():
                self.append_log("Modo 'Solo analizar' activo: se omitirá la normalización aunque esté activado el control dinámico.")
            output_text = self.output_edit.text().strip()
            output_path = pathlib.Path(output_text) if output_text else input_path.with_stem(f"{input_path.stem}_normalized")
            output_format = self._resolve_output_format_for_single()
            output_path = ensure_output_path(output_path, output_format)
            self.output_edit.setText(str(output_path))

            worker = ProcessWorker(
                input_path=input_path,
                output_path=output_path,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                overwrite=self.overwrite_cb.isChecked(),
                verbose=self.verbose_cb.isChecked(),
                dynamic_eq=self.dynamic_eq_cb.isChecked(),
                brickwall=self.brickwall_cb.isChecked(),
                analyze_only=self.analyze_only_cb.isChecked(),
                output_sr=self._get_output_sample_rate(),
                output_bit_depth=self._get_output_bit_depth(),
                output_format=output_format,
                stereo_width=self.stereo_width_cb.isChecked(),
                loudness_preset=self.preset_combo.currentText(),
                output_preset=self.output_preset_combo.currentText(),
                deesser=self.deesser_cb.isChecked(),
                fade_in=self.fade_in_spin.value(),
                fade_out=self.fade_out_spin.value(),
                transparent_mode=self.transparent_cb.isChecked(),
            )
            self._start_worker(
                worker,
                on_finished=self._handle_process_finished,
            )
            self._set_busy(True, "Procesando...")

        def start_batch_process(self) -> None:
            input_dir_text = self.batch_input_edit.text().strip()
            if not input_dir_text:
                self._show_error("Selecciona una carpeta de entrada para el lote.")
                return
            input_dir = pathlib.Path(input_dir_text)
            if not input_dir.exists():
                self._show_error("La carpeta de entrada no existe.")
                return
            if not self._batch_files:
                self.refresh_batch_table()
            selected_files = self._get_selected_batch_files()
            if not selected_files:
                self._show_error("No hay archivos seleccionados para procesar.")
                return
            self.batch_progress_bar.setRange(0, len(selected_files))
            self.batch_progress_bar.setValue(0)
            self.batch_progress_label.setText(f"0/{len(selected_files)}")
            output_dir_text = self.batch_output_edit.text().strip()
            output_dir: pathlib.Path | None = None
            if output_dir_text:
                output_dir = pathlib.Path(output_dir_text)
                if not output_dir.exists():
                    self._show_error("La carpeta de salida no existe.")
                    return
            suffix = self.batch_suffix_edit.text().strip() or "_processed"

            worker = BatchWorker(
                files=selected_files,
                output_dir=output_dir,
                suffix=suffix,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                overwrite=self.overwrite_cb.isChecked(),
                verbose=self.verbose_cb.isChecked(),
                dynamic_eq=self.dynamic_eq_cb.isChecked(),
                brickwall=self.brickwall_cb.isChecked(),
                output_sr=self._get_output_sample_rate(),
                output_bit_depth=self._get_output_bit_depth(),
                output_format=self._get_output_format(),
                stereo_width=self.stereo_width_cb.isChecked(),
                loudness_preset=self.preset_combo.currentText(),
                output_preset=self.output_preset_combo.currentText(),
                deesser=self.deesser_cb.isChecked(),
                fade_in=self.fade_in_spin.value(),
                fade_out=self.fade_out_spin.value(),
                transparent_mode=self.transparent_cb.isChecked(),
            )
            self._start_worker(
                worker,
                on_finished=self._handle_batch_finished,
            )
            self._set_busy(True, "Procesando lote...")

        def _start_worker(self, worker: QObject, on_finished) -> None:
            thread = QThread(self)
            worker.moveToThread(thread)
            self._current_worker = worker

            def cleanup() -> None:
                thread.quit()
                thread.wait()
                worker.deleteLater()
                thread.deleteLater()
                self._current_thread = None
                self._current_worker = None
                self._set_busy(False)

            def handle_error(message: str) -> None:
                self._show_error(message)
                cleanup()

            def handle_success(*args) -> None:
                try:
                    on_finished(*args)
                except Exception as exc:
                    self._show_error(str(exc))
                finally:
                    cleanup()

            if hasattr(worker, "finished"):
                worker.finished.connect(handle_success)  # type: ignore[attr-defined]
            if hasattr(worker, "error"):
                worker.error.connect(handle_error)  # type: ignore[attr-defined]
            if hasattr(worker, "progress"):
                worker.progress.connect(self._handle_worker_progress)  # type: ignore[attr-defined]
            thread.started.connect(worker.run)  # type: ignore[arg-type]
            self._current_thread = thread
            thread.start()

        def _on_analyze_only_toggled(self, state: int | bool) -> None:
            checked = bool(state)
            self.normalize_btn.setEnabled(not checked)
            self.process_btn.setEnabled(not checked)

        def _handle_analyze_finished(
            self,
            stats: Dict[str, float],
            band_stats: Dict[str, float],
            suggestions: list[str],
            voice_rms: object,
            log: str,
        ) -> None:
            self.last_stats = stats
            self.last_band_stats = band_stats
            self._update_stats_display(stats)
            self._update_voice_display(voice_rms)
            self.append_log("Análisis completado.")
            self._update_eq_display(band_stats, suggestions)
            if log:
                self.append_log(log.strip())

        def _handle_process_finished(
            self,
            stats: Dict[str, float],
            band_stats: Dict[str, float],
            suggestions: list[str],
            voice_rms: object,
            log: str,
            normalize_log: str,
            output_path: object,
            toml_path: object,
            post_stats: object,
            post_voice_rms: object,
            pre_rating: object,
            post_rating: object,
        ) -> None:
            self.last_stats = stats
            self.last_band_stats = band_stats
            self._update_stats_display(stats)
            self._update_voice_display(voice_rms)
            self._update_eq_display(band_stats, suggestions)
            self._update_results_table(stats, voice_rms, post_stats, post_voice_rms, pre_rating, post_rating)
            self.append_log("Proceso completado.")
            if output_path:
                self.append_log(f"Salida -> {output_path}")
            if toml_path:
                self.append_log(f"Reporte -> {toml_path}")
            if log:
                self.append_log(log.strip())
            if normalize_log:
                self.append_log(normalize_log.strip())

        def _handle_batch_finished(self, message: str, results: object) -> None:
            self.append_log(message)
            total = self.batch_progress_bar.maximum() if hasattr(self.batch_progress_bar, "maximum") else None
            if isinstance(total, int):
                self.batch_progress_bar.setValue(total)
            if isinstance(results, list):
                self._update_batch_results_table(results)
                self.tabs.setCurrentIndex(4)

        def _handle_normalize_finished(self, log: str, output_path: str) -> None:
            self.append_log(f"Normalización completada -> {output_path}")
            if log:
                self.append_log(log.strip())

        def _update_stats_display(self, stats: Dict[str, float]) -> None:
            self.input_i_label.setText(f"{stats.get('input_i', 0):.2f}")
            self.input_tp_label.setText(f"{stats.get('input_tp', 0):.2f}")
            self.input_lra_label.setText(f"{stats.get('input_lra', 0):.2f}")
            self.threshold_label.setText(f"{stats.get('input_thresh', 0):.2f}")
            self.offset_label.setText(f"{stats.get('target_offset', 0):.2f}")

        def _update_voice_display(self, voice_rms: object) -> None:
            if isinstance(voice_rms, (float, int)):
                self.voice_band_label.setText(f"{voice_rms:.2f} dB")
            else:
                self.voice_band_label.setText("-")

        def _update_eq_display(self, band_stats: Dict[str, float], suggestions: list[str]) -> None:
            for label, value_label in self.band_labels.items():
                if label in band_stats:
                    value_label.setText(f"{band_stats[label]:.2f} dB")
                else:
                    value_label.setText("-")
            if suggestions:
                self.eq_suggestions.setPlainText("\n".join(f"- {item}" for item in suggestions))
            else:
                self.eq_suggestions.setPlainText("Sin sugerencias por bandas.")

        def _update_batch_results_table(self, results: list[dict]) -> None:
            self.batch_results_table.setRowCount(len(results))
            for row_idx, item in enumerate(results):
                before = item.get("before", {}) if isinstance(item, dict) else {}
                after = item.get("after", {}) if isinstance(item, dict) else {}
                before_rating = item.get("before_rating", "-") if isinstance(item, dict) else "-"
                after_rating = item.get("after_rating", "-") if isinstance(item, dict) else "-"
                file_name = item.get("file", "-") if isinstance(item, dict) else "-"

                values = [
                    file_name,
                    f"{before.get('input_i', 0.0):.2f}",
                    f"{after.get('input_i', 0.0):.2f}",
                    f"{before.get('input_tp', 0.0):.2f}",
                    f"{after.get('input_tp', 0.0):.2f}",
                    f"{before.get('input_lra', 0.0):.2f}",
                    f"{after.get('input_lra', 0.0):.2f}",
                    before_rating,
                    after_rating,
                ]
                for col_idx, value in enumerate(values):
                    self.batch_results_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

        def _update_results_table(
            self,
            before_stats: Dict[str, float],
            before_voice: object,
            after_stats: object,
            after_voice: object,
            before_rating: object,
            after_rating: object,
        ) -> None:
            rows = [
                ("Input I (LUFS)", before_stats.get("input_i", 0.0), after_stats.get("input_i", 0.0) if isinstance(after_stats, dict) else None),
                ("Input TP (dBTP)", before_stats.get("input_tp", 0.0), after_stats.get("input_tp", 0.0) if isinstance(after_stats, dict) else None),
                ("Input LRA (LU)", before_stats.get("input_lra", 0.0), after_stats.get("input_lra", 0.0) if isinstance(after_stats, dict) else None),
                (VOICE_BAND[0], before_voice if isinstance(before_voice, (int, float)) else None, after_voice if isinstance(after_voice, (int, float)) else None),
                ("Evaluación", before_rating if isinstance(before_rating, str) else "-", after_rating if isinstance(after_rating, str) else "-"),
            ]
            self.results_table.setRowCount(len(rows))
            for row_idx, (label, before_val, after_val) in enumerate(rows):
                self.results_table.setItem(row_idx, 0, QTableWidgetItem(str(label)))
                if isinstance(before_val, (int, float)):
                    before_text = f"{before_val:.2f}"
                else:
                    before_text = str(before_val) if before_val is not None else "-"
                if isinstance(after_val, (int, float)):
                    after_text = f"{after_val:.2f}"
                else:
                    after_text = str(after_val) if after_val is not None else "-"
                self.results_table.setItem(row_idx, 1, QTableWidgetItem(before_text))
                self.results_table.setItem(row_idx, 2, QTableWidgetItem(after_text))

        def _set_busy(self, busy: bool, message: str | None = None) -> None:
            self.analyze_btn.setEnabled(not busy)
            self.normalize_btn.setEnabled(not busy)
            self.process_btn.setEnabled(not busy)
            self.batch_process_btn.setEnabled(not busy)
            self.input_button.setEnabled(not busy)
            self.output_button.setEnabled(not busy)
            self.batch_input_button.setEnabled(not busy)
            self.batch_output_button.setEnabled(not busy)
            self.batch_refresh_button.setEnabled(not busy)
            self.batch_table.setEnabled(not busy)
            self.batch_select_all_btn.setEnabled(not busy)
            self.batch_select_none_btn.setEnabled(not busy)
            self.batch_progress_bar.setEnabled(True)
            if message:
                self.append_log(message)

        def _handle_worker_progress(self, *args) -> None:
            if len(args) >= 3 and isinstance(args[1], int) and isinstance(args[2], int):
                message = str(args[0])
                current = args[1]
                total = args[2]
                self.batch_progress_bar.setRange(0, max(1, total))
                self.batch_progress_bar.setValue(current)
                self.batch_progress_label.setText(f"{current}/{total}")
                self.append_log(message)
            elif args:
                self.append_log(str(args[0]))

        def _on_mode_changed(self, allow_navigation: bool = True) -> None:
            mode = self.mode_combo.currentText()
            if mode == "Lote":
                self.tabs.setTabEnabled(1, False)
                self.tabs.setTabEnabled(2, True)
                if allow_navigation:
                    self.tabs.setCurrentIndex(2)
                self.analyze_only_cb.setEnabled(True)
            elif mode == "Solo analizar":
                self.tabs.setTabEnabled(1, True)
                self.tabs.setTabEnabled(2, False)
                if allow_navigation:
                    self.tabs.setCurrentIndex(1)
                self.analyze_only_cb.setChecked(True)
                self.analyze_only_cb.setEnabled(False)
            else:
                self.tabs.setTabEnabled(2, False)
                self.tabs.setTabEnabled(1, True)
                if allow_navigation:
                    self.tabs.setCurrentIndex(1)
                self.analyze_only_cb.setEnabled(True)

        def is_inicio_activo(self) -> bool:
            return self.tabs.currentWidget() == self.tab_start

        def append_log(self, message: str) -> None:
            self.log_view.appendPlainText(message)

        def _show_error(self, message: str) -> None:
            self.append_log(f"Error: {message}")

        def _apply_preset(self) -> None:
            self._apply_lufs_preset(self.preset_combo.currentText(), source="main")

        def _apply_batch_preset(self) -> None:
            self._apply_lufs_preset(self.batch_preset_combo.currentText(), source="batch")

        def _apply_lufs_preset(self, preset_name: str, source: str) -> None:
            preset = LOUDNESS_PRESETS.get(preset_name)
            if preset is None:
                return
            is_manual = preset_name == "Manual"
            if self._syncing_lufs:
                return
            self._syncing_lufs = True
            try:
                if source == "main":
                    self.batch_preset_combo.setCurrentText(preset_name)
                else:
                    self.preset_combo.setCurrentText(preset_name)

                if is_manual:
                    self.target_spin.setEnabled(True)
                    self.true_peak_spin.setEnabled(True)
                    self.batch_target_spin.setEnabled(True)
                    self.batch_true_peak_spin.setEnabled(True)
                else:
                    target, true_peak = preset
                    self.target_spin.setValue(target)
                    self.true_peak_spin.setValue(true_peak)
                    self.batch_target_spin.setValue(target)
                    self.batch_true_peak_spin.setValue(true_peak)
                    self.target_spin.setEnabled(False)
                    self.true_peak_spin.setEnabled(False)
                    self.batch_target_spin.setEnabled(False)
                    self.batch_true_peak_spin.setEnabled(False)
            finally:
                self._syncing_lufs = False

        def _apply_output_preset(self) -> None:
            preset_name = self.output_preset_combo.currentText()
            preset = OUTPUT_PRESETS.get(preset_name)
            if preset is None:
                return
            if preset_name == "Manual":
                self.sample_rate_combo.setEnabled(True)
                self.bit_depth_combo.setEnabled(True)
                return
            output_sr, bit_depth = preset
            if output_sr:
                if str(output_sr) in [self.sample_rate_combo.itemText(i) for i in range(self.sample_rate_combo.count())]:
                    self.sample_rate_combo.setCurrentText(str(output_sr))
            if bit_depth:
                self.bit_depth_combo.setCurrentText(bit_depth)
            self.sample_rate_combo.setEnabled(False)
            self.bit_depth_combo.setEnabled(False)

        def _sync_lufs_from_batch(self, _value: float) -> None:
            if self._syncing_lufs:
                return
            if self.batch_preset_combo.currentText() != "Manual":
                return
            self._syncing_lufs = True
            try:
                self.target_spin.setValue(self.batch_target_spin.value())
                self.true_peak_spin.setValue(self.batch_true_peak_spin.value())
            finally:
                self._syncing_lufs = False

        def _sync_lufs_from_main(self, _value: float) -> None:
            if self._syncing_lufs:
                return
            if self.preset_combo.currentText() != "Manual":
                return
            self._syncing_lufs = True
            try:
                self.batch_target_spin.setValue(self.target_spin.value())
                self.batch_true_peak_spin.setValue(self.true_peak_spin.value())
            finally:
                self._syncing_lufs = False

        def _apply_output_format(self) -> None:
            fmt = self._get_output_format()
            if fmt in ("mp3", "m4a"):
                self.bit_depth_combo.setEnabled(False)
            else:
                if self.output_preset_combo.currentText() == "Manual":
                    self.bit_depth_combo.setEnabled(True)

        def _get_output_format(self) -> str | None:
            text = self.output_format_combo.currentText()
            if text == "Auto":
                return None
            return text.lower()

        def _resolve_output_format_for_single(self) -> str | None:
            fmt = self._get_output_format()
            if fmt is not None:
                return fmt
            ext = pathlib.Path(self.output_edit.text().strip()).suffix
            if ext:
                return ext.lstrip(".").lower()
            return None

        def _get_output_sample_rate(self) -> int | None:
            text = self.sample_rate_combo.currentText()
            if text == "Mantener":
                return None
            try:
                return int(text)
            except ValueError:
                return None

        def _get_output_bit_depth(self) -> str | None:
            text = self.bit_depth_combo.currentText()
            if text == "Mantener":
                return None
            return text


def run_gui() -> int:
    if not PYSIDE_AVAILABLE:
        sys.stderr.write("PySide6 no está instalado. Ejecuta: pip install -r requirements.txt\n")
        return 1
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        owns_app = True
    else:
        owns_app = False
    window = MainWindow()
    window.show()
    return app.exec() if owns_app else 0
