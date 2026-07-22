from __future__ import annotations

from config import APP_NAME, APP_VENDOR, APP_VERSION, BAND_CONFIG, LOGO_PATH, VOICE_BAND
from ui.drag_order import DragItem, DragOrderWidget
from ui.qt_compat import (
    PYQTGRAPH_AVAILABLE,
    PYSIDE_AVAILABLE,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QDoubleSpinBox,
    QSvgWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    Qt,
    pg,
)


def build_start_tab(window) -> QWidget:
    tab_start = QWidget()
    window.tab_start = tab_start
    start_layout = QVBoxLayout()
    start_form = QFormLayout()
    start_form.addRow("Modo de trabajo:", window.mode_combo)
    start_layout.addLayout(start_form)
    if PYSIDE_AVAILABLE and LOGO_PATH:
        logo = QSvgWidget(LOGO_PATH)
        logo.setMaximumWidth(120)
        logo.setMaximumHeight(120)
        logo.setMinimumWidth(96)
        logo.setMinimumHeight(96)
        start_layout.addWidget(logo)
        start_layout.setAlignment(logo, Qt.AlignmentFlag.AlignCenter)

    title = QLabel(f"{APP_NAME} {APP_VERSION} — {APP_VENDOR}")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    start_layout.addWidget(title)

    intro = QLabel(
        f"Bienvenido a {APP_NAME}.\n\n"
        "El mastering siempre es decidido por IA.\n"
        "- Auto-Master (Audio único): procesa una canción.\n"
        "- Auto-Master (Lote): procesa cada canción individualmente.\n"
        "- Sin tokens o API disponible: usa automáticamente SUNO Clásico."
    )
    intro.setWordWrap(True)
    start_layout.addWidget(intro)
    tab_start.setLayout(start_layout)
    return tab_start


def build_audio_tab(window) -> QWidget:
    tab_single = QWidget()
    window.tab_single = tab_single
    tab_single_layout = QVBoxLayout()
    tab_single_layout.setSpacing(6)
    tab_single_layout.setContentsMargins(8, 8, 8, 8)
    single_input_layout = QHBoxLayout()
    single_input_layout.addWidget(QLabel("Entrada:"))
    single_input_layout.addWidget(window.input_edit)
    single_input_layout.addWidget(window.input_button)
    tab_single_layout.addLayout(single_input_layout)

    single_output_layout = QHBoxLayout()
    single_output_layout.addWidget(QLabel("Salida:"))
    single_output_layout.addWidget(window.output_edit)
    single_output_layout.addWidget(window.output_button)
    tab_single_layout.addLayout(single_output_layout)

    window.analyze_btn.setVisible(False)
    window.normalize_btn.setVisible(False)
    audio_help = QLabel(
        "Selecciona un archivo de entrada y una ruta de salida. "
        "Luego presiona \"Procesar audio\" para analizar, ajustar y re-analizar el resultado."
    )
    audio_help.setWordWrap(True)
    tab_single_layout.addWidget(audio_help)
    tab_single.setLayout(tab_single_layout)
    return tab_single


def build_batch_tab(window) -> QWidget:
    tab_batch = QWidget()
    window.tab_batch = tab_batch
    batch_layout = QVBoxLayout()
    batch_in_layout = QHBoxLayout()
    batch_in_layout.addWidget(QLabel("Carpeta entrada:"))
    batch_in_layout.addWidget(window.batch_input_edit)
    batch_in_layout.addWidget(window.batch_input_button)
    batch_in_layout.addWidget(window.batch_refresh_button)
    batch_layout.addLayout(batch_in_layout)

    batch_out_layout = QHBoxLayout()
    batch_out_layout.addWidget(QLabel("Carpeta salida:"))
    batch_out_layout.addWidget(window.batch_output_edit)
    batch_out_layout.addWidget(window.batch_output_button)
    batch_layout.addLayout(batch_out_layout)

    batch_form = QFormLayout()
    batch_form.addRow("Artista en nombre:", window.batch_suffix_edit)
    batch_layout.addLayout(batch_form)
    batch_layout.addWidget(QLabel("Archivos encontrados:"))
    batch_layout.addWidget(window.batch_table, 1)
    batch_select_layout = QHBoxLayout()
    batch_select_layout.addWidget(window.batch_select_all_btn)
    batch_select_layout.addWidget(window.batch_select_none_btn)
    batch_layout.addLayout(batch_select_layout)
    tab_batch.setLayout(batch_layout)
    return tab_batch


def build_process_tab(window) -> QWidget:
    """Construye el tab de procesos organizado en Reparación, Mezcla y Mastering."""
    tab_process = QWidget()
    window.tab_process = tab_process
    process_layout = QVBoxLayout()
    
    # Tab widget principal con las 3 categorías + opciones
    main_tabs = QTabWidget()
    window.process_tabs = main_tabs  # Mantener referencia para compatibilidad

    # ==================== REPARACIÓN ====================
    repair_widget = QWidget()
    repair_layout = QVBoxLayout()
    
    # Checkbox para habilitar/deshabilitar toda la reparación
    repair_layout.addWidget(window.repair_enabled_cb)
    
    repair_tabs = QTabWidget()
    
    # Tab Reparación - Reducción de ruido
    tab_repair = QWidget()
    tab_repair_layout = QFormLayout()
    tab_repair_layout.addRow("Noise reduction:", window.noise_reduction_combo)
    tab_repair_layout.addRow("Pink noise:", window.pink_noise_combo)
    tab_repair_layout.addRow("De-clip:", window.declip_combo)
    tab_repair_layout.addRow("De-click/pop:", window.declick_combo)
    tab_repair_layout.addRow("", window.auto_repair_cb)
    tab_repair.setLayout(tab_repair_layout)
    
    # Tab Entrada (DC offset, ganancia)
    tab_input = QWidget()
    tab_input_layout = QFormLayout()
    tab_input_layout.addRow("Ganancia entrada:", window.input_gain_spin)
    tab_input_layout.addRow("", window.dc_offset_cb)
    tab_input_layout.addRow("Input RMS:", window.input_rms_label)
    tab_input_layout.addRow("Input Peak:", window.input_peak_label)
    tab_input.setLayout(tab_input_layout)
    
    repair_tabs.addTab(tab_repair, "🔇 Ruido")
    repair_tabs.addTab(tab_input, "📥 Entrada")
    repair_layout.addWidget(repair_tabs)
    repair_widget.setLayout(repair_layout)
    
    # ==================== MEZCLA ====================
    mix_widget = QWidget()
    mix_layout = QVBoxLayout()
    
    # Checkbox para habilitar/deshabilitar toda la mezcla
    mix_layout.addWidget(window.mix_enabled_cb)
    
    mix_tabs = QTabWidget()

    # Tab Tono/EQ
    tab_tone = QWidget()
    tab_tone_layout = QFormLayout()
    tab_tone_layout.addRow("Preset:", window.tone_eq_preset_combo)
    tab_tone_layout.addRow("EQ low:", window.eq_low_spin)
    tab_tone_layout.addRow("Sub bass:", window.sub_bass_spin)
    tab_tone_layout.addRow("EQ mid:", window.eq_mid_spin)
    tab_tone_layout.addRow("EQ high:", window.eq_high_spin)
    tab_tone_layout.addRow("Tilt EQ:", window.tilt_eq_spin)
    tab_tone.setLayout(tab_tone_layout)

    # Tab Dinámica/EQ
    tab_dyn = QWidget()
    tab_dyn_layout = QVBoxLayout()
    tab_dyn_layout.addWidget(QLabel("Preset Dinamica EQ:"))
    tab_dyn_layout.addWidget(window.dynamic_eq_preset_combo)
    tab_dyn_layout.addWidget(window.dynamic_eq_cb)
    if PYQTGRAPH_AVAILABLE:
        dyn_plot = pg.PlotWidget()
        dyn_plot.setMinimumHeight(200)
        dyn_plot.showGrid(x=False, y=True, alpha=0.25)
        dyn_plot.setLabel("left", "Ajuste dB")
        dyn_plot.setYRange(-6.0, 6.0)
        window.dynamic_band_plot = dyn_plot
        tab_dyn_layout.addWidget(dyn_plot)
    dyn_form = QFormLayout()
    window.dynamic_band_spins.clear()
    for label, _low, _high, _attack, _release, _width in BAND_CONFIG:
        spin = QDoubleSpinBox()
        spin.setRange(-6.0, 6.0)
        spin.setDecimals(1)
        spin.setValue(0.0)
        spin.setSuffix(" dB")
        spin.valueChanged.connect(window._update_dynamic_band_plot)
        window.dynamic_band_spins[label] = spin
        dyn_form.addRow(label + ":", spin)
    tab_dyn_layout.addLayout(dyn_form)
    window._update_dynamic_band_plot()
    tab_dyn.setLayout(tab_dyn_layout)

    # Tab De-Esser
    tab_deesser = QWidget()
    tab_deesser_layout = QFormLayout()
    tab_deesser_layout.addRow("Preset:", window.deesser_preset_combo)
    tab_deesser_layout.addRow("", window.deesser_cb)
    tab_deesser_layout.addRow("Frecuencia:", window.deesser_freq_spin)
    tab_deesser_layout.addRow("Intensidad:", window.deesser_intensity_spin)
    tab_deesser.setLayout(tab_deesser_layout)

    # Tab Glue (compresión suave)
    tab_glue = QWidget()
    tab_glue_layout = QFormLayout()
    tab_glue_layout.addRow("Preset:", window.glue_preset_combo)
    tab_glue_layout.addRow("", window.glue_cb)
    tab_glue_layout.addRow("Glue threshold:", window.glue_threshold_spin)
    tab_glue_layout.addRow("Glue ratio:", window.glue_ratio_spin)
    tab_glue_layout.addRow("Glue attack:", window.glue_attack_spin)
    tab_glue_layout.addRow("Glue release:", window.glue_release_spin)
    tab_glue_layout.addRow("Glue makeup:", window.glue_makeup_spin)
    tab_glue.setLayout(tab_glue_layout)

    # Tab Stereo Width
    tab_stereo = QWidget()
    tab_stereo_layout = QVBoxLayout()
    tab_stereo_layout.addWidget(window.stereo_width_cb)
    if PYQTGRAPH_AVAILABLE:
        stereo_plot = pg.PlotWidget()
        stereo_plot.setMinimumHeight(200)
        stereo_plot.showGrid(x=False, y=True, alpha=0.25)
        stereo_plot.setLabel("left", "Ancho estereo")
        stereo_plot.setYRange(0.0, 2.0)
        window.stereo_band_plot = stereo_plot
        tab_stereo_layout.addWidget(stereo_plot)
    stereo_form = QFormLayout()
    window.stereo_band_spins.clear()
    for label, _low, _high, _attack, _release, width in BAND_CONFIG:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 3.0)
        spin.setDecimals(2)
        spin.setValue(float(width))
        spin.setSuffix(" x")
        spin.valueChanged.connect(window._update_stereo_band_plot)
        window.stereo_band_spins[label] = spin
        stereo_form.addRow(label + ":", spin)
    tab_stereo_layout.addLayout(stereo_form)
    window._update_stereo_band_plot()
    tab_stereo.setLayout(tab_stereo_layout)

    # Tab Stereo Dynamic
    tab_stereo_dynamic = QWidget()
    tab_stereo_dynamic_layout = QFormLayout()
    tab_stereo_dynamic_layout.addRow("", window.stereo_dynamic_cb)
    tab_stereo_dynamic_layout.addRow("Threshold:", window.stereo_dynamic_threshold_spin)
    tab_stereo_dynamic_layout.addRow("Ratio:", window.stereo_dynamic_ratio_spin)
    tab_stereo_dynamic_layout.addRow("Attack:", window.stereo_dynamic_attack_spin)
    tab_stereo_dynamic_layout.addRow("Release:", window.stereo_dynamic_release_spin)
    tab_stereo_dynamic_layout.addRow("Mix:", window.stereo_dynamic_mix_spin)
    window.stereo_dynamic_band_mix_spins.clear()
    for label, _low, _high, _attack, _release, _width in BAND_CONFIG:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setDecimals(2)
        spin.setValue(0.6)
        window.stereo_dynamic_band_mix_spins[label] = spin
        tab_stereo_dynamic_layout.addRow(f"Mix {label}:", spin)
    tab_stereo_dynamic.setLayout(tab_stereo_dynamic_layout)

    # Tab Saturación
    tab_saturation = QWidget()
    tab_saturation_layout = QFormLayout()
    tab_saturation_layout.addRow("", window.saturation_enable_cb)
    tab_saturation_layout.addRow("", window.saturation_per_band_cb)
    tab_saturation_layout.addRow("Tipo:", window.saturation_type_combo)
    tab_saturation_layout.addRow("Drive:", window.saturation_drive_spin)
    tab_saturation_layout.addRow("Mix:", window.saturation_mix_spin)
    band_form = QFormLayout()
    window.saturation_band_drive_spins.clear()
    window.saturation_band_mix_spins.clear()
    for label, _low, _high, _attack, _release, _width in BAND_CONFIG:
        drive = QDoubleSpinBox()
        drive.setRange(-24.0, 24.0)
        drive.setDecimals(1)
        drive.setValue(1.0)
        drive.setSuffix(" dB")
        mix = QDoubleSpinBox()
        mix.setRange(0.0, 100.0)
        mix.setDecimals(0)
        mix.setValue(5.0)
        mix.setSuffix(" %")
        row = QHBoxLayout()
        row.addWidget(QLabel("Drive"))
        row.addWidget(drive)
        row.addWidget(QLabel("Mix"))
        row.addWidget(mix)
        container = QWidget()
        container.setLayout(row)
        band_form.addRow(label + ":", container)
        window.saturation_band_drive_spins[label] = drive
        window.saturation_band_mix_spins[label] = mix
    tab_saturation_layout.addRow(QLabel("Saturacion por bandas (Drive/Mix):"))
    tab_saturation_layout.addRow(band_form)
    tab_saturation.setLayout(tab_saturation_layout)

    mix_tabs.addTab(tab_tone, "🎚️ Tono/EQ")
    mix_tabs.addTab(tab_dyn, "📊 Dinámica")
    mix_tabs.addTab(tab_deesser, "🔊 De-Esser")
    mix_tabs.addTab(tab_glue, "🔗 Glue")
    mix_tabs.addTab(tab_stereo, "↔️ Stereo W")
    mix_tabs.addTab(tab_stereo_dynamic, "↔️ Stereo D")
    mix_tabs.addTab(tab_saturation, "🔥 Saturación")
    mix_layout.addWidget(mix_tabs)
    mix_widget.setLayout(mix_layout)

    # ==================== MASTERING ====================
    master_widget = QWidget()
    master_layout = QVBoxLayout()
    
    # Checkbox para habilitar/deshabilitar todo el mastering
    master_layout.addWidget(window.master_enabled_cb)
    
    master_tabs = QTabWidget()

    # Tab Loudness
    tab_loudness = QWidget()
    tab_loudness_layout = QFormLayout()
    tab_loudness_layout.addRow("Preset LUFS:", window.preset_combo)
    tab_loudness_layout.addRow("Target LUFS:", window.target_spin)
    tab_loudness_layout.addRow("True Peak:", window.true_peak_spin)
    tab_loudness_layout.addRow("Medicion pre:", window.loudness_pre_label)
    tab_loudness_layout.addRow("Medicion post:", window.loudness_post_label)
    tab_loudness.setLayout(tab_loudness_layout)

    # Tab Limitador
    tab_limiter = QWidget()
    tab_limiter_layout = QFormLayout()
    tab_limiter_layout.addRow("Preset:", window.limiter_preset_combo)
    tab_limiter_layout.addRow("", window.brickwall_cb)
    tab_limiter_layout.addRow("Ceiling:", window.limiter_ceiling_spin)
    tab_limiter_layout.addRow("Release:", window.limiter_release_spin)
    tab_limiter.setLayout(tab_limiter_layout)

    # Tab Salida
    tab_output = QWidget()
    tab_output_layout = QFormLayout()
    tab_output_layout.addRow("Preset salida:", window.output_preset_combo)
    tab_output_layout.addRow("Sample rate:", window.sample_rate_combo)
    tab_output_layout.addRow("Bit depth:", window.bit_depth_combo)
    tab_output_layout.addRow("Fade in:", window.fade_in_spin)
    tab_output_layout.addRow("Fade out:", window.fade_out_spin)
    tab_output_layout.addRow("Formato salida:", window.output_format_combo)
    output_help = QLabel(
        "Usa Manual para editar valores. Los presets afectan audio unico y lote. "
        "El true peak se respeta al final con limiter."
    )
    output_help.setWordWrap(True)
    tab_output_layout.addRow("", output_help)
    tab_output.setLayout(tab_output_layout)

    master_tabs.addTab(tab_loudness, "📢 Loudness")
    master_tabs.addTab(tab_limiter, "🧱 Limitador")
    master_tabs.addTab(tab_output, "📤 Salida")
    master_layout.addWidget(master_tabs)
    master_widget.setLayout(master_layout)

    # ==================== OPCIONES ====================
    options_widget = QWidget()
    options_layout = QVBoxLayout()
    options_tabs = QTabWidget()

    # Tab Opciones generales
    tab_options = QWidget()
    tab_options_layout = QVBoxLayout()
    tab_options_layout.addWidget(window.analyze_only_cb)
    tab_options_layout.addWidget(window.verbose_cb)
    tab_options_layout.addWidget(window.overwrite_cb)
    tab_options_layout.addWidget(window.transparent_cb)
    tab_options_layout.addWidget(window.auto_band_gain_cb)
    tab_options_layout.addWidget(window.autogain_cb)
    tab_options.setLayout(tab_options_layout)

    # Tab Orden de procesos
    tab_order = QWidget()
    tab_order_layout = QVBoxLayout()
    tab_order_layout.addWidget(QLabel("Arrastra las cajas para ordenar el flujo."))
    window.process_order_widget = DragOrderWidget()
    items = [
        ("Entrada", "input"),
        ("Reparacion", "repair"),
        ("De-Esser", "deesser"),
        ("EQ estatico", "tone_eq"),
        ("Glue", "glue"),
        ("Stereo width", "stereo_width"),
        ("Stereo dinamico", "stereo_dynamic"),
        ("Saturacion", "saturation"),
        ("EQ dinamico", "dynamic_eq"),
        ("Loudness", "loudness"),
        ("Limitador", "limiter"),
        ("Fades", "fades"),
        ("Salida", "output"),
    ]
    for name, key in items:
        item = DragItem(name, key)
        if hasattr(window, "_on_process_item_activated"):
            item.activated.connect(window._on_process_item_activated)
        window.process_order_widget.add_item(item)
    tab_order_layout.addWidget(window.process_order_widget, 1)
    tab_order.setLayout(tab_order_layout)

    options_tabs.addTab(tab_options, "⚙️ General")
    options_tabs.addTab(tab_order, "🔀 Orden")
    options_layout.addWidget(options_tabs)
    options_widget.setLayout(options_layout)

    # ==================== TABS PRINCIPALES ====================
    main_tabs.addTab(repair_widget, "🔧 Reparación")
    main_tabs.addTab(mix_widget, "🎛️ Mezcla")
    main_tabs.addTab(master_widget, "🎚️ Mastering")
    main_tabs.addTab(options_widget, "⚙️ Opciones")

    # Índices para compatibilidad con navegación existente
    window.process_tab_input_index = 0  # En Reparación
    window.process_tab_repair_index = 0  # En Reparación
    window.process_tab_tone_index = 1  # En Mezcla
    window.process_tab_dyn_index = 1  # En Mezcla
    window.process_tab_deesser_index = 1  # En Mezcla
    window.process_tab_glue_index = 1  # En Mezcla
    window.process_tab_stereo_index = 1  # En Mezcla
    window.process_tab_stereo_dynamic_index = 1  # En Mezcla
    window.process_tab_saturation_index = 1  # En Mezcla
    window.process_tab_loudness_index = 2  # En Mastering
    window.process_tab_limiter_index = 2  # En Mastering
    window.process_tab_fades_index = 2  # En Mastering
    window.process_tab_options_index = 3  # En Opciones
    window.process_tab_order_index = 3  # En Opciones
    window.process_tab_output_index = 2  # En Mastering

    # Guardar referencias a subtabs para navegación detallada
    window.repair_tabs = repair_tabs
    window.mix_tabs = mix_tabs
    window.master_tabs = master_tabs
    window.options_tabs = options_tabs

    process_layout.addWidget(main_tabs)
    tab_process.setLayout(process_layout)
    return tab_process


def build_waveform_tab(window) -> QWidget:
    tab_waveform = QWidget()
    window.tab_waveform = tab_waveform
    waveform_layout = QHBoxLayout()
    waveform_left = QVBoxLayout()
    waveform_left.addWidget(QLabel("Audios:"))
    waveform_left.addWidget(window.waveform_table, 1)
    waveform_left.addWidget(window.waveform_global_label)
    waveform_form = QFormLayout()
    waveform_form.addRow("Fade in:", window.waveform_fade_in_spin)
    waveform_form.addRow("Fade out:", window.waveform_fade_out_spin)
    waveform_left.addLayout(waveform_form)
    waveform_buttons = QHBoxLayout()
    waveform_buttons.addWidget(window.waveform_apply_btn)
    waveform_buttons.addWidget(window.waveform_use_global_btn)
    waveform_left.addLayout(waveform_buttons)
    waveform_layout.addLayout(waveform_left, 1)

    waveform_right = QVBoxLayout()
    if PYQTGRAPH_AVAILABLE:
        window.waveform_help = QLabel(
            "Forma de onda interactiva. Arrastra las zonas para ajustar Fade in/out."
        )
        window.waveform_help.setWordWrap(True)
        waveform_right.addWidget(window.waveform_help)
        window.waveform_plot = pg.PlotWidget()
        window.waveform_plot.setMinimumHeight(240)
        window.waveform_plot.showGrid(x=True, y=True, alpha=0.25)
        window.waveform_plot.setLabel("bottom", "Tiempo", units="s")
        window.waveform_plot.setLabel("left", "Amplitud")
        window.waveform_plot.setYRange(-1.05, 1.05)
        window.waveform_curve = window.waveform_plot.plot([], [])
        window.fade_in_region = pg.LinearRegionItem([0.0, 0.0], brush=(80, 200, 120, 60))
        window.fade_in_region.setMovable(True)
        window.fade_out_region = pg.LinearRegionItem([0.0, 0.0], brush=(200, 80, 80, 60))
        window.fade_out_region.setMovable(True)
        window.waveform_plot.addItem(window.fade_in_region)
        window.waveform_plot.addItem(window.fade_out_region)
        waveform_right.addWidget(window.waveform_plot, 1)
    else:
        window.waveform_help = QLabel("Instala pyqtgraph para ver la forma de onda interactiva.")
        window.waveform_help.setWordWrap(True)
        waveform_right.addWidget(window.waveform_help)
    waveform_layout.addLayout(waveform_right, 2)
    tab_waveform.setLayout(waveform_layout)
    return tab_waveform


def build_results_tab(window) -> QWidget:
    tab_results = QWidget()
    window.tab_results = tab_results
    results_layout = QVBoxLayout()
    window.single_results_container = QWidget()
    single_results_layout = QVBoxLayout()
    stats_layout = QFormLayout()
    stats_layout.addRow("Input I (LUFS):", window.input_i_label)
    stats_layout.addRow("Input TP (dBTP):", window.input_tp_label)
    stats_layout.addRow("Input LRA (LU):", window.input_lra_label)
    stats_layout.addRow("Threshold (dB):", window.threshold_label)
    stats_layout.addRow("Offset recomendado:", window.offset_label)
    stats_layout.addRow(f"{VOICE_BAND[0]}:", window.voice_band_label)
    single_results_layout.addLayout(stats_layout)

    eq_layout = QFormLayout()
    for label, _low, _high, _attack, _release, _width in BAND_CONFIG:
        value_label = QLabel("-")
        window.band_labels[label] = value_label
        eq_layout.addRow(label + ":", value_label)
    single_results_layout.addLayout(eq_layout)

    window.single_results_container.setLayout(single_results_layout)
    results_layout.addWidget(window.single_results_container)

    results_tabs = QTabWidget()
    window.results_tabs = results_tabs

    tab_eq = QWidget()
    tab_eq_layout = QVBoxLayout()
    tab_eq_layout.addWidget(window.eq_suggestions)
    tab_eq.setLayout(tab_eq_layout)

    tab_single_results = QWidget()
    tab_single_layout = QVBoxLayout()
    tab_single_layout.addWidget(window.results_table)
    tab_single_layout.addWidget(window.results_text)
    tab_single_layout.addWidget(window.copy_results_btn)
    tab_single_results.setLayout(tab_single_layout)

    window.batch_results_table = window.batch_results_table
    tab_batch_results = QWidget()
    tab_batch_results_layout = QVBoxLayout()
    tab_batch_results_layout.addWidget(window.batch_results_table)
    tab_batch_results.setLayout(tab_batch_results_layout)

    tab_batch_summary = QWidget()
    tab_batch_summary_layout = QVBoxLayout()
    tab_batch_summary_layout.addWidget(window.batch_summary_text)
    tab_batch_summary.setLayout(tab_batch_summary_layout)

    tab_analysis_summary = QWidget()
    tab_analysis_layout = QVBoxLayout()
    tab_analysis_layout.addWidget(window.analysis_summary_text)
    
    # Agregar gráfico de espectro con matplotlib
    if hasattr(window, 'spectrum_canvas') and window.spectrum_canvas is not None:
        tab_analysis_layout.addWidget(QLabel("📊 Análisis de Espectro:"))
        tab_analysis_layout.addWidget(window.spectrum_canvas)
    
    tab_analysis_summary.setLayout(tab_analysis_layout)

    tab_log = QWidget()
    tab_log_layout = QVBoxLayout()
    log_actions = QHBoxLayout()
    log_actions.addWidget(window.clear_log_btn)
    log_actions.addWidget(window.copy_log_path_btn)
    log_actions.addStretch(1)
    tab_log_layout.addLayout(log_actions)
    tab_log_layout.addWidget(window.log_path_label)
    history_actions = QHBoxLayout()
    history_actions.addWidget(window.log_history_load_btn)
    history_actions.addStretch(1)
    tab_log_layout.addLayout(history_actions)
    tab_log_layout.addWidget(window.log_history_table)
    tab_log_layout.addWidget(window.log_view)
    tab_log.setLayout(tab_log_layout)

    tab_spectrum = QWidget()
    tab_spectrum_layout = QVBoxLayout()
    if PYQTGRAPH_AVAILABLE and hasattr(window, "spectrum_plot"):
        tab_spectrum_layout.addWidget(window.spectrum_plot, 1)
    else:
        tab_spectrum_layout.addWidget(QLabel("Instala pyqtgraph para ver el espectro."))
    tab_spectrum_layout.addWidget(window.spectrum_diag)
    tab_spectrum.setLayout(tab_spectrum_layout)

    results_tabs.addTab(tab_eq, "Sugerencias EQ")
    results_tabs.addTab(tab_single_results, "Antes / Después")
    results_tabs.addTab(tab_batch_results, "Resultados lote")
    results_tabs.addTab(tab_batch_summary, "Resumen lote")
    results_tabs.addTab(tab_analysis_summary, "Resumen análisis")
    results_tabs.addTab(tab_spectrum, "Espectro")
    results_tabs.addTab(tab_log, "Logs")
    window.results_tab_eq_index = results_tabs.indexOf(tab_eq)
    window.results_tab_single_index = results_tabs.indexOf(tab_single_results)
    window.results_tab_batch_index = results_tabs.indexOf(tab_batch_results)
    window.results_tab_batch_summary_index = results_tabs.indexOf(tab_batch_summary)
    window.results_tab_analysis_summary_index = results_tabs.indexOf(tab_analysis_summary)
    window.results_tab_spectrum_index = results_tabs.indexOf(tab_spectrum)
    window.results_tab_log_index = results_tabs.indexOf(tab_log)
    results_layout.addWidget(results_tabs)
    tab_results.setLayout(results_layout)
    return tab_results


def build_signature_tab(window) -> QWidget:
    tab_signature = QWidget()
    window.tab_signature = tab_signature
    signature_layout = QVBoxLayout()
    signature_layout.setSpacing(6)
    signature_layout.setContentsMargins(8, 8, 8, 8)
    signature_preset_layout = QHBoxLayout()
    signature_preset_layout.addWidget(QLabel("Preset firma:"))
    signature_preset_layout.addWidget(window.signature_preset_combo)
    signature_preset_layout.addWidget(window.signature_save_btn)
    signature_preset_layout.addWidget(window.signature_delete_btn)
    signature_layout.addLayout(signature_preset_layout)
    signature_form = QFormLayout()
    signature_form.addRow("Artist / Creator:", window.signature_artist_edit)
    signature_form.addRow("Copyright:", window.signature_copyright_edit)
    signature_form.addRow("Comments:", window.signature_comment_edit)
    signature_form.addRow("URL (opcional):", window.signature_url_edit)
    signature_form.addRow("Email (opcional):", window.signature_email_edit)
    signature_form.addRow("Sello discografico:", window.signature_label_edit)
    signature_form.addRow("Company / Marca:", window.signature_company_edit)
    signature_layout.addLayout(signature_form)
    signature_help = QLabel(
        "Estos datos se insertan en los WAV de salida (audio unico y lote). "
        "Artist, Copyright y Comments son obligatorios."
    )
    signature_help.setWordWrap(True)
    signature_layout.addWidget(signature_help)
    tab_signature.setLayout(signature_layout)
    return tab_signature


def build_about_tab(window) -> QWidget:
    tab_about = QWidget()
    about_layout = QVBoxLayout()
    about_layout.setSpacing(6)
    about_layout.setContentsMargins(12, 12, 12, 12)
    about_text = QLabel(
        f"{APP_NAME} {APP_VERSION}\n"
        "By SABE Software\n\n"
        "Creditos:\n"
        "Direccion y desarrollo: Martin Alejandro Oviedo\n"
        "Asistencia tecnica: Codex (OpenAI)\n\n"
        "Contacto:\n"
        "martinoviedo@disroot.org\n\n"
        "Licencia:\n"
        "Licencia de pago (posible donation ware a partir de un monto)."
    )
    about_text.setWordWrap(True)
    about_layout.addWidget(about_text)
    tab_about.setLayout(about_layout)
    return tab_about


def build_auto_master_tab(window) -> QWidget:
    tab_auto = QWidget()
    auto_layout = QVBoxLayout()
    auto_layout.setSpacing(6)
    auto_layout.setContentsMargins(8, 8, 8, 8)
    auto_form = QFormLayout()
    auto_form.addRow("Estilo:", window.auto_master_style_combo)
    auto_form.addRow("", window.auto_master_intelligent_cb)
    auto_form.addRow("", window.auto_master_profile_label)
    auto_form.addRow("LRA mínimo:", window.auto_master_min_lra_spin)
    auto_form.addRow("Crest mínimo:", window.auto_master_min_crest_spin)
    auto_form.addRow("", window.auto_master_enable_process_cb)
    # Nueva opción: Solo por bloque
    window.auto_master_block_mode_cb = QCheckBox("Solo por bloque (por sección)")
    window.auto_master_block_mode_cb.setChecked(False)
    window.auto_master_block_mode_cb.setToolTip(
        "Si está activado, el Auto-Master analiza y ajusta cada sección/bloque por separado "
        "en lugar de aplicar una configuración única a todo el archivo."
    )
    auto_form.addRow("", window.auto_master_block_mode_cb)
    auto_form.addRow("", window.auto_master_enable_process_cb)
    auto_form.addRow("", window.auto_master_apply_btn)
    auto_layout.addLayout(auto_form)
    auto_layout.addWidget(QLabel("Resumen y Análisis:"))
    auto_layout.addWidget(window.auto_master_notes)
    tab_auto.setLayout(auto_layout)
    return tab_auto


def build_ia_config_tab(window) -> QWidget:
    """Configuración IA: API keys multi-proveedor. NVIDIA + DeepSeek + custom OpenAI-compatible."""
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
        QCheckBox, QGroupBox
    )

    tab = QWidget()
    layout = QVBoxLayout()
    layout.setSpacing(8)

    # ── NVIDIA ──
    nv_grp = QGroupBox("NVIDIA NIM")
    nv_f = QFormLayout()
    nv_row = QHBoxLayout()
    window.ia_nvidia_key_edit = QLineEdit()
    window.ia_nvidia_key_edit.setPlaceholderText("nvapi-...")
    window.ia_nvidia_key_edit.setEchoMode(QLineEdit.Password)
    window.ia_nvidia_on_cb = QCheckBox("Activo")
    window.ia_nvidia_on_cb.setChecked(True)
    nv_row.addWidget(window.ia_nvidia_key_edit, 1)
    nv_row.addWidget(window.ia_nvidia_on_cb)
    nv_f.addRow("Key:", nv_row)
    nv_grp.setLayout(nv_f)
    layout.addWidget(nv_grp)

    # ── DeepSeek ──
    ds_grp = QGroupBox("DeepSeek")
    ds_f = QFormLayout()
    ds_row = QHBoxLayout()
    window.ia_api_key_edit = QLineEdit()
    window.ia_api_key_edit.setPlaceholderText("sk-...")
    window.ia_api_key_edit.setEchoMode(QLineEdit.Password)
    window.ia_ds_on_cb = QCheckBox("Activo")
    window.ia_ds_on_cb.setChecked(True)
    ds_row.addWidget(window.ia_api_key_edit, 1)
    ds_row.addWidget(window.ia_ds_on_cb)
    ds_f.addRow("Key:", ds_row)
    ds_grp.setLayout(ds_f)
    layout.addWidget(ds_grp)

    # ── Custom endpoint ──
    cust_grp = QGroupBox("Custom (OpenAI-compatible)")
    cust_f = QFormLayout()
    window.ia_custom_url_edit = QLineEdit()
    window.ia_custom_url_edit.setPlaceholderText("https://api.openai.com/v1/chat/completions")
    cust_f.addRow("URL:", window.ia_custom_url_edit)
    window.ia_custom_key_edit = QLineEdit()
    window.ia_custom_key_edit.setPlaceholderText("sk-...")
    window.ia_custom_key_edit.setEchoMode(QLineEdit.Password)
    cust_f.addRow("Key:", window.ia_custom_key_edit)
    window.ia_custom_model_edit = QLineEdit()
    window.ia_custom_model_edit.setPlaceholderText("gpt-4o-mini")
    cust_f.addRow("Model:", window.ia_custom_model_edit)
    window.ia_custom_on_cb = QCheckBox("Activo")
    cust_f.addRow("", window.ia_custom_on_cb)
    cust_grp.setLayout(cust_f)
    layout.addWidget(cust_grp)

    # ── Status ──
    window.ia_api_status = QLabel("Proveedores activos: —")
    window.ia_api_status.setStyleSheet("color: #fff; font-size: 11px;")
    layout.addWidget(window.ia_api_status)
    layout.addStretch()
    tab.setLayout(layout)
    return tab


def build_contexto_ia_tab(window) -> QWidget:
    """Contexto IA: artista, track, prompt SUNO, letras, notas. Datos para generación."""
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
        QTextEdit, QPushButton, QGroupBox
    )

    tab = QWidget()
    layout = QVBoxLayout()
    layout.setSpacing(6)

    # ── Artista ──
    art_grp = QGroupBox("Artista")
    art_f = QFormLayout()
    window.ia_artist_edit = QLineEdit("O-M-A")
    art_f.addRow("Nombre:", window.ia_artist_edit)
    window.ia_label_edit = QLineEdit("Detected Records Argentina")
    art_f.addRow("Sello:", window.ia_label_edit)
    art_grp.setLayout(art_f)
    layout.addWidget(art_grp)

    # ── Track ──
    trk_grp = QGroupBox("Track")
    trk_f = QFormLayout()
    trk_row = QHBoxLayout()
    window.ia_title_edit = QLineEdit()
    window.ia_title_edit.setPlaceholderText("Título del track")
    window.ia_title_btn = QPushButton("📂 Extraer")
    window.ia_title_btn.setMaximumWidth(90)
    trk_row.addWidget(window.ia_title_edit, 1)
    trk_row.addWidget(window.ia_title_btn)
    trk_f.addRow("Título:", trk_row)
    trk_grp.setLayout(trk_f)
    layout.addWidget(trk_grp)

    # ── SUNO Prompt ──
    suno_grp = QGroupBox("Prompt SUNO")
    suno_l = QVBoxLayout()
    window.ia_suno_prompt = QTextEdit()
    window.ia_suno_prompt.setPlaceholderText("Prompt original SUNO: género, tempo, voces...")
    window.ia_suno_prompt.setMinimumHeight(55)
    suno_l.addWidget(window.ia_suno_prompt)
    suno_grp.setLayout(suno_l)
    layout.addWidget(suno_grp)

    # ── Letra ──
    lyr_grp = QGroupBox("Letra / Lyrics")
    lyr_l = QVBoxLayout()
    lyr_h = QHBoxLayout()
    window.ia_lyrics_edit = QTextEdit()
    window.ia_lyrics_edit.setPlaceholderText("Letra...")
    window.ia_lyrics_edit.setMinimumHeight(70)
    window.ia_gen_lyrics_btn = QPushButton("🤖 Generar")
    window.ia_gen_lyrics_btn.setMaximumWidth(100)
    lyr_h.addStretch()
    lyr_h.addWidget(window.ia_gen_lyrics_btn)
    lyr_l.addLayout(lyr_h)
    lyr_l.addWidget(window.ia_lyrics_edit)
    lyr_grp.setLayout(lyr_l)
    layout.addWidget(lyr_grp)

    # ── Notas ──
    nts_grp = QGroupBox("Notas adicionales")
    nts_l = QVBoxLayout()
    window.ia_notes_edit = QTextEdit()
    window.ia_notes_edit.setPlaceholderText("Influencias, historia, datos curiosos...")
    window.ia_notes_edit.setMinimumHeight(45)
    nts_l.addWidget(window.ia_notes_edit)
    nts_grp.setLayout(nts_l)
    layout.addWidget(nts_grp)

    tab.setLayout(layout)
    return tab


def build_suno_prompt_tab(window) -> QWidget:
    """Formulario base para generar prompts SUNO desde lyrics, style y exclude styles."""
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
        QTextEdit, QComboBox, QGroupBox, QPushButton
    )

    tab = QWidget()
    layout = QVBoxLayout()
    layout.setSpacing(8)

    context_grp = QGroupBox("Idea para generar la musica")
    context_form = QFormLayout()
    window.suno_track_title_edit = QLineEdit()
    window.suno_track_title_edit.setPlaceholderText("Título o idea del track")
    context_form.addRow("Título:", window.suno_track_title_edit)
    window.suno_language_combo = QComboBox()
    window.suno_language_combo.addItems(["Español", "Inglés", "Instrumental", "Bilingüe"])
    context_form.addRow("Idioma:", window.suno_language_combo)
    window.suno_theme_edit = QLineEdit()
    window.suno_theme_edit.setPlaceholderText("Tema, historia o concepto de la letra")
    context_form.addRow("Tema:", window.suno_theme_edit)
    window.suno_mood_edit = QLineEdit()
    window.suno_mood_edit.setPlaceholderText("Oscuro, eufórico, melancólico, nocturno...")
    context_form.addRow("Mood:", window.suno_mood_edit)
    window.suno_structure_edit = QLineEdit()
    window.suno_structure_edit.setPlaceholderText("house, techno, pop, verse/chorus, intro/build/drop...")
    context_form.addRow("Estructura / estilo:", window.suno_structure_edit)
    window.suno_music_style_combo = QComboBox()
    window.suno_music_style_combo.setEditable(True)
    window.suno_music_style_combo.addItems([
        "house", "deep house", "tech house", "techno", "melodic techno",
        "synthwave", "ambient", "pop", "rock", "trap", "hip-hop",
        "drum and bass", "experimental",
    ])
    context_form.addRow("Estilo musical:", window.suno_music_style_combo)
    context_grp.setLayout(context_form)
    layout.addWidget(context_grp)

    api_grp = QGroupBox("Motor IA")
    api_form = QFormLayout()
    window.suno_nvidia_key_edit = QLineEdit()
    window.suno_nvidia_key_edit.setPlaceholderText("nvapi-... NVIDIA NIM")
    window.suno_nvidia_key_edit.setEchoMode(QLineEdit.Password)
    api_form.addRow("NVIDIA:", window.suno_nvidia_key_edit)
    window.suno_deepseek_key_edit = QLineEdit()
    window.suno_deepseek_key_edit.setPlaceholderText("sk-... DeepSeek")
    window.suno_deepseek_key_edit.setEchoMode(QLineEdit.Password)
    api_form.addRow("DeepSeek:", window.suno_deepseek_key_edit)
    window.suno_api_status_label = QLabel("Sin API key: usará fallback local")
    window.suno_api_status_label.setStyleSheet("color: #fff; font-size: 11px;")
    api_form.addRow("", window.suno_api_status_label)
    api_grp.setLayout(api_form)
    layout.addWidget(api_grp)

    dataset_grp = QGroupBox("Dataset SUNO")
    dataset_form = QFormLayout()
    window.suno_dataset_path_edit = QLineEdit("dataset/suno.jsonl")
    window.suno_dataset_path_edit.setPlaceholderText("Archivo JSONL con documentación SUNO curada")
    dataset_form.addRow("JSONL:", window.suno_dataset_path_edit)
    window.suno_dataset_status_label = QLabel("Listo para leer el dataset JSONL.")
    window.suno_dataset_status_label.setWordWrap(True)
    window.suno_dataset_status_label.setStyleSheet("color: #fff; font-size: 11px;")
    dataset_form.addRow("", window.suno_dataset_status_label)
    dataset_grp.setLayout(dataset_form)
    layout.addWidget(dataset_grp)

    actions_layout = QHBoxLayout()
    window.suno_generate_btn = QPushButton("🤖 Generar prompts para Suno")
    window.suno_generate_btn.setMinimumHeight(34)
    window.suno_generate_btn.setToolTip(
        "Lee el JSONL configurado y genera Lyrics Prompt, Style Prompt y Exclude Styles."
    )
    window.suno_copy_btn = QPushButton("📋 Copiar todo")
    window.suno_copy_btn.setMinimumHeight(34)
    window.suno_copy_btn.setToolTip("Copia los tres campos generados al portapapeles.")
    actions_layout.addWidget(window.suno_generate_btn)
    actions_layout.addWidget(window.suno_copy_btn)
    layout.addLayout(actions_layout)

    style_grp = QGroupBox("Paso 1 - Style Prompt")
    style_layout = QVBoxLayout()
    style_form = QFormLayout()
    window.suno_style_instructions_edit = QTextEdit()
    window.suno_style_instructions_edit.setPlaceholderText(
        "Indicaciones para el estilo: tempo, instrumentos, voces, energía, producción..."
    )
    window.suno_style_instructions_edit.setMinimumHeight(70)
    style_form.addRow("Indicaciones:", window.suno_style_instructions_edit)
    style_layout.addLayout(style_form)
    window.suno_generate_style_btn = QPushButton("🎛️ Generar Style")
    window.suno_generate_style_btn.setMinimumHeight(32)
    style_layout.addWidget(window.suno_generate_style_btn)
    window.suno_style_prompt_edit = QTextEdit()
    window.suno_style_prompt_edit.setPlaceholderText(
        "Style final para pegar en Suno."
    )
    window.suno_style_prompt_edit.setMinimumHeight(90)
    style_layout.addWidget(window.suno_style_prompt_edit)
    style_grp.setLayout(style_layout)
    layout.addWidget(style_grp)

    lyrics_grp = QGroupBox("Paso 2 - Lyrics Prompt")
    lyrics_layout = QVBoxLayout()
    lyrics_form = QFormLayout()
    window.suno_lyrics_instructions_edit = QTextEdit()
    window.suno_lyrics_instructions_edit.setPlaceholderText(
        "Tema de la canción, historia, punto de vista, palabras clave, tono emocional..."
    )
    window.suno_lyrics_instructions_edit.setMinimumHeight(80)
    lyrics_form.addRow("Tema / indicaciones:", window.suno_lyrics_instructions_edit)
    lyrics_layout.addLayout(lyrics_form)
    window.suno_generate_lyrics_prompt_btn = QPushButton("✍️ Generar Lyrics Prompt")
    window.suno_generate_lyrics_prompt_btn.setMinimumHeight(32)
    lyrics_layout.addWidget(window.suno_generate_lyrics_prompt_btn)
    window.suno_lyrics_prompt_edit = QTextEdit()
    window.suno_lyrics_prompt_edit.setPlaceholderText(
        "Prompt final para generar la letra en Suno."
    )
    window.suno_lyrics_prompt_edit.setMinimumHeight(110)
    lyrics_layout.addWidget(window.suno_lyrics_prompt_edit)
    lyrics_grp.setLayout(lyrics_layout)
    layout.addWidget(lyrics_grp)

    exclude_grp = QGroupBox("Paso 3 - Exclude Styles")
    exclude_layout = QVBoxLayout()
    window.suno_exclude_instructions_edit = QTextEdit()
    window.suno_exclude_instructions_edit.setPlaceholderText(
        "Qué querés evitar: géneros, voces, clichés, sonido sucio, distorsión, etc."
    )
    window.suno_exclude_instructions_edit.setMinimumHeight(55)
    exclude_layout.addWidget(window.suno_exclude_instructions_edit)
    window.suno_generate_exclude_btn = QPushButton("🚫 Generar Exclude Styles")
    window.suno_generate_exclude_btn.setMinimumHeight(32)
    exclude_layout.addWidget(window.suno_generate_exclude_btn)
    window.suno_exclude_styles_edit = QTextEdit()
    window.suno_exclude_styles_edit.setPlaceholderText(
        "Estilos, instrumentos, técnicas o clichés que SUNO debe evitar."
    )
    window.suno_exclude_styles_edit.setMinimumHeight(80)
    exclude_layout.addWidget(window.suno_exclude_styles_edit)
    exclude_grp.setLayout(exclude_layout)
    layout.addWidget(exclude_grp)

    layout.addStretch()
    tab.setLayout(layout)
    return tab


def build_ai_text_tab(window) -> QWidget:
    """Contenedor de generación de textos IA: Configuración, Contexto, Suno, Bandcamp."""
    from PySide6.QtWidgets import QScrollArea, QTabWidget, QVBoxLayout, QWidget

    def scroll_wrap(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    tab = QWidget()
    layout = QVBoxLayout()
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    text_tabs = QTabWidget()
    text_tabs.setDocumentMode(True)
    window.ai_text_tabs = text_tabs

    config_tab = build_ia_config_tab(window)
    context_tab = build_contexto_ia_tab(window)
    suno_tab = build_suno_prompt_tab(window)
    bandcamp_tab = build_bandcamp_tab(window)

    text_tabs.addTab(scroll_wrap(config_tab), "⚙️ Configuración")
    text_tabs.addTab(scroll_wrap(context_tab), "🧠 Contexto")
    text_tabs.addTab(scroll_wrap(suno_tab), "🎵 Suno")
    text_tabs.addTab(scroll_wrap(bandcamp_tab), "🎸 Bandcamp")

    layout.addWidget(text_tabs)
    tab.setLayout(layout)
    window.tab_ai_text = tab
    return tab


def build_bandcamp_tab(window) -> QWidget:
    """Salida Bandcamp: tags, release msg, descripción, créditos, metadatos. Lee contexto de la tab Contexto."""
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
        QTextEdit, QPushButton, QDateEdit, QDoubleSpinBox, QGroupBox
    )
    from PySide6.QtCore import QDate

    tab = QWidget()
    layout = QVBoxLayout()
    layout.setSpacing(8)

    # ── Generar ──
    gen_row = QHBoxLayout()
    window.bc_gen_btn = QPushButton("🤖 Generar textos Bandcamp")
    window.bc_gen_btn.setMinimumHeight(34)
    gen_row.addStretch()
    gen_row.addWidget(window.bc_gen_btn)
    layout.addLayout(gen_row)

    # ── Tags ──
    tags_grp = QGroupBox("Tags / Géneros")
    tags_lay = QVBoxLayout()
    window.bc_tags_edit = QLineEdit()
    window.bc_tags_edit.setPlaceholderText("minimal techno, house, electronic...")
    tags_lay.addWidget(window.bc_tags_edit)
    window.bc_tags_lbl = QLabel("—")
    window.bc_tags_lbl.setStyleSheet("color: #fff; font-size: 11px;")
    tags_lay.addWidget(window.bc_tags_lbl)
    tags_grp.setLayout(tags_lay)
    layout.addWidget(tags_grp)

    # ── Release msg ──
    rel_grp = QGroupBox("Mensaje de lanzamiento")
    rel_lay = QVBoxLayout()
    window.bc_release_msg_edit = QTextEdit()
    window.bc_release_msg_edit.setPlaceholderText("Nota para seguidores al publicar...")
    window.bc_release_msg_edit.setMaximumHeight(90)
    window.bc_release_chars = QLabel("1000 caracteres restantes")
    window.bc_release_chars.setStyleSheet("color: #fff; font-size: 11px;")
    rel_lay.addWidget(window.bc_release_msg_edit)
    rel_lay.addWidget(window.bc_release_chars)
    rel_grp.setLayout(rel_lay)
    layout.addWidget(rel_grp)

    # ── Descripción ──
    desc_grp = QGroupBox("Descripción / About")
    desc_lay = QVBoxLayout()
    window.bc_desc_edit = QTextEdit()
    window.bc_desc_edit.setPlaceholderText("Historia detrás del álbum...")
    window.bc_desc_edit.setMinimumHeight(80)
    desc_lay.addWidget(window.bc_desc_edit)
    desc_grp.setLayout(desc_lay)
    layout.addWidget(desc_grp)

    # ── Créditos ──
    cred_grp = QGroupBox("Créditos")
    cred_lay = QVBoxLayout()
    window.bc_credits_edit = QTextEdit()
    window.bc_credits_edit.setPlaceholderText("Producido, mezclado y masterizado por...")
    window.bc_credits_edit.setMinimumHeight(60)
    cred_lay.addWidget(window.bc_credits_edit)
    cred_grp.setLayout(cred_lay)
    layout.addWidget(cred_grp)

    # ── Metadatos ──
    meta_grp = QGroupBox("Metadatos")
    meta_f = QFormLayout()
    window.bc_date_edit = QDateEdit()
    window.bc_date_edit.setCalendarPopup(True)
    window.bc_date_edit.setDate(QDate.currentDate())
    meta_f.addRow("Fecha:", window.bc_date_edit)
    window.bc_catalog_edit = QLineEdit()
    window.bc_catalog_edit.setPlaceholderText("ej: DR-001")
    meta_f.addRow("Catálogo:", window.bc_catalog_edit)
    window.bc_price_spin = QDoubleSpinBox()
    window.bc_price_spin.setRange(0, 100)
    window.bc_price_spin.setValue(9.00)
    window.bc_price_spin.setPrefix("$ ")
    meta_f.addRow("Precio:", window.bc_price_spin)
    meta_grp.setLayout(meta_f)
    layout.addWidget(meta_grp)

    # ── Copiar ──
    window.bc_copy_btn = QPushButton("📋 Copiar todo al portapapeles")
    layout.addWidget(window.bc_copy_btn)
    layout.addStretch()
    tab.setLayout(layout)
    return tab
