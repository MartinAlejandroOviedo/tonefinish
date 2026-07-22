import json
import math
import os
import pathlib
import sys
import textwrap
from datetime import datetime
from typing import Any, Callable, Dict, cast

from audio_analysis import (
    analyze_silence_edges,
    compute_spectrum,
    evaluate_mix,
    format_analysis_summary,
    write_analysis_toml,
)
from logic_backend import ensure_output_path, resolve_repair_levels
from audio_tools import get_audio_duration, get_waveform_samples, cancel_running_ffmpeg_processes
from auto_master_intelligence import (
    analyze_audio_for_automaster,
    adapt_preset_to_audio,
    AudioCharacteristics,
)
from output_naming import mastered_output_stem
from compute_backend import ComputeBackend
from config import (
    BAND_CONFIG,
    DEFAULT_BAND_RANGE_DB,
    DEFAULT_MAX_ADJUST_DB,
    APP_NAME,
    APP_VERSION,
    LOGO_PATH,
    INPUT_FORMATS,
    LOUDNESS_PRESETS,
    MULTIBAND_LIMITER_DEFAULTS,
    OUTPUT_PRESETS,
    OUTPUT_FORMATS,
    TRANSPARENT_BAND_RANGE_DB,
    TRANSPARENT_MAX_ADJUST_DB,
    VOICE_BAND,
    is_premium,
    get_license_display_name,
    LICENSE_TYPE_FREE,
    LICENSE_TYPE_PREMIUM,
    clear_resource_profile_name,
    load_resource_profile_name,
    save_resource_profile_name,
    save_license_type,
    load_api_keys,
    save_api_keys,
)
from ui.qt_compat import (
    QApplication,
    PYSIDE_AVAILABLE,
    PYQTGRAPH_AVAILABLE,
    PlotWidget,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QIcon,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QObject,
    QShortcut,
    Signal,
    QSizePolicy,
    QSpacerItem,
    QStyle,
    QEvent,
    QKeySequence,
    QSvgWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    pg,
)
from ui.workers import (
    AnalyzeWorker,
    AutoMasterAnalysisWorker,
    BatchAutoMasterWorker,
    BatchWorker,
    CliBatchWorker,
    NormalizeWorker,
    ProcessWorker,
)
from resource_monitor import ResourceMonitor
from resource_governor import ResourceGovernor
from runtime_reproducibility import check_runtime_reproducibility
from bandcamp_bok import (
    generate_all as _bok_generate_all,
    generate_lyrics as _bok_generate_lyrics,
    build_providers as _bok_build_providers,
)
from ui.tabs import (
    build_about_tab,
    build_audio_tab,
    build_auto_master_tab,
    build_batch_tab,
    build_process_tab,
    build_results_tab,
    build_signature_tab,
    build_start_tab,
    build_ai_text_tab,
)
from ui.tabs_new import (
    build_start_tab_new,
    build_project_tab_new,
    build_processing_tab_new,
    build_results_tab_new,
    build_about_tab_new,
    build_auto_master_preview_tab,
    build_diagnostic_tab,
)
from ui.batch_drop_table import BatchDropTable

AUTO_MASTER_STANDARD_STYLES = [
    "SUNO Clean (Mastering conservador)",
    "Universal (Rock, Pop, Electrónica)",
    "Natural (Acústico, Jazz, Folk)",
    "Claridad (Clásica, R&B, Cantautor)",
    "Cinta (Jazz, Alternativa, Indie)",
    "Fuego (Trap, Reguetón, Hip-Hop)",
]
DEFAULT_SUBTLE_FADE_IN_S = 0.02
DEFAULT_SUBTLE_FADE_OUT_S = 0.10
MAX_AUTO_FADE_IN_S = 0.08
MAX_AUTO_FADE_OUT_S = 0.30
LOG_ROTATE_MAX_BYTES = 5 * 1024 * 1024
LOG_ROTATE_KEEP_FILES = 5
LOG_RESOLUTION_MARKER_FILE = "resolved_issues.json"
HISTORICAL_LOG_FIXES = [
    {
        "issue_id": "ffmpeg_filter_tanh_missing",
        "status": "resolved",
        "note": "Error historico: No such filter 'tanh' en cadenas legacy.",
    },
    {
        "issue_id": "normalize_audio_sub_bass_db_kwarg",
        "status": "resolved",
        "note": "Error historico: normalize_audio() no aceptaba sub_bass_db.",
    },
    {
        "issue_id": "batch_worker_autogain_maxgain_kwarg",
        "status": "resolved",
        "note": "Error historico: BatchWorker.__init__() no aceptaba autogain_maxgain.",
    },
    {
        "issue_id": "calibration_runaway_iterations",
        "status": "resolved",
        "note": "Calibracion limitada para evitar divergencias en iteraciones largas.",
    },
]

# Importaciones opcionales para preview (independiente de matplotlib)
try:
    from audio_preview import AudioPreview
    PREVIEW_AVAILABLE = True
except ImportError:
    PREVIEW_AVAILABLE = False
    AudioPreview = None  # type: ignore

# Importaciones opcionales para espectro (requiere matplotlib)
try:
    from spectrum_analyzer import analyze_spectrum_fft, generate_spectrum_plot_data
    import matplotlib
    matplotlib.use('QtAgg')  # Backend Qt para PySide6
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    SPECTRUM_AVAILABLE = True
except ImportError:
    SPECTRUM_AVAILABLE = False
    FigureCanvas = None
    Figure = None


if PYSIDE_AVAILABLE:
    def _apply_global_ui_styles(app: QApplication) -> None:
        """Aplica una base visual consistente para toda la interfaz."""
        app.setStyle("Fusion")
        app.setStyleSheet(
            """
            QWidget {
                color: #ffffff;
            }
            QWidget#MainWindow {
                background-color: #1b2230;
                color: #ffffff;
            }
            QGroupBox {
                margin-top: 16px;
                padding-top: 16px;
                border: 1px solid #405063;
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.02);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: #ffffff;
                font-weight: 600;
            }
            QTabWidget::pane {
                border: 1px solid #405063;
                top: -1px;
                background-color: #111827;
            }
            QTabBar::tab {
                background-color: #283244;
                color: #ffffff;
                border: 1px solid #405063;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 7px 12px;
                min-height: 22px;
            }
            QTabBar::tab:selected {
                background-color: #364152;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #313c4f;
            }
            QLineEdit,
            QComboBox,
            QDoubleSpinBox,
            QPlainTextEdit,
            QTableWidget {
                background-color: #111827;
                color: #ffffff;
                border: 1px solid #405063;
                border-radius: 6px;
            }
            QLineEdit,
            QComboBox,
            QDoubleSpinBox {
                min-height: 28px;
                padding: 4px 8px;
            }
            QPlainTextEdit {
                padding: 6px;
            }
            QPushButton {
                min-height: 30px;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid #516177;
                background-color: #2f3b4f;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #39485f;
            }
            QPushButton:pressed {
                background-color: #253043;
            }
            QHeaderView::section {
                background-color: #283244;
                color: #ffffff;
                padding: 6px 8px;
                border: 1px solid #405063;
            }
            QProgressBar {
                border: 1px solid #405063;
                border-radius: 6px;
                text-align: center;
                background-color: #111827;
                color: #ffffff;
            }
            QLabel, QCheckBox, QRadioButton, QMenu, QMenuBar, QToolButton,
            QListWidget, QListView, QTreeWidget, QTreeView, QTableWidget,
            QTableView, QAbstractItemView, QStatusBar, QToolTip {
                color: #ffffff;
            }
            QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled,
            QPushButton:disabled, QCheckBox:disabled, QLabel:disabled {
                color: #ffffff;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background-color: #4aa3ff;
            }
            """
        )

    class MainWindow(QWidget):
        log_signal = Signal(str)
        # Señales para diagnóstico (thread-safe)
        diagnostic_progress_signal = Signal(int, str)
        diagnostic_finished_signal = Signal(object, str)
        benchmark_finished_signal = Signal(object, str)
        
        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("MainWindow")
            self.setWindowTitle("ToneFinish")
            self.setMinimumWidth(480)
            if LOGO_PATH:
                self.setWindowIcon(QIcon(LOGO_PATH))
            self._current_thread = None
            self._current_worker = None
            self._worker_finish_handler = None
            self._resource_monitor = ResourceMonitor()
            self._resource_governor = ResourceGovernor(self._resource_monitor)
            self._resource_monitor_timer = None
            self._last_resource_snapshot = None
            self._last_resource_profile = None
            self._last_resource_gpu_summary = None
            self._current_processing_budget = None
            self._resource_profile_override = load_resource_profile_name()
            self.resource_profile_combo = QComboBox()
            self.resource_profile_combo.addItems(["Auto", "Baja", "Media", "Alta", "Muy alta"])
            self.resource_profile_combo.blockSignals(True)
            self.resource_profile_combo.setCurrentText(self._resource_profile_override or "Auto")
            self.resource_profile_combo.blockSignals(False)
            self.last_stats: Dict[str, float] | None = None
            self.last_band_stats: Dict[str, float] | None = None
            self.band_labels: Dict[str, QLabel] = {}
            self.tab_start = None
            self.tab_single = None
            self.tab_batch = None
            self.tab_process = None
            self.tab_waveform = None
            self.tab_results = None
            self.tab_presets = None
            self.tab_signature = None
            
            # Widgets de diagnóstico (se inicializan en build_diagnostic_tab)
            self.diagnostic_run_btn: Any = None
            self.diagnostic_copy_btn: Any = None
            self.diagnostic_markdown_cb: Any = None
            self.diagnostic_metrics_table: Any = None
            self.diagnostic_bands_table: Any = None
            self.diagnostic_eval_text: Any = None
            self.diagnostic_report_text: Any = None
            self.diagnostic_status_label: Any = None
            self.diagnostic_progress_bar: Any = None
            self.diagnostic_progress_label: Any = None
            self._last_diagnostic_result: Any = None

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
            self.output_preset_combo.setCurrentText("Studio Max (96 kHz / 24-bit)")

            self.output_format_combo = QComboBox()
            self.output_format_combo.addItems(["Auto"] + [fmt.upper() for fmt in OUTPUT_FORMATS])
            self.output_format_combo.setCurrentText("WAV")

            self.mode_combo = QComboBox()
            self.mode_combo.addItems([
                "Auto-Master (Audio único)", "Auto-Master (Lote)",
                "Solo analizar", "Generar con IA",
            ])
            self.mode_combo.setCurrentIndex(0)
            self.mode_combo.setToolTip(
                "La IA controla siempre el mastering; sin tokens se usa SUNO Clásico."
            )

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
            self.fade_in_spin.setValue(DEFAULT_SUBTLE_FADE_IN_S)
            self.fade_in_spin.setSuffix(" s")

            self.fade_out_spin = QDoubleSpinBox()
            self.fade_out_spin.setRange(0.0, 30.0)
            self.fade_out_spin.setDecimals(2)
            self.fade_out_spin.setValue(DEFAULT_SUBTLE_FADE_OUT_S)
            self.fade_out_spin.setSuffix(" s")

            self.fade_overrides: dict[str, tuple[float, float]] = {}
            self.waveform_plot = None
            self.waveform_curve = None
            self.fade_in_region = None
            self.fade_out_region = None
            self.waveform_help = None
            self._waveform_duration = None
            self._waveform_syncing = False
            self.single_waveform_plot = None
            self.single_waveform_curve = None
            self.single_waveform_help = None
            self.stereo_band_plot = None
            self.stereo_band_bars = None
            self.stereo_band_spins: dict[str, QDoubleSpinBox] = {}
            self.dynamic_band_plot = None
            self.dynamic_band_bars = None
            self.dynamic_band_spins: dict[str, QDoubleSpinBox] = {}
            self.stereo_dynamic_band_mix_spins: dict[str, QDoubleSpinBox] = {}
            self.dynamic_eq_preset_combo = QComboBox()
            self.dynamic_eq_preset_combo.addItems(
                [
                    "Manual",
                    "Neutral (0 / 0 / 0 / 0 / 0 / 0)",
                    "Balanced (+0.2 / +0.2 / 0 / 0 / 0 / +0.2)",
                    "Warm Glue (+0.5 / +0.5 / -0.3 / -0.2 / 0 / 0)",
                    "Bright Lift (-0.3 / -0.2 / 0 / +0.2 / +0.4 / +0.6)",
                    "Tight Low (-0.8 / -0.6 / -0.2 / 0 / +0.2 / +0.2)",
                    "Vocal Focus (-0.2 / 0 / +0.5 / +0.8 / +0.3 / 0)",
                    "Smooth Top (0 / 0 / -0.2 / -0.2 / -0.4 / -0.6)",
                    "Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)",
                    "Airy (-0.2 / -0.2 / 0 / +0.1 / +0.4 / +0.8)",
                    "Master General (+0.3 / +0.2 / -0.1 / 0 / +0.2 / +0.3)",
                    "Auto Control (+0.1 / 0 / -0.4 / -0.6 / -0.8 / -1.0)",
                ]
            )
            self.dynamic_eq_preset_combo.setCurrentIndex(0)
            self.waveform_table = QTableWidget(0, 3)
            self.waveform_table.setHorizontalHeaderLabels(["Archivo", "Fade in", "Fade out"])
            self.waveform_table.horizontalHeader().setStretchLastSection(True)
            if PYSIDE_AVAILABLE:
                self.waveform_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                self.waveform_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.waveform_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.waveform_fade_in_spin = QDoubleSpinBox()
            self.waveform_fade_in_spin.setRange(0.0, 30.0)
            self.waveform_fade_in_spin.setDecimals(2)
            self.waveform_fade_in_spin.setValue(DEFAULT_SUBTLE_FADE_IN_S)
            self.waveform_fade_in_spin.setSuffix(" s")
            self.waveform_fade_out_spin = QDoubleSpinBox()
            self.waveform_fade_out_spin.setRange(0.0, 30.0)
            self.waveform_fade_out_spin.setDecimals(2)
            self.waveform_fade_out_spin.setValue(DEFAULT_SUBTLE_FADE_OUT_S)
            self.waveform_fade_out_spin.setSuffix(" s")
            self.waveform_global_label = QLabel("Global: - / -")
            self.waveform_use_global_btn = QPushButton("Usar global para este audio")
            self.waveform_apply_btn = QPushButton("Guardar override")
            self._waveform_selected_path: pathlib.Path | None = None
            self._waveform_files: list[pathlib.Path] = []

            self.noise_reduction_combo = QComboBox()
            self.noise_reduction_combo.addItems(["Off", "Auto", "Leve", "Medio", "Alto"])
            self.noise_reduction_combo.setCurrentIndex(1)

            self.input_gain_spin = QDoubleSpinBox()
            self.input_gain_spin.setRange(-24.0, 24.0)
            self.input_gain_spin.setDecimals(1)
            self.input_gain_spin.setValue(-17.0)
            self.input_gain_spin.setSuffix(" dB")

            self.dc_offset_cb = QCheckBox("Eliminar DC offset")
            self.dc_offset_cb.setChecked(True)

            self.input_rms_label = QLabel("-")
            self.input_peak_label = QLabel("-")

            self.declip_combo = QComboBox()
            self.declip_combo.addItems(["Off", "Auto", "Leve", "Medio", "Alto"])
            self.declip_combo.setCurrentIndex(1)

            self.declick_combo = QComboBox()
            self.declick_combo.addItems(["Off", "Auto", "Leve", "Medio", "Alto"])
            self.declick_combo.setCurrentIndex(1)

            self.auto_repair_cb = QCheckBox("Auto completo (Noise/Clip/Pop)")
            self.auto_repair_cb.setChecked(True)

            # Pink Noise reduction - compensa curva -3dB/octava
            self.pink_noise_combo = QComboBox()
            self.pink_noise_combo.addItems(["Off", "Leve", "Medio", "Alto"])
            self.pink_noise_combo.setCurrentIndex(0)

            self.glue_threshold_spin = QDoubleSpinBox()
            self.glue_threshold_spin.setRange(-60.0, 0.0)
            self.glue_threshold_spin.setDecimals(1)
            self.glue_threshold_spin.setValue(-18.0)
            self.glue_threshold_spin.setSuffix(" dB")

            self.glue_ratio_spin = QDoubleSpinBox()
            self.glue_ratio_spin.setRange(1.0, 10.0)
            self.glue_ratio_spin.setDecimals(2)
            self.glue_ratio_spin.setValue(1.4)

            self.glue_attack_spin = QDoubleSpinBox()
            self.glue_attack_spin.setRange(1.0, 200.0)
            self.glue_attack_spin.setDecimals(0)
            self.glue_attack_spin.setValue(20.0)
            self.glue_attack_spin.setSuffix(" ms")

            self.glue_release_spin = QDoubleSpinBox()
            self.glue_release_spin.setRange(20.0, 1000.0)
            self.glue_release_spin.setDecimals(0)
            self.glue_release_spin.setValue(120.0)
            self.glue_release_spin.setSuffix(" ms")

            self.glue_makeup_spin = QDoubleSpinBox()
            self.glue_makeup_spin.setRange(-12.0, 12.0)
            self.glue_makeup_spin.setDecimals(1)
            self.glue_makeup_spin.setValue(0.0)
            self.glue_makeup_spin.setSuffix(" dB")

            self.glue_preset_combo = QComboBox()
            self.glue_preset_combo.addItems(
                [
                    "Manual",
                    "Clasico (-22 / 1.5 / 30 / 180 / 0.0)",
                    "Pop (-18 / 2.0 / 12 / 140 / 0.8)",
                    "Jazz (-24 / 1.3 / 40 / 200 / 0.0)",
                    "Funk (-17 / 2.2 / 10 / 130 / 0.8)",
                    "Disco (-16 / 2.4 / 10 / 120 / 1.0)",
                ]
            )
            self.glue_preset_combo.setCurrentIndex(0)

            self.deesser_freq_spin = QDoubleSpinBox()
            self.deesser_freq_spin.setRange(2000.0, 12000.0)
            self.deesser_freq_spin.setDecimals(0)
            self.deesser_freq_spin.setValue(6000.0)
            self.deesser_freq_spin.setSuffix(" Hz")

            self.deesser_intensity_spin = QDoubleSpinBox()
            self.deesser_intensity_spin.setRange(0.2, 1.0)
            self.deesser_intensity_spin.setDecimals(2)
            self.deesser_intensity_spin.setValue(1.0)
            self.deesser_intensity_spin.setSuffix(" x")

            self.deesser_preset_combo = QComboBox()
            self.deesser_preset_combo.addItems(
                [
                    "Manual",
                    "Tenor (6.5 kHz / 0.70)",
                    "Baritono (5.5 kHz / 0.65)",
                    "Bajo (4.5 kHz / 0.60)",
                    "Soprano (8.0 kHz / 0.75)",
                    "Mezzo-soprano (7.0 kHz / 0.70)",
                    "Contralto (5.2 kHz / 0.65)",
                    "Rap agresivo (6.0 kHz / 0.85)",
                    "Rap suave (5.0 kHz / 0.75)",
                    "Vocoder (9.0 kHz / 0.60)",
                    "Voz hablada (5.5 kHz / 0.60)",
                    "Voz brillante (6.5 kHz / 0.55)",
                ]
            )
            self.deesser_preset_combo.setCurrentIndex(0)

            self.stereo_dynamic_threshold_spin = QDoubleSpinBox()
            self.stereo_dynamic_threshold_spin.setRange(-60.0, -6.0)
            self.stereo_dynamic_threshold_spin.setDecimals(1)
            self.stereo_dynamic_threshold_spin.setValue(-24.0)
            self.stereo_dynamic_threshold_spin.setSuffix(" dB")

            self.stereo_dynamic_ratio_spin = QDoubleSpinBox()
            self.stereo_dynamic_ratio_spin.setRange(1.0, 10.0)
            self.stereo_dynamic_ratio_spin.setDecimals(2)
            self.stereo_dynamic_ratio_spin.setValue(1.6)

            self.stereo_dynamic_attack_spin = QDoubleSpinBox()
            self.stereo_dynamic_attack_spin.setRange(1.0, 200.0)
            self.stereo_dynamic_attack_spin.setDecimals(0)
            self.stereo_dynamic_attack_spin.setValue(20.0)
            self.stereo_dynamic_attack_spin.setSuffix(" ms")

            self.stereo_dynamic_release_spin = QDoubleSpinBox()
            self.stereo_dynamic_release_spin.setRange(20.0, 1000.0)
            self.stereo_dynamic_release_spin.setDecimals(0)
            self.stereo_dynamic_release_spin.setValue(150.0)
            self.stereo_dynamic_release_spin.setSuffix(" ms")

            self.stereo_dynamic_mix_spin = QDoubleSpinBox()
            self.stereo_dynamic_mix_spin.setRange(0.0, 1.0)
            self.stereo_dynamic_mix_spin.setDecimals(2)
            self.stereo_dynamic_mix_spin.setValue(0.6)

            self.eq_low_spin = QDoubleSpinBox()
            self.eq_low_spin.setRange(-12.0, 12.0)
            self.eq_low_spin.setDecimals(1)
            self.eq_low_spin.setValue(0.0)
            self.eq_low_spin.setSuffix(" dB")

            self.sub_bass_spin = QDoubleSpinBox()
            self.sub_bass_spin.setRange(-12.0, 12.0)
            self.sub_bass_spin.setDecimals(1)
            self.sub_bass_spin.setValue(0.0)
            self.sub_bass_spin.setSuffix(" dB")

            self.eq_mid_spin = QDoubleSpinBox()
            self.eq_mid_spin.setRange(-12.0, 12.0)
            self.eq_mid_spin.setDecimals(1)
            self.eq_mid_spin.setValue(0.0)
            self.eq_mid_spin.setSuffix(" dB")

            self.eq_high_spin = QDoubleSpinBox()
            self.eq_high_spin.setRange(-12.0, 12.0)
            self.eq_high_spin.setDecimals(1)
            self.eq_high_spin.setValue(0.0)
            self.eq_high_spin.setSuffix(" dB")

            self.tone_eq_preset_combo = QComboBox()
            self.tone_eq_preset_combo.addItems(
                [
                    "Manual",
                    "Neutral (0 / 0 / 0)",
                    "Warm (+1.0 / -0.5 / -0.5)",
                    "Bright (-0.5 / 0 / +1.0)",
                    "Air (0 / -0.5 / +1.5)",
                    "Tight Low (-1.0 / 0 / +0.5)",
                    "Vocal Focus (-0.5 / +1.0 / +0.5)",
                    "Smooth (+0.5 / -1.0 / +0.5)",
                    "Mid Scoop (+0.5 / -1.5 / +0.5)",
                    "Low Punch (+1.5 / -0.5 / 0)",
                    "Dark (+0.5 / 0 / -1.5)",
                ]
            )
            self.tone_eq_preset_combo.setCurrentIndex(0)

            self.tilt_eq_spin = QDoubleSpinBox()
            self.tilt_eq_spin.setRange(-6.0, 6.0)
            self.tilt_eq_spin.setDecimals(1)
            self.tilt_eq_spin.setValue(0.0)
            self.tilt_eq_spin.setSuffix(" dB")

            self.saturation_drive_spin = QDoubleSpinBox()
            self.saturation_drive_spin.setRange(-24.0, 24.0)
            self.saturation_drive_spin.setDecimals(1)
            self.saturation_drive_spin.setValue(0.5)
            self.saturation_drive_spin.setSuffix(" dB")

            self.saturation_mix_spin = QDoubleSpinBox()
            self.saturation_mix_spin.setRange(0.0, 100.0)
            self.saturation_mix_spin.setDecimals(0)
            self.saturation_mix_spin.setValue(4.0)
            self.saturation_mix_spin.setSuffix(" %")

            self.saturation_type_combo = QComboBox()
            self.saturation_type_combo.addItems(["Tape", "Tube", "Soft Clip"])
            self.saturation_type_combo.setCurrentIndex(0)

            self.saturation_enable_cb = QCheckBox("Saturacion")
            # Por defecto dejamos la saturación desactivada: Auto-Master la activará cuando corresponda.
            # Esto evita que el modo "Universal" o presets sin color agreguen distorsión no deseada.
            self.saturation_enable_cb.setChecked(False)
            self.saturation_per_band_cb = QCheckBox("Saturacion por bandas")
            self.saturation_per_band_cb.setChecked(False)
            self.saturation_band_drive_spins: dict[str, QDoubleSpinBox] = {}
            self.saturation_band_mix_spins: dict[str, QDoubleSpinBox] = {}

            # Control de Saturación Final
            self.saturation_limiter_cb = QCheckBox("Control de saturación final")
            self.saturation_limiter_cb.setChecked(False)
            self.saturation_limiter_cb.setToolTip(
                "Controla saturación excesiva antes de la normalización final"
            )

            self.saturation_target_thd_spin = QDoubleSpinBox()
            self.saturation_target_thd_spin.setRange(1.0, 10.0)
            self.saturation_target_thd_spin.setDecimals(1)
            self.saturation_target_thd_spin.setValue(3.0)
            self.saturation_target_thd_spin.setSuffix(" % THD")
            self.saturation_target_thd_spin.setToolTip(
                "THD objetivo (1-10%). Valores bajos = control más agresivo"
            )

            self.saturation_reduction_mode_combo = QComboBox()
            self.saturation_reduction_mode_combo.addItems(["musical", "transparent"])
            self.saturation_reduction_mode_combo.setCurrentIndex(0)
            self.saturation_reduction_mode_combo.setToolTip(
                "Musical: suave y cálido | Transparent: preciso y limpio"
            )

            self.adaptive_saturation_control_cb = QCheckBox("Control adaptativo de volumen")
            self.adaptive_saturation_control_cb.setChecked(False)
            self.adaptive_saturation_control_cb.setToolTip(
                "Ajusta automáticamente el volumen final si detecta saturación excesiva"
            )

            self.loudness_pre_label = QLabel("-")
            self.loudness_post_label = QLabel("-")

            self.limiter_ceiling_spin = QDoubleSpinBox()
            self.limiter_ceiling_spin.setRange(-6.0, 0.0)
            self.limiter_ceiling_spin.setDecimals(1)
            self.limiter_ceiling_spin.setValue(-1.0)
            self.limiter_ceiling_spin.setSuffix(" dBTP")

            self.limiter_release_spin = QDoubleSpinBox()
            self.limiter_release_spin.setRange(10.0, 500.0)
            self.limiter_release_spin.setDecimals(0)
            self.limiter_release_spin.setValue(100.0)
            self.limiter_release_spin.setSuffix(" ms")

            self.limiter_preset_combo = QComboBox()
            self.limiter_preset_combo.addItems(
                [
                    "Manual",
                    "Seguro (-1.0 / 120)",
                    "Transparente (-1.0 / 200)",
                    "Punchy (-0.8 / 80)",
                    "Loud (-0.6 / 60)",
                    "Clasico (-0.9 / 120)",
                ]
            )
            self.limiter_preset_combo.setCurrentIndex(0)

            # Multiband Limiter - Brickwall por bandas
            self.multiband_limiter_cb = QCheckBox("Limitador Multibanda")
            self.multiband_limiter_cb.setChecked(False)
            self.multiband_limiter_cb.setToolTip(
                "Aplica un limitador brickwall independiente a cada banda de frecuencia"
            )
            self.multiband_limiter_spins: dict[str, QDoubleSpinBox] = {}
            for band_label, default_db in MULTIBAND_LIMITER_DEFAULTS.items():
                spin = QDoubleSpinBox()
                spin.setRange(-12.0, 0.0)
                spin.setDecimals(1)
                spin.setValue(default_db)
                spin.setSuffix(" dB")
                self.multiband_limiter_spins[band_label] = spin

            self.auto_master_style_combo = QComboBox()
            self.auto_master_style_combo.addItems(AUTO_MASTER_STANDARD_STYLES)
            # Segundo combo sincronizado para el tab Auto-Master dedicado
            self.auto_master_style_combo_tab = QComboBox()
            self.auto_master_style_combo_tab.addItems(AUTO_MASTER_STANDARD_STYLES)
            self.auto_master_enable_process_cb = QCheckBox("Habilitar Procesos")
            self.auto_master_enable_process_cb.setChecked(False)
            self.auto_master_enable_process_cb.setVisible(True)
            self.auto_master_intelligent_cb = QCheckBox("Análisis Inteligente")
            self.auto_master_intelligent_cb.setChecked(True)
            self.auto_master_intelligent_cb.setEnabled(False)
            self.auto_master_intelligent_cb.setVisible(False)
            self.auto_master_intelligent_cb.setToolTip(
                "Analiza el audio y adapta el preset automáticamente según el contenido"
            )
            self.auto_master_ai_assist_cb = QCheckBox("Master asistido por IA")
            self.auto_master_ai_assist_cb.setChecked(True)
            self.auto_master_ai_assist_cb.setEnabled(False)
            self.auto_master_ai_assist_cb.setVisible(False)
            self.auto_master_ai_assist_cb.setToolTip(
                "Si está activo, Auto-Master consulta DeepSeek/NVIDIA con las métricas del audio "
                "para decidir la estrategia. Si no hay API key válida o la IA falla, usa el motor local."
            )
            self.auto_master_ai_assist_cb_tab = QCheckBox("Master asistido por IA")
            self.auto_master_ai_assist_cb_tab.setChecked(True)
            self.auto_master_ai_assist_cb_tab.setEnabled(False)
            self.auto_master_ai_assist_cb_tab.setVisible(False)
            self.auto_master_ai_assist_cb_tab.setToolTip(self.auto_master_ai_assist_cb.toolTip())
            self.auto_master_profile_label = QLabel("Perfil Auto-Master: -")
            self.auto_master_profile_label.setStyleSheet(
                "QLabel { font-weight: bold; color: #ffffff; }"
            )
            self.auto_master_min_lra_spin = QDoubleSpinBox()
            self.auto_master_min_lra_spin.setRange(2.0, 10.0)
            self.auto_master_min_lra_spin.setDecimals(1)
            self.auto_master_min_lra_spin.setSingleStep(0.5)
            self.auto_master_min_lra_spin.setValue(4.5)
            self.auto_master_min_lra_spin.setSuffix(" LU")
            self.auto_master_min_lra_spin.setToolTip(
                "Si el LRA está por debajo de este valor, Auto-Master activa procesamiento mínimo."
            )
            self.auto_master_min_crest_spin = QDoubleSpinBox()
            self.auto_master_min_crest_spin.setRange(5.0, 15.0)
            self.auto_master_min_crest_spin.setDecimals(1)
            self.auto_master_min_crest_spin.setSingleStep(0.5)
            self.auto_master_min_crest_spin.setValue(8.5)
            self.auto_master_min_crest_spin.setSuffix(" dB")
            self.auto_master_min_crest_spin.setToolTip(
                "Si el crest factor está por debajo de este valor, Auto-Master activa procesamiento mínimo."
            )
            self.auto_master_block_mode_cb = QCheckBox("Solo por bloque (por sección)")
            self.auto_master_block_mode_cb.setChecked(False)
            self.auto_master_block_mode_cb.setToolTip(
                "Si está activado, el Auto-Master analiza y ajusta cada sección/bloque por separado "
                "en lugar de aplicar una configuración única a todo el archivo."
            )
            self.auto_master_motion_preset_combo = QComboBox()
            self.auto_master_motion_preset_combo.addItems(
                [
                    "Off",
                    "Subtle",
                    "Musical",
                    "Creative",
                    "Custom",
                ]
            )
            self.auto_master_motion_preset_combo.setCurrentText("Musical")
            self.auto_master_motion_preset_combo.setToolTip(
                "Preset rápido de movimiento (Fase 6)."
            )
            self.auto_master_motion_profile_combo = QComboBox()
            self.auto_master_motion_profile_combo.addItems(
                [
                    "Auto",
                    "Tight (estable)",
                    "Balanced (equilibrado)",
                    "Airy (abierto)",
                ]
            )
            self.auto_master_motion_profile_combo.setCurrentIndex(0)
            self.auto_master_motion_profile_combo.setToolTip(
                "Perfil de movimiento para Band Motion Fase 5."
            )
            self.auto_master_motion_amount_spin = QDoubleSpinBox()
            self.auto_master_motion_amount_spin.setRange(0.0, 150.0)
            self.auto_master_motion_amount_spin.setDecimals(0)
            self.auto_master_motion_amount_spin.setSingleStep(5.0)
            self.auto_master_motion_amount_spin.setValue(100.0)
            self.auto_master_motion_amount_spin.setSuffix(" %")
            self.auto_master_motion_amount_spin.setToolTip(
                "Cantidad global de movimiento. 0% desactiva Band Motion."
            )
            self.auto_master_apply_btn = QPushButton("Auto-configurar")
            self.auto_master_notes = QPlainTextEdit()
            self.auto_master_notes.setReadOnly(True)
            self.auto_master_notes.setMinimumHeight(150)

            self.signature_artist_edit = QLineEdit()
            self.signature_artist_edit.setText("O-M-A")
            self.signature_copyright_edit = QLineEdit()
            self.signature_comment_edit = QPlainTextEdit()
            self.signature_comment_edit.setMinimumHeight(80)
            self.signature_url_edit = QLineEdit()
            self.signature_email_edit = QLineEdit()
            self.signature_label_edit = QLineEdit()
            self.signature_company_edit = QLineEdit("SABE Software")
            self.signature_company_edit.setReadOnly(True)
            default_year = datetime.now().year
            self.signature_copyright_edit.setText(
                f"(c) {default_year} <Artist>. Procesado por SABE Software."
            )
            self.signature_preset_combo = QComboBox()
            self.signature_preset_combo.setEditable(True)
            self.signature_save_btn = QPushButton("Guardar preset")
            self.signature_delete_btn = QPushButton("Eliminar preset")

            # Presets personalizados de Mezcla
            self.mix_preset_combo = QComboBox()
            self.mix_preset_combo.setEditable(True)
            self.mix_preset_combo.setPlaceholderText("Nombre del preset...")
            self.mix_save_btn = QPushButton("💾 Guardar")
            self.mix_delete_btn = QPushButton("🗑️ Eliminar")
            self.mix_save_btn.setMaximumWidth(100)
            self.mix_delete_btn.setMaximumWidth(100)

            # Presets personalizados de Mastering
            self.master_preset_combo = QComboBox()
            self.master_preset_combo.setEditable(True)
            self.master_preset_combo.setPlaceholderText("Nombre del preset...")
            self.master_save_btn = QPushButton("💾 Guardar")
            self.master_delete_btn = QPushButton("🗑️ Eliminar")
            self.master_save_btn.setMaximumWidth(100)
            self.master_delete_btn.setMaximumWidth(100)

            self.batch_input_edit = QLineEdit()
            self.batch_input_button = QPushButton("Carpeta entrada...")
            self.batch_input_button.clicked.connect(self.choose_batch_input)
            self.batch_refresh_button = QPushButton("Actualizar lista")
            self.batch_refresh_button.clicked.connect(self.refresh_batch_table)

            self.batch_output_edit = QLineEdit()
            self.batch_output_button = QPushButton("Carpeta salida...")
            self.batch_output_button.clicked.connect(self.choose_batch_output)

            self.batch_suffix_edit = QLineEdit()
            self.batch_suffix_edit.setText("O-M-A")
            # El artista visible en el nombre y el artista embebido en metadata
            # son una única identidad, aunque aparezcan en dos pestañas.
            self.signature_artist_edit.textChanged.connect(self.batch_suffix_edit.setText)
            self.batch_suffix_edit.textChanged.connect(self.signature_artist_edit.setText)

            self.batch_table = BatchDropTable(0, 3)
            self.batch_table.setHorizontalHeaderLabels(["Procesar", "Archivo", "Formato"])
            self.batch_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.batch_table.setColumnWidth(0, 90)
            self.batch_table.setColumnWidth(2, 90)
            self.batch_table.horizontalHeader().setStretchLastSection(False)
            self.batch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.batch_table.files_dropped.connect(self._on_batch_files_dropped)
            self.batch_select_all_btn = QPushButton("Seleccionar todo")
            self.batch_select_none_btn = QPushButton("Ninguno")
            self.batch_select_all_btn.clicked.connect(lambda: self._set_batch_selection(True))
            self.batch_select_none_btn.clicked.connect(lambda: self._set_batch_selection(False))

            self.batch_process_btn = QPushButton("Procesar lote")
            self.batch_automaster_btn = QPushButton("🧠 Auto-configurar Lote")
            self.batch_automaster_btn.setToolTip(
                "Analiza los archivos del lote y configura automáticamente\n"
                "los parámetros de procesamiento óptimos para todos"
            )
            self._batch_files: list[pathlib.Path] = []

            self.overwrite_cb = QCheckBox("Sobrescribir salida si existe")
            self.overwrite_cb.setChecked(True)
            self.analyze_only_cb = QCheckBox("Solo analizar (no escribir salida)")
            self.verbose_cb = QCheckBox("Verbose (muestra comandos ffmpeg)")
            self.dynamic_eq_cb = QCheckBox("Control dinámico por bandas")
            self.brickwall_cb = QCheckBox("Master Limiter (True Peak)")
            self.master_limiter_mode_combo = QComboBox()
            self.master_limiter_mode_combo.addItems(["transparent", "musical", "aggressive"])
            self.master_limiter_mode_combo.setCurrentText("transparent")
            self.stereo_width_cb = QCheckBox("Stereo width por bandas")
            self.deesser_cb = QCheckBox("De-Esser (sibilancia)")
            self.stereo_dynamic_cb = QCheckBox("Stereo dinamico")
            self.transparent_cb = QCheckBox("Modo transparente")
            self.auto_band_gain_cb = QCheckBox("Auto-gain por bandas (evita suma)")
            self.glue_cb = QCheckBox("Glue compression")
            
            # Checkboxes para habilitar/deshabilitar cadenas completas
            self.repair_enabled_cb = QCheckBox("🔧 Reparación habilitada")
            self.mix_enabled_cb = QCheckBox("🎛️ Mezcla habilitada")
            self.master_enabled_cb = QCheckBox("🎚️ Mastering habilitado")
            self.autogain_cb = QCheckBox("🎚️ AutoGain (control de picos)")
            self.repair_enabled_cb.setChecked(True)
            self.mix_enabled_cb.setChecked(True)
            self.master_enabled_cb.setChecked(True)
            self.autogain_cb.setChecked(True)
            self.repair_enabled_cb.setToolTip("Deshabilita toda la cadena de reparación (ruido, declip, declick, pink noise, DC offset)")
            self.mix_enabled_cb.setToolTip("Deshabilita toda la cadena de mezcla (EQ, dinámica, saturación, stereo, glue, de-esser)")
            self.master_enabled_cb.setToolTip("Deshabilita toda la cadena de mastering (loudness, limiter, fades)")
            self.autogain_cb.setToolTip(
                "AutoGain: controla la ganancia durante el procesamiento\\n"
                "• Inicia a -17dB para evitar saturación\\n"
                "• Aplica limitadores suaves entre procesos (picos < 0dB)\\n"
                "• Normaliza el pico final a -1dB antes de loudnorm"
            )
            
            self.dynamic_eq_cb.setChecked(True)
            self.brickwall_cb.setChecked(True)
            self.stereo_width_cb.setChecked(True)
            self.deesser_cb.setChecked(True)
            self.stereo_dynamic_cb.setChecked(True)
            self.transparent_cb.setChecked(True)
            self.auto_band_gain_cb.setChecked(True)
            self.glue_cb.setChecked(True)

            self.analyze_btn = QPushButton("Analizar")
            self.normalize_btn = QPushButton("Normalizar")
            self.process_btn = QPushButton("Procesar audio")
            
            # Botones de preview y comparación A/B
            self.preview_btn = QPushButton("🎧 Preview (30s)")
            self.play_original_btn = QPushButton("▶️ Original")
            self.play_processed_btn = QPushButton("▶️ Procesado")
            self.stop_preview_btn = QPushButton("⏹️ Detener")

            self.input_i_label = QLabel("-")
            self.input_tp_label = QLabel("-")
            self.input_lra_label = QLabel("-")
            self.threshold_label = QLabel("-")
            self.offset_label = QLabel("-")
            self.voice_band_label = QLabel("-")
            self.single_results_container = None

            self.eq_suggestions = QPlainTextEdit()
            self.eq_suggestions.setReadOnly(True)
            self.eq_suggestions.setMinimumHeight(120)

            self.results_table = QTableWidget(5, 3)
            self.results_table.setHorizontalHeaderLabels(["Métrica", "Antes", "Después"])
            self.results_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.results_table.horizontalHeader().setStretchLastSection(True)
            self.results_text = QPlainTextEdit()
            self.results_text.setReadOnly(True)
            self.results_text.setMinimumHeight(100)
            self.copy_results_btn = QPushButton("Copiar resumen")

            # Indicadores visuales de telemetría (Paso 4)
            self.validation_warnings_label = QLabel("")
            self.validation_warnings_label.setWordWrap(True)
            self.validation_warnings_label.setStyleSheet(
                "QLabel { padding: 8px; border-radius: 4px; }"
            )
            self.validation_warnings_label.setVisible(False)
            
            # Barra de progreso de GR con gradiente visual
            self.compression_gr_bar = QProgressBar()
            self.compression_gr_bar.setRange(0, 100)  # 0-10 dB en escala de 0-100
            self.compression_gr_bar.setValue(0)
            self.compression_gr_bar.setFormat("GR: 0.0 dB")
            self.compression_gr_bar.setTextVisible(True)
            self.compression_gr_bar.setMinimumHeight(28)
            self.compression_gr_bar.setStyleSheet(
                "QProgressBar {"
                "    border: 2px solid #ccc;"
                "    border-radius: 5px;"
                "    text-align: center;"
                "    font-weight: bold;"
                "    background-color: #111827;"
                "    color: #ffffff;"
                "}"
                "QProgressBar::chunk {"
                "    background: qlineargradient("
                "        x1:0, y1:0, x2:1, y2:0,"
                "        stop:0 #4CAF50,"
                "        stop:0.4 #8BC34A,"
                "        stop:0.6 #FFC107,"
                "        stop:0.8 #FF9800,"
                "        stop:1.0 #F44336"
                "    );"
                "    border-radius: 3px;"
                "}"
            )
            self.compression_gr_bar.setToolTip(
                "Gain Reduction total estimado\n"
                "\u2022 <4 dB: Saludable (verde)\n"
                "\u2022 4-6 dB: Moderado (amarillo)\n"
                "\u2022 6-8 dB: Alto (naranja)\n"
                "\u2022 >8 dB: Cr\u00edtico (rojo)"
            )
            
            self.process_stages_label = QLabel("")
            self.process_stages_label.setStyleSheet(
                "QLabel { font-size: 10pt; color: #ffffff; }"
            )
            self.process_stages_label.setVisible(False)
            self.process_state_label = QLabel("Estado: listo")
            self.process_state_label.setStyleSheet(
                "QLabel { font-size: 10pt; font-weight: bold; color: #ffffff; }"
            )
            self.process_file_label = QLabel("Archivo: -")
            self.process_file_label.setWordWrap(True)
            self.process_file_label.setStyleSheet("QLabel { font-size: 9pt; color: #ffffff; }")
            self.process_history_text = QPlainTextEdit()
            self.process_history_text.setReadOnly(True)
            self.process_history_text.setMaximumHeight(140)
            self.process_history_text.setStyleSheet("font-family: monospace; font-size: 10px;")
            self.process_history_text.setPlaceholderText("El historial del proceso aparecerá aquí.")
            self._process_history_lines: list[str] = []
            self._batch_history_lines: list[str] = []
            self._current_process_file: str | None = None
            self._process_state_styles = {
                "listo": "QLabel { font-size: 10pt; font-weight: bold; color: #ffffff; }",
                "analizando": "QLabel { font-size: 10pt; font-weight: bold; color: #ffffff; }",
                "procesando": "QLabel { font-size: 10pt; font-weight: bold; color: #ffffff; }",
                "validando": "QLabel { font-size: 10pt; font-weight: bold; color: #ffffff; }",
                "finalizado": "QLabel { font-size: 10pt; font-weight: bold; color: #ffffff; }",
                "error": "QLabel { font-size: 10pt; font-weight: bold; color: #ffffff; }",
            }

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

            self.results_tabs = QTabWidget()
            self.results_tab_eq_index = -1
            self.results_tab_single_index = -1
            self.results_tab_batch_index = -1
            self.results_tab_batch_summary_index = -1
            self.results_tab_analysis_summary_index = -1
            self.results_tab_spectrum_index = -1
            self.results_tab_log_index = -1
            self.results_tab_inspector_index = -1
            self.process_tabs: QTabWidget | None = None
            self.project_tabs: QTabWidget | None = None
            self.batch_results_group = None  # QGroupBox, asignado en build_results_tab_new
            self.log_group = None  # QGroupBox, asignado en build_results_tab_new
            self.details_group = None  # QGroupBox, asignado en build_results_tab_new
            self.process_order_widget = None

            self.log_view = QPlainTextEdit()
            self.log_view.setReadOnly(True)
            self.log_view.setMinimumHeight(160)
            self.clear_log_btn = QPushButton("Limpiar log")
            self.copy_log_path_btn = QPushButton("Copiar ruta log")
            self.log_path_label = QLabel()
            self.log_history_table = QTableWidget()
            self.log_history_table.setColumnCount(9)
            self.log_history_table.setHorizontalHeaderLabels(
                ["Fecha", "Accion", "Modo", "Entrada", "Salida", "Estilo", "Procesos", "LUFS", "TP"]
            )
            self.log_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.log_history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.log_history_table.horizontalHeader().setStretchLastSection(True)
            self.log_history_table.verticalHeader().setVisible(False)
            self.log_history_table.setMinimumHeight(140)
            self.log_history_load_btn = QPushButton("Cargar log")
            self.log_history_list: list[dict] = []
            self.inspector_mts_path_edit = QLineEdit()
            self.inspector_mts_path_edit.setPlaceholderText("Ruta a *.mts.json")
            self.inspector_mts_browse_btn = QPushButton("Buscar MTS")
            self.inspector_mts_load_btn = QPushButton("Cargar Inspector")
            self.inspector_mts_from_history_btn = QPushButton("Desde historial")
            self.inspector_text = QPlainTextEdit()
            self.inspector_text.setReadOnly(True)
            self.inspector_text.setMinimumHeight(220)
            self.inspector_text.setPlainText(
                "Inspector: carga un archivo .mts.json para ver secciones, eventos y decisiones adaptativas."
            )

            self.global_progress_label = QLabel("Listo")
            self.global_progress_bar = QProgressBar()
            self.global_progress_bar.setRange(0, 1)
            self.global_progress_bar.setValue(0)
            self.global_progress_bar.setTextVisible(True)
            self.global_progress_bar.setFormat("%p%")
            self.progress_popup = QWidget(self, Qt.WindowType.Window)
            self.progress_popup.setWindowTitle("Progreso del Proceso")
            self.progress_popup.resize(760, 420)
            popup_layout = QVBoxLayout()
            popup_layout.setContentsMargins(10, 10, 10, 10)
            self.progress_popup_label = QLabel("Listo")
            self.progress_popup_label.setWordWrap(True)
            self.progress_popup_bar = QProgressBar()
            self.progress_popup_bar.setRange(0, 1)
            self.progress_popup_bar.setValue(0)
            self.progress_popup_bar.setTextVisible(True)
            self.progress_popup_bar.setFormat("%p%")
            self.progress_popup_log = QPlainTextEdit()
            self.progress_popup_log.setReadOnly(True)
            self.progress_popup_log.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.progress_popup_log.setPlaceholderText("El detalle del proceso aparecerá aquí.")
            self.progress_popup_log.setStyleSheet("font-family: monospace; font-size: 10px;")
            self.progress_popup_hide_btn = QPushButton("Ocultar")
            self.progress_popup_cancel_btn = QPushButton("Cancelar proceso")
            self.progress_popup_copy_btn = QPushButton("Copiar log")
            self.progress_popup_hide_btn.clicked.connect(self.progress_popup.hide)
            self.progress_popup_cancel_btn.clicked.connect(self._cancel_current_process)
            self.progress_popup_copy_btn.clicked.connect(self._copy_progress_popup_log)
            popup_layout.addWidget(self.progress_popup_label)
            popup_layout.addWidget(self.progress_popup_bar)
            popup_layout.addWidget(self.progress_popup_log, 1)
            popup_layout.addWidget(self.progress_popup_copy_btn)
            popup_layout.addWidget(self.progress_popup_hide_btn)
            popup_layout.addWidget(self.progress_popup_cancel_btn)
            self.progress_popup.setLayout(popup_layout)
            self._progress_popup_max_lines = 2000
            self._progress_context = "Listo"
            self._progress_detail = ""

            self.batch_summary_text = QPlainTextEdit()
            self.batch_summary_text.setReadOnly(True)
            self.batch_summary_text.setMinimumHeight(80)
            self.analysis_summary_text = QPlainTextEdit()
            self.analysis_summary_text.setReadOnly(True)
            self.analysis_summary_text.setMinimumHeight(140)
            self.spectrum_diag = QPlainTextEdit()
            self.spectrum_diag.setReadOnly(True)
            self.spectrum_diag.setMinimumHeight(120)
            
            # Variables de preview y espectro
            self.preview_player = None
            self.spectrum_canvas = None
            self.spectrum_figure = None
            self.current_spectrum_data = None
            
            if PYQTGRAPH_AVAILABLE:
                self.spectrum_plot = pg.PlotWidget()
                self.spectrum_plot.setMinimumHeight(180)
                self.spectrum_plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self.spectrum_plot.showGrid(x=True, y=True, alpha=0.25)
                self.spectrum_plot.setLabel("bottom", "Frecuencia", units="Hz")
                self.spectrum_plot.setLabel("left", "Magnitud", units="dB")
                self.spectrum_plot.setLogMode(x=True, y=False)
                self.spectrum_plot.addLegend()
                self.spectrum_curve_pre = self.spectrum_plot.plot([], [], pen=pg.mkPen("#4aa3ff", width=2), name="Pre")
                self.spectrum_curve_post = self.spectrum_plot.plot([], [], pen=pg.mkPen("#ffa64d", width=2), name="Post")
                self.spectrum_curve_conflict = self.spectrum_plot.plot([], [], pen=pg.mkPen("#ffd24d", width=2), name="Conflicto ±2 dB")
            else:
                self.spectrum_plot = None
                self.spectrum_curve_pre = None
            self.spectrum_curve_post = None
            self.spectrum_curve_conflict = None
            self.log_file_path = pathlib.Path.home() / ".tonefinish" / "logs" / "tonefinish.log"
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path_label.setText(f"Log histórico: {self.log_file_path}")
            self.log_history_path = self.log_file_path.parent / "history.jsonl"
            self.log_resolution_marker_path = self.log_file_path.parent / LOG_RESOLUTION_MARKER_FILE
            self.batch_checkpoint_path = self.log_file_path.parent / "batch_checkpoint.json"
            self._ensure_log_resolution_marker()
            self.log_signal.connect(self._append_log_gui, Qt.ConnectionType.QueuedConnection)
            # Conectar señales de diagnóstico
            self.diagnostic_progress_signal.connect(self._update_diagnostic_progress, Qt.ConnectionType.QueuedConnection)
            self.diagnostic_finished_signal.connect(self._on_diagnostic_finished, Qt.ConnectionType.QueuedConnection)
            self.benchmark_finished_signal.connect(self._on_benchmark_finished, Qt.ConnectionType.QueuedConnection)
            self.window_toggle_btn = QPushButton("Maximizar")
            self.window_toggle_btn.setMaximumWidth(120)
            self.window_toggle_btn.clicked.connect(self._toggle_window_maximize)
            self.window_toggle_btn.setToolTip("Alterna entre maximizar y restaurar la ventana (también F11).")

            def tip(widget: QWidget, text: str) -> None:
                widget.setToolTip(text)

            tip(self.mode_combo, "Auto-Master IA para audio único o lote; fallback SUNO Clásico sin tokens.")
            tip(self.input_edit, "Ruta del audio de entrada.")
            tip(self.input_button, "Seleccionar archivo de entrada.")
            tip(self.output_edit, "Salida automática: ARTISTA - nombre de la canción.ext")
            tip(self.output_button, "Seleccionar archivo de salida.")
            tip(self.batch_input_button, "Seleccionar carpeta con audios de entrada.")
            tip(self.batch_output_button, "Seleccionar carpeta de salida para el lote.")
            tip(self.batch_suffix_edit, "Artista usado en el nombre: ARTISTA - canción.ext")
            tip(self.batch_refresh_button, "Actualizar la lista de archivos.")
            tip(self.batch_select_all_btn, "Seleccionar todos los archivos del lote.")
            tip(self.batch_select_none_btn, "Deseleccionar todos los archivos del lote.")
            tip(self.batch_process_btn, "Procesar todos los archivos seleccionados.")
            tip(self.batch_automaster_btn, "Analiza lote y auto-configura parámetros.")
            tip(self.analyze_btn, "Solo analiza el audio sin escribir salida.")
            tip(self.normalize_btn, "Normaliza usando el ultimo analisis.")
            tip(self.process_btn, "Analiza y procesa en un solo paso.")
            tip(self.preview_btn, "Genera preview de 30s con los filtros configurados.")
            tip(self.play_original_btn, "Reproduce el audio original sin procesamiento.")
            tip(self.play_processed_btn, "Reproduce el audio procesado completo.")
            tip(self.stop_preview_btn, "Detiene la reproducción actual.")
            tip(self.preset_combo, "Preset de loudness (LUFS y true peak).")
            tip(self.target_spin, "Objetivo de loudness en LUFS.")
            tip(self.true_peak_spin, "Limite de true peak en dBTP.")
            tip(self.output_preset_combo, "Preset de salida (sample rate y bit depth).")
            tip(self.output_format_combo, "Formato de salida. Auto usa la extension.")
            tip(self.sample_rate_combo, "Sample rate de salida.")
            tip(self.bit_depth_combo, "Bit depth de salida.")
            tip(self.overwrite_cb, "Sobrescribe el archivo de salida si existe.")
            tip(self.analyze_only_cb, "No escribe salida, solo analiza.")
            tip(self.verbose_cb, "Muestra comandos ffmpeg en el log.")
            tip(self.transparent_cb, "Procesamiento mas suave y conservador.")
            tip(self.auto_band_gain_cb, "Normaliza la suma de bandas para evitar acumulacion.")
            tip(self.dynamic_eq_cb, "Activa EQ dinamica por bandas.")
            tip(self.deesser_cb, "Controla sibilancias y brillo excesivo.")
            tip(self.glue_cb, "Compresion suave para cohesionar la mezcla.")
            tip(self.stereo_width_cb, "Ajusta apertura estereo por bandas.")
            tip(self.stereo_dynamic_cb, "Compresion dinamica en el canal Side.")
            tip(self.brickwall_cb, 
                "Master Limiter: Limitador final con True Peak protection\\n"
                "• Detecta Inter-Sample Peaks (ISP)\\n"
                "• Modos: transparent (suave), musical (pump), aggressive (rápido)\\n"
                "• Última línea de defensa contra clipping"
            )
            tip(self.master_limiter_mode_combo,
                "Modo del limitador maestro:\\n"
                "• transparent: Attack suave, release normal (uso general)\\n"
                "• musical: Attack lento, más pump (música dinámica)\\n"
                "• aggressive: Attack rápido, menos pump (música comprimida)"
            )
            tip(self.saturation_enable_cb, "Saturacion global ligera.")
            tip(self.saturation_per_band_cb, "Saturacion por bandas con control fino.")
            tip(self.saturation_type_combo, "Tipo de saturacion.")
            tip(self.saturation_drive_spin, "Ganancia previa a la saturacion.")
            tip(self.saturation_mix_spin, "Porcentaje de mezcla saturada.")
            tip(self.deesser_preset_combo, "Preset del de-esser.")
            tip(self.deesser_freq_spin, "Frecuencia objetivo del de-esser.")
            tip(self.deesser_intensity_spin, "Intensidad del de-esser.")
            tip(self.glue_preset_combo, "Preset del glue compresor.")
            tip(self.glue_threshold_spin, "Umbral del glue compresor.")
            tip(self.glue_ratio_spin, "Ratio del glue compresor.")
            tip(self.glue_attack_spin, "Ataque del glue compresor.")
            tip(self.glue_release_spin, "Release del glue compresor.")
            tip(self.glue_makeup_spin, "Makeup gain del glue compresor.")
            tip(self.limiter_preset_combo, "Preset del limitador brickwall.")
            tip(self.limiter_ceiling_spin, "Ceiling del limitador (dBTP).")
            tip(self.limiter_release_spin, "Release del limitador (ms).")
            tip(self.multiband_limiter_cb, "Activa limitador brickwall por bandas.")
            for band_label, spin in self.multiband_limiter_spins.items():
                tip(spin, f"Umbral del limitador para banda {band_label}.")
            tip(self.eq_low_spin, "EQ de graves.")
            tip(self.sub_bass_spin, "Sub bass: puedes subir o cortar subgrave para controlar picos y saturación.")
            tip(self.eq_mid_spin, "EQ de medios.")
            tip(self.eq_high_spin, "EQ de agudos.")
            tip(self.tilt_eq_spin, "Tilt EQ (inclina graves vs agudos).")
            tip(self.tone_eq_preset_combo, "Preset de EQ tonal.")
            tip(self.dynamic_eq_preset_combo, "Preset de EQ dinamica.")
            tip(self.stereo_dynamic_threshold_spin, "Umbral del stereo dinamico.")
            tip(self.stereo_dynamic_ratio_spin, "Ratio del stereo dinamico.")
            tip(self.stereo_dynamic_attack_spin, "Ataque del stereo dinamico.")
            tip(self.stereo_dynamic_release_spin, "Release del stereo dinamico.")
            tip(self.stereo_dynamic_mix_spin, "Mezcla dry/wet del stereo dinamico.")
            tip(self.noise_reduction_combo, "Reduccion de ruido.")
            tip(self.pink_noise_combo, "Reduce pink noise (ruido rosa) aplicando compensación +3dB/octava.")
            tip(self.declip_combo, "Nivel de declip.")
            tip(self.declick_combo, "Nivel de declick.")
            tip(self.auto_repair_cb, "Activa niveles Auto de repair.")
            tip(self.input_gain_spin, "Headroom inicial antes del procesamiento. -17dB es óptimo para evitar saturación durante el proceso. El loudnorm final recupera el volumen al target LUFS.")
            tip(self.dc_offset_cb, "Elimina DC offset antes del procesamiento.")
            tip(self.auto_master_style_combo, "Selecciona el estilo según el género musical y características deseadas.")
            tip(self.auto_master_enable_process_cb, "Muestra la tab Procesos.")
            tip(self.auto_master_intelligent_cb, "Analiza el audio y adapta el preset según contenido.")
            tip(self.auto_master_ai_assist_cb, "Permite que la IA proponga la estrategia de mastering cuando hay API key válida.")
            tip(self.auto_master_ai_assist_cb_tab, "Permite que la IA proponga la estrategia de mastering cuando hay API key válida.")
            tip(self.auto_master_block_mode_cb, "Si está activado, el Auto-Master analiza y ajusta cada sección/bloque por separado en lugar de aplicar una configuración única a todo el archivo.")
            tip(self.auto_master_profile_label, "Perfil calculado automáticamente por Auto-Master.")
            tip(self.auto_master_min_lra_spin, "Umbral de LRA para activar el modo de procesamiento mínimo.")
            tip(self.auto_master_min_crest_spin, "Umbral de crest factor para activar el modo de procesamiento mínimo.")
            tip(self.auto_master_motion_preset_combo, "Preset rápido de movimiento Auto-Master (Fase 6).")
            tip(self.auto_master_motion_profile_combo, "Perfil de movimiento Auto-Master (Fase 5).")
            tip(self.auto_master_motion_amount_spin, "Cantidad global de movimiento Auto-Master (Fase 5).")
            tip(self.auto_master_apply_btn, "Aplica presets y ajustes automaticos.")
            tip(self.auto_master_notes, "Resumen de decisiones y análisis de Auto-Master.")
            tip(self.clear_log_btn, "Limpia el log visible para un nuevo proceso.")
            tip(self.copy_log_path_btn, "Copia la ruta del log historico.")
            tip(self.log_history_load_btn, "Carga el log seleccionado del historial.")
            tip(self.inspector_mts_browse_btn, "Busca un archivo MTS (.mts.json).")
            tip(self.inspector_mts_load_btn, "Carga MTS + decisiones + shadow en el Inspector.")
            tip(self.inspector_mts_from_history_btn, "Intenta cargar Inspector desde la fila seleccionada del historial.")
            tip(self.signature_artist_edit, "Artista (metadata).")
            tip(self.signature_copyright_edit, "Copyright (metadata).")
            tip(self.signature_comment_edit, "Comentario (metadata).")
            tip(self.signature_url_edit, "URL (metadata).")
            tip(self.signature_email_edit, "Email (metadata).")
            tip(self.signature_label_edit, "Sello/Label (metadata).")
            tip(self.signature_preset_combo, "Preset de firma.")
            tip(self.signature_save_btn, "Guardar preset de firma.")
            tip(self.signature_delete_btn, "Eliminar preset de firma.")
            tip(self.waveform_table, "Listado de audios con fades.")
            tip(self.waveform_fade_in_spin, "Fade in global (segundos).")
            tip(self.waveform_fade_out_spin, "Fade out global (segundos).")
            tip(self.waveform_apply_btn, "Guardar fade para este audio.")
            tip(self.waveform_use_global_btn, "Copiar fades globales al audio seleccionado.")
            tip(self.global_progress_bar, "Progreso del proceso actual.")

            self._mode_initialized = False
            self._build_layout()
            self._wire_events()
            self._sync_motion_preset_from_controls()
            self._install_window_toggle_filters()
            self._window_toggle_shortcut = QShortcut(QKeySequence("F11"), self)
            self._window_toggle_shortcut.activated.connect(self._toggle_window_maximize)
            self._sync_window_toggle_button()

            self.analyze_only_cb.stateChanged.connect(self._on_analyze_only_toggled)
            self._on_analyze_only_toggled(self.analyze_only_cb.isChecked())
            self._on_auto_repair_toggled(self.auto_repair_cb.isChecked())
            self._on_mode_changed(allow_navigation=False)
            self.tabs.setCurrentIndex(0)


        def _build_layout(self) -> None:
            layout = QVBoxLayout()

            header_layout = QHBoxLayout()
            header_layout.addStretch(1)
            header_layout.addWidget(self.window_toggle_btn)
            layout.addLayout(header_layout)

            tabs = QTabWidget()
            self.tabs = tabs

            # Nueva estructura de 5 tabs principales
            tab_start = build_start_tab_new(self)
            tab_project = build_project_tab_new(self)
            tab_auto_master = build_auto_master_preview_tab(self)
            tab_processing = build_processing_tab_new(self)
            tab_results = build_results_tab_new(self)
            tab_diagnostic = build_diagnostic_tab(self)
            tab_about = build_about_tab_new(self)
            tab_ai_text = build_ai_text_tab(self)

            tabs.addTab(tab_start, "🏠 Inicio")
            tabs.addTab(tab_ai_text, "🤖 Generar con IA")
            tabs.addTab(tab_project, "📂 Proyecto")
            tabs.addTab(tab_auto_master, "🎯 Auto-Master")
            tabs.addTab(tab_processing, "🎛️ Procesamiento")
            tabs.addTab(tab_results, "📊 Resultados")
            tabs.addTab(tab_diagnostic, "🔬 Diagnóstico")
            tabs.addTab(tab_about, "ℹ️ Acerca de")
            tabs.setCurrentIndex(0)
            
            # Bandcamp tab connections (must be after tab creation)
            self.bc_gen_btn.clicked.connect(self._generate_bandcamp_texts)
            self.bc_copy_btn.clicked.connect(self._copy_bandcamp_texts)
            self.bc_release_msg_edit.textChanged.connect(self._update_bc_char_count)
            # Contexto IA connections
            self.ia_api_key_edit.textChanged.connect(self._on_api_keys_changed)
            self.ia_nvidia_key_edit.textChanged.connect(self._on_api_keys_changed)
            self.suno_deepseek_key_edit.textChanged.connect(self._on_api_keys_changed)
            self.suno_nvidia_key_edit.textChanged.connect(self._on_api_keys_changed)
            self.auto_master_ai_assist_cb.toggled.connect(self._sync_auto_master_ai_assist)
            self.auto_master_ai_assist_cb_tab.toggled.connect(self._sync_auto_master_ai_assist)
            self.suno_generate_btn.clicked.connect(self._generate_suno_prompts_from_dataset)
            self.suno_generate_style_btn.clicked.connect(self._generate_suno_style_from_dataset)
            self.suno_generate_lyrics_prompt_btn.clicked.connect(self._generate_suno_lyrics_prompt_from_dataset)
            self.suno_generate_exclude_btn.clicked.connect(self._generate_suno_exclude_from_dataset)
            self.suno_copy_btn.clicked.connect(self._copy_suno_prompts)

            # Restaurar API keys persistidas
            keys = load_api_keys()
            api_key_widgets = (
                self.ia_api_key_edit,
                self.ia_nvidia_key_edit,
                self.suno_deepseek_key_edit,
                self.suno_nvidia_key_edit,
            )
            for widget in api_key_widgets:
                widget.blockSignals(True)
            try:
                if keys.get("deepseek"):
                    self.ia_api_key_edit.setText(keys["deepseek"])
                    self.suno_deepseek_key_edit.setText(keys["deepseek"])
                if keys.get("nvidia"):
                    self.ia_nvidia_key_edit.setText(keys["nvidia"])
                    self.suno_nvidia_key_edit.setText(keys["nvidia"])
            finally:
                for widget in api_key_widgets:
                    widget.blockSignals(False)
            self._update_api_status(persist=False)
            
            # Índices de tabs para navegación
            self.tab_index_start = 0
            self.tab_index_ai_text = 1
            self.tab_index_project = 2
            self.tab_index_auto_master = 3
            self.tab_index_processing = 4
            self.tab_index_results = 5
            self.tab_index_diagnostic = 6
            self.tab_index_about = 7
            self.tab_index_contexto_ia = self.tab_index_ai_text
            self.tab_index_suno_prompt = self.tab_index_ai_text
            self.tab_index_bandcamp = self.tab_index_ai_text
            
            # Mantener compatibilidad con código existente
            self.tab_index_audio = self.tab_index_project
            self.tab_index_batch = self.tab_index_project
            self.tab_index_signature = self.tab_index_project
            self.tab_index_process = self.tab_index_processing
            self.signature_tab_index = self.tab_index_project
            
            self._apply_tab_icons()
            self._apply_button_icons()

            progress_layout = QHBoxLayout()
            progress_layout.addWidget(QLabel("Progreso:"))
            progress_layout.addWidget(self.global_progress_bar)
            progress_layout.addWidget(self.global_progress_label)
            self.progress_bar_widget = QWidget()
            self.progress_bar_widget.setLayout(progress_layout)

            layout.addWidget(tabs)
            actions_layout = QHBoxLayout()
            actions_layout.addWidget(self.process_btn)
            actions_layout.addWidget(self.batch_process_btn)
            actions_layout.addWidget(self.batch_automaster_btn)
            actions_layout.addWidget(self.analyze_btn)
            self.mastering_actions_widget = QWidget()
            self.mastering_actions_widget.setLayout(actions_layout)
            layout.addWidget(self.mastering_actions_widget)
            
            # Los botones de preview ahora están en la tab Auto-Master
            layout.addWidget(self.progress_bar_widget)
            self.setLayout(layout)
            self.tabs.currentChanged.connect(self._on_main_tab_changed)
            self._on_main_tab_changed(self.tabs.currentIndex())

        def _toggle_window_maximize(self) -> None:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            self._sync_window_toggle_button()

        def _sync_window_toggle_button(self) -> None:
            if self.isMaximized():
                self.window_toggle_btn.setText("Restaurar")
                self.window_toggle_btn.setToolTip("Restaurar la ventana a su tamaño normal (también F11).")
            else:
                self.window_toggle_btn.setText("Maximizar")
                self.window_toggle_btn.setToolTip("Maximizar la ventana (también F11).")

        def _on_main_tab_changed(self, index: int) -> None:
            in_text_generation = index == getattr(self, "tab_index_ai_text", -1)
            if hasattr(self, "mastering_actions_widget"):
                self.mastering_actions_widget.setVisible(not in_text_generation)
            if hasattr(self, "progress_bar_widget"):
                self.progress_bar_widget.setVisible(not in_text_generation)

        def _should_toggle_window_from_widget(self, widget: QWidget) -> bool:
            blocked_types = (
                QLineEdit,
                QPlainTextEdit,
                QComboBox,
                QDoubleSpinBox,
                QPushButton,
                QCheckBox,
                QTableWidget,
                QTabWidget,
                QAbstractItemView,
            )
            return not isinstance(widget, blocked_types)

        def _install_window_toggle_filters(self) -> None:
            self.installEventFilter(self)
            for widget in self.findChildren(QWidget):
                try:
                    widget.installEventFilter(self)
                except Exception:
                    pass

        def eventFilter(self, obj: object, event: object) -> bool:  # type: ignore[override]
            try:
                if (
                    isinstance(obj, QWidget)
                    and event.type() == QEvent.Type.MouseButtonDblClick
                    and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton
                    and (obj is self or self.isAncestorOf(obj))
                    and self._should_toggle_window_from_widget(obj)
                ):
                    self._toggle_window_maximize()
                    return True
            except Exception:
                pass
            return super().eventFilter(obj, event)

        def changeEvent(self, event: object) -> None:  # type: ignore[override]
            try:
                if event.type() == QEvent.Type.WindowStateChange:
                    self._sync_window_toggle_button()
            except Exception:
                pass
            return super().changeEvent(event)

        def _wire_events(self) -> None:
            self.analyze_btn.clicked.connect(self.start_analyze)
            self.normalize_btn.clicked.connect(self.start_normalize)
            self.process_btn.clicked.connect(self.start_process)
            self.batch_process_btn.clicked.connect(self.start_batch_process)
            self.batch_automaster_btn.clicked.connect(self._apply_batch_auto_master)
            self.preview_btn.clicked.connect(self._generate_preview)
            self.play_original_btn.clicked.connect(self._play_original)
            self.play_processed_btn.clicked.connect(self._play_processed)
            self.stop_preview_btn.clicked.connect(self._stop_preview)
            self.preset_combo.currentIndexChanged.connect(self._apply_preset)
            self.output_preset_combo.currentIndexChanged.connect(self._apply_output_preset)
            self.output_format_combo.currentIndexChanged.connect(self._apply_output_format)
            self.deesser_preset_combo.currentIndexChanged.connect(self._apply_deesser_preset)
            self.glue_preset_combo.currentIndexChanged.connect(self._apply_glue_preset)
            self.tone_eq_preset_combo.currentIndexChanged.connect(self._apply_tone_eq_preset)
            self.dynamic_eq_preset_combo.currentIndexChanged.connect(self._apply_dynamic_eq_preset)
            self.limiter_preset_combo.currentIndexChanged.connect(self._apply_limiter_preset)
            self.auto_master_apply_btn.clicked.connect(self._apply_auto_master)
            self.resource_profile_combo.currentTextChanged.connect(self._on_resource_profile_changed)
            if hasattr(self, "quick_master_clean_btn"):
                self.quick_master_clean_btn.clicked.connect(lambda: self._apply_quick_master_profile("clean"))
            if hasattr(self, "quick_master_vocal_btn"):
                self.quick_master_vocal_btn.clicked.connect(lambda: self._apply_quick_master_profile("vocal"))
            if hasattr(self, "quick_master_tight_btn"):
                self.quick_master_tight_btn.clicked.connect(lambda: self._apply_quick_master_profile("tight"))
            self.auto_master_style_combo.currentIndexChanged.connect(
                lambda _idx: self._apply_auto_master(emit_log=False, write_preset=False)
            )
            self.auto_master_motion_preset_combo.currentIndexChanged.connect(self._on_motion_preset_changed)
            self.auto_master_motion_profile_combo.currentIndexChanged.connect(self._on_motion_controls_changed)
            self.auto_master_motion_amount_spin.valueChanged.connect(self._on_motion_controls_changed)
            # Sincronizar ambos combos de estilo
            self.auto_master_style_combo.currentIndexChanged.connect(
                lambda idx: self.auto_master_style_combo_tab.setCurrentIndex(idx)
            )
            self.auto_master_style_combo_tab.currentIndexChanged.connect(
                lambda idx: self.auto_master_style_combo.setCurrentIndex(idx)
            )
            self.auto_master_style_combo_tab.currentIndexChanged.connect(
                lambda _idx: self._apply_auto_master(emit_log=False, write_preset=False)
            )
            self.clear_log_btn.clicked.connect(self._clear_log_view)
            self.copy_log_path_btn.clicked.connect(self._copy_log_path)
            self.log_history_load_btn.clicked.connect(self._load_selected_history_log)
            self.inspector_mts_browse_btn.clicked.connect(self._browse_inspector_mts)
            self.inspector_mts_load_btn.clicked.connect(self._load_inspector_from_current_path)
            self.inspector_mts_from_history_btn.clicked.connect(self._load_inspector_from_history_selection)
            self.log_history_table.cellDoubleClicked.connect(
                lambda _row, _col: self._load_selected_history_log()
            )
            self.auto_master_enable_process_cb.stateChanged.connect(
                lambda _state: self._show_tabs_for_mode(self.mode_combo.currentText())
            )
            self.auto_master_enable_process_cb.stateChanged.connect(
                lambda _state: self._apply_processing_density_view()
            )
            self.mode_combo.currentIndexChanged.connect(lambda: self._on_mode_changed(allow_navigation=True))
            self.auto_repair_cb.stateChanged.connect(self._on_auto_repair_toggled)
            
            # Conexiones para actualizar la cadena de procesos visualmente
            self.repair_enabled_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.mix_enabled_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.master_enabled_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.auto_repair_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.deesser_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.glue_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.stereo_width_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.stereo_dynamic_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.saturation_enable_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.saturation_enable_cb.stateChanged.connect(self._on_saturation_global_changed)
            self.saturation_per_band_cb.stateChanged.connect(self._on_saturation_per_band_changed)
            self.dynamic_eq_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            self.brickwall_cb.stateChanged.connect(lambda _: self._update_process_chain_display())
            
            # Conectar actualización de indicadores de telemetría (Paso 4)
            self.dynamic_eq_cb.stateChanged.connect(lambda _: self._update_telemetry_indicators())
            self.glue_cb.stateChanged.connect(lambda _: self._update_telemetry_indicators())
            self.stereo_dynamic_cb.stateChanged.connect(lambda _: self._update_telemetry_indicators())
            self.autogain_cb.stateChanged.connect(lambda _: self._update_telemetry_indicators())
            self.saturation_enable_cb.stateChanged.connect(lambda _: self._update_telemetry_indicators())
            self.saturation_per_band_cb.stateChanged.connect(lambda _: self._update_telemetry_indicators())
            self.brickwall_cb.stateChanged.connect(lambda _: self._update_telemetry_indicators())
            
            self.signature_save_btn.clicked.connect(self._save_signature_preset)
            self.signature_delete_btn.clicked.connect(self._delete_signature_preset)
            self.signature_preset_combo.currentIndexChanged.connect(self._load_signature_preset)
            # Presets de Mezcla personalizados
            self.mix_save_btn.clicked.connect(self._save_mix_preset)
            self.mix_delete_btn.clicked.connect(self._delete_mix_preset)
            self.mix_preset_combo.currentIndexChanged.connect(self._load_mix_preset)
            # Presets de Mastering personalizados
            self.master_save_btn.clicked.connect(self._save_master_preset)
            self.master_delete_btn.clicked.connect(self._delete_master_preset)
            self.master_preset_combo.currentIndexChanged.connect(self._load_master_preset)
            self.input_edit.editingFinished.connect(self._refresh_waveform_from_input)
            self.copy_results_btn.clicked.connect(self._copy_results_text)
            self.fade_in_spin.valueChanged.connect(self._on_fade_spin_changed)
            self.fade_out_spin.valueChanged.connect(self._on_fade_spin_changed)
            self.waveform_table.itemSelectionChanged.connect(self._on_waveform_selection_changed)
            self.waveform_fade_in_spin.valueChanged.connect(self._on_waveform_fade_changed)
            self.waveform_fade_out_spin.valueChanged.connect(self._on_waveform_fade_changed)
            self.waveform_apply_btn.clicked.connect(self._apply_waveform_override)
            self.waveform_use_global_btn.clicked.connect(self._use_global_for_selected)
            if self.fade_in_region is not None:
                self.fade_in_region.sigRegionChangeFinished.connect(self._on_fade_in_region_changed)
            if self.fade_out_region is not None:
                self.fade_out_region.sigRegionChangeFinished.connect(self._on_fade_out_region_changed)
            self._apply_preset()
            self._apply_output_preset()
            self._apply_output_format()
            self._apply_deesser_preset()
            self._apply_glue_preset()
            self._apply_tone_eq_preset()
            self._apply_dynamic_eq_preset()
            self._apply_limiter_preset()
            self._apply_auto_master(emit_log=False, write_preset=False)
            self._load_log_history()
            self._refresh_signature_presets()
            self._refresh_mix_presets()
            self._refresh_master_presets()
            self._update_waveform_global_label()
            self._refresh_waveform_tab_list()
            self._init_spectrum_canvas()  # Inicializar canvas de espectro
            self._update_process_chain_display()  # Actualizar visualización de cadena
            self._apply_processing_density_view()  # Aplicar vista compacta/avanzada inicial
            self._update_telemetry_indicators()  # Actualizar indicadores de telemetría (Paso 4)
            
            # Conexiones para el tab de Diagnóstico
            if hasattr(self, 'diagnostic_run_btn'):
                self.diagnostic_run_btn.clicked.connect(self._run_diagnostic)
            if hasattr(self, 'diagnostic_benchmark_btn'):
                self.diagnostic_benchmark_btn.clicked.connect(self._run_spectrum_benchmark)
            if hasattr(self, 'diagnostic_copy_btn'):
                self.diagnostic_copy_btn.clicked.connect(self._copy_diagnostic_to_clipboard)

        def choose_input(self) -> None:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Seleccionar WAV de entrada", "", "WAV (*.wav);;Todos los archivos (*)"
            )
            if file_path:
                self.input_edit.setText(file_path)
                if not self.output_edit.text():
                    path = pathlib.Path(file_path)
                    self.output_edit.setText(str(path.with_stem(
                        mastered_output_stem(path.stem, self.batch_suffix_edit.text())
                    )))
                self._update_single_waveform(file_path)
                self._update_waveform(file_path)
                self._refresh_waveform_tab_list()

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
            self._render_batch_table()

        def _render_batch_table(self) -> None:
            self.batch_table.setRowCount(len(self._batch_files))
            for row, audio_path in enumerate(self._batch_files):
                checkbox = QCheckBox()
                checkbox.setChecked(True)
                self.batch_table.setCellWidget(row, 0, checkbox)
                self.batch_table.setItem(row, 1, QTableWidgetItem(audio_path.name))
                self.batch_table.setItem(row, 2, QTableWidgetItem(audio_path.suffix.lower().lstrip(".")))
            self._refresh_waveform_tab_list()

        def _on_batch_files_dropped(self, dropped_paths: list[pathlib.Path]) -> None:
            files: list[pathlib.Path] = []
            for path in dropped_paths:
                if path.is_dir():
                    files.extend(
                        p for p in path.iterdir() if p.is_file() and p.suffix.lower() in INPUT_FORMATS
                    )
                elif path.is_file() and path.suffix.lower() in INPUT_FORMATS:
                    files.append(path)
            if not files:
                return

            current = {p.resolve(): p for p in self._batch_files}
            for path in files:
                current[path.resolve()] = path
            self._batch_files = sorted(current.values(), key=lambda p: p.name.lower())
            self._render_batch_table()

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
            self._clear_log_view()
            worker = AnalyzeWorker(
                input_path=input_path,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                verbose=self.verbose_cb.isChecked(),
                transparent_mode=self.transparent_cb.isChecked(),
            )
            self._apply_resource_profile()
            self._start_worker(
                worker,
                on_finished=self._handle_analyze_finished,
            )
            self._set_progress(indeterminate=True, message="Analizando...")
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
            output_path = pathlib.Path(output_text) if output_text else input_path.with_stem(
                mastered_output_stem(input_path.stem, self.batch_suffix_edit.text())
            )
            output_format = self._resolve_output_format_for_single()
            output_path = ensure_output_path(output_path, output_format)
            self.output_edit.setText(str(output_path))
            self._clear_log_view()
            if self.analyze_only_cb.isChecked():
                self.append_log("Modo 'Solo analizar' activo: no se realizará escritura de salida.")
                return
            metadata = self._collect_signature_metadata()
            if metadata is None:
                if isinstance(getattr(self, "signature_tab_index", None), int):
                    self.tabs.setCurrentIndex(self.signature_tab_index)
                return
            fade_in, fade_out = self._resolve_fades_for_path(input_path)
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
                master_limiter_enabled=self.brickwall_cb.isChecked(),
                master_limiter_mode=self.master_limiter_mode_combo.currentText(),
                master_limiter_ceiling_db=-1.0,  # True Peak ceiling por defecto
                master_limiter_release_ms=150.0,  # Release por defecto
                master_limiter_lookahead_ms=5.0,  # Lookahead por defecto
                output_sr=self._get_output_sample_rate(),
                output_bit_depth=self._get_output_bit_depth(),
                output_format=output_format,
                stereo_width=self.stereo_width_cb.isChecked(),
                deesser=self.deesser_cb.isChecked(),
                deesser_freq_hz=self.deesser_freq_spin.value(),
                deesser_intensity=self.deesser_intensity_spin.value(),
                tone_low_db=self.eq_low_spin.value(),
                sub_bass_db=self.sub_bass_spin.value(),
                tone_mid_db=self.eq_mid_spin.value(),
                tone_high_db=self.eq_high_spin.value(),
                tone_tilt_db=self.tilt_eq_spin.value(),
                band_adjust_db=self._get_dynamic_band_adjust_db(),
                band_widths=self._get_stereo_band_widths(),
                auto_band_gain=self.auto_band_gain_cb.isChecked(),
                saturation_enabled=self.saturation_enable_cb.isChecked(),
                saturation_per_band=self.saturation_per_band_cb.isChecked(),
                saturation_type=self.saturation_type_combo.currentText(),
                saturation_drive_db=self.saturation_drive_spin.value(),
                saturation_mix=self.saturation_mix_spin.value() / 100.0,
                saturation_band_drive_db=self._get_saturation_band_drive_db(),
                saturation_band_mix=self._get_saturation_band_mix(),
                process_order=self._get_process_order(),
                stereo_dynamic=self.stereo_dynamic_cb.isChecked(),
                stereo_dynamic_band_mix=self._get_stereo_dynamic_band_mix(),
                stereo_dynamic_threshold_db=self.stereo_dynamic_threshold_spin.value(),
                stereo_dynamic_ratio=self.stereo_dynamic_ratio_spin.value(),
                stereo_dynamic_attack_ms=self.stereo_dynamic_attack_spin.value(),
                stereo_dynamic_release_ms=self.stereo_dynamic_release_spin.value(),
                stereo_dynamic_mix=self.stereo_dynamic_mix_spin.value(),
                glue_enabled=self.glue_cb.isChecked(),
                glue_threshold_db=self.glue_threshold_spin.value(),
                glue_ratio=self.glue_ratio_spin.value(),
                glue_attack_ms=self.glue_attack_spin.value(),
                glue_release_ms=self.glue_release_spin.value(),
                glue_makeup_db=self.glue_makeup_spin.value(),
                limiter_ceiling_db=self.limiter_ceiling_spin.value(),
                limiter_release_ms=self.limiter_release_spin.value(),
                metadata=metadata,
                noise_reduction_level=self.noise_reduction_combo.currentText(),
                declip_level=self.declip_combo.currentText(),
                declick_level=self.declick_combo.currentText(),
                pink_noise_level=self.pink_noise_combo.currentText(),
                fade_in=fade_in,
                fade_out=fade_out,
                transparent_mode=self.transparent_cb.isChecked(),
                repair_enabled=self.repair_enabled_cb.isChecked(),
                mix_enabled=self.mix_enabled_cb.isChecked(),
                master_enabled=self.master_enabled_cb.isChecked(),
                autogain_enabled=self.autogain_cb.isChecked(),
                autogain_maxgain=self._resolve_autogain_maxgain(),
                multiband_limiter_enabled=self.multiband_limiter_cb.isChecked(),
                multiband_limiter_thresholds=self._get_multiband_limiter_thresholds(),
            )
            ai_actions = getattr(self, "_ai_audio_actions", None)
            if isinstance(ai_actions, list):
                worker._ai_audio_actions = [dict(action) for action in ai_actions]
                fingerprint = getattr(self, "_ai_source_fingerprint", None)
                if fingerprint:
                    worker._ai_source_fingerprint = fingerprint
            self._apply_resource_profile()
            self._start_worker(
                worker,
                on_finished=self._handle_normalize_finished,
            )
            self._set_progress(indeterminate=True, message="Normalizando...")
            self._set_busy(True, "Normalizando...")

        def _build_process_worker(
            self,
            *,
            input_path: pathlib.Path,
            output_path: pathlib.Path,
            output_format: str,
            metadata: dict[str, str],
            fade_in: float,
            fade_out: float,
            pre_analysis_stats: dict[str, float] | None = None,
            pre_analysis_band_stats: dict[str, float] | None = None,
            pre_analysis_voice_rms: float | None = None,
        ) -> ProcessWorker:
            worker = ProcessWorker(
                input_path=input_path,
                output_path=output_path,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                overwrite=self.overwrite_cb.isChecked(),
                verbose=self.verbose_cb.isChecked(),
                dynamic_eq=self.dynamic_eq_cb.isChecked(),
                master_limiter_enabled=self.brickwall_cb.isChecked(),
                master_limiter_mode=self.master_limiter_mode_combo.currentText(),
                master_limiter_ceiling_db=-1.0,  # True Peak ceiling por defecto
                master_limiter_release_ms=150.0,  # Release por defecto
                master_limiter_lookahead_ms=5.0,  # Lookahead por defecto
                analyze_only=self.analyze_only_cb.isChecked(),
                output_sr=self._get_output_sample_rate(),
                output_bit_depth=self._get_output_bit_depth(),
                output_format=output_format,
                stereo_width=self.stereo_width_cb.isChecked(),
                loudness_preset=self.preset_combo.currentText(),
                output_preset=self.output_preset_combo.currentText(),
                deesser=self.deesser_cb.isChecked(),
                deesser_freq_hz=self.deesser_freq_spin.value(),
                deesser_intensity=self.deesser_intensity_spin.value(),
                tone_low_db=self.eq_low_spin.value(),
                sub_bass_db=self.sub_bass_spin.value(),
                tone_mid_db=self.eq_mid_spin.value(),
                tone_high_db=self.eq_high_spin.value(),
                tone_tilt_db=self.tilt_eq_spin.value(),
                band_adjust_db=self._get_dynamic_band_adjust_db(),
                band_widths=self._get_stereo_band_widths(),
                auto_band_gain=self.auto_band_gain_cb.isChecked(),
                saturation_enabled=self.saturation_enable_cb.isChecked(),
                saturation_per_band=self.saturation_per_band_cb.isChecked(),
                saturation_type=self.saturation_type_combo.currentText(),
                saturation_drive_db=self.saturation_drive_spin.value(),
                saturation_mix=self.saturation_mix_spin.value() / 100.0,
                saturation_band_drive_db=self._get_saturation_band_drive_db(),
                saturation_band_mix=self._get_saturation_band_mix(),
                process_order=self._get_process_order(),
                stereo_dynamic=self.stereo_dynamic_cb.isChecked(),
                stereo_dynamic_band_mix=self._get_stereo_dynamic_band_mix(),
                stereo_dynamic_threshold_db=self.stereo_dynamic_threshold_spin.value(),
                stereo_dynamic_ratio=self.stereo_dynamic_ratio_spin.value(),
                stereo_dynamic_attack_ms=self.stereo_dynamic_attack_spin.value(),
                stereo_dynamic_release_ms=self.stereo_dynamic_release_spin.value(),
                stereo_dynamic_mix=self.stereo_dynamic_mix_spin.value(),
                glue_enabled=self.glue_cb.isChecked(),
                glue_threshold_db=self.glue_threshold_spin.value(),
                glue_ratio=self.glue_ratio_spin.value(),
                glue_attack_ms=self.glue_attack_spin.value(),
                glue_release_ms=self.glue_release_spin.value(),
                glue_makeup_db=self.glue_makeup_spin.value(),
                limiter_ceiling_db=self.limiter_ceiling_spin.value(),
                limiter_release_ms=self.limiter_release_spin.value(),
                metadata=metadata,
                noise_reduction_level=self.noise_reduction_combo.currentText(),
                declip_level=self.declip_combo.currentText(),
                declick_level=self.declick_combo.currentText(),
                pink_noise_level=self.pink_noise_combo.currentText(),
                fade_in=fade_in,
                fade_out=fade_out,
                transparent_mode=self.transparent_cb.isChecked(),
                headroom_db=self.input_gain_spin.value(),
                repair_enabled=self.repair_enabled_cb.isChecked(),
                mix_enabled=self.mix_enabled_cb.isChecked(),
                master_enabled=self.master_enabled_cb.isChecked(),
                autogain_enabled=self.autogain_cb.isChecked(),
                autogain_maxgain=self._resolve_autogain_maxgain(),
                multiband_limiter_enabled=self.multiband_limiter_cb.isChecked(),
                multiband_limiter_thresholds=self._get_multiband_limiter_thresholds(),
                pre_analysis_stats=pre_analysis_stats,
                pre_analysis_band_stats=pre_analysis_band_stats,
                pre_analysis_voice_rms=pre_analysis_voice_rms,
            )
            ai_actions = getattr(self, "_ai_audio_actions", None)
            if isinstance(ai_actions, list):
                worker._ai_audio_actions = [dict(action) for action in ai_actions]
                fingerprint = getattr(self, "_ai_source_fingerprint", None)
                if fingerprint:
                    worker._ai_source_fingerprint = fingerprint
            return worker

        def _start_process_worker_from_current_state(
            self,
            pre_analysis_stats: dict[str, float] | None = None,
            pre_analysis_band_stats: dict[str, float] | None = None,
            pre_analysis_voice_rms: float | None = None,
        ) -> None:
            input_path = pathlib.Path(self.input_edit.text().strip())
            if self.dynamic_eq_cb.isChecked() and self.analyze_only_cb.isChecked():
                self.append_log("Modo 'Solo analizar' activo: se omitirá la normalización aunque esté activado el control dinámico.")
            output_text = self.output_edit.text().strip()
            output_path = (
                pathlib.Path(output_text)
                if output_text
                else input_path.with_stem(
                    mastered_output_stem(input_path.stem, self.batch_suffix_edit.text())
                )
            )
            output_format = self._resolve_output_format_for_single()
            output_path = ensure_output_path(output_path, output_format)
            self.output_edit.setText(str(output_path))
            metadata: dict[str, str] = {}
            if not self.analyze_only_cb.isChecked():
                metadata = self._collect_signature_metadata()
            fade_in, fade_out = self._resolve_fades_for_path(input_path)
            worker = self._build_process_worker(
                input_path=input_path,
                output_path=output_path,
                output_format=output_format,
                metadata=metadata,
                fade_in=fade_in,
                fade_out=fade_out,
                pre_analysis_stats=pre_analysis_stats,
                pre_analysis_band_stats=pre_analysis_band_stats,
                pre_analysis_voice_rms=pre_analysis_voice_rms,
            )
            self._apply_resource_profile()
            self._start_worker(
                worker,
                on_finished=self._handle_process_finished,
            )
            self._set_progress(indeterminate=True, message="Procesando...")
            self._set_busy(True, "Procesando...")

        def _handle_auto_master_analysis_finished(
            self,
            analyzed_input: pathlib.Path,
            characteristics: object,
            recommendations: object,
            spectrum_data: object,
        ) -> None:
            current_input = pathlib.Path(self.input_edit.text().strip())
            if current_input != analyzed_input:
                self.append_log("Auto-Master inteligente cancelado: cambió el archivo de entrada durante el análisis.")
                return
            if isinstance(characteristics, dict):
                try:
                    characteristics = AudioCharacteristics(
                        band_stats=characteristics.get("band_stats", {}) if isinstance(characteristics.get("band_stats", {}), dict) else {},
                        voice_rms=characteristics.get("voice_rms", None),
                        clipping_info=characteristics.get("clipping_info", None),
                        noise_info=characteristics.get("noise_info", None),
                        stereo_info=characteristics.get("stereo_info", None),
                        band_peaks=characteristics.get("band_peaks", None),
                        silence_info=characteristics.get("silence_info", None),
                        loudness_metrics=characteristics.get("loudness_metrics", None),
                        tempo_info=characteristics.get("tempo_info", None),
                    )
                except Exception:
                    pass
            self.append_log("🎯 Auto-Master inteligente completado. Aplicando configuración...")
            self._apply_auto_master(
                emit_log=True,
                write_preset=False,
                analysis_result=(characteristics, recommendations, spectrum_data),
            )
            pre_analysis_stats = None
            pre_analysis_band_stats = None
            pre_analysis_voice_rms = None
            try:
                if hasattr(characteristics, "lufs"):
                    lufs = float(getattr(characteristics, "lufs", -70.0))
                    pre_analysis_stats = {
                        "input_i": lufs,
                        "input_tp": float(getattr(characteristics, "true_peak", -70.0)),
                        "input_lra": float(getattr(characteristics, "lra", 0.0)),
                        "input_thresh": lufs - 10.0,
                        "target_offset": self.target_spin.value() - lufs,
                    }
                if hasattr(characteristics, "band_stats") and isinstance(characteristics.band_stats, dict):
                    pre_analysis_band_stats = dict(characteristics.band_stats)
                voice_rms = getattr(characteristics, "voice_rms", None)
                if isinstance(voice_rms, (float, int)):
                    pre_analysis_voice_rms = float(voice_rms)
            except Exception:
                pre_analysis_stats = None
                pre_analysis_band_stats = None
                pre_analysis_voice_rms = None
            self._start_process_worker_from_current_state(
                pre_analysis_stats=pre_analysis_stats,
                pre_analysis_band_stats=pre_analysis_band_stats,
                pre_analysis_voice_rms=pre_analysis_voice_rms,
            )

        def start_process(self) -> None:
            input_path = pathlib.Path(self.input_edit.text().strip())
            if not input_path.exists():
                self._show_error("Selecciona un archivo WAV de entrada válido.")
                return

            self._clear_log_view()

            current_mode = self.mode_combo.currentText()
            if current_mode.startswith("Auto-Master"):
                self.append_log("🎯 Modo Auto-Master: aplicando configuración automática...")
                if hasattr(self, "auto_master_intelligent_cb") and self.auto_master_intelligent_cb.isChecked():
                    self._set_progress(indeterminate=True, message="Analizando Auto-Master...")
                    self._set_busy(True, "Analizando Auto-Master...")
                    analysis_worker = AutoMasterAnalysisWorker(
                        input_path=input_path,
                        verbose=self.verbose_cb.isChecked(),
                    )
                    self._start_worker(
                        analysis_worker,
                        on_finished=lambda characteristics, recommendations, spectrum_data: self._handle_auto_master_analysis_finished(
                            input_path,
                            characteristics,
                            recommendations,
                            spectrum_data,
                        ),
                    )
                    return
                self._apply_auto_master(emit_log=True, write_preset=False)

            self._start_process_worker_from_current_state()

        def start_batch_process(self) -> None:
            input_dir_text = self.batch_input_edit.text().strip()
            if not self._batch_files:
                if not input_dir_text:
                    self._show_error("Selecciona una carpeta de entrada para el lote o arrastra archivos a la lista.")
                    return
                input_dir = pathlib.Path(input_dir_text)
                if not input_dir.exists():
                    self._show_error("La carpeta de entrada no existe.")
                    return
                self.refresh_batch_table()
            elif input_dir_text:
                input_dir = pathlib.Path(input_dir_text)
                if not input_dir.exists():
                    self._show_error("La carpeta de entrada no existe.")
                    return
            selected_files = self._get_selected_batch_files()
            if not selected_files:
                self._show_error("No hay archivos seleccionados para procesar.")
                return
            output_dir_text = self.batch_output_edit.text().strip()
            if output_dir_text:
                output_dir = pathlib.Path(output_dir_text)
                if not output_dir.exists():
                    self._show_error("La carpeta de salida no existe.")
                    return
            self._clear_log_view()

            # En modo Auto-Master (Lote), aplicar auto-configuración antes de procesar
            current_mode = self.mode_combo.currentText()
            if current_mode == "Auto-Master (Lote)":
                self.append_log(
                    "🎯 Modo Auto-Master (Lote): procesamiento secuencial por tema "
                    "(sin preanálisis global de lote)."
                )
                _ia_providers_preview, ia_status_preview = self._build_auto_master_ia_providers()
                if ia_status_preview == "off":
                    self.append_log("Master asistido por IA: OFF (switch desactivado).")
                elif not _ia_providers_preview:
                    self.append_log(f"Master asistido por IA: {ia_status_preview}; se usará motor local.")
                else:
                    self.append_log(f"Master asistido por IA: {ia_status_preview}.")

            self._start_batch_process_worker(selected_files)

        def _start_batch_process_worker(self, selected_files: list[pathlib.Path]) -> None:
            metadata = self._collect_signature_metadata()
            output_dir_text = self.batch_output_edit.text().strip()
            output_dir: pathlib.Path | None = None
            if output_dir_text:
                output_dir = pathlib.Path(output_dir_text)
            suffix = self.batch_suffix_edit.text().strip() or (metadata or {}).get("artist", "O-M-A")
            self._set_progress(current=0, total=len(selected_files), message="Procesando lote...")
            output_format = self._get_output_format()
            ia_providers, ia_status = self._build_auto_master_ia_providers()
            auto_master_style = self._resolve_standard_auto_master_style(self.auto_master_style_combo.currentText())
            minimal_lra, minimal_crest = self._get_minimal_processing_thresholds()
            motion_profile, motion_amount = self._get_motion_preferences()
            block_mode = self.auto_master_block_mode_cb.isChecked()
            if ia_status != "off":
                self.append_log(f"Master asistido por IA: {ia_status}")

            # No omitir archivos automáticamente en lote: si ya existen salidas,
            # pedir confirmación explícita para sobrescribir.
            if not self.overwrite_cb.isChecked():
                existing_outputs: list[pathlib.Path] = []
                for audio_path in selected_files:
                    out_dir = output_dir if output_dir else audio_path.parent
                    output_base = out_dir / mastered_output_stem(audio_path.stem, suffix)
                    fmt = output_format or audio_path.suffix.lstrip(".")
                    candidate = ensure_output_path(output_base, fmt)
                    if candidate.exists():
                        existing_outputs.append(candidate)
                if existing_outputs:
                    sample = "\n".join(f"• {p.name}" for p in existing_outputs[:5])
                    if len(existing_outputs) > 5:
                        sample += f"\n• ... y {len(existing_outputs) - 5} más"
                    answer = QMessageBox.question(
                        self,
                        "Archivos de salida existentes",
                        (
                            f"Se encontraron {len(existing_outputs)} archivo(s) de salida ya existentes.\n\n"
                            f"{sample}\n\n"
                            "¿Querés sobrescribirlos?"
                        ),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if answer == QMessageBox.StandardButton.Yes:
                        self.overwrite_cb.setChecked(True)
                    else:
                        self.append_log("Lote cancelado por el usuario: no se sobrescribieron archivos existentes.")
                        self._set_progress(current=0, total=len(selected_files), message="Lote cancelado.")
                        return

            worker_kwargs = dict(
                files=selected_files,
                output_dir=output_dir,
                suffix=suffix,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                overwrite=self.overwrite_cb.isChecked(),
                verbose=self.verbose_cb.isChecked(),
                dynamic_eq=self.dynamic_eq_cb.isChecked(),
                master_limiter_enabled=self.brickwall_cb.isChecked(),
                master_limiter_mode=self.master_limiter_mode_combo.currentText(),
                master_limiter_ceiling_db=-1.0,
                master_limiter_release_ms=150.0,
                master_limiter_lookahead_ms=5.0,
                output_sr=self._get_output_sample_rate(),
                output_bit_depth=self._get_output_bit_depth(),
                output_format=output_format,
                stereo_width=self.stereo_width_cb.isChecked(),
                loudness_preset=self.preset_combo.currentText(),
                output_preset=self.output_preset_combo.currentText(),
                deesser=self.deesser_cb.isChecked(),
                deesser_freq_hz=self.deesser_freq_spin.value(),
                deesser_intensity=self.deesser_intensity_spin.value(),
                tone_low_db=self.eq_low_spin.value(),
                sub_bass_db=self.sub_bass_spin.value(),
                tone_mid_db=self.eq_mid_spin.value(),
                tone_high_db=self.eq_high_spin.value(),
                tone_tilt_db=self.tilt_eq_spin.value(),
                band_adjust_db=self._get_dynamic_band_adjust_db(),
                band_widths=self._get_stereo_band_widths(),
                auto_band_gain=self.auto_band_gain_cb.isChecked(),
                saturation_enabled=self.saturation_enable_cb.isChecked(),
                saturation_per_band=self.saturation_per_band_cb.isChecked(),
                saturation_type=self.saturation_type_combo.currentText(),
                saturation_drive_db=self.saturation_drive_spin.value(),
                saturation_mix=self.saturation_mix_spin.value() / 100.0,
                saturation_band_drive_db=self._get_saturation_band_drive_db(),
                saturation_band_mix=self._get_saturation_band_mix(),
                process_order=self._get_process_order(),
                stereo_dynamic=self.stereo_dynamic_cb.isChecked(),
                stereo_dynamic_band_mix=self._get_stereo_dynamic_band_mix(),
                stereo_dynamic_threshold_db=self.stereo_dynamic_threshold_spin.value(),
                stereo_dynamic_ratio=self.stereo_dynamic_ratio_spin.value(),
                stereo_dynamic_attack_ms=self.stereo_dynamic_attack_spin.value(),
                stereo_dynamic_release_ms=self.stereo_dynamic_release_spin.value(),
                stereo_dynamic_mix=self.stereo_dynamic_mix_spin.value(),
                glue_enabled=self.glue_cb.isChecked(),
                glue_threshold_db=self.glue_threshold_spin.value(),
                glue_ratio=self.glue_ratio_spin.value(),
                glue_attack_ms=self.glue_attack_spin.value(),
                glue_release_ms=self.glue_release_spin.value(),
                glue_makeup_db=self.glue_makeup_spin.value(),
                limiter_ceiling_db=self.limiter_ceiling_spin.value(),
                limiter_release_ms=self.limiter_release_spin.value(),
                metadata=metadata,
                noise_reduction_level=self.noise_reduction_combo.currentText(),
                declip_level=self.declip_combo.currentText(),
                declick_level=self.declick_combo.currentText(),
                pink_noise_level=self.pink_noise_combo.currentText(),
                fade_in=self.fade_in_spin.value(),
                fade_out=self.fade_out_spin.value(),
                fade_overrides=self.fade_overrides,
                transparent_mode=self.transparent_cb.isChecked(),
                headroom_db=self.input_gain_spin.value(),
                repair_enabled=self.repair_enabled_cb.isChecked(),
                mix_enabled=self.mix_enabled_cb.isChecked(),
                master_enabled=self.master_enabled_cb.isChecked(),
                autogain_enabled=self.autogain_cb.isChecked(),
                autogain_maxgain=self._resolve_autogain_maxgain(),
                multiband_limiter_enabled=self.multiband_limiter_cb.isChecked(),
                multiband_limiter_thresholds=self._get_multiband_limiter_thresholds(),
                checkpoint_path=self.batch_checkpoint_path,
                resume_completed_files=set(),
                global_adjustments=getattr(self, "_last_auto_master_adjustments", None),
                ia_providers=ia_providers,
                ia_status=ia_status,
                auto_master_style=auto_master_style,
                minimal_lra_threshold=minimal_lra,
                minimal_crest_threshold=minimal_crest,
                motion_profile_preference=motion_profile,
                motion_amount=motion_amount,
                block_mode=block_mode,
            )

            # La ruta Python garantiza decisión IA por pista y el único fallback
            # permitido (SUNO Clásico). El backend CLI legacy no conoce ese contrato.
            use_cli_batch_worker = False
            if use_cli_batch_worker:
                payload = dict(worker_kwargs)
                for secret_key in ("ia_providers", "ia_status"):
                    payload.pop(secret_key, None)
                payload["files"] = [str(p) for p in selected_files]
                payload["output_dir"] = str(output_dir) if output_dir else None
                payload["checkpoint_path"] = str(self.batch_checkpoint_path)
                payload["fade_overrides"] = {
                    str(k): [float(v[0]), float(v[1])] for k, v in (self.fade_overrides or {}).items()
                }
                worker = CliBatchWorker(payload=payload)
                self.append_log("BatchWorker backend: CLI (SpASM job orchestration).")
            else:
                worker = BatchWorker(**worker_kwargs)
                if ia_providers:
                    self.append_log("BatchWorker backend: Python (IA por tema activa).")
            self._apply_resource_profile()
            self._start_worker(
                worker,
                on_finished=self._handle_batch_finished,
            )
            self._set_busy(True, "Procesando lote...")

        def _selection_signature(self, files: list[pathlib.Path]) -> str:
            return "|".join(sorted(str(p.resolve()) for p in files))

        def _save_batch_checkpoint_selection(self, selected_files: list[pathlib.Path]) -> None:
            payload = {
                "selection_signature": self._selection_signature(selected_files),
                "completed_files": [],
            }
            try:
                self.batch_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                with self.batch_checkpoint_path.open("w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False, indent=2)
            except Exception:
                pass

        def _load_batch_checkpoint_for_selection(self, selected_files: list[pathlib.Path]) -> set[str]:
            if not self.batch_checkpoint_path.exists():
                return set()
            try:
                with self.batch_checkpoint_path.open("r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                if not isinstance(payload, dict):
                    return set()
                if payload.get("selection_signature") != self._selection_signature(selected_files):
                    return set()
                completed = payload.get("completed_files", [])
                if not isinstance(completed, list):
                    return set()
                return {str(item) for item in completed if isinstance(item, str)}
            except Exception:
                return set()

        def _clear_batch_checkpoint(self) -> None:
            try:
                if self.batch_checkpoint_path.exists():
                    self.batch_checkpoint_path.unlink()
            except Exception:
                pass

        def _start_worker(self, worker: QObject, on_finished) -> None:
            thread = QThread(self)
            worker.moveToThread(thread)
            self._current_worker = worker
            self._worker_finish_handler = on_finished

            def handle_error(message: str) -> None:
                self._show_error(message)
                thread.quit()

            def handle_success(*args) -> None:
                try:
                    on_finished(*args)
                except Exception as exc:
                    self._show_error(str(exc))
                finally:
                    thread.quit()

            if hasattr(worker, "finished"):
                cast(Any, worker).finished.connect(
                    self._handle_worker_finished, Qt.ConnectionType.QueuedConnection
                )
            if hasattr(worker, "error"):
                cast(Any, worker).error.connect(
                    self._handle_worker_error, Qt.ConnectionType.QueuedConnection
                )
            if hasattr(worker, "progress"):
                cast(Any, worker).progress.connect(
                    self._handle_worker_progress, Qt.ConnectionType.QueuedConnection
                )
            if hasattr(worker, "processing_progress"):
                cast(Any, worker).processing_progress.connect(
                    self._handle_worker_processing_progress, Qt.ConnectionType.QueuedConnection
                )
            thread.finished.connect(
                lambda worker_ref=worker, thread_ref=thread: self._cleanup_worker(worker_ref, thread_ref),
                Qt.ConnectionType.QueuedConnection,
            )
            thread.started.connect(worker.run)  # type: ignore[arg-type]
            self._current_thread = thread
            thread.start()

        def _cleanup_worker(self, worker: QObject | None = None, thread: QThread | None = None) -> None:
            if worker is not None:
                worker.deleteLater()
            if thread is not None:
                thread.deleteLater()
            if worker is self._current_worker:
                self._current_worker = None
            if thread is self._current_thread:
                self._current_thread = None
            if worker is self._current_worker or thread is self._current_thread:
                self._worker_finish_handler = None
            if self._current_worker is None and self._current_thread is None:
                self._worker_finish_handler = None
                self._set_busy(False)

        def _handle_worker_finished(self, *args) -> None:
            try:
                handler = self._worker_finish_handler
                if handler is not None:
                    handler(*args)
            except Exception as exc:
                self._show_error(str(exc))
            finally:
                thread = self._current_thread
                if thread is not None:
                    thread.quit()

        def _handle_worker_error(self, message: str) -> None:
            self._show_error(message)
            thread = self._current_thread
            if thread is not None:
                thread.quit()

        def _cancel_current_process(self) -> None:
            worker = self._current_worker
            thread = self._current_thread
            if worker is not None and hasattr(worker, "cancel"):
                try:
                    cast(Any, worker).cancel()
                except Exception:
                    pass
            from logic_backend import cancel_active_spasm_call
            spasm_cancelled = cancel_active_spasm_call()
            cancelled = cancel_running_ffmpeg_processes()
            msg = f"Cancelación solicitada. FFmpeg: {cancelled}, SpASM: {spasm_cancelled}."
            self.append_log(msg)
            self.progress_popup_cancel_btn.setEnabled(False)

            # Fallback duro: si el hilo no responde en unos segundos, forzar terminación.
            def _force_stop_if_needed() -> None:
                running_thread = self._current_thread
                if running_thread is None:
                    self.progress_popup_cancel_btn.setEnabled(True)
                    return
                is_running = bool(getattr(running_thread, "isRunning", lambda: False)())
                if not is_running:
                    self.progress_popup_cancel_btn.setEnabled(True)
                    return
                self.append_log("Cancelación forzada: terminando hilo de trabajo no responsivo.")
                try:
                    cast(Any, running_thread).terminate()
                except Exception:
                    pass
                try:
                    cast(Any, running_thread).wait(1500)
                except Exception:
                    pass
                self._set_busy(False)
                self.progress_popup_cancel_btn.setEnabled(True)

            if thread is not None and bool(getattr(thread, "isRunning", lambda: False)()):
                QTimer.singleShot(2500, _force_stop_if_needed)
            else:
                self.progress_popup_cancel_btn.setEnabled(True)

        def _copy_progress_popup_log(self) -> None:
            QApplication.clipboard().setText(self.progress_popup_log.toPlainText())
            self.append_log("Log del popup copiado al portapapeles.")

        def _update_bc_char_count(self) -> None:
            remaining = 1000 - len(self.bc_release_msg_edit.toPlainText())
            self.bc_release_chars.setText("%d caracteres restantes" % remaining)
            if remaining < 0:
                self.bc_release_chars.setStyleSheet("color: #ffffff; font-size: 11px;")
            else:
                self.bc_release_chars.setStyleSheet("color: #ffffff; font-size: 11px;")

        def _extract_title_from_file(self) -> None:
            """Extrae el título del track desde el nombre del archivo .wav de entrada."""
            input_path = self.input_edit.text().strip()
            if input_path:
                path = pathlib.Path(input_path)
                name = path.stem
                # Limpiar sufijos comunes
                for suffix in ["_processed", "_master", "_final", "_mix"]:
                    if name.endswith(suffix):
                        name = name[:-len(suffix)]
                self.ia_title_edit.setText(name)
                self.append_log("📂 Título extraído: %s" % name)

        def _on_api_keys_changed(self) -> None:
            sender = self.sender()
            if sender is self.ia_api_key_edit:
                self._set_api_key_text(self.suno_deepseek_key_edit, self.ia_api_key_edit.text())
            elif sender is self.suno_deepseek_key_edit:
                self._set_api_key_text(self.ia_api_key_edit, self.suno_deepseek_key_edit.text())
            elif sender is self.ia_nvidia_key_edit:
                self._set_api_key_text(self.suno_nvidia_key_edit, self.ia_nvidia_key_edit.text())
            elif sender is self.suno_nvidia_key_edit:
                self._set_api_key_text(self.ia_nvidia_key_edit, self.suno_nvidia_key_edit.text())
            self._update_api_status(persist=True)

        def _set_api_key_text(self, widget: QLineEdit, value: str) -> None:
            widget.blockSignals(True)
            try:
                widget.setText(value)
            finally:
                widget.blockSignals(False)

        def _sync_auto_master_ai_assist(self, checked: bool) -> None:
            for widget in (
                getattr(self, "auto_master_ai_assist_cb", None),
                getattr(self, "auto_master_ai_assist_cb_tab", None),
            ):
                if widget is not None and widget.isChecked() != checked:
                    widget.blockSignals(True)
                    try:
                        widget.setChecked(checked)
                    finally:
                        widget.blockSignals(False)

        def _build_auto_master_ia_providers(self) -> tuple[list[dict], str]:
            nvidia_key = self.ia_nvidia_key_edit.text().strip() or self.suno_nvidia_key_edit.text().strip()
            deepseek_key = self.ia_api_key_edit.text().strip() or self.suno_deepseek_key_edit.text().strip()
            providers = _bok_build_providers(
                nvidia_key=nvidia_key,
                nvidia_on=bool(nvidia_key) and not deepseek_key.startswith("sk-"),
                deepseek_key=deepseek_key,
                deepseek_on=bool(deepseek_key),
            )
            if not providers:
                return [], "sin API key valida"
            providers.sort(
                key=lambda provider: 0
                if "deepseek" in str(provider.get("model", "")).lower()
                else 1
            )

            names = []
            for provider in providers:
                model = str(provider.get("model", ""))
                model_lower = model.lower()
                if "deepseek" in model_lower:
                    names.append("DeepSeek")
                elif "nvidia" in model_lower or "nemotron" in model_lower:
                    names.append("NVIDIA")
                else:
                    names.append(model or "custom")
            return providers, ", ".join(names)

        def _update_api_status(self, persist: bool = False) -> None:
            ds = self.suno_deepseek_key_edit.text().strip() or self.ia_api_key_edit.text().strip()
            nv = self.suno_nvidia_key_edit.text().strip() or self.ia_nvidia_key_edit.text().strip()
            if persist:
                save_api_keys({"deepseek": ds, "nvidia": nv})
            if nv.startswith("nvapi-"):
                text = "✅ NVIDIA NIM — generación real (Llama 3.1 Nemotron 70B)"
                style = "color: #ffffff; font-size: 11px;"
            elif ds.startswith("sk-"):
                text = "✅ DeepSeek API — generación real"
                style = "color: #ffffff; font-size: 11px;"
            else:
                text = "🔒 Sin API key — usará templates"
                style = "color: #ffffff; font-size: 11px;"
            self.ia_api_status.setText(text)
            self.ia_api_status.setStyleSheet(style)
            self.suno_api_status_label.setText(text)
            self.suno_api_status_label.setStyleSheet(style)

        def _call_deepseek(self, system_prompt: str, user_prompt: str) -> str | None:
            from bandcamp_bok import call_ai
            return call_ai(
                self.ia_nvidia_key_edit.text().strip(),
                self.ia_api_key_edit.text().strip(),
                system_prompt, user_prompt
            )

        def _load_suno_dataset_records(self, dataset_path_text: str) -> list[dict[str, Any]]:
            """Carga registros JSONL de Suno desde archivo o carpeta."""
            dataset_path = pathlib.Path(dataset_path_text.strip() or "dataset/suno.jsonl")
            if not dataset_path.is_absolute():
                dataset_path = pathlib.Path.cwd() / dataset_path
            if dataset_path.is_dir():
                files = sorted(dataset_path.glob("*.jsonl"))
            else:
                files = [dataset_path]
            records: list[dict[str, Any]] = []
            errors: list[str] = []
            for path in files:
                if not path.exists():
                    errors.append(f"No existe: {path}")
                    continue
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        for line_no, line in enumerate(handle, 1):
                            raw = line.strip()
                            if not raw:
                                continue
                            try:
                                item = json.loads(raw)
                            except json.JSONDecodeError as exc:
                                errors.append(f"{path}:{line_no}: {exc}")
                                continue
                            if isinstance(item, dict) and str(item.get("text", "")).strip():
                                records.append(item)
                except OSError as exc:
                    errors.append(f"{path}: {exc}")
            if errors:
                self.append_log("⚠️ Dataset SUNO: " + " | ".join(errors[:3]))
            return records

        def _select_suno_dataset_context(self, records: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
            """Selecciona fragmentos del dataset por coincidencia simple de tokens."""
            stopwords = {
                "the", "and", "for", "with", "that", "this", "your", "you", "una", "para",
                "con", "del", "los", "las", "que", "por", "and", "music", "style", "prompt",
            }
            normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in query)
            tokens = {token for token in normalized.split() if len(token) > 2 and token not in stopwords}
            preferred = {"prompt", "lyrics", "style", "exclude", "custom", "song", "studio", "create"}
            tokens.update(preferred)
            scored: list[tuple[int, dict[str, Any]]] = []
            for record in records:
                haystack = " ".join(
                    str(record.get(key, ""))
                    for key in ("section_title", "topic", "intent", "text")
                ).lower()
                score = sum(1 for token in tokens if token in haystack)
                title = str(record.get("section_title", "")).lower()
                if "prompt" in title or "lyrics" in title or "style" in title:
                    score += 4
                if str(record.get("intent", "")) in {"how_to", "explanation"}:
                    score += 1
                if score > 0:
                    scored.append((score, record))
            scored.sort(key=lambda item: item[0], reverse=True)
            if scored:
                return [record for _score, record in scored[:8]]
            return records[:8]

        def _build_suno_fallback_prompts(self, context: dict[str, str], dataset_context: list[dict[str, Any]]) -> dict[str, str]:
            """Fallback local cuando no hay API key o la API no responde."""
            title = context["title"] or "Untitled"
            language = context["language"]
            theme = context["theme"] or "personal transformation and emotional release"
            mood = context["mood"] or "nocturnal, intimate"
            structure = context["structure"] or "[Verse] [Chorus] [Bridge] [Outro]"
            doc_titles = []
            for item in dataset_context[:3]:
                section = str(item.get("section_title", "")).strip()
                if section and section not in doc_titles:
                    doc_titles.append(section)
            doc_note = ", ".join(doc_titles) if doc_titles else "Suno custom prompt guidance"
            return {
                "lyrics_prompt": (
                    f"Write original {language} lyrics for a song titled \"{title}\". "
                    f"Theme: {theme}. Mood: {mood}. Structure: {structure}. "
                    "Use clear section tags, strong imagery, singable phrasing, and avoid quoting existing songs. "
                    f"Dataset guidance considered: {doc_note}."
                ),
                "style_prompt": (
                    f"{mood}, {structure}, modern electronic song, polished production, emotional vocal delivery, "
                    "club-ready groove, clean arrangement, strong chorus, detailed atmosphere"
                ),
                "exclude_styles": (
                    "low quality audio, muddy mix, harsh distortion, off-key vocals, random genre switching, "
                    "spoken ads, parody, copyrighted artist imitation, overly long intro"
                ),
            }

        def _parse_suno_generation_response(self, response: str) -> dict[str, str] | None:
            """Parsea respuesta JSON estricta de la IA."""
            text = response.strip()
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return None
            if not isinstance(parsed, dict):
                return None
            result = {
                "lyrics_prompt": str(parsed.get("lyrics_prompt", "")).strip(),
                "style_prompt": str(parsed.get("style_prompt", "")).strip(),
                "exclude_styles": str(parsed.get("exclude_styles", "")).strip(),
            }
            if not any(result.values()):
                return None
            return result

        def _get_suno_prompt_context(self) -> dict[str, str]:
            return {
                "title": self.suno_track_title_edit.text().strip(),
                "language": self.suno_language_combo.currentText().strip(),
                "theme": self.suno_theme_edit.text().strip(),
                "mood": self.suno_mood_edit.text().strip(),
                "structure": self.suno_structure_edit.text().strip(),
                "music_style": self.suno_music_style_combo.currentText().strip(),
                "style_instructions": self.suno_style_instructions_edit.toPlainText().strip(),
                "lyrics_instructions": self.suno_lyrics_instructions_edit.toPlainText().strip(),
                "exclude_instructions": self.suno_exclude_instructions_edit.toPlainText().strip(),
                "style_prompt": self.suno_style_prompt_edit.toPlainText().strip(),
            }

        def _load_suno_generation_context(self, context: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str] | None:
            records = self._load_suno_dataset_records(self.suno_dataset_path_edit.text())
            if not records:
                self.suno_dataset_status_label.setText("No se pudieron cargar registros JSONL del dataset.")
                self.suno_dataset_status_label.setStyleSheet("color: #ffffff; font-size: 11px;")
                self._show_error("No se pudieron cargar registros JSONL del dataset SUNO.")
                return None
            query = " ".join(context.values())
            selected = self._select_suno_dataset_context(records, query)
            excerpts = []
            for item in selected:
                text = str(item.get("text", "")).replace("\n", " ").strip()
                excerpts.append(
                    "SECTION: {section}\nSOURCE: {source}\nTEXT: {text}".format(
                        section=str(item.get("section_title", "")),
                        source=str(item.get("source", "")),
                        text=text[:900],
                    )
                )
            return records, selected, "\n\n---\n\n".join(excerpts)

        def _call_suno_field_ai(
            self,
            field_name: str,
            context: dict[str, str],
            dataset_context: str,
            rules: str,
            fallback: str,
        ) -> tuple[str, str]:
            nvidia_key = self.suno_nvidia_key_edit.text().strip()
            deepseek_key = self.suno_deepseek_key_edit.text().strip()
            if nvidia_key or deepseek_key:
                from bandcamp_bok import call_ai
                system_prompt = (
                    "You are a Suno prompt engineer. Use the provided Suno documentation dataset excerpts "
                    "as source of truth. Return only the requested text, no markdown, no explanation."
                )
                user_prompt = (
                    "Track context:\n"
                    f"Title: {context['title']}\n"
                    f"Language: {context['language']}\n"
                    f"Music style: {context['music_style']}\n"
                    f"Mood: {context['mood']}\n"
                    f"Structure/style idea: {context['structure']}\n"
                    f"Theme: {context['theme']}\n"
                    f"Style instructions: {context['style_instructions']}\n"
                    f"Lyrics instructions: {context['lyrics_instructions']}\n"
                    f"Exclude instructions: {context['exclude_instructions']}\n"
                    f"Current style prompt: {context['style_prompt']}\n\n"
                    "Dataset excerpts:\n"
                    f"{dataset_context}\n\n"
                    f"Generate only: {field_name}\n"
                    f"Rules:\n{rules}"
                )
                ai_response = call_ai(
                    nvidia_key,
                    deepseek_key,
                    system_prompt,
                    user_prompt,
                    max_tokens=500,
                    temperature=0.55,
                )
                if ai_response:
                    used = "NVIDIA" if nvidia_key.startswith("nvapi-") else "DeepSeek"
                    return ai_response.strip(), used
            return fallback, "fallback local"

        def _update_suno_dataset_status(self, records_count: int, selected_count: int, used: str) -> None:
            status = f"Dataset cargado: {records_count} registros JSONL. Contexto usado: {selected_count} fragmentos. Motor: {used}."
            self.suno_dataset_status_label.setText(status)
            self.suno_dataset_status_label.setStyleSheet("color: #ffffff; font-size: 11px;")

        def _generate_suno_style_from_dataset(self) -> None:
            context = self._get_suno_prompt_context()
            loaded = self._load_suno_generation_context(context)
            if loaded is None:
                return
            records, selected, dataset_context = loaded
            style = context["music_style"] or context["structure"] or "modern electronic"
            mood = context["mood"] or "emotional"
            instructions = context["style_instructions"] or "polished production, clear groove, strong identity"
            fallback = f"{style}, {mood}, {instructions}, clean mix, strong arrangement, Suno-ready style prompt"
            result, used = self._call_suno_field_ai(
                "Style Prompt",
                context,
                dataset_context,
                "- Write a concise Suno Style Prompt.\n"
                "- Include genre, mood, instrumentation, vocal character if relevant, tempo/energy if implied.\n"
                "- Do not write lyrics.\n"
                "- Do not mention copyrighted artist names.\n"
                "- Return one comma-separated style line.",
                fallback,
            )
            self.suno_style_prompt_edit.setPlainText(result)
            self._update_suno_dataset_status(len(records), len(selected), used)
            self.append_log("🎛️ Style Prompt SUNO generado (%s)" % used)

        def _generate_suno_lyrics_prompt_from_dataset(self) -> None:
            context = self._get_suno_prompt_context()
            loaded = self._load_suno_generation_context(context)
            if loaded is None:
                return
            records, selected, dataset_context = loaded
            title = context["title"] or "Untitled"
            language = context["language"]
            theme = context["lyrics_instructions"] or context["theme"] or "emotional transformation"
            style_prompt = context["style_prompt"] or context["music_style"] or context["structure"] or "modern song"
            fallback = (
                f"Write original {language} lyrics for \"{title}\". Theme: {theme}. "
                f"Match this style: {style_prompt}. Use clear Suno section tags like [Verse], [Chorus], [Bridge]. "
                "Make it singable, vivid, and original."
            )
            result, used = self._call_suno_field_ai(
                "Lyrics Prompt",
                context,
                dataset_context,
                "- Write a prompt that instructs Suno to create original lyrics.\n"
                "- Use the current Style Prompt as musical context.\n"
                "- Include section tags guidance.\n"
                "- Keep it actionable and ready to paste into Suno.\n"
                "- Do not write the full lyrics, write the prompt for generating them.",
                fallback,
            )
            self.suno_lyrics_prompt_edit.setPlainText(result)
            self._update_suno_dataset_status(len(records), len(selected), used)
            self.append_log("✍️ Lyrics Prompt SUNO generado (%s)" % used)

        def _generate_suno_exclude_from_dataset(self) -> None:
            context = self._get_suno_prompt_context()
            loaded = self._load_suno_generation_context(context)
            if loaded is None:
                return
            records, selected, dataset_context = loaded
            base = context["exclude_instructions"] or "avoid low quality output and unwanted genre drift"
            fallback = (
                f"{base}, low quality audio, muddy mix, harsh distortion, off-key vocals, "
                "random genre switching, spoken ads, copyrighted artist imitation"
            )
            result, used = self._call_suno_field_ai(
                "Exclude Styles",
                context,
                dataset_context,
                "- Return comma-separated negative style terms for Suno Exclude Styles.\n"
                "- Include only things to avoid.\n"
                "- Be concise.\n"
                "- Do not include explanations.",
                fallback,
            )
            self.suno_exclude_styles_edit.setPlainText(result)
            self._update_suno_dataset_status(len(records), len(selected), used)
            self.append_log("🚫 Exclude Styles SUNO generado (%s)" % used)

        def _generate_suno_prompts_from_dataset(self) -> None:
            """Ejecuta la generación por pasos en orden."""
            self._generate_suno_style_from_dataset()
            self._generate_suno_lyrics_prompt_from_dataset()
            self._generate_suno_exclude_from_dataset()
            self.append_log("🎤 Flujo completo de prompts SUNO ejecutado.")

        def _copy_suno_prompts(self) -> None:
            parts = [
                "=== LYRICS PROMPT ===",
                self.suno_lyrics_prompt_edit.toPlainText().strip(),
                "",
                "=== STYLE PROMPT ===",
                self.suno_style_prompt_edit.toPlainText().strip(),
                "",
                "=== EXCLUDE STYLES ===",
                self.suno_exclude_styles_edit.toPlainText().strip(),
            ]
            QApplication.clipboard().setText("\n".join(parts).strip())
            self.append_log("📋 Prompts SUNO copiados al portapapeles.")

        def _generate_bandcamp_texts(self) -> None:
            """Genera textos Bandcamp usando datos del análisis + contexto IA."""
            artist = self.ia_artist_edit.text().strip() or "O-M-A"
            label = self.ia_label_edit.text().strip() or "Detected Records Argentina"
            title = self.ia_title_edit.text().strip() or ""
            if not title:
                raw = self.input_edit.text().strip()
                title = pathlib.Path(raw).stem if raw else ""
            api_key = self.ia_api_key_edit.text().strip()
            nvidia_key = self.ia_nvidia_key_edit.text().strip()

            context = {
                "artist": artist,
                "label": label,
                "title": title,
                "suno_prompt": self.suno_style_prompt_edit.toPlainText().strip(),
                "lyrics": self.suno_lyrics_prompt_edit.toPlainText().strip(),
                "exclude_styles": self.suno_exclude_styles_edit.toPlainText().strip(),
                "notes": self.ia_notes_edit.toPlainText().strip(),
                "analysis": getattr(self, "_last_auto_master_adjustments", {}),
            }

            texts = _bok_generate_all(context, nvidia_key, api_key)
            self.bc_tags_edit.setText(texts.tags)
            self.bc_desc_edit.setPlainText(texts.description)
            self.bc_release_msg_edit.setPlainText(texts.release_msg)
            self.bc_credits_edit.setPlainText(texts.credits)
            self.bc_price_spin.setValue(texts.price)
            self._update_bc_char_count()

            profile = "Normal"
            adj = context["analysis"]
            if isinstance(adj, dict):
                profile = adj.get("processing_profile", "Normal")
            self.bc_tags_lbl.setText(
                "Perfil: %s | Artista: %s | Sello: %s | Precio: $%.2f" % (
                    profile, artist, label, texts.price
                )
            )
            used_api = "NVIDIA" if nvidia_key.startswith("nvapi-") else ("DeepSeek" if api_key.startswith("sk-") else "templates")
            self.append_log("🎸 Textos Bandcamp generados (%s)" % used_api)

        def _copy_bandcamp_texts(self) -> None:
            ufeff = "\n"
            parts = [
                "=== BANDCAMP ===",
                "Titulo: " + self.ia_title_edit.text(),
                "Tags: " + self.bc_tags_edit.text(),
                "Fecha: " + self.bc_date_edit.date().toString("MM/dd/yyyy"),
                "Catalogo: " + self.bc_catalog_edit.text(),
                "Precio: $%.2f" % self.bc_price_spin.value(),
                "",
                "--- Mensaje de lanzamiento ---",
                self.bc_release_msg_edit.toPlainText(),
                "",
                "--- Descripcion ---",
                self.bc_desc_edit.toPlainText(),
                "",
                "--- Creditos ---",
                self.bc_credits_edit.toPlainText(),
            ]
            QApplication.clipboard().setText("\n".join(parts))
            self.append_log("📋 Textos Bandcamp copiados al portapapeles")

        def closeEvent(self, event) -> None:  # type: ignore[override]
            thread = self._current_thread
            if thread is not None and getattr(thread, "isRunning", lambda: False)():
                QMessageBox.warning(
                    self,
                    "Proceso en curso",
                    "Espera a que el proceso termine antes de cerrar la app.",
                )
                event.ignore()
                return
            event.accept()

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
            self._show_single_results()
            self._update_stats_display(stats)
            self._update_input_level_display(stats)
            self._update_loudness_display(stats, None)
            self._update_voice_display(voice_rms)
            self._auto_adjust_processes(stats, band_stats, voice_rms)
            self._apply_band_suggestions_dynamic(band_stats)
            self._auto_configure_fades(pathlib.Path(self.input_edit.text().strip()))
            self._update_spectrum_display(
                pre_path=pathlib.Path(self.input_edit.text().strip()),
                post_path=None,
                pre_band_stats=band_stats,
                post_band_stats=None,
            )
            self.append_log("Análisis completado.")
            self._update_process_state("Análisis completado", pathlib.Path(self.input_edit.text().strip()).name)
            self._update_eq_display(band_stats, suggestions)
            if log:
                self.append_log(log.strip())
            self._update_analysis_summary_text(
                pre_stats=stats,
                pre_band=band_stats,
                pre_voice=voice_rms,
                post_stats=None,
                post_band=None,
                post_voice=None,
                pre_rating=None,
                post_rating=None,
                log=log,
            )
            self._record_log_history(
                action="Analizar",
                input_path=pathlib.Path(self.input_edit.text().strip()),
                output_path=None,
                pre_stats=stats,
                post_stats=None,
            )

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
            post_band_stats: object,
            pre_rating: object,
            post_rating: object,
        ) -> None:
            self.last_stats = stats
            self.last_band_stats = band_stats
            self._show_single_results()
            self._update_stats_display(stats)
            self._update_input_level_display(stats)
            self._update_voice_display(voice_rms)
            self._update_eq_display(band_stats, suggestions)
            self._update_results_table(stats, voice_rms, post_stats, post_voice_rms, pre_rating, post_rating)
            self._update_loudness_display(stats, post_stats)
            self._auto_adjust_processes(stats, band_stats, voice_rms)
            self._apply_band_suggestions_dynamic(band_stats)
            if output_path:
                self._update_spectrum_display(
                    pre_path=pathlib.Path(self.input_edit.text().strip()),
                    post_path=pathlib.Path(str(output_path)),
                    pre_band_stats=band_stats,
                    post_band_stats=post_band_stats if isinstance(post_band_stats, dict) else None,
                )
            self.append_log("Proceso completado.")
            if output_path:
                self._update_process_state("Proceso completado", pathlib.Path(str(output_path)).name)
            if output_path:
                self.append_log(f"Salida -> {output_path}")
                try:
                    mts_path = self._find_mts_for_output_path(pathlib.Path(str(output_path)))
                    if mts_path is not None:
                        self._load_inspector_from_mts_json(mts_path)
                except Exception:
                    pass
            if toml_path:
                self.append_log(f"Reporte -> {toml_path}")
            if log:
                self.append_log(log.strip())
            if normalize_log:
                self.append_log(normalize_log.strip())
            QMessageBox.information(
                self,
                "Proceso finalizado",
                "El procesamiento del audio terminó correctamente.",
            )
            self._update_analysis_summary_text(
                pre_stats=stats,
                pre_band=band_stats,
                pre_voice=voice_rms,
                post_stats=post_stats if isinstance(post_stats, dict) else None,
                post_band=post_band_stats if isinstance(post_band_stats, dict) else None,
                post_voice=post_voice_rms if isinstance(post_voice_rms, (float, int)) else None,
                pre_rating=pre_rating if isinstance(pre_rating, str) else None,
                post_rating=post_rating if isinstance(post_rating, str) else None,
                log=normalize_log,
            )
            self._record_log_history(
                action="Procesar",
                input_path=pathlib.Path(self.input_edit.text().strip()),
                output_path=output_path,
                pre_stats=stats,
                post_stats=post_stats,
            )

        def _handle_batch_finished(self, message: str, results: object) -> None:
            self.append_log(message)
            self._clear_batch_checkpoint()
            self._update_process_state(message)
            batch_summary_text = None
            if isinstance(results, list):
                self._set_progress(current=len(results), total=len(results), message=message)
                batch_lines: list[str] = []
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    file_name = str(item.get("file", "-"))
                    total_seconds = item.get("total_seconds")
                    timings = item.get("timings", [])
                    if isinstance(total_seconds, (float, int)):
                        batch_lines.append(f"{file_name} | total {total_seconds:.1f}s")
                    else:
                        batch_lines.append(f"{file_name} | total -")
                    if isinstance(timings, list):
                        for stage_name, duration in timings:
                            if isinstance(stage_name, str) and isinstance(duration, (float, int)):
                                batch_lines.append(f"  - {stage_name}: {duration:.1f}s")
                if batch_lines:
                    self._append_batch_history(batch_lines)
            if isinstance(results, list):
                self._show_batch_results()
                self._update_batch_results_table(results)
                batch_summary_text = self._update_batch_summary(results)
                self.tabs.setCurrentIndex(self.tab_index_results)
            QMessageBox.information(
                self,
                "Lote finalizado",
                message,
            )
            if batch_summary_text:
                self._record_log_history(
                    action="Lote resumen",
                    input_path=pathlib.Path(self.batch_input_edit.text().strip())
                    if self.batch_input_edit.text().strip()
                    else None,
                    output_path=self.batch_output_edit.text().strip() or None,
                    pre_stats=None,
                    post_stats=None,
                    log_text_override=batch_summary_text,
                )
            self._record_log_history(
                action="Lote",
                input_path=pathlib.Path(self.batch_input_edit.text().strip())
                if self.batch_input_edit.text().strip()
                else None,
                output_path=self.batch_output_edit.text().strip() or None,
                pre_stats=None,
                post_stats=None,
            )

        def _handle_normalize_finished(self, log: str, output_path: str) -> None:
            self.append_log(f"Normalización completada -> {output_path}")
            self._update_process_state("Normalización completada", pathlib.Path(output_path).name)
            if log:
                self.append_log(log.strip())
            QMessageBox.information(
                self,
                "Normalización finalizada",
                f"Salida -> {output_path}",
            )
            self._record_log_history(
                action="Normalizar",
                input_path=pathlib.Path(self.input_edit.text().strip()),
                output_path=output_path,
                pre_stats=self.last_stats if isinstance(self.last_stats, dict) else None,
                post_stats=None,
            )

        def _update_stats_display(self, stats: Dict[str, float]) -> None:
            self.input_i_label.setText(f"{stats.get('input_i', 0):.2f}")
            self.input_tp_label.setText(f"{stats.get('input_tp', 0):.2f}")
            self.input_lra_label.setText(f"{stats.get('input_lra', 0):.2f}")
            self.threshold_label.setText(f"{stats.get('input_thresh', 0):.2f}")
            self.offset_label.setText(f"{stats.get('target_offset', 0):.2f}")

        def _update_input_level_display(self, stats: Dict[str, float]) -> None:
            self.input_rms_label.setText(f"{stats.get('input_i', 0):.2f} LUFS")
            self.input_peak_label.setText(f"{stats.get('input_tp', 0):.2f} dBTP")

        def _update_loudness_display(
            self, pre_stats: Dict[str, float], post_stats: object
        ) -> None:
            self.loudness_pre_label.setText(f"{pre_stats.get('input_i', 0):.2f} LUFS")
            if isinstance(post_stats, dict):
                self.loudness_post_label.setText(f"{post_stats.get('input_i', 0):.2f} LUFS")
            else:
                self.loudness_post_label.setText("-")

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

        def _format_batch_resource_summary(self) -> str:
            lines: list[str] = []
            if self._current_processing_budget is not None:
                lines.append(f"Governor: {self._current_processing_budget.format_summary()}")
            if self._last_resource_snapshot is not None:
                lines.append(f"CPU/RAM: {self._last_resource_snapshot.format_summary()}")
            if self._last_resource_gpu_summary and self._last_resource_gpu_summary != "GPU no disponible":
                lines.append(f"GPU: {self._last_resource_gpu_summary}")
            elif self._current_processing_budget is not None:
                lines.append(f"GPU: {self._current_processing_budget.gpu.format_summary()}")
            return "\n".join(lines)

        def _update_batch_summary(self, results: list[dict]) -> None:
            if not results:
                self.batch_summary_text.setPlainText("Sin datos de lote.")
                return "Sin datos de lote."
            def avg(values: list[float]) -> float:
                return sum(values) / len(values) if values else 0.0
            before_i = []
            after_i = []
            before_tp = []
            after_tp = []
            before_lra = []
            after_lra = []
            for item in results:
                before = item.get("before", {})
                after = item.get("after", {})
                if isinstance(before, dict):
                    before_i.append(float(before.get("input_i", 0.0)))
                    before_tp.append(float(before.get("input_tp", 0.0)))
                    before_lra.append(float(before.get("input_lra", 0.0)))
                if isinstance(after, dict):
                    after_i.append(float(after.get("input_i", 0.0)))
                    after_tp.append(float(after.get("input_tp", 0.0)))
                    after_lra.append(float(after.get("input_lra", 0.0)))
            summary = (
                f"Promedios: I {avg(before_i):.2f} -> {avg(after_i):.2f} LUFS | "
                f"TP {avg(before_tp):.2f} -> {avg(after_tp):.2f} dBTP | "
                f"LRA {avg(before_lra):.2f} -> {avg(after_lra):.2f} LU"
            )
            resource_summary = self._format_batch_resource_summary()
            if resource_summary:
                summary = f"{summary}\n\n{resource_summary}"
            self.batch_summary_text.setPlainText(summary)
            return summary

        def _fade_key(self, audio_path: pathlib.Path) -> str:
            return str(audio_path)

        def _get_global_fades(self) -> tuple[float, float]:
            return self.fade_in_spin.value(), self.fade_out_spin.value()

        def _resolve_fades_for_path(self, audio_path: pathlib.Path) -> tuple[float, float]:
            key = self._fade_key(audio_path)
            if key in self.fade_overrides:
                return self.fade_overrides[key]
            return self._get_global_fades()

        def _update_waveform_global_label(self) -> None:
            fade_in, fade_out = self._get_global_fades()
            self.waveform_global_label.setText(f"Global: {fade_in:.2f}s / {fade_out:.2f}s")

        def _update_waveform_table_globals(self) -> None:
            fade_in, fade_out = self._get_global_fades()
            for row, audio_path in enumerate(self._waveform_files):
                key = self._fade_key(audio_path)
                if key in self.fade_overrides:
                    continue
                self.waveform_table.setItem(row, 1, QTableWidgetItem(f"{fade_in:.2f}"))
                self.waveform_table.setItem(row, 2, QTableWidgetItem(f"{fade_out:.2f}"))

        def _refresh_waveform_tab_list(self) -> None:
            mode = self.mode_combo.currentText()
            files: list[pathlib.Path] = []
            if mode == "Auto-Master (Lote)":
                files = list(self._batch_files)
            else:
                input_text = self.input_edit.text().strip()
                if input_text:
                    path = pathlib.Path(input_text)
                    if path.exists():
                        files = [path]
            self._waveform_files = files
            self.waveform_table.setRowCount(len(files))
            if not files:
                self._waveform_selected_path = None
                self._clear_waveform()
                self._update_waveform_global_label()
                return
            for row, audio_path in enumerate(files):
                self.waveform_table.setItem(row, 0, QTableWidgetItem(audio_path.name))
                fade_in, fade_out = self._resolve_fades_for_path(audio_path)
                self.waveform_table.setItem(row, 1, QTableWidgetItem(f"{fade_in:.2f}"))
                self.waveform_table.setItem(row, 2, QTableWidgetItem(f"{fade_out:.2f}"))
            if files and PYSIDE_AVAILABLE:
                self.waveform_table.selectRow(0)
            self._update_waveform_global_label()

        def _update_waveform_table_row(self, audio_path: pathlib.Path) -> None:
            for row, row_path in enumerate(self._waveform_files):
                if row_path == audio_path:
                    fade_in, fade_out = self._resolve_fades_for_path(audio_path)
                    self.waveform_table.setItem(row, 1, QTableWidgetItem(f"{fade_in:.2f}"))
                    self.waveform_table.setItem(row, 2, QTableWidgetItem(f"{fade_out:.2f}"))
                    return

        def _on_waveform_selection_changed(self) -> None:
            if not self._waveform_files:
                self._waveform_selected_path = None
                self._clear_waveform()
                return
            if not PYSIDE_AVAILABLE:
                return
            row = self.waveform_table.currentRow()
            if row < 0 or row >= len(self._waveform_files):
                return
            audio_path = self._waveform_files[row]
            self._waveform_selected_path = audio_path
            fade_in, fade_out = self._resolve_fades_for_path(audio_path)
            self._waveform_syncing = True
            self.waveform_fade_in_spin.setValue(float(fade_in))
            self.waveform_fade_out_spin.setValue(float(fade_out))
            self._waveform_syncing = False
            self._update_waveform(str(audio_path))

        def _apply_waveform_override(self) -> None:
            if self._waveform_selected_path is None:
                return
            fade_in = self.waveform_fade_in_spin.value()
            fade_out = self.waveform_fade_out_spin.value()
            self.fade_overrides[self._fade_key(self._waveform_selected_path)] = (fade_in, fade_out)
            self._update_waveform_table_row(self._waveform_selected_path)

        def _use_global_for_selected(self) -> None:
            if self._waveform_selected_path is None:
                return
            key = self._fade_key(self._waveform_selected_path)
            if key in self.fade_overrides:
                del self.fade_overrides[key]
            fade_in, fade_out = self._get_global_fades()
            self._waveform_syncing = True
            self.waveform_fade_in_spin.setValue(float(fade_in))
            self.waveform_fade_out_spin.setValue(float(fade_out))
            self._waveform_syncing = False
            self._update_waveform_table_row(self._waveform_selected_path)
            self._sync_waveform_regions()

        def _on_waveform_fade_changed(self, _value: float) -> None:
            if self._waveform_syncing:
                return
            if self._waveform_selected_path is None:
                return
            fade_in = self.waveform_fade_in_spin.value()
            fade_out = self.waveform_fade_out_spin.value()
            self.fade_overrides[self._fade_key(self._waveform_selected_path)] = (fade_in, fade_out)
            self._update_waveform_table_row(self._waveform_selected_path)
            self._sync_waveform_regions()

        def _refresh_waveform_from_input(self) -> None:
            input_path = self.input_edit.text().strip()
            if input_path:
                self._update_single_waveform(input_path)
                self._update_waveform(input_path)
            else:
                self._clear_single_waveform()
            self._refresh_waveform_tab_list()

        def _set_waveform_visible(self, visible: bool) -> None:
            if self.waveform_plot is not None:
                self.waveform_plot.setVisible(visible)
            if self.waveform_help is not None:
                self.waveform_help.setVisible(visible)

        def _clear_waveform(self) -> None:
            self._waveform_duration = None
            if self.waveform_curve is not None:
                self.waveform_curve.setData([], [])
            if self.fade_in_region is not None and self.fade_out_region is not None:
                self._waveform_syncing = True
                self.fade_in_region.setRegion([0.0, 0.0])
                self.fade_out_region.setRegion([0.0, 0.0])
                self._waveform_syncing = False

        def _clear_single_waveform(self) -> None:
            if self.single_waveform_curve is not None:
                self.single_waveform_curve.setData([], [])

        def _update_single_waveform(self, input_path: str) -> None:
            if os.getenv("TONEFINISH_WAVEFORM_ENABLED", "0").strip().lower() not in {"1", "true", "yes", "on"}:
                self._clear_single_waveform()
                return
            if not PYQTGRAPH_AVAILABLE or self.single_waveform_plot is None:
                return
            if self.single_waveform_curve is None:
                return
            audio_path = pathlib.Path(input_path)
            if not audio_path.exists():
                self._clear_single_waveform()
                return
            duration = get_audio_duration(str(audio_path))
            waveform = get_waveform_samples(str(audio_path))
            if duration is None or waveform is None:
                self._clear_single_waveform()
                return
            samples, effective_rate = waveform
            times = [index / effective_rate for index in range(len(samples))]
            self.single_waveform_curve.setData(times, samples)
            self.single_waveform_plot.setXRange(0.0, duration)
            self.single_waveform_plot.setYRange(-1.05, 1.05)

        def _update_waveform(self, input_path: str) -> None:
            if os.getenv("TONEFINISH_WAVEFORM_ENABLED", "0").strip().lower() not in {"1", "true", "yes", "on"}:
                self._clear_waveform()
                return
            if not PYQTGRAPH_AVAILABLE or self.waveform_plot is None:
                return
            if self.waveform_curve is None:
                return
            self._set_waveform_visible(True)
            audio_path = pathlib.Path(input_path)
            if not audio_path.exists():
                self._clear_waveform()
                return
            duration = get_audio_duration(str(audio_path))
            waveform = get_waveform_samples(str(audio_path))
            if duration is None or waveform is None:
                self._clear_waveform()
                return
            samples, effective_rate = waveform
            times = [index / effective_rate for index in range(len(samples))]
            self.waveform_curve.setData(times, samples)
            self.waveform_plot.setXRange(0.0, duration)
            self.waveform_plot.setYRange(-1.05, 1.05)
            self._waveform_duration = duration
            self._sync_waveform_regions()

        def _sync_waveform_regions(self) -> None:
            if self._waveform_duration is None:
                return
            if self.fade_in_region is None or self.fade_out_region is None:
                return
            fade_in = min(self.waveform_fade_in_spin.value(), self._waveform_duration)
            fade_out = min(self.waveform_fade_out_spin.value(), self._waveform_duration)
            self._waveform_syncing = True
            self.fade_in_region.setRegion([0.0, fade_in])
            self.fade_out_region.setRegion([max(0.0, self._waveform_duration - fade_out), self._waveform_duration])
            self._waveform_syncing = False

        def _on_fade_spin_changed(self, _value: float) -> None:
            if self._waveform_syncing:
                return
            self._update_waveform_global_label()
            self._update_waveform_table_globals()
            if self._waveform_selected_path is None:
                return
            key = self._fade_key(self._waveform_selected_path)
            if key in self.fade_overrides:
                return
            fade_in, fade_out = self._get_global_fades()
            self._waveform_syncing = True
            self.waveform_fade_in_spin.setValue(float(fade_in))
            self.waveform_fade_out_spin.setValue(float(fade_out))
            self._waveform_syncing = False
            self._sync_waveform_regions()
            self._update_waveform_table_globals()

        def _on_fade_in_region_changed(self) -> None:
            if self._waveform_syncing or self._waveform_duration is None:
                return
            if self.fade_in_region is None:
                return
            region = cast(list[float], list(self.fade_in_region.getRegion()))
            _start = float(region[0])
            _end = float(region[1])
            new_end = max(0.0, min(self._waveform_duration, _end))
            self._waveform_syncing = True
            self.fade_in_region.setRegion([0.0, new_end])
            self.waveform_fade_in_spin.setValue(float(new_end))
            self._waveform_syncing = False

        def _on_fade_out_region_changed(self) -> None:
            if self._waveform_syncing or self._waveform_duration is None:
                return
            if self.fade_out_region is None:
                return
            region = cast(list[float], list(self.fade_out_region.getRegion()))
            _start = float(region[0])
            _end = float(region[1])
            new_start = max(0.0, min(self._waveform_duration, _start))
            fade_out = max(0.0, self._waveform_duration - new_start)
            self._waveform_syncing = True
            self.fade_out_region.setRegion([self._waveform_duration - fade_out, self._waveform_duration])
            self.waveform_fade_out_spin.setValue(float(fade_out))
            self._waveform_syncing = False

        def _show_single_results(self) -> None:
            self.single_results_container.setVisible(True)
            try:
                current_text = self.eq_suggestions.toPlainText().strip()
            except Exception:
                current_text = ""
            if current_text == "Sugerencias EQ solo disponibles en audio unico.":
                self.eq_suggestions.setPlainText("")
            self._set_results_tabs_visibility(single=True)

        def _show_batch_results(self) -> None:
            self._clear_single_results()
            self.single_results_container.setVisible(False)
            self.eq_suggestions.setPlainText("💡 Las sugerencias de EQ aparecerán aquí después de procesar un archivo individual.")
            self._set_single_results_placeholder("📊 Procesa un archivo para ver la comparación Antes/Después.")
            self._set_results_tabs_visibility(single=False)

        def _clear_single_results(self) -> None:
            self.input_i_label.setText("-")
            self.input_tp_label.setText("-")
            self.input_lra_label.setText("-")
            self.threshold_label.setText("-")
            self.offset_label.setText("-")
            self.voice_band_label.setText("-")
            self.input_rms_label.setText("-")
            self.input_peak_label.setText("-")
            self.loudness_pre_label.setText("-")
            self.loudness_post_label.setText("-")
            for label_widget in self.band_labels.values():
                label_widget.setText("-")
            self.eq_suggestions.setPlainText("")
            self.results_table.setRowCount(0)

        def _set_single_results_placeholder(self, message: str) -> None:
            """Muestra un mensaje placeholder en la tabla de resultados."""
            self.results_table.setRowCount(1)
            # Usar span para que el mensaje ocupe toda la fila visualmente
            item = QTableWidgetItem(message)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(0, 0, item)
            self.results_table.setItem(0, 1, QTableWidgetItem(""))
            self.results_table.setItem(0, 2, QTableWidgetItem(""))
            # Span de la primera celda sobre las 3 columnas
            self.results_table.setSpan(0, 0, 1, 3)

        def _set_results_tabs_visibility(self, single: bool) -> None:
            """Configura visibilidad de resultados según modo single/batch."""
            if hasattr(self, 'batch_results_group') and self.batch_results_group is not None:
                self.batch_results_group.setVisible(not single)
                if not single:
                    self.batch_results_group.setChecked(True)  # Expandir en modo lote

            if not hasattr(self, "results_tabs") or self.results_tabs is None:
                return

            def set_visible(index: int, visible: bool) -> None:
                try:
                    self.results_tabs.setTabVisible(index, visible)
                except Exception:
                    self.results_tabs.setTabEnabled(index, visible)

            if single:
                set_visible(self.results_tab_eq_index, True)
                set_visible(self.results_tab_single_index, True)
                set_visible(self.results_tab_spectrum_index, True)
                set_visible(self.results_tab_batch_index, False)
                set_visible(self.results_tab_log_index, True)
                if hasattr(self, "results_tab_analysis_summary_index"):
                    set_visible(self.results_tab_analysis_summary_index, True)
            else:
                set_visible(self.results_tab_eq_index, True)
                set_visible(self.results_tab_single_index, True)
                set_visible(self.results_tab_spectrum_index, True)
                set_visible(self.results_tab_batch_index, True)
                set_visible(self.results_tab_log_index, True)
                if hasattr(self, "results_tab_analysis_summary_index"):
                    set_visible(self.results_tab_analysis_summary_index, True)

        def _update_stereo_band_plot(self) -> None:
            if not PYQTGRAPH_AVAILABLE or self.stereo_band_plot is None:
                return
            if not self.stereo_band_spins:
                return
            labels = list(self.stereo_band_spins.keys())
            widths = [self.stereo_band_spins[label].value() for label in labels]
            x_values = list(range(len(widths)))
            max_height = max(2.0, max(widths) * 1.2)
            if self.stereo_band_bars is None:
                self.stereo_band_bars = pg.BarGraphItem(x=x_values, height=widths, width=0.6)
                self.stereo_band_plot.addItem(self.stereo_band_bars)
            else:
                self.stereo_band_bars.setOpts(x=x_values, height=widths, width=0.6)
            self.stereo_band_plot.setYRange(0.0, max_height)

        def _update_dynamic_band_plot(self) -> None:
            if not PYQTGRAPH_AVAILABLE or self.dynamic_band_plot is None:
                return
            if not self.dynamic_band_spins:
                return
            labels = list(self.dynamic_band_spins.keys())
            gains = [self.dynamic_band_spins[label].value() for label in labels]
            x_values = list(range(len(gains)))
            max_height = max(2.0, max(abs(val) for val in gains) * 1.2)
            if self.dynamic_band_bars is None:
                self.dynamic_band_bars = pg.BarGraphItem(x=x_values, height=gains, width=0.6)
                self.dynamic_band_plot.addItem(self.dynamic_band_bars)
            else:
                self.dynamic_band_bars.setOpts(x=x_values, height=gains, width=0.6)
            self.dynamic_band_plot.setYRange(-max_height, max_height)

        def _update_action_buttons(self, mode: str) -> None:
            if mode == "Solo analizar":
                self.analyze_btn.setVisible(True)
                self.process_btn.setVisible(False)
                self.batch_process_btn.setVisible(False)
                self.batch_automaster_btn.setVisible(False)
                return
            if mode == "Auto-Master (Audio único)":
                self.analyze_btn.setVisible(False)
                self.process_btn.setVisible(True)
                self.batch_process_btn.setVisible(False)
                self.batch_automaster_btn.setVisible(False)
                return
            if mode == "Auto-Master (Lote)":
                # Solo botón de procesar lote (Auto-Master se aplica automáticamente)
                self.analyze_btn.setVisible(False)
                self.process_btn.setVisible(False)
                self.batch_process_btn.setVisible(True)
                self.batch_automaster_btn.setVisible(False)  # No necesario, se aplica auto
                return
            self.analyze_btn.setVisible(False)
            self.process_btn.setVisible(False)
            self.batch_process_btn.setVisible(False)
            self.batch_automaster_btn.setVisible(False)

        def _set_tab_visible(self, index: int, visible: bool) -> None:
            if not hasattr(self, "tabs"):
                return
            try:
                self.tabs.setTabVisible(index, visible)
            except Exception:
                self.tabs.setTabEnabled(index, visible)

        def _show_only_start_tab(self) -> None:
            self._set_tab_visible(self.tab_index_start, True)
            self.analyze_btn.setVisible(False)
            self.process_btn.setVisible(False)
            self.batch_process_btn.setVisible(False)
            self.batch_automaster_btn.setVisible(False)
            for index in range(self.tabs.count()):
                if index != self.tab_index_start:
                    self._set_tab_visible(index, False)

        def _show_tabs_for_mode(self, mode: str) -> None:
            """Configura la visibilidad de tabs y secciones según el modo de trabajo."""
            self._current_mode = mode
            
            # Configurar visibilidad de tabs principales
            # Inicio siempre visible
            self._set_tab_visible(self.tab_index_start, True)
            # Tabs informativas y de texto siempre visibles
            self._set_tab_visible(self.tab_index_diagnostic, True)
            self._set_tab_visible(self.tab_index_ai_text, True)
            self._set_tab_visible(self.tab_index_about, True)
            
            # En modo Free: ocultar permanentemente el tab Procesamiento
            if not is_premium():
                self._set_tab_visible(self.tab_index_processing, False)
            
            # Configurar según modo
            if mode == "Solo analizar":
                # Solo mostrar: Inicio, Proyecto (solo audio), Resultados, About
                self._set_tab_visible(self.tab_index_project, True)
                self._set_tab_visible(self.tab_index_processing, False)  # Sin procesos
                self._set_tab_visible(self.tab_index_results, True)
                self._set_tab_visible(self.tab_index_auto_master, False)
                self._configure_project_for_mode(mode)
                self._configure_processing_for_mode(mode)
                
            elif mode == "Auto-Master (Audio único)":
                # Flujo individual gobernado por IA, sin controles manuales.
                self._set_tab_visible(self.tab_index_project, True)
                self._set_tab_visible(self.tab_index_processing, False)
                self._set_tab_visible(self.tab_index_results, True)
                self._set_tab_visible(self.tab_index_auto_master, True)
                self._configure_project_for_mode(mode)
                self._configure_processing_for_mode(mode)
                
            elif mode == "Auto-Master (Lote)":
                # UI simplificada: Proyecto (solo lote), Auto-Master, Resultados
                self._set_tab_visible(self.tab_index_project, True)
                self._set_tab_visible(self.tab_index_processing, False)  # Ocultar procesamiento manual
                self._set_tab_visible(self.tab_index_auto_master, True)  # Auto-Master es el centro
                self._set_tab_visible(self.tab_index_results, True)
                self._configure_project_for_mode(mode)
                self._configure_processing_for_mode(mode)
                # Navegar al tab Auto-Master automáticamente
                self.tabs.setCurrentIndex(self.tab_index_auto_master)
                # Aplicar Auto-Master automáticamente
                self._apply_auto_master(emit_log=False, write_preset=False)
                
            else:
                self._set_tab_visible(self.tab_index_project, False)
                self._set_tab_visible(self.tab_index_processing, False)
                self._set_tab_visible(self.tab_index_auto_master, False)
                self._set_tab_visible(self.tab_index_results, False)
                self._configure_project_for_mode(mode)
                self._configure_processing_for_mode(mode)
        
        def _configure_project_for_mode(self, mode: str) -> None:
            """Configura qué subtabs del proyecto son visibles según el modo."""
            if not hasattr(self, 'project_tabs') or self.project_tabs is None:
                return
            
            project_tabs = self.project_tabs  # Variable local para type narrowing
            try:
                # Índices de subtabs: 0=Audio, 1=Lote, 2=Firma, 3=Salida
                if mode == "Solo analizar":
                    # Solo audio y salida mínima
                    project_tabs.setTabVisible(0, True)   # Audio
                    project_tabs.setTabVisible(1, False)  # Lote
                    project_tabs.setTabVisible(2, False)  # Firma
                    project_tabs.setTabVisible(3, True)   # Salida
                elif mode == "Auto-Master (Audio único)":
                    # Audio, firma y salida (sin lote)
                    project_tabs.setTabVisible(0, True)   # Audio
                    project_tabs.setTabVisible(1, False)  # Lote
                    project_tabs.setTabVisible(2, True)   # Firma
                    project_tabs.setTabVisible(3, True)   # Salida
                elif mode == "Auto-Master (Lote)":
                    # Solo lote y salida (simplificado)
                    project_tabs.setTabVisible(0, False)  # Audio
                    project_tabs.setTabVisible(1, True)   # Lote
                    project_tabs.setTabVisible(2, True)   # Firma
                    project_tabs.setTabVisible(3, True)   # Salida
                    # Ir a tab Lote automáticamente
                    project_tabs.setCurrentIndex(1)
                else:
                    for i in range(project_tabs.count()):
                        project_tabs.setTabVisible(i, False)
            except Exception:
                pass  # Silenciar errores si el widget no soporta setTabVisible
        
        def _configure_processing_for_mode(self, mode: str) -> None:
            """Configura qué secciones de procesamiento son visibles según el modo."""
            if not hasattr(self, 'process_tabs') or self.process_tabs is None:
                return
            
            process_tabs = self.process_tabs  # Variable local para type narrowing
            try:
                # Índices: 0=Reparación, 1=Mezcla, 2=Mastering, 3=Avanzado
                if mode == "Solo analizar":
                    # Ocultar todo procesamiento
                    pass  # El tab completo está oculto
                elif mode == "Auto-Master (Lote)":
                    # En modos Auto-Master, el tab de procesamiento está oculto
                    # Los parámetros se configuran automáticamente
                    pass
                else:
                    pass
            except Exception:
                pass

            self._apply_processing_density_view()
            
            # Configurar panel lateral según modo
            self._configure_sidebar_for_mode(mode)

        def _apply_processing_density_view(self) -> None:
            """Aplica vista compacta o avanzada en la pestaña de procesamiento."""
            advanced_view = bool(self.auto_master_enable_process_cb.isChecked())

            if hasattr(self, "process_tabs") and self.process_tabs is not None:
                try:
                    if advanced_view:
                        # 0=Reparación, 1=Mezcla, 2=Mastering, 3=Avanzado
                        for idx in range(self.process_tabs.count()):
                            self.process_tabs.setTabVisible(idx, True)
                    else:
                        # Fase 2: compacto extremo (solo controles clave en Mezcla).
                        self.process_tabs.setTabVisible(0, False)
                        self.process_tabs.setTabVisible(1, True)
                        self.process_tabs.setTabVisible(2, False)
                        self.process_tabs.setTabVisible(3, False)
                except Exception:
                    pass
                if not advanced_view and self.process_tabs.currentIndex() != 1:
                    self.process_tabs.setCurrentIndex(1)

            # Telemetría detallada solo en vista avanzada.
            if hasattr(self, "processing_telemetry_group"):
                self.processing_telemetry_group.setVisible(advanced_view)
            if hasattr(self, "processing_quick_group"):
                self.processing_quick_group.setVisible(not advanced_view)

            # Reducir ancho del panel lateral en modo compacto para ganar espacio útil.
            if hasattr(self, "processing_left_panel"):
                try:
                    self.processing_left_panel.setMaximumWidth(240 if not advanced_view else 280)
                except Exception:
                    pass

            # En vista compacta ocultamos módulos de alta densidad visual.
            compact_visibility = {
                "mix_group_dyneq": advanced_view,
                "mix_group_width": advanced_view,
                "mix_group_stereo_dynamic": advanced_view,
                "mix_group_saturation_control": advanced_view,
                "mix_group_saturation_band": advanced_view,
                "master_group_fades": advanced_view,
                "master_group_measurements": advanced_view,
                "master_group_limiter": advanced_view,
            }
            for attr_name, visible in compact_visibility.items():
                if hasattr(self, attr_name):
                    widget = getattr(self, attr_name)
                    if widget is not None:
                        widget.setVisible(visible)

            # En vista compacta dejamos foco en lo esencial.
            if hasattr(self, "mix_group_deesser"):
                self.mix_group_deesser.setVisible(True)
            if hasattr(self, "mix_group_saturation"):
                self.mix_group_saturation.setVisible(True)
            if hasattr(self, "mix_group_glue"):
                self.mix_group_glue.setVisible(True)
            if hasattr(self, "master_group_limiter"):
                self.master_group_limiter.setVisible(True)
            if hasattr(self, "master_group_measurements"):
                self.master_group_measurements.setVisible(True)

        def _apply_quick_master_profile(self, profile: str) -> None:
            """Aplica un perfil rápido de mastering para modo compacto."""
            amount = 0.6
            if hasattr(self, "quick_master_amount_spin") and self.quick_master_amount_spin is not None:
                amount = max(0.0, min(1.0, float(self.quick_master_amount_spin.value())))
            amount_eff = min(0.75, amount)

            # Base conservadora común
            self.dynamic_eq_cb.setChecked(True)
            self.deesser_cb.setChecked(True)
            self.glue_cb.setChecked(True)
            self.stereo_width_cb.setChecked(True)
            self.saturation_enable_cb.setChecked(False)
            self.saturation_per_band_cb.setChecked(False)
            self.multiband_limiter_cb.setChecked(True)
            self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
            self._apply_limiter_preset()

            if profile == "clean":
                self.deesser_freq_spin.setValue(5500.0 + (250.0 * amount_eff))
                self.deesser_intensity_spin.setValue(0.42 + (0.16 * amount_eff))
                self.glue_ratio_spin.setValue(1.2 + (0.2 * amount_eff))
                self.glue_threshold_spin.setValue(-24.0 + (1.5 * amount_eff))
                self.stereo_dynamic_cb.setChecked(False)
                self.append_log(f"Quick Master: Clean (intensidad {amount_eff:.2f})")
            elif profile == "vocal":
                self.deesser_freq_spin.setValue(5800.0 + (250.0 * amount_eff))
                self.deesser_intensity_spin.setValue(0.50 + (0.18 * amount_eff))
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.28 + (0.14 * amount_eff))
                if self.dynamic_band_spins:
                    low_mid = self.dynamic_band_spins.get("Low-Mid (250-500 Hz)")
                    mid = self.dynamic_band_spins.get("Mid (500-2k Hz)")
                    high_mid = self.dynamic_band_spins.get("High-Mid (2k-6k Hz)")
                    if low_mid is not None:
                        low_mid.setValue(min(1.2, 0.3 + (0.6 * amount_eff)))
                    if mid is not None:
                        mid.setValue(min(1.0, 0.2 + (0.4 * amount_eff)))
                    if high_mid is not None:
                        high_mid.setValue(max(-1.0, -0.2 - (0.3 * amount_eff)))
                self.append_log(f"Quick Master: Vocal Body (intensidad {amount_eff:.2f})")
            elif profile == "tight":
                self.deesser_freq_spin.setValue(5600.0)
                self.deesser_intensity_spin.setValue(0.48 + (0.16 * amount_eff))
                self.stereo_dynamic_cb.setChecked(False)
                if self.dynamic_band_spins:
                    sub = self.dynamic_band_spins.get("Subbass (20-60 Hz)")
                    bass = self.dynamic_band_spins.get("Bass (60-250 Hz)")
                    low_mid = self.dynamic_band_spins.get("Low-Mid (250-500 Hz)")
                    if sub is not None:
                        sub.setValue(min(1.3, 0.3 + (0.7 * amount_eff)))
                    if bass is not None:
                        bass.setValue(max(-0.9, -0.1 - (0.4 * amount_eff)))
                    if low_mid is not None:
                        low_mid.setValue(max(-0.7, -0.1 - (0.25 * amount_eff)))
                if self.multiband_limiter_spins:
                    sub_thr = self.multiband_limiter_spins.get("Subbass (20-60 Hz)")
                    bass_thr = self.multiband_limiter_spins.get("Bass (60-250 Hz)")
                    if sub_thr is not None:
                        sub_thr.setValue(-3.1 - (0.6 * amount_eff))
                    if bass_thr is not None:
                        bass_thr.setValue(-2.6 - (0.6 * amount_eff))
                self.append_log(f"Quick Master: Tight Low (intensidad {amount_eff:.2f})")

            self._enforce_conservative_preset_limits()
            self._enforce_minimal_saturation_caps()
            self._update_process_chain_display()
            self._update_telemetry_indicators()
        
        def _configure_sidebar_for_mode(self, mode: str) -> None:
            """Configura elementos del panel lateral según el modo."""
            # Auto-master siempre visible si hay procesos o en modos Auto-Master
            show_automaster = mode not in ("Solo analizar",)
            
            # En modos Auto-Master, destacar el panel de estilo
            is_auto_master_mode = mode.startswith("Auto-Master")
            
            if hasattr(self, 'auto_master_style_combo'):
                self.auto_master_style_combo.setVisible(show_automaster)
            if hasattr(self, 'auto_master_intelligent_cb'):
                self.auto_master_intelligent_cb.setVisible(False)
            if hasattr(self, 'auto_master_apply_btn'):
                self.auto_master_apply_btn.setVisible(show_automaster)
            
            # Cadenas de proceso
            show_chains = False
            if hasattr(self, 'repair_enabled_cb'):
                self.repair_enabled_cb.setVisible(show_chains)
            if hasattr(self, 'mix_enabled_cb'):
                self.mix_enabled_cb.setVisible(show_chains)
            if hasattr(self, 'master_enabled_cb'):
                self.master_enabled_cb.setVisible(show_chains)

        def _apply_tab_icons(self) -> None:
            try:
                style = self.style()
            except Exception:
                return
            if not hasattr(style, "standardIcon"):
                return
            icon = style.standardIcon
            if self.tabs.count() >= 5:
                tab_icons = {
                    "tab_index_start": QStyle.StandardPixmap.SP_DesktopIcon,
                    "tab_index_project": QStyle.StandardPixmap.SP_DirIcon,
                    "tab_index_auto_master": QStyle.StandardPixmap.SP_DialogApplyButton,
                    "tab_index_processing": QStyle.StandardPixmap.SP_FileDialogDetailedView,
                    "tab_index_results": QStyle.StandardPixmap.SP_BrowserReload,
                    "tab_index_diagnostic": QStyle.StandardPixmap.SP_MessageBoxWarning,
                    "tab_index_ai_text": QStyle.StandardPixmap.SP_FileDialogContentsView,
                    "tab_index_about": QStyle.StandardPixmap.SP_MessageBoxInformation,
                }
                for attr_name, pixmap in tab_icons.items():
                    index = getattr(self, attr_name, None)
                    if isinstance(index, int) and index < self.tabs.count():
                        self.tabs.setTabIcon(index, icon(pixmap))
            if hasattr(self, "results_tabs") and self.results_tabs is not None and self.results_tabs.count() >= 5:
                self.results_tabs.setTabIcon(0, icon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
                self.results_tabs.setTabIcon(1, icon(QStyle.StandardPixmap.SP_MediaPlay))
                self.results_tabs.setTabIcon(2, icon(QStyle.StandardPixmap.SP_DirOpenIcon))
                self.results_tabs.setTabIcon(3, icon(QStyle.StandardPixmap.SP_FileDialogInfoView))
                self.results_tabs.setTabIcon(4, icon(QStyle.StandardPixmap.SP_ComputerIcon))

        def _on_process_item_activated(self, key: str) -> None:
            if not hasattr(self, "process_tabs"):
                return
            if not hasattr(self, "tab_index_process"):
                return
            targets = {
                "input": "process_tab_input_index",
                "repair": "process_tab_repair_index",
                "tone_eq": "process_tab_tone_index",
                "deesser": "process_tab_deesser_index",
                "dynamic_eq": "process_tab_dyn_index",
                "stereo_width": "process_tab_stereo_index",
                "stereo_dynamic": "process_tab_stereo_dynamic_index",
                "saturation": "process_tab_saturation_index",
                "glue": "process_tab_glue_index",
                "loudness": "process_tab_loudness_index",
                "limiter": "process_tab_limiter_index",
                "fades": "process_tab_fades_index",
                "output": "process_tab_output_index",
            }
            attr = targets.get(key)
            if attr is None:
                return
            index = getattr(self, attr, None)
            if isinstance(index, int):
                self.tabs.setCurrentIndex(self.tab_index_process)
                if self.process_tabs is not None:
                    self.process_tabs.setCurrentIndex(index)

        def _apply_button_icons(self) -> None:
            try:
                style = self.style()
            except Exception:
                return
            if not hasattr(style, "standardIcon"):
                return
            icon = style.standardIcon
            self.input_button.setIcon(icon(QStyle.StandardPixmap.SP_FileIcon))
            self.output_button.setIcon(icon(QStyle.StandardPixmap.SP_DialogApplyButton))
            self.batch_input_button.setIcon(icon(QStyle.StandardPixmap.SP_DirOpenIcon))
            self.batch_output_button.setIcon(icon(QStyle.StandardPixmap.SP_DialogApplyButton))
            self.batch_refresh_button.setIcon(icon(QStyle.StandardPixmap.SP_BrowserReload))
            self.batch_process_btn.setIcon(icon(QStyle.StandardPixmap.SP_MediaPlay))
            self.process_btn.setIcon(icon(QStyle.StandardPixmap.SP_MediaPlay))
            self.batch_select_all_btn.setIcon(icon(QStyle.StandardPixmap.SP_DialogYesButton))
            self.batch_select_none_btn.setIcon(icon(QStyle.StandardPixmap.SP_DialogCancelButton))
            self.analyze_btn.setIcon(icon(QStyle.StandardPixmap.SP_FileDialogInfoView))
            self.normalize_btn.setIcon(icon(QStyle.StandardPixmap.SP_DialogApplyButton))
            self.signature_save_btn.setIcon(icon(QStyle.StandardPixmap.SP_DialogYesButton))
            self.signature_delete_btn.setIcon(icon(QStyle.StandardPixmap.SP_DialogCancelButton))
            self.waveform_apply_btn.setIcon(icon(QStyle.StandardPixmap.SP_DialogApplyButton))
            self.waveform_use_global_btn.setIcon(icon(QStyle.StandardPixmap.SP_BrowserReload))

        def _set_progress(
            self,
            current: int | None = None,
            total: int | None = None,
            message: str | None = None,
            indeterminate: bool = False,
        ) -> None:
            if indeterminate:
                self.global_progress_bar.setRange(0, 0)
                self.global_progress_bar.setValue(0)
                self._progress_context = message or "Trabajando..."
                self._progress_detail = ""
                self.global_progress_label.setText(self._progress_context)
                self.progress_popup_bar.setRange(0, 0)
                self.progress_popup_bar.setValue(0)
                self.progress_popup_label.setText(self._format_progress_popup_text(self._progress_context, None))
                return
            if total is None:
                total = 1
            if current is None:
                current = 0
            total = max(1, total)
            current = min(current, total)
            percent = int((current / total) * 100)
            self.global_progress_bar.setRange(0, 100)
            self.global_progress_bar.setValue(percent)
            self.progress_popup_bar.setRange(0, 100)
            self.progress_popup_bar.setValue(percent)
            self._progress_context = message or self._progress_context
            if message:
                self.global_progress_label.setText(f"{message} ({percent}%)")
                self.progress_popup_label.setText(self._format_progress_popup_text(message, percent))
            else:
                self.global_progress_label.setText(f"{percent}%")
                self.progress_popup_label.setText(self._format_progress_popup_text("", percent))

        def _format_progress_popup_text(self, message: str, percent: int | None) -> str:
            text = (message or "").strip()
            if not text:
                return f"{percent}%" if percent is not None else "Listo"
            if " | " in text and len(text) > 120:
                text = text.replace(" | ", "\n")
            if len(text) > 420:
                text = textwrap.shorten(text, width=420, placeholder=" ...")
            if percent is not None:
                return f"{text} ({percent}%)"
            return text

        def _append_process_history(self, message: str) -> None:
            self._process_history_lines.append(message)
            self._process_history_lines = self._process_history_lines[-12:]
            self.process_history_text.setPlainText("\n".join(self._process_history_lines))

        def _append_batch_history(self, lines: list[str]) -> None:
            self._batch_history_lines.extend(lines)
            self._batch_history_lines = self._batch_history_lines[-80:]
            self.process_history_text.setPlainText("\n".join(self._batch_history_lines))

        def _update_process_state(self, message: str, file_name: str | None = None) -> None:
            lower = message.lower()
            state_key = "procesando"
            if any(token in lower for token in ("listo", "completado", "finalizado", "terminó", "terminado")):
                state_key = "finalizado"
            elif any(token in lower for token in ("validando", "re-analizando", "calibrando", "ajustando", "reporte")):
                state_key = "validando"
            elif any(token in lower for token in ("analizando", "pre-analizando")):
                state_key = "analizando"
            elif any(token in lower for token in ("error", "fall", "falló")):
                state_key = "error"
            self.process_state_label.setStyleSheet(self._process_state_styles.get(state_key, self._process_state_styles["listo"]))
            self.process_state_label.setText(f"Estado: {message}")
            if file_name is not None:
                self._current_process_file = file_name
                self.process_file_label.setText(f"Archivo: {file_name}")
            self._append_process_history(message)

        def _extract_file_name_from_progress(self, message: str) -> str | None:
            if ": " not in message:
                return None
            tail = message.rsplit(": ", 1)[-1].strip()
            if tail and "." in tail:
                return tail
            return None

        def _update_results_table(
            self,
            before_stats: Dict[str, float],
            before_voice: object,
            after_stats: object,
            after_voice: object,
            before_rating: object,
            after_rating: object,
        ) -> None:
            # Limpiar cualquier span previo (del placeholder)
            self.results_table.clearSpans()
            
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
            self._update_results_text()

        def _update_results_text(self) -> None:
            # Verificar si hay resultados reales o solo placeholder
            if self.results_table.rowCount() == 0:
                self.results_text.setPlainText("Sin resultados. Procesa un archivo primero.")
                return
            
            # Detectar si es un placeholder (1 fila con span)
            first_item = self.results_table.item(0, 0)
            if first_item and "Procesa un archivo" in first_item.text():
                self.results_text.setPlainText("Sin resultados. Procesa un archivo primero.")
                return
            
            lines: list[str] = []
            headers = ["Métrica", "Antes", "Después"]
            lines.append(" | ".join(headers))
            lines.append("-" * 28)
            for row in range(self.results_table.rowCount()):
                values: list[str] = []
                for col in range(self.results_table.columnCount()):
                    item = self.results_table.item(row, col)
                    values.append(item.text() if item else "-")
                lines.append(" | ".join(values))
            text = "\n".join(lines)
            self.results_text.setPlainText(text)

        def _copy_results_text(self) -> None:
            self._update_results_text()
            text = self.results_text.toPlainText()
            if "Sin resultados" in text:
                QApplication.clipboard().setText("No hay resultados para copiar. Procesa un archivo primero.")
            else:
                QApplication.clipboard().setText(text)

        # ====================================================================
        # MÉTODOS DE DIAGNÓSTICO
        # ====================================================================
        
        def _run_diagnostic(self) -> None:
            """Ejecuta el auto-diagnóstico comparando entrada vs salida."""
            from diagnostics import run_diagnostic, DiagnosticResult
            from config import BAND_CONFIG
            
            input_path = self.input_edit.text().strip()
            output_path = self.output_edit.text().strip()
            
            if not input_path:
                self._update_diagnostic_status("❌ No hay archivo de entrada seleccionado")
                return
            
            if not output_path or not pathlib.Path(output_path).exists():
                self._update_diagnostic_status("❌ No hay archivo de salida. Procesa el audio primero.")
                return
            
            self._update_diagnostic_status("⏳ Iniciando diagnóstico...")
            self._update_diagnostic_progress(0, "Preparando...")
            self.diagnostic_run_btn.setEnabled(False)
            self.diagnostic_copy_btn.setEnabled(False)
            
            # Recopilar parámetros de procesamiento
            processing_params = {
                "Target LUFS": self.target_spin.value(),
                "True Peak": self.true_peak_spin.value(),
                "Loudness Preset": self.preset_combo.currentText(),
                "Output Preset": self.output_preset_combo.currentText(),
                "Fade In": self.fade_in_spin.value(),
                "Fade Out": self.fade_out_spin.value(),
            }
            
            # Lista de procesos activos
            active_processes = []
            if hasattr(self, 'repair_enabled_cb') and self.repair_enabled_cb.isChecked():
                active_processes.append("Reparación")
            if hasattr(self, 'mix_enabled_cb') and self.mix_enabled_cb.isChecked():
                active_processes.append("Mezcla")
            if hasattr(self, 'master_enabled_cb') and self.master_enabled_cb.isChecked():
                active_processes.append("Mastering")
            if hasattr(self, 'deesser_cb') and self.deesser_cb.isChecked():
                active_processes.append("DeEsser")
            if hasattr(self, 'glue_cb') and self.glue_cb.isChecked():
                active_processes.append("Glue Compressor")
            if hasattr(self, 'saturation_enable_cb') and self.saturation_enable_cb.isChecked():
                active_processes.append("Saturación")
            if hasattr(self, 'dynamic_eq_cb') and self.dynamic_eq_cb.isChecked():
                active_processes.append("Dynamic EQ")
            if hasattr(self, 'stereo_width_cb') and self.stereo_width_cb.isChecked():
                active_processes.append("Stereo Width")
            if hasattr(self, 'brickwall_cb') and self.brickwall_cb.isChecked():
                active_processes.append("Brickwall Limiter")
            
            # Callback de progreso usando señales Qt (thread-safe)
            def progress_callback(percent: int, message: str):
                self.diagnostic_progress_signal.emit(percent, message)
            
            def run_in_thread():
                try:
                    result = run_diagnostic(
                        input_path=input_path,
                        output_path=output_path,
                        processing_params=processing_params,
                        active_processes=active_processes,
                        target_lufs=self.target_spin.value(),
                        target_tp=self.true_peak_spin.value(),
                        verbose=False,
                        progress_callback=progress_callback,
                    )
                    return result, None
                except Exception as e:
                    import traceback
                    return None, f"{e}\n{traceback.format_exc()}"
            
            # Ejecutar en hilo separado
            import threading
            def thread_target():
                result, error = run_in_thread()
                # Emitir señal para finalizar en hilo principal
                self.diagnostic_finished_signal.emit(result, error or "")
            
            self._diagnostic_thread = threading.Thread(target=thread_target, daemon=True)
            self._diagnostic_thread.start()

        def _run_spectrum_benchmark(self) -> None:
            """Mide CPU vs GPU para el análisis espectral del audio seleccionado."""
            input_path = self.input_edit.text().strip()
            if not input_path:
                self._update_diagnostic_status("❌ No hay archivo de entrada seleccionado")
                return
            path = pathlib.Path(input_path)
            if not path.exists():
                self._update_diagnostic_status("❌ El archivo de entrada no existe")
                return

            self._update_diagnostic_status("⏳ Ejecutando benchmark de espectro...")
            self._update_diagnostic_progress(0, "Midiendo CPU/GPU...")
            if hasattr(self, "diagnostic_run_btn"):
                self.diagnostic_run_btn.setEnabled(False)
            if hasattr(self, "diagnostic_benchmark_btn"):
                self.diagnostic_benchmark_btn.setEnabled(False)
            if hasattr(self, "diagnostic_copy_btn"):
                self.diagnostic_copy_btn.setEnabled(False)

            def thread_target() -> None:
                try:
                    from spectrum_analyzer import benchmark_spectrum_fft

                    result = benchmark_spectrum_fft(path, duration=10.0, verbose=False, runs=3)
                    self.benchmark_finished_signal.emit(result, "")
                except Exception as e:
                    import traceback
                    self.benchmark_finished_signal.emit(None, f"{e}\n{traceback.format_exc()}")

            import threading
            self._benchmark_thread = threading.Thread(target=thread_target, daemon=True)
            self._benchmark_thread.start()
        
        def _update_diagnostic_progress(self, percent: int, message: str) -> None:
            """Actualiza la barra de progreso del diagnóstico."""
            if self.diagnostic_progress_bar:
                self.diagnostic_progress_bar.setValue(percent)
            if self.diagnostic_progress_label:
                self.diagnostic_progress_label.setText(message)
        
        def _on_diagnostic_finished(self, result, error: str) -> None:
            """Callback cuando el diagnóstico termina (slot conectado a señal)."""
            if error:
                self._update_diagnostic_status(f"❌ Error en diagnóstico: {error.split(chr(10))[0]}")
                self._update_diagnostic_progress(0, "Error")
                self._last_diagnostic_result = None
            else:
                self._last_diagnostic_result = result
                self._update_diagnostic_tables(result)
                self._update_diagnostic_evaluation(result)
                self._update_diagnostic_report(result)
                self.diagnostic_copy_btn.setEnabled(True)
                
                # Contar issues
                n_success = len(result.successes) if result else 0
                n_warn = len(result.warnings) if result else 0
                n_err = len(result.errors) if result else 0
                self._update_diagnostic_status(
                    f"✅ Diagnóstico completado: {n_success} OK, {n_warn} advertencias, {n_err} errores"
                )
            
            self.diagnostic_run_btn.setEnabled(True)
        
        def _update_diagnostic_tables(self, result) -> None:
            """Actualiza las tablas de métricas con los resultados del diagnóstico."""
            from ui.qt_compat import QTableWidgetItem
            
            if not result.input_metrics or not result.output_metrics:
                return
            
            inp = result.input_metrics
            out = result.output_metrics
            
            # === Tabla de métricas generales ===
            metrics_data = [
                ("LUFS (Integrated)", f"{inp.lufs:.1f}", f"{out.lufs:.1f}", result.calculate_difference(inp.lufs, out.lufs)),
                ("True Peak (dBTP)", f"{inp.true_peak:.1f}", f"{out.true_peak:.1f}", result.calculate_difference(inp.true_peak, out.true_peak)),
                ("LRA (LU)", f"{inp.lra:.1f}", f"{out.lra:.1f}", result.calculate_difference(inp.lra, out.lra)),
                ("RMS Total (dB)", f"{inp.rms_total:.1f}", f"{out.rms_total:.1f}", result.calculate_difference(inp.rms_total, out.rms_total)),
                ("Peak Total (dB)", f"{inp.peak_total:.1f}", f"{out.peak_total:.1f}", result.calculate_difference(inp.peak_total, out.peak_total)),
                ("Crest Factor (dB)", f"{inp.crest_factor:.1f}", f"{out.crest_factor:.1f}", result.calculate_difference(inp.crest_factor, out.crest_factor)),
                ("DC Offset", f"{inp.dc_offset:.4f}", f"{out.dc_offset:.4f}", "-"),
            ]
            
            self.diagnostic_metrics_table.setRowCount(len(metrics_data))
            for row, (name, val_in, val_out, diff) in enumerate(metrics_data):
                self.diagnostic_metrics_table.setItem(row, 0, QTableWidgetItem(name))
                self.diagnostic_metrics_table.setItem(row, 1, QTableWidgetItem(val_in))
                self.diagnostic_metrics_table.setItem(row, 2, QTableWidgetItem(val_out))
                item_diff = QTableWidgetItem(diff)
                # Colorear diferencias
                if diff != "-" and diff != "N/A":
                    try:
                        diff_val = float(diff.replace("+", ""))
                        if abs(diff_val) > 3.0:
                            item_diff.setBackground(Qt.GlobalColor.yellow)
                    except ValueError:
                        pass
                self.diagnostic_metrics_table.setItem(row, 3, item_diff)
            
            # === Tabla de bandas ===
            band_names = list(inp.band_rms.keys())
            self.diagnostic_bands_table.setRowCount(len(band_names))
            for row, band_name in enumerate(band_names):
                rms_in = inp.band_rms.get(band_name, -70.0)
                rms_out = out.band_rms.get(band_name, -70.0)
                diff = result.calculate_difference(rms_in, rms_out)
                
                self.diagnostic_bands_table.setItem(row, 0, QTableWidgetItem(band_name))
                self.diagnostic_bands_table.setItem(row, 1, QTableWidgetItem(f"{rms_in:.1f}"))
                self.diagnostic_bands_table.setItem(row, 2, QTableWidgetItem(f"{rms_out:.1f}"))
                item_diff = QTableWidgetItem(diff)
                # Colorear diferencias significativas
                if diff != "N/A":
                    try:
                        diff_val = float(diff.replace("+", ""))
                        if diff_val > 6.0:
                            item_diff.setBackground(Qt.GlobalColor.yellow)
                        elif diff_val > 10.0:
                            item_diff.setBackground(Qt.GlobalColor.red)
                    except ValueError:
                        pass
                self.diagnostic_bands_table.setItem(row, 3, item_diff)
        
        def _update_diagnostic_evaluation(self, result) -> None:
            """Actualiza el texto de evaluación."""
            lines = []
            for msg in result.successes:
                lines.append(msg)
            for msg in result.warnings:
                lines.append(msg)
            for msg in result.errors:
                lines.append(msg)
            
            if not lines:
                lines.append("(Sin evaluación disponible)")
            
            self.diagnostic_eval_text.setPlainText("\n".join(lines))
        
        def _update_diagnostic_report(self, result) -> None:
            """Actualiza el reporte completo."""
            use_markdown = self.diagnostic_markdown_cb.isChecked()
            if use_markdown:
                text = result.to_markdown()
            else:
                text = result.to_text()
            self.diagnostic_report_text.setPlainText(text)
        
        def _update_diagnostic_status(self, msg: str) -> None:
            """Actualiza el label de estado del diagnóstico."""
            if hasattr(self, 'diagnostic_status_label'):
                self.diagnostic_status_label.setText(msg)

        def _format_benchmark_report(self, result: dict) -> str:
            lines: list[str] = []
            lines.append("Benchmark de espectro:")
            lines.append(f"GPU física: {'sí' if result.get('gpu_hardware_available') else 'no'}")
            lines.append(f"Backend GPU: {'sí' if result.get('gpu_backend_available') else 'no'}")
            lines.append(f"CPU promedio: {result.get('cpu_avg_seconds', 0.0):.3f} s")
            gpu_avg = result.get("gpu_avg_seconds")
            if gpu_avg is not None:
                lines.append(f"GPU promedio: {gpu_avg:.3f} s")
            speedup = result.get("speedup")
            if speedup is not None:
                lines.append(f"Speedup GPU/CPU: {speedup:.2f}x")
            lines.append(f"Recomendación: {result.get('recommended_next_stage', 'cpu_only')}")
            if result.get("recommended_next_stage") == "analysis.features":
                lines.append("Siguiente candidato: probar análisis de features en GPU.")
            elif result.get("recommended_next_stage") == "analysis.spectrum":
                lines.append("Siguiente candidato: quedarse en espectro y afinar esta etapa.")
            elif result.get("recommended_next_stage") == "gpu_backend_missing":
                lines.append("Siguiente candidato: instalar o habilitar el backend GPU.")
            else:
                lines.append("Siguiente candidato: mantener CPU-only.")
            return "\n".join(lines)

        def _on_benchmark_finished(self, result, error: str) -> None:
            if error:
                self._update_diagnostic_status(f"❌ Error en benchmark: {error.split(chr(10))[0]}")
                self._update_diagnostic_progress(0, "Error")
            else:
                report = self._format_benchmark_report(result or {})
                if hasattr(self, "diagnostic_report_text"):
                    self.diagnostic_report_text.setPlainText(report)
                self._update_diagnostic_status("✅ Benchmark completado")
                self._update_diagnostic_progress(100, "Benchmark completado")
            if hasattr(self, "diagnostic_run_btn"):
                self.diagnostic_run_btn.setEnabled(True)
            if hasattr(self, "diagnostic_benchmark_btn"):
                self.diagnostic_benchmark_btn.setEnabled(True)
            if hasattr(self, "diagnostic_copy_btn"):
                self.diagnostic_copy_btn.setEnabled(True)
        
        def _copy_diagnostic_to_clipboard(self) -> None:
            """Copia el reporte del diagnóstico al portapapeles."""
            if not hasattr(self, '_last_diagnostic_result') or self._last_diagnostic_result is None:
                QApplication.clipboard().setText("No hay diagnóstico para copiar. Ejecuta el diagnóstico primero.")
                return
            
            use_markdown = self.diagnostic_markdown_cb.isChecked()
            if use_markdown:
                text = self._last_diagnostic_result.to_markdown()
            else:
                text = self._last_diagnostic_result.to_text()
            
            QApplication.clipboard().setText(text)
            self._update_diagnostic_status("📋 Reporte copiado al portapapeles")

        def _update_analysis_summary_text(
            self,
            pre_stats: Dict[str, float] | None,
            pre_band: Dict[str, float] | None,
            pre_voice: object,
            post_stats: Dict[str, float] | None,
            post_band: Dict[str, float] | None,
            post_voice: object,
            pre_rating: str | None,
            post_rating: str | None,
            log: str | None,
        ) -> None:
            lines: list[str] = []
            if pre_stats:
                lines.append("Antes del proceso:")
                lines.append(f"  Input I (LUFS): {pre_stats.get('input_i', 0.0):.2f}")
                lines.append(f"  Input TP (dBTP): {pre_stats.get('input_tp', 0.0):.2f}")
                lines.append(f"  Input LRA (LU): {pre_stats.get('input_lra', 0.0):.2f}")
                if isinstance(pre_voice, (int, float)):
                    lines.append(f"  {VOICE_BAND[0]}: {pre_voice:.2f} dB")
                if pre_band:
                    lines.append("  Bandas (RMS dB):")
                    for label, value in pre_band.items():
                        lines.append(f"    {label}: {value:.2f}")
                if pre_rating:
                    lines.append(f"  Evaluación: {pre_rating}")
            if post_stats:
                lines.append("Despues del proceso:")
                lines.append(f"  Input I (LUFS): {post_stats.get('input_i', 0.0):.2f}")
                lines.append(f"  Input TP (dBTP): {post_stats.get('input_tp', 0.0):.2f}")
                lines.append(f"  Input LRA (LU): {post_stats.get('input_lra', 0.0):.2f}")
                if isinstance(post_voice, (int, float)):
                    lines.append(f"  {VOICE_BAND[0]}: {post_voice:.2f} dB")
                if post_band:
                    lines.append("  Bandas (RMS dB):")
                    for label, value in post_band.items():
                        lines.append(f"    {label}: {value:.2f}")
                if post_rating:
                    lines.append(f"  Evaluación: {post_rating}")
            if log:
                lines.append("FFmpeg (verbose):")
                lines.append("  ---")
                log_lines = log.strip().splitlines()
                cutoff = None
                for idx, entry in enumerate(log_lines):
                    entry_strip = entry.strip()
                    if entry_strip.startswith("Antes del proceso:") or entry_strip.startswith("Despues del proceso:"):
                        cutoff = idx
                        break
                if cutoff is not None:
                    log_lines = log_lines[:cutoff]
                for entry in log_lines:
                    lines.append(f"  {entry}")
                lines.append("  ---")
            self.analysis_summary_text.setPlainText("\n".join(lines))

        def _set_busy(self, busy: bool, message: str | None = None) -> None:
            if busy:
                self._start_resource_monitor()
                self.progress_popup.show()
                self.progress_popup.raise_()
                self.progress_popup.activateWindow()
            self.analyze_btn.setEnabled(not busy)
            self.normalize_btn.setEnabled(not busy)
            self.process_btn.setEnabled(not busy)
            self.batch_process_btn.setEnabled(not busy)
            self.batch_automaster_btn.setEnabled(not busy)
            self.input_button.setEnabled(not busy)
            self.output_button.setEnabled(not busy)
            self.batch_input_button.setEnabled(not busy)
            self.batch_output_button.setEnabled(not busy)
            self.batch_refresh_button.setEnabled(not busy)
            self.batch_table.setEnabled(not busy)
            self.batch_select_all_btn.setEnabled(not busy)
            self.batch_select_none_btn.setEnabled(not busy)
            if message:
                self.append_log(message)
            if not busy:
                self._set_progress(current=0, total=1, message="Listo")
                self.progress_popup_label.setText("Listo")
                self.progress_popup_bar.setRange(0, 1)
                self.progress_popup_bar.setValue(0)

        def _start_resource_monitor(self) -> None:
            if self._resource_monitor_timer is not None:
                return
            timer = QTimer(self)
            timer.setInterval(2500)
            timer.timeout.connect(self._update_resource_snapshot)
            timer.start()
            self._resource_monitor_timer = timer

        def _update_resource_snapshot(self) -> None:
            if not hasattr(self, "log_view") or not hasattr(self, "process_state_label"):
                return
            snapshot = self._resource_monitor.snapshot()
            if snapshot == self._last_resource_snapshot:
                return
            self._last_resource_snapshot = snapshot
            profile = self._resource_monitor.classify(snapshot)
            if profile != self._last_resource_profile:
                self._last_resource_profile = profile
                self.append_log(f"Perfil de recursos: {profile.format_summary()}")
            gpu_summary = self._resource_monitor.format_gpu_summary()
            if gpu_summary != self._last_resource_gpu_summary and gpu_summary != "GPU no disponible":
                self._last_resource_gpu_summary = gpu_summary
                self.append_log(f"GPU: {gpu_summary}")
            busy = bool(self._current_thread and self._current_thread.isRunning())
            if busy:
                self.append_log(f"Recursos: {snapshot.format_summary()}")

        def _apply_resource_profile(self) -> None:
            if not hasattr(self, "log_view"):
                return
            budget = self._resource_governor.apply(self._resource_profile_override)
            self._current_processing_budget = budget
            self._last_resource_profile = budget.profile
            self._last_resource_gpu_summary = budget.gpu.format_summary()
            limits = {
                "max_ffmpeg_processes": budget.cpu.max_ffmpeg_processes,
                "ffmpeg_threads_per_process": budget.cpu.ffmpeg_threads_per_process,
            }
            save_resource_profile_name(budget.profile.name)
            self.append_log(
                "Governor activo: "
                f"{budget.format_summary()} | "
                f"FFmpeg {limits['max_ffmpeg_processes']}x{limits['ffmpeg_threads_per_process']}"
            )

        def _on_resource_profile_changed(self, text: str) -> None:
            if not hasattr(self, "log_view"):
                self._resource_profile_override = None if text.strip().lower() == "auto" else text.strip()
                return
            text = text.strip()
            if text.lower() == "auto":
                self._resource_profile_override = None
                clear_resource_profile_name()
                self.append_log("Perfil de recursos: Auto")
                self._apply_resource_profile()
                return
            profile = self._resource_monitor.profile_by_name(text)
            if profile is None:
                return
            self._resource_profile_override = profile.name
            save_resource_profile_name(profile.name)
            self.append_log(f"Perfil de recursos fijado manualmente: {profile.name}")
            self._apply_resource_profile()

        def _handle_worker_progress(self, *args) -> None:
            if len(args) >= 3 and isinstance(args[1], int) and isinstance(args[2], int):
                message = str(args[0])
                current = args[1]
                total = args[2]
                self._set_progress(current=current, total=total, message=message)
                self.append_log(message)
                self._update_process_state(message, self._extract_file_name_from_progress(message))
            elif args:
                message = str(args[0])
                self.append_log(message)
                self._update_process_state(message, self._extract_file_name_from_progress(message))

        def _handle_worker_processing_progress(self, percent: float, time_str: str) -> None:
            percent = max(0.0, min(100.0, float(percent)))
            current_value = int(percent)
            self.global_progress_bar.setRange(0, 100)
            self.global_progress_bar.setValue(current_value)
            self.progress_popup_bar.setRange(0, 100)
            self.progress_popup_bar.setValue(current_value)
            context = self._progress_context or "Procesando"
            detail = f"{context} · {time_str}"
            self._progress_detail = detail
            self.global_progress_label.setText(f"{detail} ({current_value}%)")
            self.progress_popup_label.setText(self._format_progress_popup_text(detail, current_value))

        def _on_mode_changed(self, allow_navigation: bool = True) -> None:
            mode = self.mode_combo.currentText()
            if not self._mode_initialized and not allow_navigation:
                self._show_only_start_tab()
                return
            if mode == "Generar con IA":
                self._show_tabs_for_mode(mode)
                if allow_navigation:
                    self.tabs.setCurrentIndex(self.tab_index_ai_text)
                self.analyze_only_cb.setEnabled(False)
                self._set_results_tabs_visibility(single=False)
                self._update_action_buttons(mode)
                self._mode_initialized = True
                return
            if mode == "Auto-Master (Lote)":
                self._show_tabs_for_mode(mode)
                if allow_navigation:
                    self.tabs.setCurrentIndex(self.tab_index_batch)
                self.analyze_only_cb.setEnabled(True)
                self._set_results_tabs_visibility(single=False)
            elif mode == "Solo analizar":
                self._show_tabs_for_mode(mode)
                if allow_navigation:
                    self.tabs.setCurrentIndex(self.tab_index_audio)
                self.analyze_only_cb.setChecked(True)
                self.analyze_only_cb.setEnabled(False)
                self._set_results_tabs_visibility(single=True)
            else:
                self._show_tabs_for_mode(mode)
                if allow_navigation:
                    self.tabs.setCurrentIndex(self.tab_index_audio)
                self.analyze_only_cb.setEnabled(True)
                self._set_results_tabs_visibility(single=True)
            self._update_action_buttons(mode)
            self._mode_initialized = True
            self._set_waveform_visible(True)
            self._refresh_waveform_tab_list()

        def is_inicio_activo(self) -> bool:
            return self.tabs.currentWidget() == self.tab_start

        def append_log(self, message: str) -> None:
            self.log_signal.emit(message)

        def _ensure_log_resolution_marker(self) -> None:
            marker_payload = {
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "app_version": APP_VERSION,
                "issues": HISTORICAL_LOG_FIXES,
            }
            try:
                existing: dict[str, Any] | None = None
                if self.log_resolution_marker_path.exists():
                    with self.log_resolution_marker_path.open("r", encoding="utf-8") as handle:
                        loaded = json.load(handle)
                    if isinstance(loaded, dict):
                        existing = loaded
                should_write = True
                if isinstance(existing, dict):
                    same_version = existing.get("app_version") == APP_VERSION
                    same_issues = existing.get("issues") == HISTORICAL_LOG_FIXES
                    if same_version and same_issues:
                        should_write = False
                if should_write:
                    with self.log_resolution_marker_path.open("w", encoding="utf-8") as handle:
                        json.dump(marker_payload, handle, ensure_ascii=False, indent=2)
            except Exception:
                pass

        def _rotate_main_log_if_needed(self) -> None:
            try:
                if not self.log_file_path.exists():
                    return
                if self.log_file_path.stat().st_size < LOG_ROTATE_MAX_BYTES:
                    return
                oldest_backup = self.log_file_path.with_name(
                    f"{self.log_file_path.name}.{LOG_ROTATE_KEEP_FILES}"
                )
                if oldest_backup.exists():
                    oldest_backup.unlink()
                for idx in range(LOG_ROTATE_KEEP_FILES - 1, 0, -1):
                    src = self.log_file_path.with_name(f"{self.log_file_path.name}.{idx}")
                    dst = self.log_file_path.with_name(f"{self.log_file_path.name}.{idx + 1}")
                    if src.exists():
                        src.replace(dst)
                self.log_file_path.replace(self.log_file_path.with_name(f"{self.log_file_path.name}.1"))
            except Exception:
                pass

        def _append_log_gui(self, message: str) -> None:
            self.log_view.appendPlainText(message)
            self.progress_popup_log.appendPlainText(message)
            doc = self.progress_popup_log.document()
            if doc is not None and doc.blockCount() > self._progress_popup_max_lines:
                lines = self.progress_popup_log.toPlainText().splitlines()
                keep = lines[-self._progress_popup_max_lines:]
                self.progress_popup_log.setPlainText("\n".join(keep))
            try:
                self._rotate_main_log_if_needed()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with self.log_file_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{timestamp} {message}\n")
            except Exception:
                pass

        def _show_error(self, message: str) -> None:
            self.append_log(f"Error: {message}")

        def _clear_log_view(self) -> None:
            self.log_view.clear()
            self.progress_popup_log.clear()

        def _copy_log_path(self) -> None:
            QApplication.clipboard().setText(str(self.log_file_path))

        def _load_log_history(self) -> None:
            self.log_history_list = []
            self.log_history_table.setRowCount(0)
            if not self.log_history_path.exists():
                return
            try:
                with self.log_history_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(entry, dict):
                            self._append_log_history_entry(entry, persist=False)
            except Exception:
                pass

        def _append_log_history_entry(self, entry: dict, persist: bool = True) -> None:
            self.log_history_list.append(entry)
            row = self.log_history_table.rowCount()
            self.log_history_table.insertRow(row)
            is_summary_entry = "resumen" in str(entry.get("action", "")).lower()
            values = [
                entry.get("timestamp", "-"),
                entry.get("action", "-"),
                entry.get("mode", "-"),
                entry.get("input", "-"),
                entry.get("output", "-"),
                entry.get("style", "-"),
                entry.get("processes", "-"),
                entry.get("lufs", "-"),
                entry.get("true_peak", "-"),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                if is_summary_entry:
                    item.setBackground(Qt.GlobalColor.yellow)
                self.log_history_table.setItem(row, col, item)
            if persist:
                try:
                    with self.log_history_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass

        def _record_log_history(
            self,
            action: str,
            input_path: pathlib.Path | None,
            output_path: object,
            pre_stats: Dict[str, float] | None,
            post_stats: object,
            log_text_override: str | None = None,
        ) -> None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mode = self.mode_combo.currentText()
            style = self.auto_master_style_combo.currentText()
            processes = ", ".join(self._get_enabled_process_labels())
            resource_summary = self._last_resource_snapshot.format_summary() if self._last_resource_snapshot else None
            gpu_summary = self._last_resource_gpu_summary if self._last_resource_gpu_summary else None
            budget_summary = (
                self._current_processing_budget.format_summary()
                if getattr(self, "_current_processing_budget", None) is not None
                else None
            )
            lufs_text = "-"
            tp_text = "-"
            if isinstance(pre_stats, dict):
                pre_lufs = pre_stats.get("input_i")
                pre_tp = pre_stats.get("input_tp")
            else:
                pre_lufs = None
                pre_tp = None
            post_lufs = None
            post_tp = None
            if isinstance(post_stats, dict):
                post_lufs = post_stats.get("input_i")
                post_tp = post_stats.get("input_tp")
            if isinstance(pre_lufs, (float, int)) or isinstance(post_lufs, (float, int)):
                lufs_text = f"{pre_lufs:.2f} -> {post_lufs:.2f}" if isinstance(post_lufs, (float, int)) else f"{pre_lufs:.2f}"
            if isinstance(pre_tp, (float, int)) or isinstance(post_tp, (float, int)):
                tp_text = f"{pre_tp:.2f} -> {post_tp:.2f}" if isinstance(post_tp, (float, int)) else f"{pre_tp:.2f}"
            entry = {
                "timestamp": timestamp,
                "action": action,
                "mode": mode,
                "input": str(input_path) if input_path else "-",
                "output": str(output_path) if output_path else "-",
                "style": style,
                "processes": processes,
                "lufs": lufs_text,
                "true_peak": tp_text,
                "resources": resource_summary,
                "gpu": gpu_summary,
                "budget": budget_summary,
                "log_text": log_text_override if log_text_override is not None else self.log_view.toPlainText(),
            }
            self._append_log_history_entry(entry, persist=True)

        def _collect_process_settings(self) -> Dict[str, Any]:
            return {
                "tone_eq": {
                    "preset": self.tone_eq_preset_combo.currentText(),
                    "low_db": self.eq_low_spin.value(),
                    "mid_db": self.eq_mid_spin.value(),
                    "high_db": self.eq_high_spin.value(),
                    "tilt_db": self.tilt_eq_spin.value(),
                },
                "dynamic_eq": {
                    "preset": self.dynamic_eq_preset_combo.currentText(),
                    "enabled": self.dynamic_eq_cb.isChecked(),
                    "band_db": {label: spin.value() for label, spin in self.dynamic_band_spins.items()},
                },
                "deesser": {
                    "preset": self.deesser_preset_combo.currentText(),
                    "enabled": self.deesser_cb.isChecked(),
                    "freq_hz": self.deesser_freq_spin.value(),
                    "intensity": self.deesser_intensity_spin.value(),
                },
                "glue": {
                    "preset": self.glue_preset_combo.currentText(),
                    "enabled": self.glue_cb.isChecked(),
                    "threshold_db": self.glue_threshold_spin.value(),
                    "ratio": self.glue_ratio_spin.value(),
                    "attack_ms": self.glue_attack_spin.value(),
                    "release_ms": self.glue_release_spin.value(),
                    "makeup_db": self.glue_makeup_spin.value(),
                },
                "stereo": {
                    "width_enabled": self.stereo_width_cb.isChecked(),
                    "band_widths": {label: spin.value() for label, spin in self.stereo_band_spins.items()},
                },
                "stereo_dynamic": {
                    "enabled": self.stereo_dynamic_cb.isChecked(),
                    "threshold_db": self.stereo_dynamic_threshold_spin.value(),
                    "ratio": self.stereo_dynamic_ratio_spin.value(),
                    "attack_ms": self.stereo_dynamic_attack_spin.value(),
                    "release_ms": self.stereo_dynamic_release_spin.value(),
                    "mix": self.stereo_dynamic_mix_spin.value(),
                    "band_mix": {label: spin.value() for label, spin in self.stereo_dynamic_band_mix_spins.items()},
                },
                "saturation": {
                    "enabled": self.saturation_enable_cb.isChecked(),
                    "per_band_enabled": self.saturation_per_band_cb.isChecked(),
                    "type": self.saturation_type_combo.currentText(),
                    "drive_db": self.saturation_drive_spin.value(),
                    "mix": self.saturation_mix_spin.value(),
                    "band_drive_db": {label: spin.value() for label, spin in self.saturation_band_drive_spins.items()},
                    "band_mix": {label: spin.value() for label, spin in self.saturation_band_mix_spins.items()},
                },
                "limiter": {
                    "preset": self.limiter_preset_combo.currentText(),
                    "ceiling_db": self.limiter_ceiling_spin.value(),
                    "release_ms": self.limiter_release_spin.value(),
                    "brickwall": self.brickwall_cb.isChecked(),
                },
                "repair": {
                    "auto": self.auto_repair_cb.isChecked(),
                    "noise_reduction": self.noise_reduction_combo.currentText(),
                    "declip": self.declip_combo.currentText(),
                    "declick": self.declick_combo.currentText(),
                },
                "misc": {
                    "auto_band_gain": self.auto_band_gain_cb.isChecked(),
                },
                "auto_master": {
                    "intelligent": self.auto_master_intelligent_cb.isChecked(),
                    "minimal_lra_threshold": self.auto_master_min_lra_spin.value(),
                    "minimal_crest_threshold": self.auto_master_min_crest_spin.value(),
                    "motion_preset": self.auto_master_motion_preset_combo.currentText(),
                    "motion_profile": self.auto_master_motion_profile_combo.currentText(),
                    "motion_amount_percent": self.auto_master_motion_amount_spin.value(),
                },
            }

        def _write_auto_master_preset(self, style: str) -> None:
            safe_name = "".join(ch.lower() for ch in style if ch.isalnum() or ch in ("_", "-")).strip("_-")
            if not safe_name:
                safe_name = "preset"
            preset_dir = self.log_file_path.parent / "presets"
            preset_dir.mkdir(parents=True, exist_ok=True)
            preset_path = preset_dir / f"auto_master_{safe_name}.toml"
            data = self._collect_process_settings()
            lines = [f'style = "{style}"']
            for section, values in data.items():
                lines.append("")
                lines.append(f"[{section}]")
                for key, val in values.items():
                    if isinstance(val, dict):
                        lines.append("")
                        lines.append(f"[{section}.{key}]")
                        for sub_key, sub_val in val.items():
                            lines.append(f'{sub_key} = {json.dumps(sub_val, ensure_ascii=False)}')
                    else:
                        lines.append(f'{key} = {json.dumps(val, ensure_ascii=False)}')
            preset_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.append_log(f"Auto-master preset guardado -> {preset_path}")

        def _load_selected_history_log(self) -> None:
            row = self.log_history_table.currentRow()
            if row < 0 or row >= len(self.log_history_list):
                return
            entry = self.log_history_list[row]
            log_text = entry.get("log_text", "")
            if isinstance(log_text, str):
                self.log_view.setPlainText(log_text)
            self._load_inspector_from_entry(entry)

        def _browse_inspector_mts(self) -> None:
            start_dir = str(self.log_file_path.parent)
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar archivo MTS",
                start_dir,
                "MTS JSON (*.mts.json);;JSON (*.json)",
            )
            if not selected:
                return
            self.inspector_mts_path_edit.setText(selected)
            self._load_inspector_from_current_path()

        def _resolve_inspector_paths_from_mts_json(self, mts_json_path: pathlib.Path) -> dict[str, pathlib.Path]:
            stem = mts_json_path.name
            if stem.endswith(".mts.json"):
                base = stem[:-9]
            else:
                base = mts_json_path.stem
            parent = mts_json_path.parent
            return {
                "mts": mts_json_path,
                "decisions": parent / f"{base}.master_decisions.json",
                "shadow": parent / f"{base}.adaptive_shadow.json",
                "guard": parent / f"{base}.adaptive_guard.json",
            }

        def _load_json_if_exists(self, path: pathlib.Path) -> dict[str, Any] | None:
            try:
                if not path.exists():
                    return None
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                return None
            return None

        def _render_inspector_report(
            self,
            mts_data: dict[str, Any] | None,
            decisions_data: dict[str, Any] | None,
            shadow_data: dict[str, Any] | None,
            paths: dict[str, pathlib.Path],
        ) -> str:
            lines: list[str] = []
            lines.append("Inspector MTS")
            lines.append("")
            lines.append(f"MTS: {paths['mts']}")
            lines.append(f"Decisions: {paths['decisions']}")
            lines.append(f"Shadow: {paths['shadow']}")
            lines.append(f"Guard: {paths['guard']}")
            lines.append("")

            if not mts_data:
                lines.append("No se pudo cargar el archivo MTS.")
                return "\n".join(lines)

            source = mts_data.get("source", {}) if isinstance(mts_data.get("source"), dict) else {}
            summary = mts_data.get("summary", {}) if isinstance(mts_data.get("summary"), dict) else {}
            sections = mts_data.get("sections", [])
            events = mts_data.get("events", [])
            lines.append("Resumen")
            lines.append(f"- Duración: {source.get('duration_seconds', '-')}")
            lines.append(f"- Frames: {summary.get('frames', '-')}")
            lines.append(f"- RMS avg: {summary.get('rms_avg_db', '-')}")
            lines.append(f"- Peak max: {summary.get('peak_max_db', '-')}")
            lines.append(f"- Secciones: {summary.get('sections_count', 0)}")
            lines.append(f"- Eventos agregados: {len(events) if isinstance(events, list) else 0}")
            lines.append("")

            lines.append("Secciones")
            if isinstance(sections, list) and sections:
                for sec in sections[:20]:
                    lines.append(
                        f"- {sec.get('label', 'section')} "
                        f"[{sec.get('start_s', 0)}s - {sec.get('end_s', 0)}s] "
                        f"conf={sec.get('confidence', 0)}"
                    )
            else:
                lines.append("- none")
            lines.append("")

            lines.append("Eventos")
            if isinstance(events, list) and events:
                for ev in events[:30]:
                    lines.append(
                        f"- {ev.get('type', 'event')} "
                        f"[{ev.get('start_s', 0)}s - {ev.get('end_s', 0)}s] "
                        f"sev={ev.get('severity', 'low')} conf={ev.get('confidence', 0)}"
                    )
            else:
                lines.append("- none")
            lines.append("")

            lines.append("Decisiones")
            if decisions_data and isinstance(decisions_data.get("section_decisions"), list):
                for dec in decisions_data["section_decisions"][:20]:
                    actions = dec.get("actions", {}) if isinstance(dec.get("actions"), dict) else {}
                    lines.append(
                        f"- {dec.get('label', 'section')} "
                        f"[{dec.get('start_s', 0)}s - {dec.get('end_s', 0)}s] "
                        f"eq={actions.get('eq_db', {})} "
                        f"deesser={actions.get('deesser_intensity_delta', 0)} "
                        f"sat={actions.get('saturation_mix_mult', 1)}"
                    )
            else:
                lines.append("- no disponible")
            lines.append("")

            lines.append("Adaptive Shadow")
            if shadow_data:
                sh_summary = shadow_data.get("summary", {}) if isinstance(shadow_data.get("summary"), dict) else {}
                lines.append(f"- Mode: {shadow_data.get('mode', '-')}")
                lines.append(f"- Global risk: {sh_summary.get('global_risk', '-')}")
                lines.append(f"- Apply ready: {sh_summary.get('apply_ready', '-')}")
                recs = shadow_data.get("recommendations", [])
                if isinstance(recs, list):
                    for rec in recs[:10]:
                        lines.append(f"  • {rec}")
            else:
                lines.append("- no disponible")
            return "\n".join(lines)

        def _load_inspector_from_mts_json(self, mts_json_path: pathlib.Path) -> bool:
            paths = self._resolve_inspector_paths_from_mts_json(mts_json_path)
            mts_data = self._load_json_if_exists(paths["mts"])
            decisions_data = self._load_json_if_exists(paths["decisions"])
            shadow_data = self._load_json_if_exists(paths["shadow"])
            guard_data = self._load_json_if_exists(paths["guard"])
            report = self._render_inspector_report(mts_data, decisions_data, shadow_data, paths)
            if guard_data:
                lines = [report, "", "Adaptive Guard"]
                summary = guard_data.get("checks", [])
                lines.append(f"- Overall OK: {guard_data.get('overall_ok', '-')}")
                lines.append(f"- Recommended mode: {guard_data.get('recommended_mode', '-')}")
                lines.append(f"- Shadow forced: {guard_data.get('shadow_mode_forced', '-')}")
                blockers = guard_data.get("blockers", [])
                if isinstance(blockers, list) and blockers:
                    lines.append("  Blockers:")
                    for item in blockers[:10]:
                        lines.append(f"  • {item}")
                warnings = guard_data.get("warnings", [])
                if isinstance(warnings, list) and warnings:
                    lines.append("  Warnings:")
                    for item in warnings[:10]:
                        lines.append(f"  • {item}")
                if isinstance(summary, list):
                    lines.append(f"- Checks: {len(summary)}")
                report = "\n".join(lines)
            self.inspector_text.setPlainText(report)
            self.inspector_mts_path_edit.setText(str(paths["mts"]))
            return mts_data is not None

        def _load_inspector_from_current_path(self) -> None:
            raw = self.inspector_mts_path_edit.text().strip()
            if not raw:
                self.inspector_text.setPlainText("Inspector: selecciona un archivo .mts.json.")
                return
            mts_path = pathlib.Path(raw)
            if not mts_path.exists():
                self.inspector_text.setPlainText(f"Inspector: archivo no encontrado -> {mts_path}")
                return
            self._load_inspector_from_mts_json(mts_path)

        def _find_mts_for_output_path(self, output_path: pathlib.Path) -> pathlib.Path | None:
            log_dir = output_path.parent / "log"
            mts_path = log_dir / f"{output_path.stem}.mts.json"
            if mts_path.exists():
                return mts_path
            return None

        def _load_inspector_from_entry(self, entry: dict[str, Any]) -> None:
            output_value = entry.get("output")
            if isinstance(output_value, str) and output_value.strip():
                out_path = pathlib.Path(output_value.strip())
                mts = self._find_mts_for_output_path(out_path)
                if mts is not None:
                    self._load_inspector_from_mts_json(mts)

        def _load_inspector_from_history_selection(self) -> None:
            row = self.log_history_table.currentRow()
            if row < 0 or row >= len(self.log_history_list):
                self.inspector_text.setPlainText("Inspector: selecciona una fila del historial.")
                return
            entry = self.log_history_list[row]
            self._load_inspector_from_entry(entry)

        def _get_enabled_process_labels(self) -> list[str]:
            items = [
                ("DC offset", self.dc_offset_cb),
                ("Auto repair", self.auto_repair_cb),
                ("EQ dinámica", self.dynamic_eq_cb),
                ("Stereo width", self.stereo_width_cb),
                ("De-Esser", self.deesser_cb),
                ("Stereo dinámico", self.stereo_dynamic_cb),
                ("Saturación", self.saturation_enable_cb),
                ("Saturación/bandas", self.saturation_per_band_cb),
                ("Glue", self.glue_cb),
                ("Brickwall", self.brickwall_cb),
                ("Auto-gain bandas", self.auto_band_gain_cb),
            ]
            return [label for label, cb in items if cb.isChecked()]

        def _update_spectrum_display(
            self,
            pre_path: pathlib.Path | None,
            post_path: pathlib.Path | None,
            pre_band_stats: Dict[str, float] | None,
            post_band_stats: Dict[str, float] | None,
        ) -> None:
            if not pre_path or not pre_path.exists():
                self.spectrum_diag.setPlainText("Sin audio para analizar.")
                return
            pre_spectrum = compute_spectrum(pre_path)
            post_spectrum = compute_spectrum(post_path) if post_path and post_path.exists() else None
            if pre_spectrum and self.spectrum_curve_pre is not None:
                pre_freqs, pre_mags = pre_spectrum
                self.spectrum_curve_pre.setData(pre_freqs, pre_mags)
            elif self.spectrum_curve_pre is not None:
                self.spectrum_curve_pre.setData([], [])
            post_freqs = None
            post_mags = None
            if post_spectrum and self.spectrum_curve_post is not None:
                post_freqs, post_mags = post_spectrum
                self.spectrum_curve_post.setData(post_freqs, post_mags)
            elif self.spectrum_curve_post is not None:
                self.spectrum_curve_post.setData([], [])
            if (
                self.spectrum_curve_conflict is not None
                and pre_spectrum
                and post_freqs is not None
                and post_mags is not None
            ):
                pre_freqs, pre_mags = pre_spectrum
                count = min(len(pre_freqs), len(post_freqs))
                diffs = [post_mags[i] - pre_mags[i] for i in range(count)]
                conflict_freqs: list[float] = []
                conflict_vals: list[float] = []
                for i in range(count):
                    if abs(diffs[i]) >= 2.0:
                        conflict_freqs.append(pre_freqs[i])
                        conflict_vals.append(post_mags[i])
                    else:
                        conflict_freqs.append(pre_freqs[i])
                        conflict_vals.append(float("nan"))
                self.spectrum_curve_conflict.setData(conflict_freqs, conflict_vals)
            elif self.spectrum_curve_conflict is not None:
                self.spectrum_curve_conflict.setData([], [])
            diag_lines = ["Diagnóstico de espectro:"]

            def _diag(prefix: str, stats: Dict[str, float] | None) -> None:
                if not stats:
                    return
                values = list(stats.values())
                avg = sum(values) / len(values)

                def _avg(labels: list[str]) -> float | None:
                    vals = [stats[label] for label in labels if label in stats]
                    return sum(vals) / len(vals) if vals else None

                low = _avg(["Subbass (20-60 Hz)", "Bass (60-250 Hz)"])
                mid = _avg(["Low-Mid (250-500 Hz)", "Mid (500-2k Hz)"])
                high = _avg(["High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"])
                any_flag = False
                if low is not None:
                    if low > avg + 2.0:
                        diag_lines.append(f"{prefix} graves elevados.")
                        any_flag = True
                    elif low < avg - 2.0:
                        diag_lines.append(f"{prefix} graves bajos.")
                        any_flag = True
                if mid is not None:
                    if mid > avg + 2.0:
                        diag_lines.append(f"{prefix} medios fuertes.")
                        any_flag = True
                    elif mid < avg - 2.0:
                        diag_lines.append(f"{prefix} medios hundidos.")
                        any_flag = True
                if high is not None:
                    if high > avg + 2.0:
                        diag_lines.append(f"{prefix} agudos brillantes.")
                        any_flag = True
                    elif high < avg - 2.0:
                        diag_lines.append(f"{prefix} agudos apagados.")
                        any_flag = True
                if not any_flag:
                    diag_lines.append(f"{prefix} balance general OK.")

            _diag("Pre:", pre_band_stats)
            if post_band_stats:
                _diag("Post:", post_band_stats)
            self.spectrum_diag.setPlainText("\n".join(diag_lines))

        def _apply_band_suggestions_dynamic(self, band_stats: Dict[str, float]) -> None:
            if self.tabs.currentIndex() != self.tab_index_auto_master:
                return
            if not band_stats or not self.dynamic_band_spins:
                return
            if self.dynamic_eq_preset_combo.currentText() != "Manual":
                self.dynamic_eq_preset_combo.setCurrentText("Manual")
                self._apply_dynamic_eq_preset()
            band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_cb.isChecked() else DEFAULT_BAND_RANGE_DB
            max_adjust = TRANSPARENT_MAX_ADJUST_DB if self.transparent_cb.isChecked() else DEFAULT_MAX_ADJUST_DB
            values = list(band_stats.values())
            avg = sum(values) / len(values)
            bright_highs = False
            high_mid_val = band_stats.get("High-Mid (2k-6k Hz)")
            air_val = band_stats.get("Air (6k-16k Hz)")
            for val in (
                high_mid_val,
                air_val,
            ):
                if isinstance(val, (float, int)) and val > avg + 2.0:
                    bright_highs = True
                    break
            sensitive_highs_hot = bool(
                (isinstance(high_mid_val, (float, int)) and (high_mid_val > avg + 1.2 or high_mid_val > -24.0))
                or (isinstance(air_val, (float, int)) and (air_val > avg + 1.2 or air_val > -24.0))
            )
            applied: list[str] = []
            for label, value in band_stats.items():
                spin = self.dynamic_band_spins.get(label)
                if spin is None:
                    continue
                diff = value - avg
                if abs(diff) <= band_range:
                    target = 0.0
                else:
                    extra = max(0.5, abs(diff) - band_range)
                    target = min(max_adjust, extra)
                    if diff > 0:
                        target = -target
                if bright_highs and target > 0:
                    target = min(target, max_adjust - 1.0)
                if (
                    self.deesser_cb.isChecked()
                    and diff > 0
                    and label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)")
                ):
                    target = max(-max_adjust, target - 1.5)
                if label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)") and target > 0:
                    if sensitive_highs_hot:
                        target = min(target, 0.0)
                    elif self.deesser_cb.isChecked():
                        target = min(target, 0.6)
                    else:
                        target = min(target, 1.0)
                spin.setValue(target)
                applied.append(f"{label} {target:+.1f} dB")
            if applied:
                self._update_dynamic_band_plot()
                self.append_log("Auto-master ajustó EQ dinámica: " + ", ".join(applied))

        def _auto_configure_fades(self, audio_path: pathlib.Path) -> None:
            if self.tabs.currentIndex() != self.tab_index_auto_master:
                return
            if not audio_path or not audio_path.exists():
                return
            fade_in, fade_out, detail = analyze_silence_edges(audio_path)
            self.fade_in_spin.setValue(DEFAULT_SUBTLE_FADE_IN_S)
            self.fade_out_spin.setValue(DEFAULT_SUBTLE_FADE_OUT_S)
            if fade_in > 0 or fade_out > 0:
                self.append_log(
                    f"Auto-master detectó silencios en bordes ({detail}); se recortan en render y se aplican fades sutiles "
                    f"({DEFAULT_SUBTLE_FADE_IN_S:.2f}s/{DEFAULT_SUBTLE_FADE_OUT_S:.2f}s)."
                )

        def _append_auto_master_summary_to_log(self) -> None:
            summary = self.auto_master_notes.toPlainText().strip()
            if summary:
                self.append_log("Auto-Master resumen:")
                for line in summary.splitlines():
                    self.append_log(f"- {line}")
            enabled = self._get_enabled_process_labels()
            if enabled:
                self.append_log("Auto-Master procesos activos: " + ", ".join(enabled))

        def _auto_adjust_processes(
            self,
            stats: Dict[str, float],
            band_stats: Dict[str, float],
            voice_rms: object,
        ) -> None:
            if self.tabs.currentIndex() != self.tab_index_auto_master:
                return
            band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_cb.isChecked() else DEFAULT_BAND_RANGE_DB
            input_i = stats.get("input_i", 0.0)
            input_tp = stats.get("input_tp", -99.0)
            input_lra = stats.get("input_lra", 0.0)
            target_lufs = self.target_spin.value()
            changes: list[str] = []
            last_adjustments = getattr(self, "_last_auto_master_adjustments", None)
            auto_master_profile = "Normal"
            if isinstance(last_adjustments, dict):
                auto_master_profile = str(last_adjustments.get("processing_profile", auto_master_profile) or auto_master_profile)

            def set_check(cb: QCheckBox, value: bool, label: str) -> None:
                if cb.isChecked() != value:
                    cb.setChecked(value)
                    changes.append(f"{label}: {'ON' if value else 'OFF'}")

            max_dev = 0.0
            if band_stats:
                values = list(band_stats.values())
                avg = sum(values) / len(values)
                max_dev = max(abs(val - avg) for val in values)
            need_dynamic = bool(band_stats) and max_dev > band_range
            set_check(self.dynamic_eq_cb, need_dynamic, "EQ dinámica")

            mid = band_stats.get("Mid (500-2k Hz)") if band_stats else None
            high_mid = band_stats.get("High-Mid (2k-6k Hz)") if band_stats else None
            air = band_stats.get("Air (6k-16k Hz)") if band_stats else None
            sibilant = False
            bright_highs = False
            if isinstance(mid, (float, int)):
                for val in (high_mid, air):
                    if isinstance(val, (float, int)) and val > mid + 2.0:
                        sibilant = True
                        break
            if not sibilant and isinstance(voice_rms, (float, int)) and isinstance(mid, (float, int)):
                sibilant = voice_rms > mid + 2.0
            set_check(self.deesser_cb, sibilant, "De-Esser")
            if sibilant and band_stats:
                values = list(band_stats.values())
                avg = sum(values) / len(values)
                low_mid = band_stats.get("Low-Mid (250-500 Hz)")
                voice_preset = None
                if isinstance(air, (float, int)) and air >= avg + 3.0:
                    voice_preset = "Soprano (8.0 kHz / 0.75)"
                elif isinstance(high_mid, (float, int)) and high_mid >= avg + 2.0:
                    voice_preset = "Tenor (6.5 kHz / 0.70)"
                elif isinstance(low_mid, (float, int)) and low_mid >= avg + 2.0:
                    voice_preset = "Baritono (5.5 kHz / 0.65)"
                else:
                    voice_preset = "Voz hablada (5.5 kHz / 0.60)"
                if voice_preset and self.deesser_preset_combo.currentText() != voice_preset:
                    self.deesser_preset_combo.setCurrentText(voice_preset)
                    self._apply_deesser_preset()
                    changes.append(f"De-Esser preset: {voice_preset}")
            if band_stats:
                values = list(band_stats.values())
                avg = sum(values) / len(values)
                for val in (high_mid, air):
                    if isinstance(val, (float, int)) and val > avg + 2.0:
                        bright_highs = True
                        break
            if sibilant:
                if self.deesser_freq_spin.value() < 5200.0:
                    self.deesser_freq_spin.setValue(5200.0)
                    changes.append("De-Esser freq: 5.2 kHz")
                if self.deesser_intensity_spin.value() < 0.80:
                    self.deesser_intensity_spin.setValue(0.80)
                    changes.append("De-Esser intensidad: 0.80")

            need_glue = input_lra >= 7.0 and auto_master_profile != "Conservador"
            set_check(self.glue_cb, need_glue, "Glue")

            saturation_safe = input_tp <= -3.0 and input_i <= (target_lufs - 1.0) and auto_master_profile != "Conservador"
            set_check(self.saturation_enable_cb, saturation_safe, "Saturación")
            if sibilant and self.saturation_enable_cb.isChecked():
                self.saturation_enable_cb.setChecked(False)
                self.saturation_per_band_cb.setChecked(False)
                self.saturation_drive_spin.setValue(0.0)
                self.saturation_mix_spin.setValue(0.0)
                changes.append("Saturación: OFF (sibilancia)")
                changes.append("Saturación por bandas: OFF (sibilancia)")
                for spin in self.saturation_band_mix_spins.values():
                    spin.setValue(0.0)
            elif bright_highs and self.saturation_enable_cb.isChecked():
                if self.saturation_drive_spin.value() > 1.0:
                    self.saturation_drive_spin.setValue(1.0)
                    changes.append("Saturación drive: 1.0 dB (agudos brillantes)")
                if self.saturation_mix_spin.value() > 4.0:
                    self.saturation_mix_spin.setValue(4.0)
                    changes.append("Saturación mix: 4% (agudos brillantes)")
                for label, spin in self.saturation_band_mix_spins.items():
                    if label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)") and spin.value() > 0.0:
                        spin.setValue(0.0)
                        changes.append(f"Saturación/bandas {label}: 0%")

            need_stereo_dyn = (input_lra >= 9.0 or max_dev > (band_range * 1.2)) and auto_master_profile != "Conservador"
            set_check(self.stereo_dynamic_cb, need_stereo_dyn, "Stereo dinámico")

            if changes:
                self.append_log("Auto-master ajustó procesos: " + ", ".join(changes))
                self._append_auto_master_summary_to_log()

        def _collect_signature_metadata(self) -> Dict[str, str] | None:
            artist = self.signature_artist_edit.text().strip()
            copyright_text = self.signature_copyright_edit.text().strip()
            comment = self.signature_comment_edit.toPlainText().strip()
            url = self.signature_url_edit.text().strip()
            email = self.signature_email_edit.text().strip()
            label = self.signature_label_edit.text().strip()
            company = self.signature_company_edit.text().strip()

            # Si no hay ningún dato, retornar diccionario vacío (metadatos opcionales)
            if not any([artist, copyright_text, comment, url, email, label, company]):
                return {}

            if "<Artist>" in copyright_text:
                copyright_text = copyright_text.replace("<Artist>", artist)

            metadata: Dict[str, str] = {}
            if artist:
                metadata["artist"] = artist
            if comment:
                metadata["comment"] = comment
            if copyright_text:
                metadata["copyright"] = copyright_text
            if company:
                metadata["publisher"] = company
                metadata["encoded_by"] = company
            if url:
                metadata["url"] = url
            if email:
                metadata["contact"] = email
            if label:
                metadata["label"] = label
            return metadata

        def _signature_preset_path(self) -> pathlib.Path:
            base = pathlib.Path.home() / ".tonefinish"
            base.mkdir(parents=True, exist_ok=True)
            return base / "signature_presets.json"

        def _load_signature_presets(self) -> Dict[str, Dict[str, str]]:
            path = self._signature_preset_path()
            if not path.exists():
                return {}
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
            except Exception:
                pass
            return {}

        def _save_signature_presets(self, presets: Dict[str, Dict[str, str]]) -> None:
            path = self._signature_preset_path()
            path.write_text(json.dumps(presets, ensure_ascii=True, indent=2), encoding="utf-8")

        def _current_signature_fields(self) -> Dict[str, str]:
            return {
                "artist": self.signature_artist_edit.text().strip(),
                "copyright": self.signature_copyright_edit.text().strip(),
                "comment": self.signature_comment_edit.toPlainText().strip(),
                "url": self.signature_url_edit.text().strip(),
                "email": self.signature_email_edit.text().strip(),
                "label": self.signature_label_edit.text().strip(),
                "company": self.signature_company_edit.text().strip(),
            }

        def _apply_signature_fields(self, data: Dict[str, str]) -> None:
            self.signature_artist_edit.setText(data.get("artist", ""))
            self.signature_copyright_edit.setText(data.get("copyright", ""))
            self.signature_comment_edit.setPlainText(data.get("comment", ""))
            self.signature_url_edit.setText(data.get("url", ""))
            self.signature_email_edit.setText(data.get("email", ""))
            self.signature_label_edit.setText(data.get("label", ""))
            if data.get("company"):
                self.signature_company_edit.setText(data.get("company", "SABE Software"))

        def _refresh_signature_presets(self) -> None:
            presets = self._load_signature_presets()
            current = self.signature_preset_combo.currentText()
            self.signature_preset_combo.clear()
            if presets:
                self.signature_preset_combo.addItems(sorted(presets.keys()))
            if current:
                self.signature_preset_combo.setCurrentText(current)

        def _save_signature_preset(self) -> None:
            name = self.signature_preset_combo.currentText().strip()
            if not name:
                self._show_error("Indica un nombre para el preset de firma.")
                return
            presets = self._load_signature_presets()
            presets[name] = self._current_signature_fields()
            self._save_signature_presets(presets)
            self._refresh_signature_presets()
            self.signature_preset_combo.setCurrentText(name)

        def _delete_signature_preset(self) -> None:
            name = self.signature_preset_combo.currentText().strip()
            if not name:
                return
            presets = self._load_signature_presets()
            if name in presets:
                presets.pop(name, None)
                self._save_signature_presets(presets)
                self._refresh_signature_presets()

        def _load_signature_preset(self) -> None:
            name = self.signature_preset_combo.currentText().strip()
            if not name:
                return
            presets = self._load_signature_presets()
            if name in presets:
                self._apply_signature_fields(presets[name])

        # =====================================================================
        # PRESETS DE MEZCLA PERSONALIZADOS
        # =====================================================================
        def _mix_preset_path(self) -> pathlib.Path:
            base = pathlib.Path.home() / ".tonefinish"
            base.mkdir(parents=True, exist_ok=True)
            return base / "mix_presets.json"

        def _load_mix_presets(self) -> Dict[str, Dict[str, Any]]:
            path = self._mix_preset_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        # Migrar presets antiguos al nuevo formato
                        migrated = False
                        for name, preset in data.items():
                            if self._migrate_mix_preset(preset):
                                migrated = True
                        if migrated:
                            self._save_mix_presets(data)
                        return data
                except Exception:
                    pass
            return {}

        def _migrate_mix_preset(self, preset: Dict[str, Any]) -> bool:
            """Migra un preset de mezcla del formato antiguo al nuevo. Retorna True si hubo cambios."""
            migrations = {
                # EQ Tonal
                "eq_low": "mix.eq.low",
                "eq_mid": "mix.eq.mid",
                "eq_high": "mix.eq.high",
                "tilt_eq": "mix.eq.tilt",
                # EQ Dinámico
                "dynamic_eq_enabled": "mix.dyneq.enabled",
                "dynamic_bands": "mix.dyneq.bands",
                # Glue
                "glue_enabled": "mix.glue.enabled",
                "glue_threshold": "mix.glue.threshold",
                "glue_ratio": "mix.glue.ratio",
                "glue_attack": "mix.glue.attack",
                "glue_release": "mix.glue.release",
                "glue_makeup": "mix.glue.makeup",
                # Stereo Width
                "stereo_width_enabled": "mix.stereo.width.enabled",
                "stereo_bands": "mix.stereo.width.bands",
                # Stereo Dinámico
                "stereo_dynamic_enabled": "mix.stereo.dyn.enabled",
                "stereo_dynamic_threshold": "mix.stereo.dyn.threshold",
                "stereo_dynamic_ratio": "mix.stereo.dyn.ratio",
                "stereo_dynamic_attack": "mix.stereo.dyn.attack",
                "stereo_dynamic_release": "mix.stereo.dyn.release",
                "stereo_dynamic_mix": "mix.stereo.dyn.mix",
                # De-esser
                "deesser_enabled": "mix.deesser.enabled",
                "deesser_freq": "mix.deesser.freq",
                "deesser_intensity": "mix.deesser.intensity",
                # Saturación
                "saturation_enabled": "mix.sat.enabled",
                "saturation_per_band": "mix.sat.per_band",
                "saturation_type": "mix.sat.type",
                "saturation_drive": "mix.sat.drive",
                "saturation_mix": "mix.sat.mix",
                "saturation_bands_drive": "mix.sat.band_drive",
                "saturation_bands_mix": "mix.sat.band_mix",
            }
            changed = False
            for old_key, new_key in migrations.items():
                if old_key in preset and new_key not in preset:
                    preset[new_key] = preset.pop(old_key)
                    changed = True
            return changed

        def _save_mix_presets(self, presets: Dict[str, Dict[str, Any]]) -> None:
            path = self._mix_preset_path()
            path.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")

        def _current_mix_fields(self) -> Dict[str, Any]:
            """Captura todos los valores actuales de la sección Mezcla."""
            return {
                # === EQ Tonal ===
                "mix.eq.low": self.eq_low_spin.value(),
                "mix.eq.sub_bass": self.sub_bass_spin.value(),
                "mix.eq.mid": self.eq_mid_spin.value(),
                "mix.eq.high": self.eq_high_spin.value(),
                "mix.eq.tilt": self.tilt_eq_spin.value(),
                # === EQ Dinámico ===
                "mix.dyneq.enabled": self.dynamic_eq_cb.isChecked(),
                "mix.dyneq.bands": {k: v.value() for k, v in self.dynamic_band_spins.items()},
                # === Glue Compression ===
                "mix.glue.enabled": self.glue_cb.isChecked(),
                "mix.glue.threshold": self.glue_threshold_spin.value(),
                "mix.glue.ratio": self.glue_ratio_spin.value(),
                "mix.glue.attack": self.glue_attack_spin.value(),
                "mix.glue.release": self.glue_release_spin.value(),
                "mix.glue.makeup": self.glue_makeup_spin.value(),
                # === Stereo Width ===
                "mix.stereo.width.enabled": self.stereo_width_cb.isChecked(),
                "mix.stereo.width.bands": {k: v.value() for k, v in self.stereo_band_spins.items()},
                # === Stereo Dinámico ===
                "mix.stereo.dyn.enabled": self.stereo_dynamic_cb.isChecked(),
                "mix.stereo.dyn.threshold": self.stereo_dynamic_threshold_spin.value(),
                "mix.stereo.dyn.ratio": self.stereo_dynamic_ratio_spin.value(),
                "mix.stereo.dyn.attack": self.stereo_dynamic_attack_spin.value(),
                "mix.stereo.dyn.release": self.stereo_dynamic_release_spin.value(),
                "mix.stereo.dyn.mix": self.stereo_dynamic_mix_spin.value(),
                "mix.stereo.dyn.band_mix": {k: v.value() for k, v in self.stereo_dynamic_band_mix_spins.items()},
                # === De-esser ===
                "mix.deesser.enabled": self.deesser_cb.isChecked(),
                "mix.deesser.freq": self.deesser_freq_spin.value(),
                "mix.deesser.intensity": self.deesser_intensity_spin.value(),
                # === Saturación ===
                "mix.sat.enabled": self.saturation_enable_cb.isChecked(),
                "mix.sat.per_band": self.saturation_per_band_cb.isChecked(),
                "mix.sat.type": self.saturation_type_combo.currentText(),
                "mix.sat.drive": self.saturation_drive_spin.value(),
                "mix.sat.mix": self.saturation_mix_spin.value(),
                "mix.sat.band_drive": {k: v.value() for k, v in self.saturation_band_drive_spins.items()},
                "mix.sat.band_mix": {k: v.value() for k, v in self.saturation_band_mix_spins.items()},
                # === Opciones Generales ===
                "mix.transparent": self.transparent_cb.isChecked(),
                "mix.auto_band_gain": self.auto_band_gain_cb.isChecked(),
            }

        def _apply_mix_fields(self, data: Dict[str, Any]) -> None:
            """Aplica valores guardados a la sección Mezcla."""
            # === EQ Tonal ===
            if "mix.eq.low" in data:
                self.eq_low_spin.setValue(data["mix.eq.low"])
                self.sub_bass_spin.setValue(data.get("mix.eq.sub_bass", 0.0))
            elif "eq_low" in data:  # Compatibilidad con presets antiguos
                self.eq_low_spin.setValue(data["eq_low"])
                self.sub_bass_spin.setValue(data.get("sub_bass_db", 0.0))
            if "mix.eq.mid" in data:
                self.eq_mid_spin.setValue(data["mix.eq.mid"])
            elif "eq_mid" in data:
                self.eq_mid_spin.setValue(data["eq_mid"])
            if "mix.eq.high" in data:
                self.eq_high_spin.setValue(data["mix.eq.high"])
            elif "eq_high" in data:
                self.eq_high_spin.setValue(data["eq_high"])
            if "mix.eq.tilt" in data:
                self.tilt_eq_spin.setValue(data["mix.eq.tilt"])
            elif "tilt_eq" in data:
                self.tilt_eq_spin.setValue(data["tilt_eq"])
            # === EQ Dinámico ===
            if "mix.dyneq.enabled" in data:
                self.dynamic_eq_cb.setChecked(data["mix.dyneq.enabled"])
            elif "dynamic_eq_enabled" in data:
                self.dynamic_eq_cb.setChecked(data["dynamic_eq_enabled"])
            bands_data = data.get("mix.dyneq.bands") or data.get("dynamic_bands") or {}
            for k, v in bands_data.items():
                if k in self.dynamic_band_spins:
                    self.dynamic_band_spins[k].setValue(v)
            # === Glue ===
            if "mix.glue.enabled" in data:
                self.glue_cb.setChecked(data["mix.glue.enabled"])
            elif "glue_enabled" in data:
                self.glue_cb.setChecked(data["glue_enabled"])
            if "mix.glue.threshold" in data:
                self.glue_threshold_spin.setValue(data["mix.glue.threshold"])
            elif "glue_threshold" in data:
                self.glue_threshold_spin.setValue(data["glue_threshold"])
            if "mix.glue.ratio" in data:
                self.glue_ratio_spin.setValue(data["mix.glue.ratio"])
            elif "glue_ratio" in data:
                self.glue_ratio_spin.setValue(data["glue_ratio"])
            if "mix.glue.attack" in data:
                self.glue_attack_spin.setValue(data["mix.glue.attack"])
            elif "glue_attack" in data:
                self.glue_attack_spin.setValue(data["glue_attack"])
            if "mix.glue.release" in data:
                self.glue_release_spin.setValue(data["mix.glue.release"])
            elif "glue_release" in data:
                self.glue_release_spin.setValue(data["glue_release"])
            if "mix.glue.makeup" in data:
                self.glue_makeup_spin.setValue(data["mix.glue.makeup"])
            elif "glue_makeup" in data:
                self.glue_makeup_spin.setValue(data["glue_makeup"])
            # === Stereo Width ===
            if "mix.stereo.width.enabled" in data:
                self.stereo_width_cb.setChecked(data["mix.stereo.width.enabled"])
            elif "stereo_width_enabled" in data:
                self.stereo_width_cb.setChecked(data["stereo_width_enabled"])
            width_bands = data.get("mix.stereo.width.bands") or data.get("stereo_bands") or {}
            for k, v in width_bands.items():
                if k in self.stereo_band_spins:
                    self.stereo_band_spins[k].setValue(v)
            # === Stereo Dinámico ===
            if "mix.stereo.dyn.enabled" in data:
                self.stereo_dynamic_cb.setChecked(data["mix.stereo.dyn.enabled"])
            elif "stereo_dynamic_enabled" in data:
                self.stereo_dynamic_cb.setChecked(data["stereo_dynamic_enabled"])
            if "mix.stereo.dyn.threshold" in data:
                self.stereo_dynamic_threshold_spin.setValue(data["mix.stereo.dyn.threshold"])
            elif "stereo_dynamic_threshold" in data:
                self.stereo_dynamic_threshold_spin.setValue(data["stereo_dynamic_threshold"])
            if "mix.stereo.dyn.ratio" in data:
                self.stereo_dynamic_ratio_spin.setValue(data["mix.stereo.dyn.ratio"])
            elif "stereo_dynamic_ratio" in data:
                self.stereo_dynamic_ratio_spin.setValue(data["stereo_dynamic_ratio"])
            if "mix.stereo.dyn.attack" in data:
                self.stereo_dynamic_attack_spin.setValue(data["mix.stereo.dyn.attack"])
            elif "stereo_dynamic_attack" in data:
                self.stereo_dynamic_attack_spin.setValue(data["stereo_dynamic_attack"])
            if "mix.stereo.dyn.release" in data:
                self.stereo_dynamic_release_spin.setValue(data["mix.stereo.dyn.release"])
            elif "stereo_dynamic_release" in data:
                self.stereo_dynamic_release_spin.setValue(data["stereo_dynamic_release"])
            if "mix.stereo.dyn.mix" in data:
                self.stereo_dynamic_mix_spin.setValue(data["mix.stereo.dyn.mix"])
            elif "stereo_dynamic_mix" in data:
                self.stereo_dynamic_mix_spin.setValue(data["stereo_dynamic_mix"])
            dyn_band_mix = data.get("mix.stereo.dyn.band_mix") or {}
            for k, v in dyn_band_mix.items():
                if k in self.stereo_dynamic_band_mix_spins:
                    self.stereo_dynamic_band_mix_spins[k].setValue(v)
            # === De-esser ===
            if "mix.deesser.enabled" in data:
                self.deesser_cb.setChecked(data["mix.deesser.enabled"])
            elif "deesser_enabled" in data:
                self.deesser_cb.setChecked(data["deesser_enabled"])
            if "mix.deesser.freq" in data:
                self.deesser_freq_spin.setValue(data["mix.deesser.freq"])
            elif "deesser_freq" in data:
                self.deesser_freq_spin.setValue(data["deesser_freq"])
            if "mix.deesser.intensity" in data:
                self.deesser_intensity_spin.setValue(data["mix.deesser.intensity"])
            elif "deesser_intensity" in data:
                self.deesser_intensity_spin.setValue(data["deesser_intensity"])
            # === Saturación ===
            if "mix.sat.enabled" in data:
                self.saturation_enable_cb.setChecked(data["mix.sat.enabled"])
            elif "saturation_enabled" in data:
                self.saturation_enable_cb.setChecked(data["saturation_enabled"])
            if "mix.sat.per_band" in data:
                self.saturation_per_band_cb.setChecked(data["mix.sat.per_band"])
            elif "saturation_per_band" in data:
                self.saturation_per_band_cb.setChecked(data["saturation_per_band"])
            if "mix.sat.type" in data:
                self.saturation_type_combo.setCurrentText(data["mix.sat.type"])
            elif "saturation_type" in data:
                self.saturation_type_combo.setCurrentText(data["saturation_type"])
            if "mix.sat.drive" in data:
                self.saturation_drive_spin.setValue(data["mix.sat.drive"])
            elif "saturation_drive" in data:
                self.saturation_drive_spin.setValue(data["saturation_drive"])
            if "mix.sat.mix" in data:
                self.saturation_mix_spin.setValue(data["mix.sat.mix"])
            elif "saturation_mix" in data:
                self.saturation_mix_spin.setValue(data["saturation_mix"])
            sat_band_drive = data.get("mix.sat.band_drive") or data.get("saturation_bands_drive") or {}
            for k, v in sat_band_drive.items():
                if k in self.saturation_band_drive_spins:
                    self.saturation_band_drive_spins[k].setValue(v)
            sat_band_mix = data.get("mix.sat.band_mix") or data.get("saturation_bands_mix") or {}
            for k, v in sat_band_mix.items():
                if k in self.saturation_band_mix_spins:
                    self.saturation_band_mix_spins[k].setValue(v)
            # === Opciones Generales ===
            if "mix.transparent" in data:
                self.transparent_cb.setChecked(data["mix.transparent"])
            if "mix.auto_band_gain" in data:
                self.auto_band_gain_cb.setChecked(data["mix.auto_band_gain"])
            # Actualizar gráficos
            self._update_dynamic_band_plot()
            self._update_stereo_band_plot()

        def _refresh_mix_presets(self) -> None:
            presets = self._load_mix_presets()
            current = self.mix_preset_combo.currentText()
            self.mix_preset_combo.clear()
            if presets:
                self.mix_preset_combo.addItems(sorted(presets.keys()))
            if current and current in presets:
                self.mix_preset_combo.setCurrentText(current)

        def _save_mix_preset(self) -> None:
            name = self.mix_preset_combo.currentText().strip()
            if not name:
                self._show_error("Indica un nombre para el preset de mezcla.")
                return
            presets = self._load_mix_presets()
            presets[name] = self._current_mix_fields()
            self._save_mix_presets(presets)
            self._refresh_mix_presets()
            self.mix_preset_combo.setCurrentText(name)
            self.log_view.appendPlainText(f"✅ Preset de mezcla '{name}' guardado")

        def _delete_mix_preset(self) -> None:
            name = self.mix_preset_combo.currentText().strip()
            if not name:
                return
            presets = self._load_mix_presets()
            if name in presets:
                presets.pop(name, None)
                self._save_mix_presets(presets)
                self._refresh_mix_presets()
                self.log_view.appendPlainText(f"🗑️ Preset de mezcla '{name}' eliminado")

        def _load_mix_preset(self) -> None:
            name = self.mix_preset_combo.currentText().strip()
            if not name:
                return
            presets = self._load_mix_presets()
            if name in presets:
                self._apply_mix_fields(presets[name])
                self.log_view.appendPlainText(f"📂 Preset de mezcla '{name}' cargado")

        # =====================================================================
        # PRESETS DE MASTERING PERSONALIZADOS
        # =====================================================================
        def _master_preset_path(self) -> pathlib.Path:
            base = pathlib.Path.home() / ".tonefinish"
            base.mkdir(parents=True, exist_ok=True)
            return base / "master_presets.json"

        def _load_master_presets(self) -> Dict[str, Dict[str, Any]]:
            path = self._master_preset_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        # Migrar presets antiguos al nuevo formato
                        migrated = False
                        for name, preset in data.items():
                            if self._migrate_master_preset(preset):
                                migrated = True
                        if migrated:
                            self._save_master_presets(data)
                        return data
                except Exception:
                    pass
            return {}

        def _migrate_master_preset(self, preset: Dict[str, Any]) -> bool:
            """Migra un preset de mastering del formato antiguo al nuevo. Retorna True si hubo cambios."""
            migrations = {
                # Loudness
                "target_lufs": "master.loudness.target",
                "true_peak": "master.loudness.true_peak",
                # Limiter
                "limiter_ceiling": "master.limiter.ceiling",
                "limiter_release": "master.limiter.release",
                "brickwall": "master.limiter.brickwall",
                # Fades
                "fade_in": "master.fade.in",
                "fade_out": "master.fade.out",
                # Input
                "input_gain": "master.input.gain",
                "dc_offset": "master.input.dc_offset",
            }
            changed = False
            for old_key, new_key in migrations.items():
                if old_key in preset and new_key not in preset:
                    preset[new_key] = preset.pop(old_key)
                    changed = True
            return changed

        def _save_master_presets(self, presets: Dict[str, Dict[str, Any]]) -> None:
            path = self._master_preset_path()
            path.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")

        def _current_master_fields(self) -> Dict[str, Any]:
            """Captura todos los valores actuales de la sección Mastering."""
            fields = {
                # === Loudness ===
                "master.loudness.target": self.target_spin.value(),
                "master.loudness.true_peak": self.true_peak_spin.value(),
                # === Limiter ===
                "master.limiter.ceiling": self.limiter_ceiling_spin.value(),
                "master.limiter.release": self.limiter_release_spin.value(),
                "master.limiter.brickwall": self.brickwall_cb.isChecked(),
                # === Multiband Limiter ===
                "master.mb_limiter.enabled": self.multiband_limiter_cb.isChecked(),
                # === Fades ===
                "master.fade.in": self.fade_in_spin.value(),
                "master.fade.out": self.fade_out_spin.value(),
                # === Input ===
                "master.input.gain": self.input_gain_spin.value(),
                "master.input.dc_offset": self.dc_offset_cb.isChecked(),
                # === Output ===
                "master.output.sample_rate": self.sample_rate_combo.currentText(),
                "master.output.bit_depth": self.bit_depth_combo.currentText(),
                "master.output.format": self.output_format_combo.currentText(),
                # === Reparación ===
                "master.repair.noise": self.noise_reduction_combo.currentText(),
                "master.repair.pink_noise": self.pink_noise_combo.currentText(),
                "master.repair.declip": self.declip_combo.currentText(),
                "master.repair.declick": self.declick_combo.currentText(),
                "master.repair.auto": self.auto_repair_cb.isChecked(),
                # === Cadenas habilitadas ===
                "master.chain.repair": self.repair_enabled_cb.isChecked(),
                "master.chain.mix": self.mix_enabled_cb.isChecked(),
                "master.chain.master": self.master_enabled_cb.isChecked(),
                "master.chain.autogain": self.autogain_cb.isChecked(),
                # === Auto-Master (Fase 5) ===
                "master.auto.motion_preset": self.auto_master_motion_preset_combo.currentText(),
                "master.auto.motion_profile": self.auto_master_motion_profile_combo.currentText(),
                "master.auto.motion_amount_percent": self.auto_master_motion_amount_spin.value(),
            }
            # Agregar umbrales de multiband limiter por banda
            for band_label, spin in self.multiband_limiter_spins.items():
                fields[f"master.mb_limiter.{band_label}"] = spin.value()
            return fields

        def _apply_master_fields(self, data: Dict[str, Any]) -> None:
            """Aplica valores guardados a la sección Mastering."""
            # === Loudness ===
            if "master.loudness.target" in data:
                self.target_spin.setValue(data["master.loudness.target"])
            elif "target_lufs" in data:  # Compatibilidad
                self.target_spin.setValue(data["target_lufs"])
            if "master.loudness.true_peak" in data:
                self.true_peak_spin.setValue(data["master.loudness.true_peak"])
            elif "true_peak" in data:
                self.true_peak_spin.setValue(data["true_peak"])
            # === Limiter ===
            if "master.limiter.ceiling" in data:
                self.limiter_ceiling_spin.setValue(data["master.limiter.ceiling"])
            elif "limiter_ceiling" in data:
                self.limiter_ceiling_spin.setValue(data["limiter_ceiling"])
            if "master.limiter.release" in data:
                self.limiter_release_spin.setValue(data["master.limiter.release"])
            elif "limiter_release" in data:
                self.limiter_release_spin.setValue(data["limiter_release"])
            if "master.limiter.brickwall" in data:
                self.brickwall_cb.setChecked(data["master.limiter.brickwall"])
            elif "brickwall" in data:
                self.brickwall_cb.setChecked(data["brickwall"])
            # === Multiband Limiter ===
            if "master.mb_limiter.enabled" in data:
                self.multiband_limiter_cb.setChecked(data["master.mb_limiter.enabled"])
            for band_label, spin in self.multiband_limiter_spins.items():
                key = f"master.mb_limiter.{band_label}"
                if key in data:
                    spin.setValue(data[key])
            # === Fades ===
            if "master.fade.in" in data:
                self.fade_in_spin.setValue(data["master.fade.in"])
            elif "fade_in" in data:
                self.fade_in_spin.setValue(data["fade_in"])
            if "master.fade.out" in data:
                self.fade_out_spin.setValue(data["master.fade.out"])
            elif "fade_out" in data:
                self.fade_out_spin.setValue(data["fade_out"])
            # === Input ===
            if "master.input.gain" in data:
                self.input_gain_spin.setValue(data["master.input.gain"])
            elif "input_gain" in data:
                self.input_gain_spin.setValue(data["input_gain"])
            if "master.input.dc_offset" in data:
                self.dc_offset_cb.setChecked(data["master.input.dc_offset"])
            elif "dc_offset" in data:
                self.dc_offset_cb.setChecked(data["dc_offset"])
            # === Output ===
            if "master.output.sample_rate" in data:
                self.sample_rate_combo.setCurrentText(data["master.output.sample_rate"])
            if "master.output.bit_depth" in data:
                self.bit_depth_combo.setCurrentText(data["master.output.bit_depth"])
            if "master.output.format" in data:
                self.output_format_combo.setCurrentText(data["master.output.format"])
            # === Reparación ===
            if "master.repair.noise" in data:
                self.noise_reduction_combo.setCurrentText(data["master.repair.noise"])
            if "master.repair.pink_noise" in data:
                self.pink_noise_combo.setCurrentText(data["master.repair.pink_noise"])
            if "master.repair.declip" in data:
                self.declip_combo.setCurrentText(data["master.repair.declip"])
            if "master.repair.declick" in data:
                self.declick_combo.setCurrentText(data["master.repair.declick"])
            if "master.repair.auto" in data:
                self.auto_repair_cb.setChecked(data["master.repair.auto"])
            # === Cadenas habilitadas ===
            if "master.chain.repair" in data:
                self.repair_enabled_cb.setChecked(data["master.chain.repair"])
            if "master.chain.mix" in data:
                self.mix_enabled_cb.setChecked(data["master.chain.mix"])
            if "master.chain.master" in data:
                self.master_enabled_cb.setChecked(data["master.chain.master"])
            if "master.chain.autogain" in data:
                self.autogain_cb.setChecked(data["master.chain.autogain"])
            # === Auto-Master (Fase 5) ===
            if "master.auto.motion_preset" in data:
                self.auto_master_motion_preset_combo.setCurrentText(data["master.auto.motion_preset"])
            if "master.auto.motion_profile" in data:
                self.auto_master_motion_profile_combo.setCurrentText(data["master.auto.motion_profile"])
            if "master.auto.motion_amount_percent" in data:
                self.auto_master_motion_amount_spin.setValue(data["master.auto.motion_amount_percent"])
            self._sync_motion_preset_from_controls()

        def _refresh_master_presets(self) -> None:
            presets = self._load_master_presets()
            current = self.master_preset_combo.currentText()
            self.master_preset_combo.clear()
            if presets:
                self.master_preset_combo.addItems(sorted(presets.keys()))
            if current and current in presets:
                self.master_preset_combo.setCurrentText(current)

        def _save_master_preset(self) -> None:
            name = self.master_preset_combo.currentText().strip()
            if not name:
                self._show_error("Indica un nombre para el preset de mastering.")
                return
            presets = self._load_master_presets()
            presets[name] = self._current_master_fields()
            self._save_master_presets(presets)
            self._refresh_master_presets()
            self.master_preset_combo.setCurrentText(name)
            self.log_view.appendPlainText(f"✅ Preset de mastering '{name}' guardado")

        def _delete_master_preset(self) -> None:
            name = self.master_preset_combo.currentText().strip()
            if not name:
                return
            presets = self._load_master_presets()
            if name in presets:
                presets.pop(name, None)
                self._save_master_presets(presets)
                self._refresh_master_presets()
                self.log_view.appendPlainText(f"🗑️ Preset de mastering '{name}' eliminado")

        def _load_master_preset(self) -> None:
            name = self.master_preset_combo.currentText().strip()
            if not name:
                return
            presets = self._load_master_presets()
            if name in presets:
                self._apply_master_fields(presets[name])
                self.log_view.appendPlainText(f"📂 Preset de mastering '{name}' cargado")

        def _apply_preset(self) -> None:
            self._apply_lufs_preset(self.preset_combo.currentText())

        def _apply_lufs_preset(self, preset_name: str) -> None:
            preset = LOUDNESS_PRESETS.get(preset_name)
            if preset is None:
                return
            is_manual = preset_name == "Manual"
            if self._syncing_lufs:
                return
            self._syncing_lufs = True
            try:
                if is_manual:
                    self.target_spin.setEnabled(True)
                    self.true_peak_spin.setEnabled(True)
                else:
                    target, true_peak = preset
                    self.target_spin.setValue(target)
                    self.true_peak_spin.setValue(true_peak)
                    self.target_spin.setEnabled(False)
                    self.true_peak_spin.setEnabled(False)
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

        def _apply_deesser_preset(self) -> None:
            text = self.deesser_preset_combo.currentText()
            if text == "Manual":
                self.deesser_freq_spin.setEnabled(True)
                self.deesser_intensity_spin.setEnabled(True)
                return
            presets = {
                "Tenor (6.5 kHz / 0.70)": (6500.0, 0.70),
                "Baritono (5.5 kHz / 0.65)": (5500.0, 0.65),
                "Bajo (4.5 kHz / 0.60)": (4500.0, 0.60),
                "Soprano (8.0 kHz / 0.75)": (8000.0, 0.75),
                "Mezzo-soprano (7.0 kHz / 0.70)": (7000.0, 0.70),
                "Contralto (5.2 kHz / 0.65)": (5200.0, 0.65),
                "Rap agresivo (6.0 kHz / 0.85)": (6000.0, 0.85),
                "Rap suave (5.0 kHz / 0.75)": (5000.0, 0.75),
                "Vocoder (9.0 kHz / 0.60)": (9000.0, 0.60),
                "Voz hablada (5.5 kHz / 0.60)": (5500.0, 0.60),
                "Voz brillante (6.5 kHz / 0.55)": (6500.0, 0.55),
            }
            preset = presets.get(text)
            if preset is None:
                return
            freq, intensity = preset
            self.deesser_freq_spin.setValue(freq)
            self.deesser_intensity_spin.setValue(intensity)
            self.deesser_freq_spin.setEnabled(False)
            self.deesser_intensity_spin.setEnabled(False)

        def _apply_glue_preset(self) -> None:
            text = self.glue_preset_combo.currentText()
            if text == "Manual":
                self.glue_threshold_spin.setEnabled(True)
                self.glue_ratio_spin.setEnabled(True)
                self.glue_attack_spin.setEnabled(True)
                self.glue_release_spin.setEnabled(True)
                self.glue_makeup_spin.setEnabled(True)
                return
            presets = {
                "Clasico (-22 / 1.5 / 30 / 180 / 0.0)": (-22.0, 1.5, 30.0, 180.0, 0.0),
                "Pop (-18 / 2.0 / 12 / 140 / 0.8)": (-18.0, 2.0, 12.0, 140.0, 0.8),
                "Jazz (-24 / 1.3 / 40 / 200 / 0.0)": (-24.0, 1.3, 40.0, 200.0, 0.0),
                "Funk (-17 / 2.2 / 10 / 130 / 0.8)": (-17.0, 2.2, 10.0, 130.0, 0.8),
                "Disco (-16 / 2.4 / 10 / 120 / 1.0)": (-16.0, 2.4, 10.0, 120.0, 1.0),
            }
            preset = presets.get(text)
            if preset is None:
                return
            threshold, ratio, attack, release, makeup = preset
            self.glue_threshold_spin.setValue(threshold)
            self.glue_ratio_spin.setValue(ratio)
            self.glue_attack_spin.setValue(attack)
            self.glue_release_spin.setValue(release)
            self.glue_makeup_spin.setValue(makeup)
            self.glue_threshold_spin.setEnabled(False)
            self.glue_ratio_spin.setEnabled(False)
            self.glue_attack_spin.setEnabled(False)
            self.glue_release_spin.setEnabled(False)
            self.glue_makeup_spin.setEnabled(False)

        def _apply_tone_eq_preset(self) -> None:
            text = self.tone_eq_preset_combo.currentText()
            if text == "Manual":
                self.eq_low_spin.setEnabled(True)
                self.sub_bass_spin.setEnabled(True)
                self.eq_mid_spin.setEnabled(True)
                self.eq_high_spin.setEnabled(True)
                return
            presets = {
                "Neutral (0 / 0 / 0)": (0.0, 0.0, 0.0),
                "Warm (+1.0 / -0.5 / -0.5)": (1.0, -0.5, -0.5),
                "Bright (-0.5 / 0 / +1.0)": (-0.5, 0.0, 1.0),
                "Air (0 / -0.5 / +1.5)": (0.0, -0.5, 1.5),
                "Tight Low (-1.0 / 0 / +0.5)": (-1.0, 0.0, 0.5),
                "Vocal Focus (-0.5 / +1.0 / +0.5)": (-0.5, 1.0, 0.5),
                "Smooth (+0.5 / -1.0 / +0.5)": (0.5, -1.0, 0.5),
                "Mid Scoop (+0.5 / -1.5 / +0.5)": (0.5, -1.5, 0.5),
                "Low Punch (+1.5 / -0.5 / 0)": (1.5, -0.5, 0.0),
                "Dark (+0.5 / 0 / -1.5)": (0.5, 0.0, -1.5),
            }
            preset = presets.get(text)
            if preset is None:
                return
            low, mid, high = preset
            self.eq_low_spin.setValue(low)
            self.sub_bass_spin.setValue(0.0)
            self.eq_mid_spin.setValue(mid)
            self.eq_high_spin.setValue(high)
            self.eq_low_spin.setEnabled(False)
            self.sub_bass_spin.setEnabled(False)
            self.eq_mid_spin.setEnabled(False)
            self.eq_high_spin.setEnabled(False)

        def _apply_dynamic_eq_preset(self) -> None:
            text = self.dynamic_eq_preset_combo.currentText()
            if text == "Manual":
                for spin in self.dynamic_band_spins.values():
                    spin.setEnabled(True)
                return
            presets = {
                "Neutral (0 / 0 / 0 / 0 / 0 / 0)": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                "Balanced (+0.2 / +0.2 / 0 / 0 / 0 / +0.2)": (0.2, 0.2, 0.0, 0.0, 0.0, 0.2),
                "Warm Glue (+0.5 / +0.5 / -0.3 / -0.2 / 0 / 0)": (0.5, 0.5, -0.3, -0.2, 0.0, 0.0),
                "Bright Lift (-0.3 / -0.2 / 0 / +0.2 / +0.4 / +0.6)": (-0.3, -0.2, 0.0, 0.2, 0.4, 0.6),
                "Tight Low (-0.8 / -0.6 / -0.2 / 0 / +0.2 / +0.2)": (-0.8, -0.6, -0.2, 0.0, 0.2, 0.2),
                "Vocal Focus (-0.2 / 0 / +0.5 / +0.8 / +0.3 / 0)": (-0.2, 0.0, 0.5, 0.8, 0.3, 0.0),
                "Smooth Top (0 / 0 / -0.2 / -0.2 / -0.4 / -0.6)": (0.0, 0.0, -0.2, -0.2, -0.4, -0.6),
                "Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)": (0.6, 0.8, -0.3, 0.0, 0.2, 0.0),
                "Airy (-0.2 / -0.2 / 0 / +0.1 / +0.4 / +0.8)": (-0.2, -0.2, 0.0, 0.1, 0.4, 0.8),
                "Master General (+0.3 / +0.2 / -0.1 / 0 / +0.2 / +0.3)": (0.3, 0.2, -0.1, 0.0, 0.2, 0.3),
                "Auto Control (+0.1 / 0 / -0.4 / -0.6 / -0.8 / -1.0)": (0.1, 0.0, -0.4, -0.6, -0.8, -1.0),
            }
            preset = presets.get(text)
            if preset is None or not self.dynamic_band_spins:
                return
            labels = list(self.dynamic_band_spins.keys())
            for label, value in zip(labels, preset):
                self.dynamic_band_spins[label].setValue(value)
                self.dynamic_band_spins[label].setEnabled(False)
            for label in labels[len(preset):]:
                self.dynamic_band_spins[label].setEnabled(False)

        def _get_stereo_dynamic_band_mix(self) -> list[float]:
            if not self.stereo_dynamic_band_mix_spins:
                return []
            values: list[float] = []
            for label, *_rest in BAND_CONFIG:
                spin = self.stereo_dynamic_band_mix_spins.get(label)
                if spin is not None:
                    values.append(spin.value())
            return values

        def _get_dynamic_band_adjust_db(self) -> Dict[str, float]:
            if not self.dynamic_band_spins:
                return {}
            return {label: spin.value() for label, spin in self.dynamic_band_spins.items()}

        def _get_auto_master_band_eq_adjustments(
            self,
            adjustments: dict[str, Any] | None,
        ) -> Dict[str, float]:
            if not adjustments or adjustments.get("band_eq_enabled") is False:
                return {}
            eq_adjustments = adjustments.get("eq_adjustments")
            if not isinstance(eq_adjustments, dict):
                return {}
            valid_labels = {label for label, *_rest in BAND_CONFIG}
            normalized: Dict[str, float] = {}
            for band, value in eq_adjustments.items():
                label = str(band)
                if label not in valid_labels:
                    continue
                try:
                    normalized[label] = max(-6.0, min(6.0, float(value)))
                except (TypeError, ValueError):
                    continue
            return normalized

        def _apply_auto_master_band_eq_adjustments(
            self,
            adjustments: dict[str, Any] | None,
            summary_lines: list[str],
        ) -> bool:
            band_eq = self._get_auto_master_band_eq_adjustments(adjustments)
            if not band_eq or not self.dynamic_band_spins:
                return False
            if self.dynamic_eq_preset_combo.currentText() != "Manual":
                self.dynamic_eq_preset_combo.setCurrentText("Manual")
                self._apply_dynamic_eq_preset()
            applied_corrections: list[str] = []
            for band_label, limited_value in band_eq.items():
                spin = self.dynamic_band_spins.get(band_label)
                if spin is None:
                    continue
                spin.setEnabled(True)
                spin.setValue(limited_value)
                applied_corrections.append(f"{band_label}: {limited_value:+.1f} dB")
            if applied_corrections:
                if hasattr(self, "dynamic_eq_cb"):
                    self.dynamic_eq_cb.setChecked(True)
                summary_lines.append(
                    "✓ EQ por bandas aplicado por Auto-Master: " + ", ".join(applied_corrections)
                )
                self._update_dynamic_band_plot()
                return True
            return False

        def _get_saturation_band_drive_db(self) -> Dict[str, float]:
            if not self.saturation_band_drive_spins:
                return {}
            return {label: spin.value() for label, spin in self.saturation_band_drive_spins.items()}

        def _get_saturation_band_mix(self) -> Dict[str, float]:
            if not self.saturation_band_mix_spins:
                return {}
            return {label: spin.value() / 100.0 for label, spin in self.saturation_band_mix_spins.items()}

        def _get_stereo_band_widths(self) -> Dict[str, float]:
            if not self.stereo_band_spins:
                return {}
            return {label: spin.value() for label, spin in self.stereo_band_spins.items()}

        def _get_multiband_limiter_thresholds(self) -> Dict[str, float]:
            if not self.multiband_limiter_spins:
                return {}
            return {label: spin.value() for label, spin in self.multiband_limiter_spins.items()}

        def _get_process_order(self) -> list[str]:
            if hasattr(self, "process_order_widget"):
                try:
                    widget = self.process_order_widget
                    if widget is None:
                        return []
                    return list(widget.get_item_keys())
                except Exception:
                    return []
            return []

        def _on_saturation_per_band_changed(self, state: int) -> None:
            """
            Maneja el cambio del checkbox de saturación por banda.
            Implementa mutual-exclusión visual con saturación global.
            """
            is_per_band_active = (state == 2)  # Qt.Checked = 2
            
            if is_per_band_active:
                # Desactivar saturación global y saturation_limiter
                if self.saturation_enable_cb.isChecked():
                    self.saturation_enable_cb.blockSignals(True)
                    self.saturation_enable_cb.setChecked(False)
                    self.saturation_enable_cb.blockSignals(False)
                    self.append_log(
                        "⚠️ Saturación global desactivada automáticamente (saturación por banda activa)"
                    )
                
                if hasattr(self, 'saturation_limiter_cb') and self.saturation_limiter_cb.isChecked():
                    self.saturation_limiter_cb.blockSignals(True)
                    self.saturation_limiter_cb.setChecked(False)
                    self.saturation_limiter_cb.blockSignals(False)
                    self.append_log(
                        "⚠️ Saturation Limiter desactivado automáticamente (saturación por banda activa)"
                    )
                
                # Actualizar tooltips
                self.saturation_enable_cb.setToolTip(
                    "⚠️ Desactivado: Saturación por banda está activa.\\n"
                    "Para evitar doble saturación acumulativa."
                )
                if hasattr(self, 'saturation_limiter_cb'):
                    self.saturation_limiter_cb.setToolTip(
                        "⚠️ Desactivado: Saturación por banda está activa.\\n"
                        "La saturación por banda ya incluye limitación interna."
                    )
            else:
                # Restaurar tooltips normales
                self.saturation_enable_cb.setToolTip("Saturación global ligera.")
                if hasattr(self, 'saturation_limiter_cb'):
                    self.saturation_limiter_cb.setToolTip(
                        "Control adaptativo de saturación con limitador THD"
                    )
        
        def _on_saturation_global_changed(self, state: int) -> None:
            """
            Maneja el cambio del checkbox de saturación global.
            Advierte si hay conflicto con saturación por banda.
            """
            is_global_active = (state == 2)  # Qt.Checked = 2
            
            if is_global_active and self.saturation_per_band_cb.isChecked():
                # No desactivar automáticamente, solo advertir
                self.append_log(
                    "⚠️ ADVERTENCIA: Saturación global y por banda están activas simultáneamente"
                )
                self.append_log(
                    "   → El orquestador desactivará saturación global automáticamente"
                )
                self.append_log(
                    "   → Para evitar doble saturación acumulativa"
                )

        def _update_process_chain_display(self) -> None:
            """Actualiza la visualización del widget de orden de procesos según los checkboxes habilitados."""
            if not hasattr(self, "process_order_widget") or self.process_order_widget is None:
                return
            
            # Mapeo de keys a sus checkboxes correspondientes
            repair_enabled = self.repair_enabled_cb.isChecked()
            mix_enabled = self.mix_enabled_cb.isChecked()
            master_enabled = self.master_enabled_cb.isChecked()
            
            enabled_map = {
                # Siempre activos
                "input": True,
                "output": True,
                # Cadena de reparación
                "repair": repair_enabled and self.auto_repair_cb.isChecked(),
                # Cadena de mezcla
                "deesser": mix_enabled and self.deesser_cb.isChecked(),
                "tone_eq": mix_enabled,  # EQ estático siempre si mezcla habilitada
                "glue": mix_enabled and self.glue_cb.isChecked(),
                "stereo_width": mix_enabled and self.stereo_width_cb.isChecked(),
                "stereo_dynamic": mix_enabled and self.stereo_dynamic_cb.isChecked(),
                "saturation": mix_enabled and self.saturation_enable_cb.isChecked(),
                "dynamic_eq": mix_enabled and self.dynamic_eq_cb.isChecked(),
                # Cadena de mastering
                "loudness": master_enabled,
                "limiter": master_enabled and self.brickwall_cb.isChecked(),
                "fades": master_enabled,
            }
            
            self.process_order_widget.update_all_states(enabled_map)

        def _update_telemetry_indicators(self) -> None:
            """Actualiza los indicadores visuales de telemetría basándose en la configuración actual."""
            try:
                from processes import compression_analyzer
                
                # Verificar que los widgets necesarios existen
                if not hasattr(self, 'compression_gr_bar'):
                    return
                
                # Construir dict de parámetros actual
                params = {
                    "dynamic_eq": self.dynamic_eq_cb.isChecked(),
                    "stereo_dynamic": self.stereo_dynamic_cb.isChecked(),
                    "glue_enabled": self.glue_cb.isChecked(),
                    "autogain_enabled": self.autogain_cb.isChecked(),
                    # Parámetros de compresión (usar valores actuales de la UI)
                    "dynamic_eq_threshold_db": -18.0,  # Default
                    "dynamic_eq_ratio": 1.5,
                    "stereo_dynamic_threshold_db": -24.0,
                    "stereo_dynamic_ratio": 1.6,
                    "threshold_db": self.glue_threshold_spin.value() if hasattr(self, 'glue_threshold_spin') else -18.0,
                    "ratio": self.glue_ratio_spin.value() if hasattr(self, 'glue_ratio_spin') else 1.4,
                }
                
                # Calcular GR total y breakdown
                total_gr_db, breakdown = compression_analyzer.calculate_total_gr(params)
                assessment = compression_analyzer.get_compression_assessment(total_gr_db)
                
                # Actualizar barra de progreso de GR (0-10 dB mapeado a 0-100%)
                # Clamp a 10 dB máximo para visualización
                gr_percent = min(100, int(total_gr_db * 10))  # 1 dB = 10%
                self.compression_gr_bar.setValue(gr_percent)
                self.compression_gr_bar.setFormat(f"GR: {total_gr_db:.1f} dB")
                
                # Contar etapas activas
                saturation_stages = 0
                if self.saturation_per_band_cb.isChecked():
                    saturation_stages += 1
                if self.saturation_enable_cb.isChecked():
                    saturation_stages += 1
                
                compression_stages = len([k for k in ["dynamic_eq", "stereo_dynamic", "glue_enabled", "autogain_enabled"] 
                                         if params.get(k, False)])
                
                limiter_stages = 0
                if self.brickwall_cb.isChecked():
                    limiter_stages += 1
                if self.autogain_cb.isChecked():
                    limiter_stages += 2  # AutoGain aplica ~2 limiters
                
                # Mostrar contador de procesos
                if saturation_stages > 0 or compression_stages > 0 or limiter_stages > 0:
                    stages_text = []
                    if saturation_stages > 0:
                        stages_text.append(f"🎨 Saturación: {saturation_stages}")
                    if compression_stages > 0:
                        stages_text.append(f"🎚️ Compresión: {compression_stages}")
                    if limiter_stages > 0:
                        stages_text.append(f"🛡️ Limitadores: {limiter_stages}")
                    
                    self.process_stages_label.setText(" | ".join(stages_text))
                    self.process_stages_label.setVisible(True)
                else:
                    self.process_stages_label.setVisible(False)
                
                # Generar warnings si es necesario
                warnings = []
                if total_gr_db > 6.0:
                    severity = "⚠️ ADVERTENCIA" if total_gr_db <= 8.0 else "🔴 CRÍTICO"
                    warnings.append(f"{severity}: GR total {total_gr_db:.1f} dB > 6 dB (límite saludable)")
                    
                    if breakdown:
                        breakdown_text = []
                        for process, gr in breakdown.items():
                            breakdown_text.append(f"  • {process}: {gr:.1f} dB")
                        warnings.append("Desglose:")
                        warnings.extend(breakdown_text)
                    
                    warnings.append("→ Riesgo de sobre-compresión, pérdida de dinámica y pumping")
                
                # Validación saturación mutual-exclusiva
                if self.saturation_per_band_cb.isChecked() and self.saturation_enable_cb.isChecked():
                    warnings.append("⚠️ Saturación por banda Y global activas (duplicado)")
                
                # Mostrar warnings
                if warnings:
                    self.validation_warnings_label.setText("\n".join(warnings))
                    # Color según severidad
                    if total_gr_db > 8.0 or (self.saturation_per_band_cb.isChecked() and self.saturation_enable_cb.isChecked()):
                        warning_bg = "#3b1d24"
                        warning_border = "#F44336"
                    else:
                        warning_bg = "#3a3214"
                        warning_border = "#FFC107"
                    
                    self.validation_warnings_label.setStyleSheet(
                        f"QLabel {{ padding: 8px; border-radius: 4px; border: 2px solid {warning_border}; "
                        f"background-color: {warning_bg}; color: #ffffff; }}"
                    )
                    self.validation_warnings_label.setVisible(True)
                else:
                    self.validation_warnings_label.setVisible(False)
                
            except Exception as e:
                # Si hay algún error, no bloquear la aplicación
                print(f"Error actualizando telemetría: {e}")
                import traceback
                traceback.print_exc()

        def _apply_limiter_preset(self) -> None:
            text = self.limiter_preset_combo.currentText()
            if text == "Manual":
                self.limiter_ceiling_spin.setEnabled(True)
                self.limiter_release_spin.setEnabled(True)
                return
            presets = {
                "Seguro (-1.0 / 120)": (-1.0, 120.0),
                "Transparente (-1.0 / 200)": (-1.0, 200.0),
                "Punchy (-0.8 / 80)": (-0.8, 80.0),
                "Loud (-0.6 / 60)": (-0.6, 60.0),
                "Clasico (-0.9 / 120)": (-0.9, 120.0),
            }
            preset = presets.get(text)
            if preset is None:
                return
            ceiling, release = preset
            self.limiter_ceiling_spin.setValue(ceiling)
            self.limiter_release_spin.setValue(release)
            self.limiter_ceiling_spin.setEnabled(False)
            self.limiter_release_spin.setEnabled(False)

        def _resolve_autogain_maxgain(self) -> float:
            """Reduce el empuje de AutoGain cuando el material ya viene cerca del objetivo."""
            try:
                last_adjustments = getattr(self, "_last_auto_master_adjustments", None)
                last_profile = "Normal"
                last_minimal = False
                if isinstance(last_adjustments, dict):
                    last_profile = str(last_adjustments.get("processing_profile", last_profile) or last_profile)
                    last_minimal = bool(last_adjustments.get("minimal_processing", False))
                chars = getattr(self, "_last_auto_master_characteristics", None)
                if chars is None:
                    return 6.0
                source_lufs = float(getattr(chars, "lufs", float("nan")))
                source_lra = float(getattr(chars, "lra", float("nan")))
                source_crest = float(getattr(chars, "crest_factor", float("nan")))
                source_tp = float(getattr(chars, "true_peak", float("nan")))
                target_lufs = float(self.target_spin.value())
                minimal_lra, minimal_crest = self._get_minimal_processing_thresholds()
                if math.isfinite(source_lufs) and math.isfinite(source_lra):
                    if last_minimal or last_profile == "Conservador":
                        if abs(source_lufs - target_lufs) <= 1.5:
                            return 2.5
                        if math.isfinite(source_tp) and source_tp <= -6.0:
                            return 3.0
                        return 3.0
                    if math.isfinite(source_crest) and source_lra <= minimal_lra and source_crest <= minimal_crest:
                        if abs(source_lufs - target_lufs) <= 1.5:
                            return 2.5
                        return 3.0
                    if abs(source_lufs - target_lufs) <= 1.5 and source_lra <= minimal_lra:
                        return 3.0
                    if abs(source_lufs - target_lufs) <= 1.5:
                        return 4.0
            except Exception:
                pass
            return 6.0

        def _get_minimal_processing_thresholds(self) -> tuple[float, float]:
            minimal_lra = 4.5
            minimal_crest = 8.5
            try:
                minimal_lra = float(self.auto_master_min_lra_spin.value())
            except Exception:
                pass
            try:
                minimal_crest = float(self.auto_master_min_crest_spin.value())
            except Exception:
                pass
            return minimal_lra, minimal_crest

        def _get_motion_preferences(self) -> tuple[str, float]:
            profile_text = (self.auto_master_motion_profile_combo.currentText() or "Auto").lower()
            if profile_text.startswith("tight"):
                profile = "tight"
            elif profile_text.startswith("balanced"):
                profile = "balanced"
            elif profile_text.startswith("airy"):
                profile = "airy"
            else:
                profile = "auto"
            amount = 1.0
            try:
                amount = max(0.0, min(1.5, float(self.auto_master_motion_amount_spin.value()) / 100.0))
            except Exception:
                pass
            return profile, amount

        def _on_motion_preset_changed(self, _index: int) -> None:
            if getattr(self, "_syncing_motion_preset_controls", False):
                return
            preset = self.auto_master_motion_preset_combo.currentText().strip().lower()
            mapping: dict[str, tuple[str, float]] = {
                "off": ("Auto", 0.0),
                "subtle": ("Tight (estable)", 65.0),
                "musical": ("Auto", 100.0),
                "creative": ("Airy (abierto)", 125.0),
            }
            if preset in mapping:
                profile_label, amount_percent = mapping[preset]
                self._syncing_motion_preset_controls = True
                try:
                    self.auto_master_motion_profile_combo.setCurrentText(profile_label)
                    self.auto_master_motion_amount_spin.setValue(amount_percent)
                finally:
                    self._syncing_motion_preset_controls = False
                self._apply_auto_master(emit_log=False, write_preset=False)

        def _sync_motion_preset_from_controls(self) -> None:
            if getattr(self, "_syncing_motion_preset_controls", False):
                return
            profile = self.auto_master_motion_profile_combo.currentText().strip().lower()
            amount = float(self.auto_master_motion_amount_spin.value())
            preset = "Custom"
            if abs(amount - 0.0) <= 0.1:
                preset = "Off"
            elif profile.startswith("tight") and abs(amount - 65.0) <= 0.1:
                preset = "Subtle"
            elif profile.startswith("auto") and abs(amount - 100.0) <= 0.1:
                preset = "Musical"
            elif profile.startswith("airy") and abs(amount - 125.0) <= 0.1:
                preset = "Creative"
            self._syncing_motion_preset_controls = True
            try:
                self.auto_master_motion_preset_combo.setCurrentText(preset)
            finally:
                self._syncing_motion_preset_controls = False

        def _on_motion_controls_changed(self, _value: object = None) -> None:
            self._sync_motion_preset_from_controls()
            if getattr(self, "_syncing_motion_preset_controls", False):
                return
            self._apply_auto_master(emit_log=False, write_preset=False)

        def _apply_minimal_processing_overrides(
            self,
            adjustments: dict[str, Any],
            summary_lines: list[str],
        ) -> None:
            if not adjustments.get("minimal_processing"):
                return

            disabled: list[str] = []

            if self.glue_cb.isChecked():
                self.glue_cb.setChecked(False)
                disabled.append("Glue")
            if self.saturation_enable_cb.isChecked():
                self.saturation_enable_cb.setChecked(False)
                disabled.append("Saturación")
            if self.saturation_per_band_cb.isChecked():
                self.saturation_per_band_cb.setChecked(False)
                disabled.append("Saturación por bandas")
            if self.multiband_limiter_cb.isChecked():
                self.multiband_limiter_cb.setChecked(False)
                disabled.append("Limitador multibanda")
            if self.stereo_dynamic_cb.isChecked():
                self.stereo_dynamic_cb.setChecked(False)
                disabled.append("Stereo dinámico")
            has_band_eq = bool(self._get_auto_master_band_eq_adjustments(adjustments))
            if not has_band_eq and not adjustments.get("dynamic_eq_enabled", True) and self.dynamic_eq_cb.isChecked():
                self.dynamic_eq_cb.setChecked(False)
                disabled.append("EQ dinámica")

            if disabled:
                summary_lines.append(
                    "○ Procesamiento mínimo activado: " + ", ".join(disabled)
                )

        def _apply_processing_profile_overrides(
            self,
            adjustments: dict[str, Any],
            summary_lines: list[str],
        ) -> None:
            profile = str(adjustments.get("processing_profile", "Normal") or "Normal")
            if profile == "Conservador":
                self._apply_minimal_processing_overrides(adjustments, summary_lines)
                return
            if profile != "Agresivo":
                return

            enabled: list[str] = []
            if not self.glue_cb.isChecked():
                self.glue_cb.setChecked(True)
                enabled.append("Glue")
            if not self.saturation_enable_cb.isChecked():
                self.saturation_enable_cb.setChecked(True)
                enabled.append("Saturación")
            if not self.stereo_dynamic_cb.isChecked():
                self.stereo_dynamic_cb.setChecked(True)
                enabled.append("Stereo dinámico")
            if adjustments.get("minimal_processing"):
                adjustments["minimal_processing"] = False

            if enabled:
                summary_lines.append(
                    "○ Perfil agresivo activado: " + ", ".join(enabled)
                )

        def _update_auto_master_profile_label(self, adjustments: dict[str, Any] | None) -> None:
            if not hasattr(self, "auto_master_profile_label"):
                return
            profile = "Normal"
            if adjustments:
                profile = str(adjustments.get("processing_profile", profile) or profile)
                reasons = adjustments.get("processing_profile_reasons", [])
                if isinstance(reasons, list) and reasons:
                    reason_text = ", ".join(str(reason) for reason in reasons[:3])
                    self.auto_master_profile_label.setText(f"Perfil Auto-Master: {profile} ({reason_text})")
                    return
            self.auto_master_profile_label.setText(f"Perfil Auto-Master: {profile}")

        def _resolve_standard_auto_master_style(self, style: str) -> str:
            style_map = {
                "Espacial": "Natural (Acústico, Jazz, Folk)",
                "Cinemático": "Claridad (Clásica, R&B, Cantautor)",
                "Empuje": "Fuego (Trap, Reguetón, Hip-Hop)",
                "Techno": "Fuego (Trap, Reguetón, Hip-Hop)",
                "House": "Fuego (Trap, Reguetón, Hip-Hop)",
                "Trance": "Fuego (Trap, Reguetón, Hip-Hop)",
                "Big Room": "Fuego (Trap, Reguetón, Hip-Hop)",
                "Drum & Bass": "Fuego (Trap, Reguetón, Hip-Hop)",
                "Hardstyle": "Fuego (Trap, Reguetón, Hip-Hop)",
                "Minimal": "Natural (Acústico, Jazz, Folk)",
                "Disco": "Cinta (Jazz, Alternativa, Indie)",
            }
            for key, standard in style_map.items():
                if key in style:
                    return standard
            if style in AUTO_MASTER_STANDARD_STYLES:
                return style
            return "Universal (Rock, Pop, Electrónica)"

        def _enforce_minimal_saturation_caps(self, summary_lines: list[str] | None = None) -> None:
            global_cap_applied = False
            band_cap_applied = False
            sensitive_labels = {"High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"}
            max_global_drive = 1.5
            max_global_mix = 6.0
            max_band_drive = 2.0
            max_band_mix = 5.0
            max_sensitive_drive = 0.8
            max_sensitive_mix = 2.0

            if self.saturation_enable_cb.isChecked():
                if self.saturation_drive_spin.value() > max_global_drive:
                    self.saturation_drive_spin.setValue(max_global_drive)
                    global_cap_applied = True
                if self.saturation_mix_spin.value() > max_global_mix:
                    self.saturation_mix_spin.setValue(max_global_mix)
                    global_cap_applied = True

            if self.saturation_per_band_cb.isChecked() and self.saturation_band_drive_spins and self.saturation_band_mix_spins:
                for label, drive_spin in self.saturation_band_drive_spins.items():
                    mix_spin = self.saturation_band_mix_spins.get(label)
                    if mix_spin is None:
                        continue
                    drive_cap = max_sensitive_drive if label in sensitive_labels else max_band_drive
                    mix_cap = max_sensitive_mix if label in sensitive_labels else max_band_mix
                    if drive_spin.value() > drive_cap:
                        drive_spin.setValue(drive_cap)
                        band_cap_applied = True
                    if mix_spin.value() > mix_cap:
                        mix_spin.setValue(mix_cap)
                        band_cap_applied = True

            if summary_lines is not None:
                if global_cap_applied:
                    summary_lines.append("🎛️ Saturación global limitada a perfil mínimo (drive <= 1.5 dB, mix <= 6%).")
                if band_cap_applied:
                    summary_lines.append("🎛️ Saturación por banda limitada para evitar suma en medios/agudos.")

        def _enforce_conservative_preset_limits(self, summary_lines: list[str] | None = None) -> None:
            """Aplica límites conservadores a presets para mantener resultados estables."""
            touched = False

            if self.deesser_intensity_spin.value() > 0.72:
                self.deesser_intensity_spin.setValue(0.72)
                touched = True

            for spin in (self.eq_low_spin, self.sub_bass_spin, self.eq_mid_spin, self.eq_high_spin):
                if spin.value() > 1.0:
                    spin.setValue(1.0)
                    touched = True
                elif spin.value() < -1.0:
                    spin.setValue(-1.0)
                    touched = True

            for spin in self.dynamic_band_spins.values():
                if spin.value() > 1.2:
                    spin.setValue(1.2)
                    touched = True
                elif spin.value() < -1.2:
                    spin.setValue(-1.2)
                    touched = True

            if self.glue_ratio_spin.value() > 1.8:
                self.glue_ratio_spin.setValue(1.8)
                touched = True
            if self.glue_makeup_spin.value() > 0.6:
                self.glue_makeup_spin.setValue(0.6)
                touched = True

            if self.stereo_dynamic_mix_spin.value() > 0.45:
                self.stereo_dynamic_mix_spin.setValue(0.45)
                touched = True

            limiter_text = self.limiter_preset_combo.currentText()
            if limiter_text in ("Loud (-0.6 / 60)", "Punchy (-0.8 / 80)", "Clasico (-0.9 / 120)"):
                self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
                self._apply_limiter_preset()
                touched = True

            for label, spin in self.multiband_limiter_spins.items():
                safe_floor = -4.8 if label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)") else -4.0
                safe_ceiling = -1.8 if label in ("Subbass (20-60 Hz)", "Bass (60-250 Hz)") else -1.2
                val = spin.value()
                if val > safe_ceiling:
                    spin.setValue(safe_ceiling)
                    touched = True
                elif val < safe_floor:
                    spin.setValue(safe_floor)
                    touched = True

            if touched and summary_lines is not None:
                summary_lines.append("🧯 Presets ajustados a límites conservadores (safe mastering).")

        def _apply_auto_master(
            self,
            emit_log: bool = True,
            write_preset: bool = True,
            analysis_result: tuple[object, object, object] | None = None,
        ) -> None:
            if getattr(self, "_applying_auto_master", False):
                return
            self._applying_auto_master = True
            raw_style = self.auto_master_style_combo.currentText()
            style = self._resolve_standard_auto_master_style(raw_style)
            if style != raw_style:
                self.auto_master_style_combo.blockSignals(True)
                self.auto_master_style_combo_tab.blockSignals(True)
                self.auto_master_style_combo.setCurrentText(style)
                self.auto_master_style_combo_tab.setCurrentText(style)
                self.auto_master_style_combo.blockSignals(False)
                self.auto_master_style_combo_tab.blockSignals(False)
            summary_lines = [f"Estilo: {style}"]
            motion_profile, motion_amount = self._get_motion_preferences()
            summary_lines.append(
                f"Movimiento: perfil={motion_profile}, amount={motion_amount*100:.0f}%"
            )
            ia_providers, ia_status = self._build_auto_master_ia_providers()
            if ia_status != "off":
                summary_lines.append(f"Master asistido por IA: {ia_status}")
            
            # Análisis inteligente del audio si está habilitado
            characteristics = None
            adjustments = None
            intelligent_mode = self.auto_master_intelligent_cb.isChecked()
            
            if intelligent_mode and analysis_result is not None:
                characteristics, recommendations, spectrum_data = analysis_result
                if isinstance(characteristics, dict):
                    try:
                        characteristics = AudioCharacteristics(
                            band_stats=characteristics.get("band_stats", {}) if isinstance(characteristics.get("band_stats", {}), dict) else {},
                            voice_rms=characteristics.get("voice_rms", None),
                            clipping_info=characteristics.get("clipping_info", None),
                            noise_info=characteristics.get("noise_info", None),
                            stereo_info=characteristics.get("stereo_info", None),
                            band_peaks=characteristics.get("band_peaks", None),
                            silence_info=characteristics.get("silence_info", None),
                            loudness_metrics=characteristics.get("loudness_metrics", None),
                            tempo_info=characteristics.get("tempo_info", None),
                        )
                    except Exception:
                        pass
                summary_lines.append("\n=== ANÁLISIS INTELIGENTE ===")
                if isinstance(recommendations, list):
                    summary_lines.extend(str(item) for item in recommendations)

                if isinstance(spectrum_data, dict) and spectrum_data and SPECTRUM_AVAILABLE:
                    self._update_spectrum_plot(spectrum_data)
                    summary_lines.append("✓ Espectro analizado y graficado")

                minimal_lra, minimal_crest = self._get_minimal_processing_thresholds()
                adjustments = adapt_preset_to_audio(
                    style,
                    characteristics,
                    minimal_lra_threshold=minimal_lra,
                    minimal_crest_threshold=minimal_crest,
                    motion_profile_preference=motion_profile,
                    motion_amount=motion_amount,
                    ia_providers=ia_providers,
                    target_lufs=self.target_spin.value(),
                    true_peak=self.true_peak_spin.value(),
                    audio_id=self.input_edit.text().strip() or "unknown",
                )
                self._last_auto_master_characteristics = characteristics
                self._last_auto_master_adjustments = adjustments
                actions = adjustments.get("audio_actions")
                self._ai_audio_actions = [dict(action) for action in actions] if isinstance(actions, list) else []
                self._ai_source_fingerprint = adjustments.get("source_fingerprint")

                if adjustments.get("warnings"):
                    summary_lines.append("\n⚠️  === ADVERTENCIAS ===")
                    summary_lines.extend(adjustments["warnings"])

                if adjustments.get("alternative_presets"):
                    summary_lines.append("\n💡 === PRESETS ALTERNATIVOS SUGERIDOS ===")
                    for alt_preset in adjustments["alternative_presets"]:
                        summary_lines.append(f"   • {alt_preset}")

                if adjustments.get("suggestions"):
                    summary_lines.append("\n🎛️  === SUGERENCIAS DE EQ ===")
                    summary_lines.extend(adjustments["suggestions"])

                self._update_auto_master_profile_label(adjustments)
                summary_lines.append("\n=== AJUSTES AUTOMÁTICOS ===")
                summary_lines.extend(adjustments["notes"])
                summary_lines.append("")

            elif intelligent_mode:
                input_file = self.input_edit.text().strip()
                if input_file and pathlib.Path(input_file).exists():
                    summary_lines.append("\n=== ANÁLISIS INTELIGENTE ===")
                    try:
                        characteristics, recommendations, spectrum_data = analyze_audio_for_automaster(
                            input_path=pathlib.Path(input_file),
                            verbose=False,
                            use_spectrum=True,
                            full_analysis=True,
                        )
                        summary_lines.extend(recommendations)
                        
                        # Actualizar gráfico de espectro si disponible
                        if spectrum_data and SPECTRUM_AVAILABLE:
                            self._update_spectrum_plot(spectrum_data)
                            summary_lines.append("✓ Espectro analizado y graficado")
                        
                        # Adaptar preset según características
                        minimal_lra, minimal_crest = self._get_minimal_processing_thresholds()
                        adjustments = adapt_preset_to_audio(
                            style,
                            characteristics,
                            minimal_lra_threshold=minimal_lra,
                            minimal_crest_threshold=minimal_crest,
                            motion_profile_preference=motion_profile,
                            motion_amount=motion_amount,
                            ia_providers=ia_providers,
                            target_lufs=self.target_spin.value(),
                            true_peak=self.true_peak_spin.value(),
                            audio_id=input_file,
                        )
                        self._last_auto_master_characteristics = characteristics
                        self._last_auto_master_adjustments = adjustments
                        actions = adjustments.get("audio_actions")
                        self._ai_audio_actions = [dict(action) for action in actions] if isinstance(actions, list) else []
                        self._ai_source_fingerprint = adjustments.get("source_fingerprint")
                        
                        # Mostrar advertencias si existen
                        if adjustments.get("warnings"):
                            summary_lines.append("\n⚠️  === ADVERTENCIAS ===")
                            summary_lines.extend(adjustments["warnings"])
                        
                        # Mostrar presets alternativos si existen
                        if adjustments.get("alternative_presets"):
                            summary_lines.append("\n💡 === PRESETS ALTERNATIVOS SUGERIDOS ===")
                            for alt_preset in adjustments["alternative_presets"]:
                                summary_lines.append(f"   • {alt_preset}")
                        
                        # Mostrar sugerencias de EQ si existen
                        if adjustments.get("suggestions"):
                            summary_lines.append("\n🎛️  === SUGERENCIAS DE EQ ===")
                            summary_lines.extend(adjustments["suggestions"])

                        self._update_auto_master_profile_label(adjustments)
                        summary_lines.append("\n=== AJUSTES AUTOMÁTICOS ===")
                        summary_lines.extend(adjustments["notes"])
                        summary_lines.append("")
                        
                    except Exception as e:
                        summary_lines.append(f"⚠ Error en análisis: {str(e)}")
                        summary_lines.append("Aplicando preset estándar...")
                else:
                    summary_lines.append("⚠ No hay archivo de entrada - preset estándar")

            if adjustments is None:
                self.auto_master_profile_label.setText("Perfil Auto-Master: SUNO Clásico (fallback)")
                self._ai_audio_actions = []
                self._ai_source_fingerprint = None
            
            summary_lines.append("\n=== CONFIGURACIÓN APLICADA ===")
            
            # Función para aplicar ajustes de EQ automáticamente
            def apply_eq_corrections() -> None:
                """Aplica correcciones de EQ basadas en el análisis inteligente."""
                self._apply_auto_master_band_eq_adjustments(adjustments, summary_lines)
            
            def set_band_saturation(profile: dict[str, tuple[float, float]]) -> None:
                if not self.saturation_band_drive_spins or not self.saturation_band_mix_spins:
                    return
                for label, spin in self.saturation_band_drive_spins.items():
                    # Por defecto no saturar bandas no definidas en el perfil.
                    drive, mix = profile.get(label, (0.0, 0.0))
                    
                    # Aplicar multiplicadores globales de saturación (LUFS/balance/dinámica)
                    # para que el modo inteligente reduzca/aumente también la saturación por banda.
                    if adjustments:
                        drive *= adjustments.get("saturation_drive_mult", 1.0)
                        mix *= adjustments.get("saturation_mix_mult", 1.0)

                    # Aplicar ajustes inteligentes si existen
                    if adjustments and label in adjustments.get("band_saturation_adjustments", {}):
                        band_adj = adjustments["band_saturation_adjustments"][label]
                        drive *= band_adj.get("drive_mult", 1.0)
                        mix *= band_adj.get("mix_mult", 1.0)
                    
                    spin.setValue(drive)
                    mix_spin = self.saturation_band_mix_spins.get(label)
                    if mix_spin is not None:
                        mix_spin.setValue(mix)

            # Reset "Color" a valores seguros antes de aplicar un estilo.
            # Evita que queden saturaciones activas por default o de un estilo anterior.
            self.eq_low_spin.setValue(0.0)
            self.sub_bass_spin.setValue(0.0)
            self.eq_mid_spin.setValue(0.0)
            self.eq_high_spin.setValue(0.0)
            self.tilt_eq_spin.setValue(0.0)
            self.saturation_enable_cb.setChecked(False)
            self.saturation_per_band_cb.setChecked(False)
            self.saturation_drive_spin.setValue(0.0)
            self.saturation_mix_spin.setValue(0.0)
            if self.saturation_band_drive_spins and self.saturation_band_mix_spins:
                for spin in self.saturation_band_drive_spins.values():
                    spin.setValue(0.0)
                for spin in self.saturation_band_mix_spins.values():
                    spin.setValue(0.0)

            if "SUNO Clean" in style:
                # Preset técnico para masters ya mezclados (Suno): correcciones mínimas y control seguro.
                # Objetivo más suave para evitar saltos bruscos de ganancia en material irregular.
                self.target_spin.setValue(-15.5)
                self.tone_eq_preset_combo.setCurrentText("Neutral (0 / 0 / 0)")
                # Anti-fatiga: bajar presencia/brillo sostenido y un toque de sub-bass.
                self.dynamic_eq_preset_combo.setCurrentText("Manual")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Jazz (-24 / 1.3 / 40 / 200 / 0.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(False)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(False)
                self.saturation_enable_cb.setChecked(False)
                self.saturation_per_band_cb.setChecked(False)
                self.stereo_width_cb.setChecked(True)
                self.stereo_dynamic_cb.setChecked(False)
                self.stereo_dynamic_mix_spin.setValue(0.20)
                if self.stereo_dynamic_band_mix_spins:
                    recommended_mix = {
                        "Subbass (20-60 Hz)": 0.00,
                        "Bass (60-250 Hz)": 0.03,
                        "Low-Mid (250-500 Hz)": 0.06,
                        "Mid (500-2k Hz)": 0.10,
                        "High-Mid (2k-6k Hz)": 0.14,
                        "Air (6k-16k Hz)": 0.18,
                    }
                    for band_label, mix_val in recommended_mix.items():
                        mix_spin = self.stereo_dynamic_band_mix_spins.get(band_label)
                        if mix_spin is not None:
                            mix_spin.setValue(mix_val)
                self.multiband_limiter_cb.setChecked(False)
                if self.multiband_limiter_spins:
                    safe_thresholds = {
                        "Subbass (20-60 Hz)": -4.2,
                        "Bass (60-250 Hz)": -3.6,
                        "Low-Mid (250-500 Hz)": -2.2,
                        "Mid (500-2k Hz)": -2.0,
                        "High-Mid (2k-6k Hz)": -3.8,
                        "Air (6k-16k Hz)": -5.2,
                    }
                    for band_label, thr in safe_thresholds.items():
                        thr_spin = self.multiband_limiter_spins.get(band_label)
                        if thr_spin is not None:
                            thr_spin.setValue(thr)
                self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
                self.true_peak_spin.setValue(-2.2)
                self.fade_in_spin.setValue(0.03)
                self.fade_out_spin.setValue(1.2)
                if self.dynamic_band_spins:
                    anti_fatigue = {
                        "Subbass (20-60 Hz)": -0.25,
                        "Bass (60-250 Hz)": 0.00,
                        "Low-Mid (250-500 Hz)": -0.10,
                        "Mid (500-2k Hz)": 0.00,
                        "High-Mid (2k-6k Hz)": -0.85,
                        "Air (6k-16k Hz)": -1.15,
                    }
                    for band_label, val in anti_fatigue.items():
                        spin = self.dynamic_band_spins.get(band_label)
                        if spin is not None:
                            spin.setEnabled(True)
                            spin.setValue(val)
                summary_lines.append(
                    "Preset SUNO Clean: ajuste conservador anti-fatiga (menos high-mid/air y subbass levemente controlado)."
                )
            elif "Universal" in style:
                self.tone_eq_preset_combo.setCurrentText("Neutral (0 / 0 / 0)")
                self.eq_low_spin.setValue(0.0)
                self.sub_bass_spin.setValue(-0.8)
                self.eq_mid_spin.setValue(0.0)
                self.eq_high_spin.setValue(0.0)
                self.tilt_eq_spin.setValue(0.0)
                self.dynamic_eq_preset_combo.setCurrentText("Balanced (+0.2 / +0.2 / 0 / 0 / 0 / +0.2)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Jazz (-24 / 1.3 / 40 / 200 / 0.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.saturation_enable_cb.setChecked(False)
                self.stereo_width_cb.setChecked(True)
                self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
                # Fades
                self.fade_in_spin.setValue(0.05)
                self.fade_out_spin.setValue(1.5)
                summary_lines.append("Balance tonal dinámico y natural para cualquier género. Sub bass reducido para controlar exceso de low-end.")
            elif "Cinta" in style:
                self.tone_eq_preset_combo.setCurrentText("Warm (+1.0 / -0.5 / -0.5)")
                self.dynamic_eq_preset_combo.setCurrentText("Warm Glue (+0.5 / +0.5 / -0.3 / -0.2 / 0 / 0)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Clasico (-22 / 1.5 / 30 / 180 / 0.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                
                # Aplicar multiplicadores inteligentes
                sat_drive = 3.0
                sat_mix = 20.0
                if adjustments:
                    sat_drive *= adjustments.get("saturation_drive_mult", 1.0)
                    sat_mix *= adjustments.get("saturation_mix_mult", 1.0)
                self.saturation_drive_spin.setValue(sat_drive)
                self.saturation_mix_spin.setValue(sat_mix)
                
                self.stereo_width_cb.setChecked(True)
                self.limiter_preset_combo.setCurrentText("Seguro (-1.0 / 120)")
                # Fades
                self.fade_in_spin.setValue(0.1)
                self.fade_out_spin.setValue(2.0)
                summary_lines.append("Saturación cálida con dinámica analógica (Jazz, Indie, Rock).")
            elif "Natural" in style:
                self.tone_eq_preset_combo.setCurrentText("Neutral (0 / 0 / 0)")
                self.dynamic_eq_preset_combo.setCurrentText("Neutral (0 / 0 / 0 / 0 / 0 / 0)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Jazz (-24 / 1.3 / 40 / 200 / 0.0)")
                self.dynamic_eq_cb.setChecked(False)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(False)
                self.saturation_enable_cb.setChecked(False)
                self.stereo_width_cb.setChecked(True)
                self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
                # Fades
                self.fade_in_spin.setValue(0.08)
                self.fade_out_spin.setValue(2.0)
                summary_lines.append("Dinámicas equilibradas con compresión suave (Acústico, Folk).")
            elif "Espacial" in style:
                self.tone_eq_preset_combo.setCurrentText("Air (0 / -0.5 / +1.5)")
                self.dynamic_eq_preset_combo.setCurrentText("Airy (-0.2 / -0.2 / 0 / +0.1 / +0.4 / +0.8)")
                self.deesser_preset_combo.setCurrentText("Soprano (8.0 kHz / 0.75)")
                self.glue_preset_combo.setCurrentText("Pop (-18 / 2.0 / 12 / 140 / 0.8)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.5)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tube")
                self.saturation_drive_spin.setValue(2.0)
                self.saturation_mix_spin.setValue(15.0)
                self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
                # Fades
                self.fade_in_spin.setValue(0.2)
                self.fade_out_spin.setValue(3.5)
                summary_lines.append("Reverberación atmosférica y amplitud de stereo mejorada (Ambient).")
            elif "Fuego" in style:
                self.tone_eq_preset_combo.setCurrentText("Low Punch (+1.5 / -0.5 / 0)")
                self.dynamic_eq_preset_combo.setCurrentText("Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)")
                self.deesser_preset_combo.setCurrentText("Rap agresivo (6.0 kHz / 0.85)")
                self.glue_preset_combo.setCurrentText("Disco (-16 / 2.4 / 10 / 120 / 1.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.7)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(2.0)
                self.saturation_mix_spin.setValue(6.0)
                set_band_saturation(
                    {
                        "Subbass (20-60 Hz)": (1.5, 6.0),
                        "Bass (60-250 Hz)": (1.5, 6.0),
                        "Low-Mid (250-500 Hz)": (0.8, 1.5),
                        "Mid (500-2k Hz)": (0.0, 0.0),
                        "High-Mid (2k-6k Hz)": (0.0, 0.0),
                        "Air (6k-16k Hz)": (0.0, 0.0),
                    }
                )
                self.limiter_preset_combo.setCurrentText("Punchy (-0.8 / 80)")
                # Fades
                self.fade_in_spin.setValue(0.05)
                self.fade_out_spin.setValue(1.0)
                summary_lines.append("Bajos impactantes y claridad de rango medio (Trap, Reguetón).")
            elif "Cinemático" in style:
                self.tone_eq_preset_combo.setCurrentText("Air (0 / -0.5 / +1.5)")
                self.dynamic_eq_preset_combo.setCurrentText("Airy (-0.2 / -0.2 / 0 / +0.1 / +0.4 / +0.8)")
                self.deesser_preset_combo.setCurrentText("Soprano (8.0 kHz / 0.75)")
                self.glue_preset_combo.setCurrentText("Pop (-18 / 2.0 / 12 / 140 / 0.8)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tube")
                self.saturation_drive_spin.setValue(4.0)
                self.saturation_mix_spin.setValue(30.0)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.3)
                self.limiter_preset_combo.setCurrentText("Clasico (-0.9 / 120)")
                # Fades
                self.fade_in_spin.setValue(0.25)
                self.fade_out_spin.setValue(3.0)
                summary_lines.append("Saturación intensa y distorsión armónica (Orquestal, Soundtrack).")
            elif "Empuje" in style:
                self.tone_eq_preset_combo.setCurrentText("Bright (-0.5 / 0 / +1.0)")
                self.dynamic_eq_preset_combo.setCurrentText("Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)")
                self.deesser_preset_combo.setCurrentText("Rap agresivo (6.0 kHz / 0.85)")
                self.glue_preset_combo.setCurrentText("Disco (-16 / 2.4 / 10 / 120 / 1.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.7)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(2.5)
                self.saturation_mix_spin.setValue(8.0)
                set_band_saturation(
                    {
                        "Subbass (20-60 Hz)": (2.0, 7.0),
                        "Bass (60-250 Hz)": (2.0, 7.0),
                        "Low-Mid (250-500 Hz)": (1.0, 2.0),
                        "Mid (500-2k Hz)": (0.0, 0.0),
                        "High-Mid (2k-6k Hz)": (1.0, 3.0),
                        "Air (6k-16k Hz)": (1.5, 4.0),
                    }
                )
                self.limiter_preset_combo.setCurrentText("Punchy (-0.8 / 80)")
                # Fades
                self.fade_in_spin.setValue(0.05)
                self.fade_out_spin.setValue(1.0)
                summary_lines.append("Bajo enérgico combinado con agudos potenciados (EDM, Bass Music).")
            elif "Claridad" in style:
                self.tone_eq_preset_combo.setCurrentText("Air (0 / -0.5 / +1.5)")
                self.dynamic_eq_preset_combo.setCurrentText("Balanced (+0.2 / +0.2 / 0 / 0 / 0 / +0.2)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Jazz (-24 / 1.3 / 40 / 200 / 0.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(False)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.5)
                self.saturation_enable_cb.setChecked(False)
                self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
                # Fades
                self.fade_in_spin.setValue(0.1)
                self.fade_out_spin.setValue(2.5)
                summary_lines.append("Agudos prístinos con ligera expansión dinámica (Clásica, R&B).")
            
            # ==================== ELECTRÓNICA - DISCOTECA ====================
            
            elif "Techno" in style:
                # Techno: Oscuro, bajo profundo, kicks duros, atmósferas industriales
                self.tone_eq_preset_combo.setCurrentText("Low Punch (+1.5 / -0.5 / 0)")
                self.dynamic_eq_preset_combo.setCurrentText("Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Disco (-16 / 2.4 / 10 / 120 / 1.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(False)  # Sin vocales
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.6)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(3.0)
                self.saturation_mix_spin.setValue(12.0)
                set_band_saturation({
                    "Subbass (20-60 Hz)": (3.0, 10.0),
                    "Bass (60-250 Hz)": (2.5, 8.0),
                    "Low-Mid (250-500 Hz)": (0.5, 2.0),
                    "Mid (500-2k Hz)": (0.0, 0.0),
                    "High-Mid (2k-6k Hz)": (1.0, 3.0),
                    "Air (6k-16k Hz)": (0.5, 2.0),
                })
                self.limiter_preset_combo.setCurrentText("Punchy (-0.8 / 80)")
                self.fade_in_spin.setValue(0.02)
                self.fade_out_spin.setValue(0.5)
                summary_lines.append("🎧 Techno oscuro con kicks duros y bajo profundo.")
            
            elif "House" in style:
                # House: Groove, bajo cálido, vocales claras, ambiente disco
                self.tone_eq_preset_combo.setCurrentText("Warm (+1.0 / -0.5 / -0.5)")
                self.dynamic_eq_preset_combo.setCurrentText("Warm Glue (+0.5 / +0.5 / -0.3 / -0.2 / 0 / 0)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Pop (-18 / 2.0 / 12 / 140 / 0.8)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.5)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(2.5)
                self.saturation_mix_spin.setValue(15.0)
                set_band_saturation({
                    "Subbass (20-60 Hz)": (2.0, 8.0),
                    "Bass (60-250 Hz)": (2.0, 7.0),
                    "Low-Mid (250-500 Hz)": (1.0, 3.0),
                    "Mid (500-2k Hz)": (0.5, 2.0),
                    "High-Mid (2k-6k Hz)": (0.5, 2.0),
                    "Air (6k-16k Hz)": (1.0, 3.0),
                })
                self.limiter_preset_combo.setCurrentText("Clasico (-0.9 / 120)")
                self.fade_in_spin.setValue(0.05)
                self.fade_out_spin.setValue(1.5)
                summary_lines.append("🎧 House con groove cálido y vocales claras.")
            
            elif "Trance" in style:
                # Trance: Melodías épicas, builds largos, leads brillantes, pads amplios
                self.tone_eq_preset_combo.setCurrentText("Bright (-0.5 / 0 / +1.0)")
                self.dynamic_eq_preset_combo.setCurrentText("Airy (-0.2 / -0.2 / 0 / +0.1 / +0.4 / +0.8)")
                self.deesser_preset_combo.setCurrentText("Soprano (8.0 kHz / 0.75)")
                self.glue_preset_combo.setCurrentText("Pop (-18 / 2.0 / 12 / 140 / 0.8)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.7)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tube")
                self.saturation_drive_spin.setValue(2.0)
                self.saturation_mix_spin.setValue(10.0)
                set_band_saturation({
                    "Subbass (20-60 Hz)": (1.5, 5.0),
                    "Bass (60-250 Hz)": (1.5, 5.0),
                    "Low-Mid (250-500 Hz)": (0.5, 2.0),
                    "Mid (500-2k Hz)": (1.0, 3.0),
                    "High-Mid (2k-6k Hz)": (1.5, 5.0),
                    "Air (6k-16k Hz)": (2.0, 6.0),
                })
                self.limiter_preset_combo.setCurrentText("Punchy (-0.8 / 80)")
                self.fade_in_spin.setValue(0.1)
                self.fade_out_spin.setValue(3.0)
                summary_lines.append("🎧 Trance épico con leads brillantes y pads amplios.")
            
            elif "Big Room" in style:
                # Big Room: Festival, mainstage, drops masivos, máximo loudness
                self.tone_eq_preset_combo.setCurrentText("Low Punch (+1.5 / -0.5 / 0)")
                self.dynamic_eq_preset_combo.setCurrentText("Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)")
                self.deesser_preset_combo.setCurrentText("Rap agresivo (6.0 kHz / 0.85)")
                self.glue_preset_combo.setCurrentText("Disco (-16 / 2.4 / 10 / 120 / 1.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.8)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(4.0)
                self.saturation_mix_spin.setValue(18.0)
                set_band_saturation({
                    "Subbass (20-60 Hz)": (3.5, 12.0),
                    "Bass (60-250 Hz)": (3.0, 10.0),
                    "Low-Mid (250-500 Hz)": (1.0, 3.0),
                    "Mid (500-2k Hz)": (0.5, 2.0),
                    "High-Mid (2k-6k Hz)": (1.5, 5.0),
                    "Air (6k-16k Hz)": (2.0, 6.0),
                })
                self.limiter_preset_combo.setCurrentText("Punchy (-0.8 / 80)")
                self.fade_in_spin.setValue(0.02)
                self.fade_out_spin.setValue(0.5)
                summary_lines.append("🎧 Big Room con drops masivos para festival.")
            
            elif "Drum & Bass" in style:
                # D&B: Breaks rápidos, bajo envolvente, energía intensa
                self.tone_eq_preset_combo.setCurrentText("Low Punch (+1.5 / -0.5 / 0)")
                self.dynamic_eq_preset_combo.setCurrentText("Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Disco (-16 / 2.4 / 10 / 120 / 1.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.6)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(3.5)
                self.saturation_mix_spin.setValue(14.0)
                set_band_saturation({
                    "Subbass (20-60 Hz)": (4.0, 15.0),
                    "Bass (60-250 Hz)": (3.0, 12.0),
                    "Low-Mid (250-500 Hz)": (1.0, 3.0),
                    "Mid (500-2k Hz)": (0.5, 2.0),
                    "High-Mid (2k-6k Hz)": (2.0, 6.0),
                    "Air (6k-16k Hz)": (1.5, 4.0),
                })
                self.limiter_preset_combo.setCurrentText("Punchy (-0.8 / 80)")
                self.fade_in_spin.setValue(0.02)
                self.fade_out_spin.setValue(0.5)
                summary_lines.append("🎧 Drum & Bass con breaks rápidos y bajo envolvente.")
            
            elif "Hardstyle" in style:
                # Hardstyle/Hardcore: Kicks distorsionados, máxima agresividad
                self.tone_eq_preset_combo.setCurrentText("Low Punch (+1.5 / -0.5 / 0)")
                self.dynamic_eq_preset_combo.setCurrentText("Punchy (+0.6 / +0.8 / -0.3 / 0 / +0.2 / 0)")
                self.deesser_preset_combo.setCurrentText("Rap agresivo (6.0 kHz / 0.85)")
                self.glue_preset_combo.setCurrentText("Disco (-16 / 2.4 / 10 / 120 / 1.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(False)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.5)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(5.0)
                self.saturation_mix_spin.setValue(25.0)
                set_band_saturation({
                    "Subbass (20-60 Hz)": (5.0, 20.0),
                    "Bass (60-250 Hz)": (4.0, 18.0),
                    "Low-Mid (250-500 Hz)": (2.0, 8.0),
                    "Mid (500-2k Hz)": (1.0, 4.0),
                    "High-Mid (2k-6k Hz)": (2.0, 6.0),
                    "Air (6k-16k Hz)": (1.5, 4.0),
                })
                self.limiter_preset_combo.setCurrentText("Punchy (-0.8 / 80)")
                self.fade_in_spin.setValue(0.01)
                self.fade_out_spin.setValue(0.3)
                summary_lines.append("🎧 Hardstyle/Hardcore con kicks distorsionados.")
            
            elif "Minimal" in style:
                # Minimal/Dub Techno: Sutileza, espacio, texturas
                self.tone_eq_preset_combo.setCurrentText("Neutral (0 / 0 / 0)")
                self.dynamic_eq_preset_combo.setCurrentText("Balanced (+0.2 / +0.2 / 0 / 0 / 0 / +0.2)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Jazz (-24 / 1.3 / 40 / 200 / 0.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(False)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(False)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.4)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(False)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(1.5)
                self.saturation_mix_spin.setValue(8.0)
                self.limiter_preset_combo.setCurrentText("Transparente (-1.0 / 200)")
                self.fade_in_spin.setValue(0.1)
                self.fade_out_spin.setValue(2.0)
                summary_lines.append("🎧 Minimal con espacio, sutileza y texturas.")
            
            elif "Disco" in style:
                # Nu-Disco/Funky: Groove, bajo funky, brillo disco
                self.tone_eq_preset_combo.setCurrentText("Warm (+1.0 / -0.5 / -0.5)")
                self.dynamic_eq_preset_combo.setCurrentText("Warm Glue (+0.5 / +0.5 / -0.3 / -0.2 / 0 / 0)")
                self.deesser_preset_combo.setCurrentText("Voz hablada (5.5 kHz / 0.60)")
                self.glue_preset_combo.setCurrentText("Clasico (-22 / 1.5 / 30 / 180 / 0.0)")
                self.dynamic_eq_cb.setChecked(True)
                self.deesser_cb.setChecked(True)
                self.glue_cb.setChecked(True)
                self.brickwall_cb.setChecked(True)
                self.auto_band_gain_cb.setChecked(True)
                self.stereo_width_cb.setChecked(True)
                self.dynamic_eq_cb.setChecked(True)  # Activa procesamiento por bandas (incluyendo stereo dynamic)
                self.stereo_dynamic_cb.setChecked(True)
                self.stereo_dynamic_mix_spin.setValue(0.6)
                self.saturation_enable_cb.setChecked(True)
                self.saturation_per_band_cb.setChecked(True)
                self.saturation_type_combo.setCurrentText("Tape")
                self.saturation_drive_spin.setValue(3.0)
                self.saturation_mix_spin.setValue(20.0)
                set_band_saturation({
                    "Subbass (20-60 Hz)": (2.0, 8.0),
                    "Bass (60-250 Hz)": (2.5, 10.0),
                    "Low-Mid (250-500 Hz)": (1.5, 5.0),
                    "Mid (500-2k Hz)": (1.0, 3.0),
                    "High-Mid (2k-6k Hz)": (1.5, 5.0),
                    "Air (6k-16k Hz)": (2.0, 7.0),
                })
                self.limiter_preset_combo.setCurrentText("Clasico (-0.9 / 120)")
                self.fade_in_spin.setValue(0.08)
                self.fade_out_spin.setValue(2.0)
                summary_lines.append("🎧 Nu-Disco con groove funky y brillo vintage.")
            
            # Aplicar presets
            self._apply_tone_eq_preset()
            self._apply_dynamic_eq_preset()
            self._apply_deesser_preset()
            self._apply_glue_preset()
            self._apply_limiter_preset()
            
            # Aplicar correcciones de EQ si el análisis inteligente lo sugiere
            if intelligent_mode and adjustments and adjustments.get("eq_adjustments"):
                apply_eq_corrections()
            
            # Aplicar ajustes inteligentes finales si están disponibles
            if adjustments:
                # Ajustar saturación global si no se hizo en el preset específico
                if "Cinta" not in style:  # Ya se ajustó arriba para Cinta
                    current_drive = self.saturation_drive_spin.value()
                    current_mix = self.saturation_mix_spin.value()
                    self.saturation_drive_spin.setValue(
                        current_drive * adjustments.get("saturation_drive_mult", 1.0)
                    )
                    self.saturation_mix_spin.setValue(
                        current_mix * adjustments.get("saturation_mix_mult", 1.0)
                    )
                
                # Ajustar glue compression threshold
                glue_offset = adjustments.get("glue_threshold_offset", 0.0)
                if abs(glue_offset) > 0.1:
                    current_preset = self.glue_preset_combo.currentText()
                    # Extraer threshold actual y ajustarlo
                    import re
                    match = re.search(r'\((-?\d+)', current_preset)
                    if match:
                        current_thresh = float(match.group(1))
                        new_thresh = current_thresh + glue_offset
                        summary_lines.append(
                            f"🎚️ Glue threshold ajustado: {current_thresh:.1f} → {new_thresh:.1f} dB"
                        )
                
                # Verificar si EQ dinámico debe activarse/desactivarse
                has_band_eq = bool(self._get_auto_master_band_eq_adjustments(adjustments))
                if not has_band_eq and not adjustments.get("dynamic_eq_enabled", True):
                    if self.dynamic_eq_cb.isChecked():
                        self.dynamic_eq_cb.setChecked(False)
                
                # === APLICAR CONTROLES DE SATURACIÓN POST-PROCESO ===
                if adjustments.get("saturation_limiter_enabled"):
                    self.saturation_limiter_cb.setChecked(True)
                    target_thd = adjustments.get("saturation_target_thd", 3.0)
                    self.saturation_target_thd_spin.setValue(target_thd)
                    mode = adjustments.get("saturation_reduction_mode", "musical")
                    self.saturation_reduction_mode_combo.setCurrentText(mode)
                    summary_lines.append(
                        f"🛡️ Control de saturación: THD {target_thd:.1f}% ({mode})"
                    )
                else:
                    self.saturation_limiter_cb.setChecked(False)
                
                if adjustments.get("adaptive_saturation_control"):
                    self.adaptive_saturation_control_cb.setChecked(True)
                    compensation = adjustments.get("saturation_compensation_db", 0.0)
                    if compensation != 0.0:
                        summary_lines.append(
                            f"🔉 Compensación de volumen: {compensation:+.1f} dB"
                        )
                else:
                    self.adaptive_saturation_control_cb.setChecked(False)
                    summary_lines.append("○ Control adaptativo de saturación desactivado por análisis")

                source_lufs = None
                source_lra = None
                try:
                    source_lufs = float(getattr(characteristics, "lufs", float("nan")))
                    source_lra = float(getattr(characteristics, "lra", float("nan")))
                except Exception:
                    pass
                target_lufs = float(self.target_spin.value())
                near_target = (
                    source_lufs is not None
                    and math.isfinite(source_lufs)
                    and abs(source_lufs - target_lufs) <= 1.5
                )
                low_dynamic = (
                    source_lra is not None
                    and math.isfinite(source_lra)
                    and source_lra <= 4.5
                )
                if "SUNO Clean" in style:
                    # SUNO Clean: limitar empuje de volumen para minimizar saltos percibidos.
                    self.input_gain_spin.setValue(-14.0 if near_target else -16.0)
                    adjustments["autogain_maxgain"] = 2.0 if (near_target and low_dynamic) else 2.5
                    summary_lines.append(
                        "🛑 SUNO Clean seguro: empuje de loudness limitado para evitar cambios bruscos."
                    )
                elif "Universal" in style:
                    self.input_gain_spin.setValue(-12.0 if near_target else -14.0)
                    if near_target and low_dynamic:
                        adjustments["autogain_maxgain"] = 3.0
                        summary_lines.append(
                            "🛑 AutoGain limitado: material cercano al target y muy comprimido."
                        )
                    else:
                        adjustments["autogain_maxgain"] = 4.0
                        summary_lines.append(
                            "🎚️ AutoGain conservador: límite de empuje reducido."
                        )
                else:
                    adjustments.setdefault("autogain_maxgain", 6.0)
                if adjustments.get("minimal_processing"):
                    current_maxgain = float(adjustments.get("autogain_maxgain", 6.0) or 6.0)
                    adjustments["autogain_maxgain"] = min(current_maxgain, 2.5)
                    summary_lines.append(
                        "🛑 Procesamiento mínimo: AutoGain recortado para no re-comprimir la salida."
                    )
                
                # ---- APLICAR AJUSTES INTELIGENTES ADICIONALES ----
                
                # 1. Repair settings (declip, noise_reduction)
                repair = adjustments.get("repair_settings", {})
                if repair.get("declip"):
                    self.declip_combo.setCurrentText(repair["declip"])
                    summary_lines.append(f"🔧 Declip: {repair['declip']}")
                if repair.get("noise_reduction"):
                    self.noise_reduction_combo.setCurrentText(repair["noise_reduction"])
                    summary_lines.append(f"🔇 Reducción de ruido: {repair['noise_reduction']}")
                
                # 2. Multiband limiter
                if adjustments.get("multiband_limiter_enabled"):
                    self.multiband_limiter_cb.setChecked(True)
                    mb_thresholds = adjustments.get("multiband_limiter_thresholds", {})
                    for band_label, threshold_val in mb_thresholds.items():
                        if band_label in self.multiband_limiter_spins:
                            self.multiband_limiter_spins[band_label].setValue(threshold_val)
                    summary_lines.append(f"🎚️ Limitador multibanda activado con umbrales auto-ajustados")
                
                # 3. Stereo dynamic (ahora dentro de Multiband)
                if adjustments.get("stereo_dynamic_enabled") is not None:
                    enabled = adjustments["stereo_dynamic_enabled"]
                    self.dynamic_eq_cb.setChecked(enabled or self.dynamic_eq_cb.isChecked())  # Activar procesamiento por bandas si stereo_dynamic está activo
                    
                    # Configurar parámetros de stereo dynamic
                    if adjustments.get("stereo_dynamic_threshold_db") is not None:
                        self.stereo_dynamic_threshold_spin.setValue(adjustments["stereo_dynamic_threshold_db"])
                    if adjustments.get("stereo_dynamic_ratio") is not None:
                        self.stereo_dynamic_ratio_spin.setValue(adjustments["stereo_dynamic_ratio"])
                    if adjustments.get("stereo_dynamic_attack_ms") is not None:
                        self.stereo_dynamic_attack_spin.setValue(adjustments["stereo_dynamic_attack_ms"])
                    if adjustments.get("stereo_dynamic_release_ms") is not None:
                        self.stereo_dynamic_release_spin.setValue(adjustments["stereo_dynamic_release_ms"])
                    if adjustments.get("stereo_dynamic_mix") is not None:
                        self.stereo_dynamic_mix_spin.setValue(adjustments["stereo_dynamic_mix"])
                    
                    # Band mix específico
                    band_mix = adjustments.get("stereo_dynamic_band_mix", {})
                    for band_label, mix_val in band_mix.items():
                        if band_label in self.stereo_dynamic_band_mix_spins:
                            self.stereo_dynamic_band_mix_spins[band_label].setValue(mix_val)
                    
                    status = "activado" if enabled else "desactivado"
                    params = f"(Th:{adjustments.get('stereo_dynamic_threshold_db', -24):.0f}dB, Ratio:{adjustments.get('stereo_dynamic_ratio', 1.6):.1f})" if enabled else ""
                    summary_lines.append(f"🔊 Stereo dynamic {status} {params}".strip())
                
                # 4. Fades sugeridos
                if adjustments.get("suggested_fade_in", 0) > 0:
                    suggested_fade_in = float(adjustments["suggested_fade_in"])
                    target_fade_in = min(MAX_AUTO_FADE_IN_S, max(DEFAULT_SUBTLE_FADE_IN_S, suggested_fade_in))
                    self.fade_in_spin.setValue(target_fade_in)
                    summary_lines.append(
                        f"⏮️ Fade-in auto limitado a {target_fade_in:.2f}s (sutil)"
                    )
                if adjustments.get("suggested_fade_out", 0) > 0:
                    suggested_fade_out = float(adjustments["suggested_fade_out"])
                    target_fade_out = min(MAX_AUTO_FADE_OUT_S, max(DEFAULT_SUBTLE_FADE_OUT_S, suggested_fade_out))
                    self.fade_out_spin.setValue(target_fade_out)
                    summary_lines.append(
                        f"⏭️ Fade-out auto limitado a {target_fade_out:.2f}s (sutil)"
                    )

                # Aplicar orden de procesos dinámico del auto-master
                if adjustments and "process_order" in adjustments:
                    try:
                        worker = getattr(self, "_current_worker", None)
                        if worker:
                            worker._auto_process_order = adjustments["process_order"]
                    except Exception:
                        pass
                
                self._apply_processing_profile_overrides(adjustments, summary_lines)
                self._enforce_conservative_preset_limits(summary_lines)
                self._enforce_minimal_saturation_caps(summary_lines)
                self.auto_master_notes.setPlainText("\n".join(summary_lines))
                if emit_log:
                    self._append_auto_master_summary_to_log()
                if write_preset:
                    self._write_auto_master_preset(style)

                # Actualizar visualización de la cadena de procesos
            self._update_process_chain_display()
            self._applying_auto_master = False


        def _apply_batch_auto_master(
            self,
            on_finished: Callable[[], None] | None = None,
        ) -> None:
            """
            Analiza los archivos del lote y aplica auto-configuración basada en análisis combinado.
            """
            input_dir_text = self.batch_input_edit.text().strip()
            if not self._batch_files:
                if not input_dir_text:
                    self._show_error("Selecciona una carpeta de entrada para el lote o arrastra archivos a la lista.")
                    return
                input_dir = pathlib.Path(input_dir_text)
                if not input_dir.exists():
                    self._show_error(f"La carpeta no existe: {input_dir}")
                    return
                self.refresh_batch_table()
            elif input_dir_text:
                input_dir = pathlib.Path(input_dir_text)
                if not input_dir.exists():
                    self._show_error(f"La carpeta no existe: {input_dir}")
                    return

            selected_files: list[pathlib.Path] = []
            for row in range(self.batch_table.rowCount()):
                cb_widget = self.batch_table.cellWidget(row, 0)
                if cb_widget is not None and isinstance(cb_widget, QCheckBox) and cb_widget.isChecked():
                    if row < len(self._batch_files):
                        selected_files.append(self._batch_files[row])

            if not selected_files:
                self._show_error("No hay archivos seleccionados para analizar.")
                return

            raw_style = self.auto_master_style_combo.currentText()
            style = self._resolve_standard_auto_master_style(raw_style)
            if style != raw_style:
                self.auto_master_style_combo.setCurrentText(style)
                self.auto_master_style_combo_tab.setCurrentText(style)

            minimal_lra, minimal_crest = self._get_minimal_processing_thresholds()
            motion_profile, motion_amount = self._get_motion_preferences()
            ia_providers, ia_status = self._build_auto_master_ia_providers()
            if ia_status not in ("off",):
                self.append_log(f"Master asistido por IA: {ia_status}")
            worker = BatchAutoMasterWorker(
                files=selected_files,
                style=style,
                target_lufs=self.target_spin.value(),
                true_peak=self.true_peak_spin.value(),
                verbose=self.verbose_cb.isChecked(),
                use_spectrum=False,
                max_files_to_analyze=5,
                minimal_lra_threshold=minimal_lra,
                minimal_crest_threshold=minimal_crest,
                motion_profile_preference=motion_profile,
                motion_amount=motion_amount,
                block_mode=self.auto_master_block_mode_cb.isChecked(),
                ia_providers=ia_providers,
            )
            self._set_busy(True, "Analizando lote...")
            self._set_progress(indeterminate=True, message="Analizando lote...")
            self._start_worker(
                worker,
                on_finished=lambda result: self._handle_batch_auto_master_finished(
                    style,
                    selected_files,
                    result,
                    on_finished=on_finished,
                ),
            )
            return

            # Obtener archivos seleccionados del lote
            input_dir_text = self.batch_input_edit.text().strip()
            if not input_dir_text:
                self._show_error("Selecciona una carpeta de entrada para el lote.")
                return
            
            input_dir = pathlib.Path(input_dir_text)
            if not input_dir.exists():
                self._show_error(f"La carpeta no existe: {input_dir}")
                return
            
            # Obtener archivos seleccionados
            selected_files: list[pathlib.Path] = []
            for row in range(self.batch_table.rowCount()):
                cb_widget = self.batch_table.cellWidget(row, 0)
                if cb_widget is not None and isinstance(cb_widget, QCheckBox) and cb_widget.isChecked():
                    if row < len(self._batch_files):
                        selected_files.append(self._batch_files[row])
            
            if not selected_files:
                self._show_error("No hay archivos seleccionados para analizar.")
                return
            
            # Mostrar progreso
            self._set_busy(True, "Analizando lote...")
            summary_lines = []
            
            try:
                raw_style = self.auto_master_style_combo.currentText()
                style = self._resolve_standard_auto_master_style(raw_style)
                if style != raw_style:
                    self.auto_master_style_combo.setCurrentText(style)
                    self.auto_master_style_combo_tab.setCurrentText(style)
                summary_lines.append(f"🎨 Estilo base: {style}")
                
                # Analizar lote
                def update_batch_progress(idx: int, total: int, name: str) -> None:
                    self._set_progress(current=idx, total=total, message=f"Analizando: {name}")
                    QApplication.processEvents()

                merged_chars, recommendations, individual_results = analyze_batch_for_automaster(
                    files=selected_files,
                    verbose=False,
                    use_spectrum=False,  # Desactivado para velocidad
                    max_files_to_analyze=len(selected_files),
                    progress_callback=update_batch_progress,
                )
                
                summary_lines.extend(recommendations)
                
                # Adaptar preset según características combinadas
                minimal_lra, minimal_crest = self._get_minimal_processing_thresholds()
                motion_profile, motion_amount = self._get_motion_preferences()
                ia_providers, _ia_status = self._build_auto_master_ia_providers()
                adjustments = adapt_preset_to_audio(
                    style,
                    merged_chars,
                    minimal_lra_threshold=minimal_lra,
                    minimal_crest_threshold=minimal_crest,
                    motion_profile_preference=motion_profile,
                    motion_amount=motion_amount,
                    ia_providers=ia_providers,
                    target_lufs=self.target_spin.value(),
                    true_peak=self.true_peak_spin.value(),
                )
                
                # Actualizar presupuestos de saturación individuales
                individual_results = update_saturation_budgets_for_batch(
                    individual_results, adjustments
                )
                self._update_auto_master_profile_label(adjustments)
                
                # Reportar presupuestos de saturación si están habilitados
                if adjustments.get("saturation_limiter_enabled"):
                    summary_lines.append("\n📊 === PRESUPUESTOS DE SATURACIÓN ===")
                    for file_path, result in individual_results.items():
                        budget = result.get("saturation_budget", {})
                        if budget:
                            filename = pathlib.Path(file_path).name
                            thd = budget.get("estimated_thd", 0.0)
                            risk = budget.get("risk_level", "unknown")
                            summary_lines.append(
                                f"  {filename}: THD {thd:.1f}% ({risk})"
                            )
                
                # === 1) Aplicar preset base primero (sin análisis de un solo archivo) ===
                # En lote no usamos self.input_edit, así que desactivamos el "Análisis Inteligente"
                # temporalmente para evitar que _apply_auto_master intente analizar un archivo inexistente.
                prev_intelligent = False
                if hasattr(self, "auto_master_intelligent_cb") and self.auto_master_intelligent_cb is not None:
                    prev_intelligent = self.auto_master_intelligent_cb.isChecked()
                    if prev_intelligent:
                        self.auto_master_intelligent_cb.blockSignals(True)
                        self.auto_master_intelligent_cb.setChecked(False)
                        self.auto_master_intelligent_cb.blockSignals(False)
                try:
                    self._apply_auto_master(emit_log=False, write_preset=False)
                finally:
                    if hasattr(self, "auto_master_intelligent_cb") and self.auto_master_intelligent_cb is not None:
                        self.auto_master_intelligent_cb.blockSignals(True)
                        self.auto_master_intelligent_cb.setChecked(prev_intelligent)
                        self.auto_master_intelligent_cb.blockSignals(False)

                # === 2) Aplicar overrides derivados del análisis del lote ===
                # 2.1 Repair settings
                repair = adjustments.get("repair_settings", {})
                if repair.get("declip"):
                    self.declip_combo.setCurrentText(repair["declip"])
                    summary_lines.append(f"🔧 Declip: {repair['declip']}")
                if repair.get("noise_reduction"):
                    self.noise_reduction_combo.setCurrentText(repair["noise_reduction"])
                    summary_lines.append(f"🔇 Reducción de ruido: {repair['noise_reduction']}")
                if repair.get("declick"):
                    self.declick_combo.setCurrentText(repair["declick"])
                    summary_lines.append(f"🖱️ De-click: {repair['declick']}")
                if repair.get("dc_offset_correction"):
                    self.dc_offset_cb.setChecked(True)
                    summary_lines.append("🔧 DC Offset: ON")

                # 2.2 Toggle de procesos (conservador en lote)
                if adjustments.get("dynamic_eq_enabled") is not None:
                    self.dynamic_eq_cb.setChecked(bool(adjustments["dynamic_eq_enabled"]))
                if adjustments.get("stereo_width_enabled") is not None:
                    self.stereo_width_cb.setChecked(bool(adjustments["stereo_width_enabled"]))
                self._apply_auto_master_band_eq_adjustments(adjustments, summary_lines)

                # 2.3 Multiband limiter
                mb_enabled = bool(adjustments.get("multiband_limiter_enabled", False))
                self.multiband_limiter_cb.setChecked(mb_enabled)
                if mb_enabled:
                    mb_thresholds = adjustments.get("multiband_limiter_thresholds", {})
                    for band_label, threshold_val in mb_thresholds.items():
                        if band_label in self.multiband_limiter_spins:
                            self.multiband_limiter_spins[band_label].setValue(threshold_val)
                    summary_lines.append("🎚️ Limitador multibanda activado")

                # 2.4 Stereo dynamic
                if adjustments.get("stereo_dynamic_enabled") is not None:
                    self.stereo_dynamic_cb.setChecked(bool(adjustments["stereo_dynamic_enabled"]))
                    if adjustments.get("stereo_dynamic_mix") is not None:
                        self.stereo_dynamic_mix_spin.setValue(adjustments["stereo_dynamic_mix"])
                    if adjustments.get("stereo_dynamic_threshold_db") is not None:
                        self.stereo_dynamic_threshold_spin.setValue(adjustments["stereo_dynamic_threshold_db"])
                    if adjustments.get("stereo_dynamic_ratio") is not None:
                        self.stereo_dynamic_ratio_spin.setValue(adjustments["stereo_dynamic_ratio"])
                    if adjustments.get("stereo_dynamic_attack_ms") is not None:
                        self.stereo_dynamic_attack_spin.setValue(adjustments["stereo_dynamic_attack_ms"])
                    if adjustments.get("stereo_dynamic_release_ms") is not None:
                        self.stereo_dynamic_release_spin.setValue(adjustments["stereo_dynamic_release_ms"])
                    band_mix = adjustments.get("stereo_dynamic_band_mix", {})
                    for band_label, mix_val in band_mix.items():
                        if band_label in self.stereo_dynamic_band_mix_spins:
                            self.stereo_dynamic_band_mix_spins[band_label].setValue(mix_val)

                # 2.5 Glue: aplicar offsets/multiplicadores si existen
                glue_thr_offset = float(adjustments.get("glue_threshold_offset", 0.0) or 0.0)
                if abs(glue_thr_offset) > 0.001:
                    thr = self.glue_threshold_spin.value() + glue_thr_offset
                    thr = max(-60.0, min(0.0, thr))
                    self.glue_threshold_spin.setValue(thr)
                glue_ratio_mult = float(adjustments.get("glue_ratio_mult", 1.0) or 1.0)
                if abs(glue_ratio_mult - 1.0) > 0.001:
                    ratio = self.glue_ratio_spin.value() * glue_ratio_mult
                    ratio = max(1.0, min(10.0, ratio))
                    self.glue_ratio_spin.setValue(ratio)

                # 2.6 De-esser intensity multiplier
                deess_mult = float(adjustments.get("deesser_intensity_mult", 1.0) or 1.0)
                if abs(deess_mult - 1.0) > 0.001:
                    val = self.deesser_intensity_spin.value() * deess_mult
                    val = max(0.2, min(1.0, val))
                    self.deesser_intensity_spin.setValue(val)

                # 2.7 Saturación: en lote somos conservadores (nunca aumentamos)
                sat_drive_mult = float(adjustments.get("saturation_drive_mult", 1.0) or 1.0)
                sat_mix_mult = float(adjustments.get("saturation_mix_mult", 1.0) or 1.0)
                sat_drive_mult = min(1.0, sat_drive_mult)
                sat_mix_mult = min(1.0, sat_mix_mult)
                if self.saturation_enable_cb.isChecked():
                    # Nunca aumentar saturación (si el valor es negativo, mantenerlo).
                    base_drive = self.saturation_drive_spin.value()
                    drive = min(base_drive, base_drive * sat_drive_mult)
                    drive = max(-24.0, min(24.0, drive))
                    self.saturation_drive_spin.setValue(drive)
                    mix = self.saturation_mix_spin.value() * sat_mix_mult
                    mix = max(0.0, min(100.0, mix))
                    self.saturation_mix_spin.setValue(mix)

                band_sat_adj = adjustments.get("band_saturation_adjustments", {}) or {}
                if self.saturation_per_band_cb.isChecked():
                    # Aplicar reducción global (LUFS/balance) a TODAS las bandas.
                    for drive_spin in self.saturation_band_drive_spins.values():
                        base_drive = drive_spin.value()
                        val = min(base_drive, base_drive * sat_drive_mult)
                        val = max(-24.0, min(24.0, val))
                        drive_spin.setValue(val)
                    for mix_spin in self.saturation_band_mix_spins.values():
                        val = mix_spin.value() * sat_mix_mult
                        val = max(0.0, min(100.0, val))
                        mix_spin.setValue(val)

                    # Aplicar ajustes específicos por banda (p.ej. proteger agudos).
                    if band_sat_adj:
                        for band_label, adj in band_sat_adj.items():
                            if not isinstance(adj, dict):
                                continue
                            drive_mult = float(adj.get("drive_mult", 1.0) or 1.0)
                            mix_mult = float(adj.get("mix_mult", 1.0) or 1.0)
                            drive_mult = min(1.0, drive_mult)
                            mix_mult = min(1.0, mix_mult)
                            drive_spin = self.saturation_band_drive_spins.get(band_label)
                            mix_spin = self.saturation_band_mix_spins.get(band_label)
                            if drive_spin is not None:
                                base_drive = drive_spin.value()
                                val = min(base_drive, base_drive * drive_mult)
                                val = max(-24.0, min(24.0, val))
                                drive_spin.setValue(val)
                            if mix_spin is not None:
                                val = mix_spin.value() * mix_mult
                                val = max(0.0, min(100.0, val))
                                mix_spin.setValue(val)

                # 2.8 Fades sugeridos
                if adjustments.get("suggested_fade_in", 0) > 0:
                    suggested_fade_in = float(adjustments["suggested_fade_in"])
                    self.fade_in_spin.setValue(min(MAX_AUTO_FADE_IN_S, max(DEFAULT_SUBTLE_FADE_IN_S, suggested_fade_in)))
                if adjustments.get("suggested_fade_out", 0) > 0:
                    suggested_fade_out = float(adjustments["suggested_fade_out"])
                    self.fade_out_spin.setValue(min(MAX_AUTO_FADE_OUT_S, max(DEFAULT_SUBTLE_FADE_OUT_S, suggested_fade_out)))

                # 2.9 Controles de saturación post-proceso (no afectan al motor actual,
                # pero los usamos para ajustar parámetros de forma segura)
                if adjustments.get("notes"):
                    summary_lines.append("\n=== AJUSTES APLICADOS ===")
                    summary_lines.extend(adjustments["notes"])
                
                if adjustments.get("saturation_limiter_enabled"):
                    self.saturation_limiter_cb.setChecked(True)
                    target_thd = adjustments.get("saturation_target_thd", 3.0)
                    self.saturation_target_thd_spin.setValue(target_thd)
                    mode = adjustments.get("saturation_reduction_mode", "musical")
                    self.saturation_reduction_mode_combo.setCurrentText(mode)
                    summary_lines.append(f"🛡️ Control de saturación lote: THD {target_thd:.1f}% ({mode})")
                    # Cerrar un poco el "color" si el análisis detecta riesgo.
                    if self.saturation_enable_cb.isChecked():
                        self.saturation_mix_spin.setValue(min(self.saturation_mix_spin.value(), 15.0))
                    if self.saturation_per_band_cb.isChecked() and self.saturation_band_mix_spins:
                        for mix_spin in self.saturation_band_mix_spins.values():
                            mix_spin.setValue(min(mix_spin.value(), 10.0))
                
                if adjustments.get("adaptive_saturation_control"):
                    self.adaptive_saturation_control_cb.setChecked(True)
                    compensation = adjustments.get("saturation_compensation_db", 0.0)
                    if compensation != 0.0:
                        summary_lines.append(f"🔉 Compensación volumen lote: {compensation:+.1f} dB")
                        # Aplicar compensación reduciendo el "headroom" (más negativo = menos drive hacia procesos).
                        new_headroom = self.input_gain_spin.value() + float(compensation)
                        new_headroom = max(-24.0, min(24.0, new_headroom))
                        self.input_gain_spin.setValue(new_headroom)
                else:
                    self.adaptive_saturation_control_cb.setChecked(False)

                self._apply_processing_profile_overrides(adjustments, summary_lines)

                self._enforce_conservative_preset_limits(summary_lines)
                self._enforce_minimal_saturation_caps(summary_lines)
                
                # Asegurar que la vista de orden de procesos refleje los overrides.
                self._update_process_chain_display()
                
                summary_lines.append("\n✅ Auto-configuración de lote completada")
                summary_lines.append(f"   Archivos analizados: {len(individual_results)}/{len(selected_files)}")
                
            except Exception as e:
                summary_lines.append(f"\n❌ Error durante análisis: {str(e)}")
            finally:
                self._set_busy(False)
                self._set_progress(current=0, total=0, message="")
            
            # Mostrar resumen
            self.auto_master_notes.setPlainText("\n".join(summary_lines))
            self.append_log(f"\n{'='*50}\nAuto-Master Lote\n{'='*50}\n" + "\n".join(summary_lines))


        def _handle_batch_auto_master_finished(
            self,
            style: str,
            selected_files: list[pathlib.Path],
            result: object,
            on_finished: Callable[[], None] | None = None,
        ) -> None:
            if not isinstance(result, dict):
                raise TypeError("Resultado inválido del Auto-Master de lote.")

            merged_chars = result.get("merged_chars")
            recommendations = list(result.get("recommendations") or [])
            individual_results = result.get("individual_results") or {}
            adjustments = result.get("adjustments") or {}

            summary_lines: list[str] = [f"🎨 Estilo base: {style}"]
            summary_lines.extend(str(item) for item in recommendations)

            self._last_auto_master_characteristics = merged_chars
            self._last_auto_master_adjustments = adjustments
            self._update_auto_master_profile_label(adjustments)

            if adjustments.get("saturation_limiter_enabled"):
                summary_lines.append("\n📊 === PRESUPUESTOS DE SATURACIÓN ===")
                if isinstance(individual_results, dict):
                    for file_path, item in individual_results.items():
                        budget = item.get("saturation_budget", {}) if isinstance(item, dict) else {}
                        if budget:
                            filename = pathlib.Path(str(file_path)).name
                            thd = budget.get("estimated_thd", 0.0)
                            risk = budget.get("risk_level", "unknown")
                            summary_lines.append(f"  {filename}: THD {thd:.1f}% ({risk})")

            prev_intelligent = False
            if hasattr(self, "auto_master_intelligent_cb") and self.auto_master_intelligent_cb is not None:
                prev_intelligent = self.auto_master_intelligent_cb.isChecked()
                if prev_intelligent:
                    self.auto_master_intelligent_cb.blockSignals(True)
                    self.auto_master_intelligent_cb.setChecked(False)
                    self.auto_master_intelligent_cb.blockSignals(False)
            try:
                self._apply_auto_master(emit_log=False, write_preset=False)
            finally:
                if hasattr(self, "auto_master_intelligent_cb") and self.auto_master_intelligent_cb is not None:
                    self.auto_master_intelligent_cb.blockSignals(True)
                    self.auto_master_intelligent_cb.setChecked(prev_intelligent)
                    self.auto_master_intelligent_cb.blockSignals(False)

            repair = adjustments.get("repair_settings", {})
            if repair.get("declip"):
                self.declip_combo.setCurrentText(repair["declip"])
                summary_lines.append(f"🔧 Declip: {repair['declip']}")
            if repair.get("noise_reduction"):
                self.noise_reduction_combo.setCurrentText(repair["noise_reduction"])
                summary_lines.append(f"🔇 Reducción de ruido: {repair['noise_reduction']}")
            if repair.get("declick"):
                self.declick_combo.setCurrentText(repair["declick"])
                summary_lines.append(f"🖱️ De-click: {repair['declick']}")
            if repair.get("dc_offset_correction"):
                self.dc_offset_cb.setChecked(True)
                summary_lines.append("🔧 DC Offset: ON")

            if adjustments.get("dynamic_eq_enabled") is not None:
                self.dynamic_eq_cb.setChecked(bool(adjustments["dynamic_eq_enabled"]))
            if adjustments.get("stereo_width_enabled") is not None:
                self.stereo_width_cb.setChecked(bool(adjustments["stereo_width_enabled"]))
            self._apply_auto_master_band_eq_adjustments(adjustments, summary_lines)

            mb_enabled = bool(adjustments.get("multiband_limiter_enabled", False))
            self.multiband_limiter_cb.setChecked(mb_enabled)
            if mb_enabled:
                mb_thresholds = adjustments.get("multiband_limiter_thresholds", {})
                for band_label, threshold_val in mb_thresholds.items():
                    if band_label in self.multiband_limiter_spins:
                        self.multiband_limiter_spins[band_label].setValue(threshold_val)
                summary_lines.append("🎚️ Limitador multibanda activado")

            if adjustments.get("stereo_dynamic_enabled") is not None:
                self.stereo_dynamic_cb.setChecked(bool(adjustments["stereo_dynamic_enabled"]))
                if adjustments.get("stereo_dynamic_mix") is not None:
                    self.stereo_dynamic_mix_spin.setValue(adjustments["stereo_dynamic_mix"])
                if adjustments.get("stereo_dynamic_threshold_db") is not None:
                    self.stereo_dynamic_threshold_spin.setValue(adjustments["stereo_dynamic_threshold_db"])
                if adjustments.get("stereo_dynamic_ratio") is not None:
                    self.stereo_dynamic_ratio_spin.setValue(adjustments["stereo_dynamic_ratio"])
                if adjustments.get("stereo_dynamic_attack_ms") is not None:
                    self.stereo_dynamic_attack_spin.setValue(adjustments["stereo_dynamic_attack_ms"])
                if adjustments.get("stereo_dynamic_release_ms") is not None:
                    self.stereo_dynamic_release_spin.setValue(adjustments["stereo_dynamic_release_ms"])
                band_mix = adjustments.get("stereo_dynamic_band_mix", {})
                for band_label, mix_val in band_mix.items():
                    if band_label in self.stereo_dynamic_band_mix_spins:
                        self.stereo_dynamic_band_mix_spins[band_label].setValue(mix_val)

            glue_thr_offset = float(adjustments.get("glue_threshold_offset", 0.0) or 0.0)
            if abs(glue_thr_offset) > 0.001:
                thr = self.glue_threshold_spin.value() + glue_thr_offset
                thr = max(-60.0, min(0.0, thr))
                self.glue_threshold_spin.setValue(thr)
            glue_ratio_mult = float(adjustments.get("glue_ratio_mult", 1.0) or 1.0)
            if abs(glue_ratio_mult - 1.0) > 0.001:
                ratio = self.glue_ratio_spin.value() * glue_ratio_mult
                ratio = max(1.0, min(10.0, ratio))
                self.glue_ratio_spin.setValue(ratio)

            deess_mult = float(adjustments.get("deesser_intensity_mult", 1.0) or 1.0)
            if abs(deess_mult - 1.0) > 0.001:
                val = self.deesser_intensity_spin.value() * deess_mult
                val = max(0.2, min(1.0, val))
                self.deesser_intensity_spin.setValue(val)

            sat_drive_mult = min(1.0, float(adjustments.get("saturation_drive_mult", 1.0) or 1.0))
            sat_mix_mult = min(1.0, float(adjustments.get("saturation_mix_mult", 1.0) or 1.0))
            if self.saturation_enable_cb.isChecked():
                base_drive = self.saturation_drive_spin.value()
                drive = min(base_drive, base_drive * sat_drive_mult)
                drive = max(-24.0, min(24.0, drive))
                self.saturation_drive_spin.setValue(drive)
                mix = self.saturation_mix_spin.value() * sat_mix_mult
                mix = max(0.0, min(100.0, mix))
                self.saturation_mix_spin.setValue(mix)

            band_sat_adj = adjustments.get("band_saturation_adjustments", {}) or {}
            if self.saturation_per_band_cb.isChecked():
                for drive_spin in self.saturation_band_drive_spins.values():
                    base_drive = drive_spin.value()
                    val = min(base_drive, base_drive * sat_drive_mult)
                    val = max(-24.0, min(24.0, val))
                    drive_spin.setValue(val)
                for mix_spin in self.saturation_band_mix_spins.values():
                    val = mix_spin.value() * sat_mix_mult
                    val = max(0.0, min(100.0, val))
                    mix_spin.setValue(val)
                if band_sat_adj:
                    for band_label, adj in band_sat_adj.items():
                        if not isinstance(adj, dict):
                            continue
                        drive_mult = min(1.0, float(adj.get("drive_mult", 1.0) or 1.0))
                        mix_mult = min(1.0, float(adj.get("mix_mult", 1.0) or 1.0))
                        drive_spin = self.saturation_band_drive_spins.get(band_label)
                        mix_spin = self.saturation_band_mix_spins.get(band_label)
                        if drive_spin is not None:
                            base_drive = drive_spin.value()
                            val = min(base_drive, base_drive * drive_mult)
                            val = max(-24.0, min(24.0, val))
                            drive_spin.setValue(val)
                        if mix_spin is not None:
                            val = mix_spin.value() * mix_mult
                            val = max(0.0, min(100.0, val))
                            mix_spin.setValue(val)

            if adjustments.get("suggested_fade_in", 0) > 0:
                suggested_fade_in = float(adjustments["suggested_fade_in"])
                self.fade_in_spin.setValue(min(MAX_AUTO_FADE_IN_S, max(DEFAULT_SUBTLE_FADE_IN_S, suggested_fade_in)))
            if adjustments.get("suggested_fade_out", 0) > 0:
                suggested_fade_out = float(adjustments["suggested_fade_out"])
                self.fade_out_spin.setValue(min(MAX_AUTO_FADE_OUT_S, max(DEFAULT_SUBTLE_FADE_OUT_S, suggested_fade_out)))

            if adjustments.get("notes"):
                summary_lines.append("\n=== AJUSTES APLICADOS ===")
                summary_lines.extend(adjustments["notes"])

            if adjustments.get("saturation_limiter_enabled"):
                self.saturation_limiter_cb.setChecked(True)
                target_thd = adjustments.get("saturation_target_thd", 3.0)
                self.saturation_target_thd_spin.setValue(target_thd)
                mode = adjustments.get("saturation_reduction_mode", "musical")
                self.saturation_reduction_mode_combo.setCurrentText(mode)
                summary_lines.append(f"🛡️ Control de saturación lote: THD {target_thd:.1f}% ({mode})")
                if self.saturation_enable_cb.isChecked():
                    self.saturation_mix_spin.setValue(min(self.saturation_mix_spin.value(), 15.0))
                if self.saturation_per_band_cb.isChecked() and self.saturation_band_mix_spins:
                    for mix_spin in self.saturation_band_mix_spins.values():
                        mix_spin.setValue(min(mix_spin.value(), 10.0))

            if adjustments.get("adaptive_saturation_control"):
                self.adaptive_saturation_control_cb.setChecked(True)
                compensation = adjustments.get("saturation_compensation_db", 0.0)
                if compensation != 0.0:
                    summary_lines.append(f"🔉 Compensación volumen lote: {compensation:+.1f} dB")
                    new_headroom = self.input_gain_spin.value() + float(compensation)
                    new_headroom = max(-24.0, min(24.0, new_headroom))
                    self.input_gain_spin.setValue(new_headroom)
            else:
                self.adaptive_saturation_control_cb.setChecked(False)

            self._apply_processing_profile_overrides(adjustments, summary_lines)
            self._enforce_conservative_preset_limits(summary_lines)
            self._enforce_minimal_saturation_caps(summary_lines)
            self._update_process_chain_display()

            summary_lines.append("\n✅ Auto-configuración de lote completada")
            summary_lines.append(f"   Archivos analizados: {len(individual_results)}/{len(selected_files)}")
            resource_summary = self._format_batch_resource_summary()
            if resource_summary:
                summary_lines.append("\n📟 === RECURSOS ===")
                summary_lines.extend(resource_summary.splitlines())
            summary_text = "\n".join(summary_lines)
            self.auto_master_notes.setPlainText(summary_text)
            self.append_log(f"\n{'='*50}\nAuto-Master Lote\n{'='*50}\n" + summary_text)
            self._record_log_history(
                action="Auto-Master Lote resumen",
                input_path=pathlib.Path(self.batch_input_edit.text().strip())
                if self.batch_input_edit.text().strip()
                else None,
                output_path=self.batch_output_edit.text().strip() or None,
                pre_stats=None,
                post_stats=None,
                log_text_override=summary_text,
            )
            self._set_progress(current=0, total=0, message="")
            if on_finished is not None:
                on_finished()

        def _apply_output_format(self) -> None:
            fmt = self._get_output_format()
            if fmt in ("mp3", "m4a"):
                self.bit_depth_combo.setEnabled(False)
            else:
                if self.output_preset_combo.currentText() == "Manual":
                    self.bit_depth_combo.setEnabled(True)

        def _on_auto_repair_toggled(self, state: int | bool) -> None:
            enabled = bool(state)
            if enabled:
                self.noise_reduction_combo.setCurrentText("Auto")
                self.declip_combo.setCurrentText("Auto")
                self.declick_combo.setCurrentText("Auto")
            self.noise_reduction_combo.setEnabled(not enabled)
            self.declip_combo.setEnabled(not enabled)
            self.declick_combo.setEnabled(not enabled)

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

        # ================== FUNCIONES DE PREVIEW Y ESPECTRO ==================
        
        def _init_spectrum_canvas(self) -> None:
            """Inicializa el canvas de matplotlib para el espectro."""
            if not SPECTRUM_AVAILABLE or not hasattr(self, 'spectrum_canvas'):
                return
            
            if self.spectrum_canvas is None and Figure is not None and FigureCanvas is not None:
                self.spectrum_figure = Figure(figsize=(8, 4))
                self.spectrum_canvas = FigureCanvas(self.spectrum_figure)
                self.spectrum_canvas.setMinimumHeight(300)
                self.spectrum_canvas.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
                )
        
        def _update_spectrum_plot(self, spectrum_data: dict) -> None:
            """Actualiza el gráfico de espectro con los datos proporcionados."""
            if not SPECTRUM_AVAILABLE or self.spectrum_figure is None or self.spectrum_canvas is None:
                return
            
            try:
                self.spectrum_figure.clear()
                ax = self.spectrum_figure.add_subplot(111)
                
                freqs = spectrum_data.get('frequencies', [])
                magnitudes = spectrum_data.get('magnitudes', [])
                peaks = spectrum_data.get('peaks', [])
                
                if len(freqs) > 0 and len(magnitudes) > 0:
                    # Gráfico principal del espectro
                    ax.plot(freqs, magnitudes, color='#2196F3', linewidth=1.5, label='Espectro')
                    
                    # Marcar picos (peaks es lista de tuplas (freq, mag))
                    if len(peaks) > 0:
                        # peaks puede ser lista de tuplas (freq, mag) o lista de índices
                        if isinstance(peaks[0], (list, tuple)):
                            peak_freqs = [p[0] for p in peaks]
                            peak_mags = [p[1] for p in peaks]
                        else:
                            peak_freqs = [freqs[i] for i in peaks if i < len(freqs)]
                            peak_mags = [magnitudes[i] for i in peaks if i < len(magnitudes)]
                        ax.scatter(peak_freqs, peak_mags, color='#FF5722', s=50, zorder=5, label='Picos')
                    
                    # Configuración del gráfico
                    ax.set_xlabel('Frecuencia (Hz)', fontsize=10)
                    ax.set_ylabel('Magnitud (dB)', fontsize=10)
                    ax.set_title('Análisis de Espectro FFT', fontsize=12, fontweight='bold')
                    ax.grid(True, alpha=0.3, linestyle='--')
                    ax.legend(loc='upper right')
                    ax.set_xlim(20, 20000)
                    ax.set_xscale('log')
                    
                    self.spectrum_figure.tight_layout()
                    self.spectrum_canvas.draw()
                    self.current_spectrum_data = spectrum_data
                    
            except Exception as e:
                self.append_log(f"⚠️ Error al actualizar gráfico de espectro: {e}")
        
        def _generate_preview(self) -> None:
            """Genera y reproduce un preview de 30s del audio con filtros aplicados."""
            if not PREVIEW_AVAILABLE:
                self._show_error("Preview no disponible. Instala: pip install -r requirements.txt")
                return
            
            input_path = pathlib.Path(self.input_edit.text().strip())
            if not input_path.exists():
                self._show_error("Selecciona un archivo de audio válido primero.")
                return
            
            try:
                self._stop_preview()  # Detener cualquier reproducción previa
                
                # Feedback visual: deshabilitar botones y mostrar progreso
                self.preview_btn.setEnabled(False)
                self.play_original_btn.setEnabled(False)
                self.play_processed_btn.setEnabled(False)
                self.preview_btn.setText("⏳ Generando...")
                self.global_progress_label.setText("Generando preview...")
                self.global_progress_bar.setRange(0, 0)  # Modo indeterminado
                QApplication.processEvents()  # Actualizar UI inmediatamente
                
                self.append_log("🎧 Generando preview de 30 segundos...")
                
                # Crear preview sin filtros
                if AudioPreview is None:
                    self._show_error("AudioPreview no disponible")
                    self._reset_preview_buttons()
                    return
                    
                self.preview_player = AudioPreview()
                preview_path = self.preview_player.generate_preview(
                    input_path=input_path,
                    filter_complex="",
                    duration=30
                )
                
                # Restaurar botones
                self._reset_preview_buttons()
                
                if preview_path and preview_path.exists():
                    self.append_log(f"✓ Preview generado: {preview_path}")
                    self.global_progress_label.setText("▶️ Reproduciendo preview...")
                    
                    # Reproducir automáticamente
                    if self.preview_player.play():
                        self.append_log("▶️ Reproduciendo preview...")
                    else:
                        self.append_log("⚠️ No se pudo reproducir el preview automáticamente")
                        self.global_progress_label.setText("Listo")
                else:
                    self.append_log("⚠️ Error al generar preview")
                    self.global_progress_label.setText("Error en preview")
                    
            except Exception as e:
                self._reset_preview_buttons()
                self.append_log(f"❌ Error generando preview: {e}")
                self._show_error(f"Error al generar preview: {e}")
        
        def _reset_preview_buttons(self) -> None:
            """Restaura el estado de los botones de preview."""
            self.preview_btn.setEnabled(True)
            self.play_original_btn.setEnabled(True)
            self.play_processed_btn.setEnabled(True)
            self.preview_btn.setText("🎧 Preview (30s)")
            self.global_progress_bar.setRange(0, 1)
            self.global_progress_bar.setValue(0)
            self.global_progress_label.setText("Listo")
        
        def _play_original(self) -> None:
            """Reproduce el audio original sin procesamiento."""
            if not PREVIEW_AVAILABLE:
                self._show_error("Reproducción no disponible. Instala: pip install -r requirements.txt")
                return
            
            input_path = pathlib.Path(self.input_edit.text().strip())
            if not input_path.exists():
                self._show_error("Selecciona un archivo de audio válido primero.")
                return
            
            try:
                self._stop_preview()
                
                # Feedback visual
                self.play_original_btn.setEnabled(False)
                self.play_original_btn.setText("⏳ Cargando...")
                self.global_progress_label.setText("Generando preview original...")
                self.global_progress_bar.setRange(0, 0)
                QApplication.processEvents()
                
                self.append_log("▶️ Reproduciendo audio original...")
                
                if AudioPreview is None:
                    self._show_error("AudioPreview no disponible")
                    self._reset_preview_buttons()
                    return
                    
                self.preview_player = AudioPreview()
                preview_path = self.preview_player.generate_preview(
                    input_path=input_path,
                    filter_complex="",
                    duration=30
                )
                
                # Restaurar botones
                self._reset_preview_buttons()
                self.play_original_btn.setText("▶️ Original")
                
                if preview_path and self.preview_player.play():
                    self.append_log("✓ Reproduciendo original (30s)")
                    self.global_progress_label.setText("▶️ Original...")
                else:
                    self.append_log("⚠️ Error al reproducir original")
                    
            except Exception as e:
                self._reset_preview_buttons()
                self.play_original_btn.setText("▶️ Original")
                self.append_log(f"❌ Error reproduciendo original: {e}")
        
        def _play_processed(self) -> None:
            """Reproduce el audio procesado completo si existe."""
            if not PREVIEW_AVAILABLE:
                self._show_error("Reproducción no disponible. Instala: pip install -r requirements.txt")
                return
            
            output_path = pathlib.Path(self.output_edit.text().strip())
            if not output_path.exists():
                self._show_error("No hay archivo procesado. Ejecuta 'Procesar audio' primero.")
                return
            
            try:
                self._stop_preview()
                
                # Feedback visual
                self.play_processed_btn.setEnabled(False)
                self.play_processed_btn.setText("⏳ Cargando...")
                self.global_progress_label.setText("Generando preview procesado...")
                self.global_progress_bar.setRange(0, 0)
                QApplication.processEvents()
                
                self.append_log("▶️ Reproduciendo audio procesado...")
                
                if AudioPreview is None:
                    self._show_error("AudioPreview no disponible")
                    self._reset_preview_buttons()
                    return
                    
                self.preview_player = AudioPreview()
                preview_path = self.preview_player.generate_preview(
                    input_path=output_path,
                    filter_complex="",
                    duration=30
                )
                
                # Restaurar botones
                self._reset_preview_buttons()
                self.play_processed_btn.setText("▶️ Procesado")
                
                if preview_path and self.preview_player.play():
                    self.append_log("✓ Reproduciendo procesado (30s)")
                    self.global_progress_label.setText("▶️ Procesado...")
                else:
                    self.append_log("⚠️ Error al reproducir procesado")
                    
            except Exception as e:
                self._reset_preview_buttons()
                self.play_processed_btn.setText("▶️ Procesado")
                self.append_log(f"❌ Error reproduciendo procesado: {e}")
        
        def _stop_preview(self) -> None:
            """Detiene la reproducción actual y limpia recursos."""
            if self.preview_player is not None:
                try:
                    self.preview_player.stop()
                    self.preview_player.cleanup()
                    self.preview_player = None
                    self.append_log("⏹️ Reproducción detenida")
                except Exception as e:
                    self.append_log(f"⚠️ Error deteniendo reproducción: {e}")


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
    if LOGO_PATH:
        app.setApplicationName("ToneFinish")
        app.setDesktopFileName("tonefinish")
        app.setWindowIcon(QIcon(LOGO_PATH))
    _apply_global_ui_styles(app)
    window = MainWindow()
    repro = check_runtime_reproducibility()
    if repro.warnings:
        window.append_log("Aviso de reproducibilidad: se detectaron diferencias de entorno.")
        for item in repro.warnings:
            window.append_log(f"- {item}")
    window.show()
    return app.exec() if owns_app else 0
