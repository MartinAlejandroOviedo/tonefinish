"""
Nueva GUI reorganizada para ToneFinish.

Estructura simplificada:
- 4 tabs principales: Inicio, Proyecto, Procesamiento, Resultados
- Máximo 2 niveles de anidamiento
- Panel lateral con estado en Procesamiento
- Vista Simple/Avanzada
- Auto-Master integrado en Procesamiento
- Firma integrada en Proyecto
"""
from __future__ import annotations

from config import APP_NAME, APP_VENDOR, APP_VERSION, BAND_CONFIG, LOGO_PATH, VOICE_BAND
from ui.drag_order import DragItem, DragOrderWidget
from ui.process_order import ProcessOrderWidget, PROCESS_CONFIG
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
    QGroupBox,
    QFrame,
    QSplitter,
    QScrollArea,
    QSizePolicy,
    Qt,
    pg,
    QPushButton,
    QMessageBox,
)


def _wrap_in_scroll(widget: QWidget) -> QScrollArea:
    """Envuelve un widget en un área con scroll vertical para evitar desbordes."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    return area


# ============================================================================
# TAB INICIO - Simplificado con logo y selección de modo
# ============================================================================
def build_start_tab_new(window) -> QWidget:
    """Tab de inicio con logo, modo de trabajo y acceso rápido."""
    from config import is_premium, get_license_display_name
    
    tab = QWidget()
    layout = QVBoxLayout()
    layout.setSpacing(16)
    layout.setContentsMargins(24, 24, 24, 24)
    
    # Logo centrado
    if PYSIDE_AVAILABLE and LOGO_PATH:
        logo = QSvgWidget(LOGO_PATH)
        logo.setMaximumSize(140, 140)
        logo.setMinimumSize(100, 100)
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
    
    # Título con indicador de licencia
    license_text = get_license_display_name()
    license_color = "#4CAF50" if is_premium() else "#FF9800"
    
    title = QLabel(f"{APP_NAME} {APP_VERSION}")
    title.setStyleSheet("font-size: 20px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    
    license_label = QLabel(license_text)
    license_label.setStyleSheet(f"font-size: 12px; color: {license_color}; font-weight: bold;")
    license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(license_label)
    
    subtitle = QLabel(APP_VENDOR)
    subtitle.setStyleSheet("font-size: 12px; color: #fff;")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(subtitle)
    
    layout.addSpacing(20)
    
    # Modo de trabajo
    mode_group = QGroupBox("🎯 Modo de Trabajo")
    mode_layout = QVBoxLayout()
    mode_layout.addWidget(window.mode_combo)
    
    mode_help = QLabel(
        "• <b>Auto-Master (Audio único)</b>: la IA decide todos los plugins\n"
        "• <b>Auto-Master (Lote)</b>: decisión independiente para cada canción\n"
        "• <b>Sin tokens</b>: fallback automático al preset SUNO Clásico\n"
        "• <b>Solo analizar</b>: análisis sin escribir salida"
    )
    mode_help.setWordWrap(True)
    mode_help.setTextFormat(Qt.TextFormat.RichText)
    mode_layout.addWidget(mode_help)
    mode_group.setLayout(mode_layout)
    layout.addWidget(mode_group)
    
    layout.addStretch()
    tab.setLayout(layout)
    window.tab_start = tab
    return tab


# ============================================================================
# TAB PROYECTO - Unifica Audio, Lote y Firma
# ============================================================================
def build_project_tab_new(window) -> QWidget:
    """Tab de proyecto que unifica entrada/salida, lote y firma digital."""
    tab = QWidget()
    layout = QVBoxLayout()
    layout.setSpacing(12)
    layout.setContentsMargins(16, 16, 16, 16)
    
    project_tabs = QTabWidget()
    project_tabs.setDocumentMode(True)
    window.project_tabs = project_tabs
    
    # --- Subtab: Audio Único ---
    tab_audio = QWidget()
    audio_layout = QVBoxLayout()
    audio_layout.setSpacing(8)
    
    # Entrada
    input_group = QGroupBox("📂 Entrada")
    input_layout = QHBoxLayout()
    input_layout.addWidget(window.input_edit)
    input_layout.addWidget(window.input_button)
    input_group.setLayout(input_layout)
    audio_layout.addWidget(input_group)
    
    # Salida
    output_group = QGroupBox("💾 Salida")
    output_layout = QHBoxLayout()
    output_layout.addWidget(window.output_edit)
    output_layout.addWidget(window.output_button)
    output_group.setLayout(output_layout)
    audio_layout.addWidget(output_group)
    
    tab_audio.setLayout(audio_layout)
    project_tabs.addTab(tab_audio, "🎵 Audio")
    
    # --- Subtab: Lote ---
    tab_batch = QWidget()
    batch_layout = QVBoxLayout()
    batch_layout.setSpacing(8)
    
    # Carpetas
    folders_group = QGroupBox("📁 Carpetas")
    folders_layout = QFormLayout()
    
    batch_in_row = QHBoxLayout()
    batch_in_row.addWidget(window.batch_input_edit)
    batch_in_row.addWidget(window.batch_input_button)
    batch_in_row.addWidget(window.batch_refresh_button)
    folders_layout.addRow("Entrada:", batch_in_row)
    
    batch_out_row = QHBoxLayout()
    batch_out_row.addWidget(window.batch_output_edit)
    batch_out_row.addWidget(window.batch_output_button)
    folders_layout.addRow("Salida:", batch_out_row)
    
    folders_layout.addRow("Artista en nombre:", window.batch_suffix_edit)
    folders_group.setLayout(folders_layout)
    batch_layout.addWidget(folders_group)
    
    # Tabla de archivos
    files_group = QGroupBox("📋 Archivos")
    files_layout = QVBoxLayout()
    files_layout.addWidget(window.batch_table, 1)
    
    select_row = QHBoxLayout()
    select_row.addWidget(window.batch_select_all_btn)
    select_row.addWidget(window.batch_select_none_btn)
    select_row.addStretch()
    files_layout.addLayout(select_row)
    files_group.setLayout(files_layout)
    batch_layout.addWidget(files_group, 1)
    
    tab_batch.setLayout(batch_layout)
    project_tabs.addTab(tab_batch, "📁 Lote")
    
    # --- Subtab: Firma Digital ---
    tab_signature = QWidget()
    sig_layout = QVBoxLayout()
    sig_layout.setSpacing(8)
    
    sig_group = QGroupBox("✍️ Firma Digital (Metadatos)")
    sig_form = QFormLayout()
    
    # Preset de firma
    preset_row = QHBoxLayout()
    preset_row.addWidget(window.signature_preset_combo)
    preset_row.addWidget(window.signature_save_btn)
    preset_row.addWidget(window.signature_delete_btn)
    sig_form.addRow("Preset:", preset_row)
    
    sig_form.addRow("Artista:", window.signature_artist_edit)
    sig_form.addRow("Copyright:", window.signature_copyright_edit)
    sig_form.addRow("Comentarios:", window.signature_comment_edit)
    sig_form.addRow("URL:", window.signature_url_edit)
    sig_form.addRow("Email:", window.signature_email_edit)
    sig_form.addRow("Sello:", window.signature_label_edit)
    sig_form.addRow("Empresa:", window.signature_company_edit)
    sig_group.setLayout(sig_form)
    sig_layout.addWidget(sig_group)
    
    sig_help = QLabel(
        "⚠️ Artista, Copyright y Comentarios son obligatorios para procesar."
    )
    sig_help.setStyleSheet("color: #fff; font-weight: bold;")
    sig_layout.addWidget(sig_help)
    sig_layout.addStretch()
    
    tab_signature.setLayout(sig_layout)
    project_tabs.addTab(tab_signature, "✅ Firma")
    
    # --- Subtab: Salida ---
    tab_output = QWidget()
    out_layout = QVBoxLayout()
    
    out_group = QGroupBox("📤 Configuración de Salida")
    out_form = QFormLayout()
    out_form.addRow("Preset:", window.output_preset_combo)
    out_form.addRow("Sample Rate:", window.sample_rate_combo)
    out_form.addRow("Bit Depth:", window.bit_depth_combo)
    out_form.addRow("Formato:", window.output_format_combo)
    out_form.addRow("Fade In:", window.fade_in_spin)
    out_form.addRow("Fade Out:", window.fade_out_spin)
    out_group.setLayout(out_form)
    out_layout.addWidget(out_group)
    out_layout.addStretch()
    
    tab_output.setLayout(out_layout)
    project_tabs.addTab(tab_output, "📤 Salida")
    
    layout.addWidget(project_tabs)
    tab.setLayout(layout)
    window.tab_project = tab
    return tab


# ============================================================================
# TAB PROCESAMIENTO - Con Auto-Master integrado y panel lateral
# ============================================================================
def build_processing_tab_new(window) -> QWidget:
    """Tab de procesamiento con Auto-Master integrado y vista simple/avanzada."""
    tab = QWidget()
    main_layout = QHBoxLayout()
    main_layout.setSpacing(8)
    
    # ========== PANEL IZQUIERDO: Estado y Auto-Master ==========
    left_panel = QWidget()
    window.processing_left_panel = left_panel
    left_panel.setMaximumWidth(280)
    left_panel.setMinimumWidth(220)
    left_layout = QVBoxLayout()
    left_layout.setSpacing(12)
    
    # --- Auto-Master (integrado) ---
    auto_group = QGroupBox("🎨 Estilo Auto-Master")
    auto_layout = QVBoxLayout()
    auto_layout.addWidget(window.auto_master_style_combo)
    auto_layout.addWidget(window.auto_master_intelligent_cb)
    auto_layout.addWidget(window.auto_master_ai_assist_cb)
    auto_layout.addWidget(window.auto_master_apply_btn)
    auto_group.setLayout(auto_layout)
    left_layout.addWidget(auto_group)
    
    # --- Cadenas habilitadas ---
    chains_group = QGroupBox("🔗 Cadenas de Proceso")
    chains_layout = QVBoxLayout()
    chains_layout.addWidget(window.repair_enabled_cb)
    chains_layout.addWidget(window.mix_enabled_cb)
    chains_layout.addWidget(window.master_enabled_cb)
    chains_layout.addWidget(window.autogain_cb)
    chains_group.setLayout(chains_layout)
    left_layout.addWidget(chains_group)
    
    # --- Loudness rápido ---
    loud_group = QGroupBox("📢 Loudness")
    loud_layout = QFormLayout()
    loud_layout.addRow("Preset:", window.preset_combo)
    loud_layout.addRow("Target:", window.target_spin)
    loud_layout.addRow("True Peak:", window.true_peak_spin)
    loud_group.setLayout(loud_layout)
    left_layout.addWidget(loud_group)

    # --- Quick Master (Fase 3) ---
    quick_group = QGroupBox("⚡ Quick Master")
    window.processing_quick_group = quick_group
    quick_layout = QVBoxLayout()
    quick_form = QFormLayout()
    window.quick_master_amount_spin = QDoubleSpinBox()
    window.quick_master_amount_spin.setRange(0.0, 1.0)
    window.quick_master_amount_spin.setDecimals(2)
    window.quick_master_amount_spin.setSingleStep(0.05)
    window.quick_master_amount_spin.setValue(0.60)
    quick_form.addRow("Intensidad:", window.quick_master_amount_spin)
    quick_layout.addLayout(quick_form)

    quick_btns = QHBoxLayout()
    window.quick_master_clean_btn = QPushButton("Clean")
    window.quick_master_vocal_btn = QPushButton("Vocal Body")
    window.quick_master_tight_btn = QPushButton("Tight Low")
    quick_btns.addWidget(window.quick_master_clean_btn)
    quick_btns.addWidget(window.quick_master_vocal_btn)
    quick_btns.addWidget(window.quick_master_tight_btn)
    quick_layout.addLayout(quick_btns)
    quick_group.setLayout(quick_layout)
    left_layout.addWidget(quick_group)
    
    # --- Opciones rápidas ---
    opts_group = QGroupBox("⚙️ Opciones")
    opts_layout = QVBoxLayout()
    opts_layout.addWidget(window.brickwall_cb)
    opts_layout.addWidget(window.transparent_cb)
    opts_layout.addWidget(window.overwrite_cb)
    opts_layout.addWidget(window.verbose_cb)
    opts_group.setLayout(opts_layout)
    left_layout.addWidget(opts_group)
    
    # --- Indicadores de Telemetría (Paso 4) ---
    telemetry_group = QGroupBox("📊 Telemetría")
    window.processing_telemetry_group = telemetry_group
    telemetry_layout = QVBoxLayout()
    telemetry_layout.addWidget(window.resource_profile_combo)
    status_card = QGroupBox("Estado del proceso")
    status_layout = QVBoxLayout()
    status_layout.addWidget(window.process_state_label)
    status_layout.addWidget(window.process_file_label)
    status_layout.addWidget(window.process_history_text)
    status_card.setLayout(status_layout)
    telemetry_layout.addWidget(status_card)
    telemetry_layout.addWidget(window.compression_gr_bar)
    telemetry_layout.addWidget(window.process_stages_label)
    telemetry_layout.addWidget(window.validation_warnings_label)
    telemetry_group.setLayout(telemetry_layout)
    left_layout.addWidget(telemetry_group)
    
    left_layout.addStretch()
    left_panel.setLayout(left_layout)
    
    # ========== PANEL DERECHO: Procesos detallados ==========
    right_panel = QWidget()
    window.processing_right_panel = right_panel
    right_layout = QVBoxLayout()
    
    # Toggle simple/avanzado
    view_toggle = QHBoxLayout()
    window.simple_view_cb = window.auto_master_enable_process_cb
    window.simple_view_cb.setText("👁️ Mostrar controles técnicos")
    view_toggle.addWidget(window.simple_view_cb)
    view_toggle.addStretch()
    right_layout.addLayout(view_toggle)
    
    # Tabs de procesos
    process_tabs = QTabWidget()
    window.process_tabs = process_tabs
    
    # === REPARACIÓN ===
    repair_widget = _build_repair_section(window)
    process_tabs.addTab(_wrap_in_scroll(repair_widget), "🔧 Reparación")
    
    # === MEZCLA (agrupado) ===
    mix_widget = _build_mix_section(window)
    process_tabs.addTab(_wrap_in_scroll(mix_widget), "🎛️ Mezcla")
    
    # === MASTERING ===
    master_widget = _build_master_section(window)
    process_tabs.addTab(_wrap_in_scroll(master_widget), "🎚️ Mastering")
    
    # === OPCIONES AVANZADAS ===
    options_widget = _build_options_section(window)
    process_tabs.addTab(_wrap_in_scroll(options_widget), "⚙️ Avanzado")
    
    right_layout.addWidget(process_tabs, 1)
    right_panel.setLayout(right_layout)
    
    # Ensamblar paneles
    main_layout.addWidget(left_panel)
    
    # Separador visual
    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.VLine)
    separator.setFrameShadow(QFrame.Shadow.Sunken)
    main_layout.addWidget(separator)
    
    main_layout.addWidget(right_panel, 1)
    
    tab.setLayout(main_layout)
    window.tab_process = tab
    return tab


def _build_repair_section(window) -> QWidget:
    """Construye la sección de reparación."""
    widget = QWidget()
    layout = QVBoxLayout()
    
    # Ruido
    noise_group = QGroupBox("🔇 Reducción de Ruido")
    noise_form = QFormLayout()
    noise_form.addRow("Noise:", window.noise_reduction_combo)
    noise_form.addRow("Pink Noise:", window.pink_noise_combo)
    noise_form.addRow("De-clip:", window.declip_combo)
    noise_form.addRow("De-click:", window.declick_combo)
    noise_form.addRow("", window.auto_repair_cb)
    noise_group.setLayout(noise_form)
    layout.addWidget(noise_group)
    
    # Entrada
    input_group = QGroupBox("📥 Entrada")
    input_form = QFormLayout()
    input_form.addRow("Ganancia:", window.input_gain_spin)
    input_form.addRow("", window.dc_offset_cb)
    input_form.addRow("RMS:", window.input_rms_label)
    input_form.addRow("Peak:", window.input_peak_label)
    input_group.setLayout(input_form)
    layout.addWidget(input_group)
    
    layout.addStretch()
    widget.setLayout(layout)
    return widget


def _build_mix_section(window) -> QWidget:
    """Construye la sección de mezcla con subtabs agrupados."""
    widget = QWidget()
    layout = QVBoxLayout()
    
    # Barra de presets personalizados
    preset_group = QGroupBox("💾 Preset de Mezcla")
    preset_layout = QHBoxLayout()
    preset_layout.addWidget(window.mix_preset_combo, 1)
    preset_layout.addWidget(window.mix_save_btn)
    preset_layout.addWidget(window.mix_delete_btn)
    preset_group.setLayout(preset_layout)
    layout.addWidget(preset_group)
    
    mix_tabs = QTabWidget()
    window.mix_tabs = mix_tabs
    
    # --- Tab: Tono (EQ estático + Tilt) ---
    tab_tone = QWidget()
    tone_layout = QVBoxLayout()
    
    eq_group = QGroupBox("🎚️ Ecualizador")
    eq_form = QFormLayout()
    eq_form.addRow("Preset:", window.tone_eq_preset_combo)
    eq_form.addRow("Graves:", window.eq_low_spin)
    eq_form.addRow("Sub bass:", window.sub_bass_spin)
    eq_form.addRow("Medios:", window.eq_mid_spin)
    eq_form.addRow("Agudos:", window.eq_high_spin)
    eq_form.addRow("Tilt:", window.tilt_eq_spin)
    eq_group.setLayout(eq_form)
    tone_layout.addWidget(eq_group)
    tone_layout.addStretch()
    tab_tone.setLayout(tone_layout)
    mix_tabs.addTab(tab_tone, "🎚️ Tono")
    
    # --- Tab: Dinámica (EQ dinámico + Glue) ---
    tab_dyn = QWidget()
    dyn_layout = QVBoxLayout()
    
    # EQ Dinámico
    dyneq_group = QGroupBox("📊 EQ Dinámico")
    window.mix_group_dyneq = dyneq_group
    dyneq_layout = QVBoxLayout()
    dyneq_layout.addWidget(window.dynamic_eq_cb)
    dyneq_layout.addWidget(window.dynamic_eq_preset_combo)
    
    if PYQTGRAPH_AVAILABLE:
        dyn_plot = pg.PlotWidget()
        dyn_plot.setMinimumHeight(140)
        dyn_plot.showGrid(x=False, y=True, alpha=0.25)
        dyn_plot.setLabel("left", "dB")
        dyn_plot.setYRange(-6.0, 6.0)
        window.dynamic_band_plot = dyn_plot
        dyneq_layout.addWidget(dyn_plot)
    
    # Spins por banda (compacto)
    band_row = QHBoxLayout()
    for i, (label, _low, _high, _attack, _release, _width) in enumerate(BAND_CONFIG):
        spin = QDoubleSpinBox()
        spin.setRange(-6.0, 6.0)
        spin.setDecimals(1)
        spin.setValue(0.0)
        spin.setSuffix("dB")
        spin.setMaximumWidth(70)
        spin.valueChanged.connect(window._update_dynamic_band_plot)
        window.dynamic_band_spins[label] = spin
        
        col = QVBoxLayout()
        short_label = label.split()[0][:4]  # "Subb", "Bass", etc.
        col.addWidget(QLabel(short_label))
        col.addWidget(spin)
        band_row.addLayout(col)
    dyneq_layout.addLayout(band_row)
    dyneq_group.setLayout(dyneq_layout)
    dyn_layout.addWidget(dyneq_group)
    
    # Glue
    glue_group = QGroupBox("🔗 Glue Compression")
    window.mix_group_glue = glue_group
    glue_layout = QVBoxLayout()
    glue_layout.addWidget(window.glue_cb)
    glue_form = QFormLayout()
    glue_form.addRow("Preset:", window.glue_preset_combo)
    glue_form.addRow("Threshold:", window.glue_threshold_spin)
    glue_form.addRow("Ratio:", window.glue_ratio_spin)
    
    glue_row = QHBoxLayout()
    glue_row.addWidget(QLabel("Atk:"))
    glue_row.addWidget(window.glue_attack_spin)
    glue_row.addWidget(QLabel("Rel:"))
    glue_row.addWidget(window.glue_release_spin)
    glue_form.addRow("", glue_row)
    glue_form.addRow("Makeup:", window.glue_makeup_spin)
    glue_layout.addLayout(glue_form)
    glue_group.setLayout(glue_layout)
    dyn_layout.addWidget(glue_group)
    
    tab_dyn.setLayout(dyn_layout)
    mix_tabs.addTab(tab_dyn, "📊 Dinámica")
    
    # --- Tab: Estéreo (Width + Dynamic) ---
    tab_stereo = QWidget()
    stereo_layout = QVBoxLayout()
    
    # Stereo Width
    width_group = QGroupBox("↔️ Stereo Width")
    window.mix_group_width = width_group
    width_layout = QVBoxLayout()
    width_layout.addWidget(window.stereo_width_cb)
    
    if PYQTGRAPH_AVAILABLE:
        stereo_plot = pg.PlotWidget()
        stereo_plot.setMinimumHeight(120)
        stereo_plot.showGrid(x=False, y=True, alpha=0.25)
        stereo_plot.setLabel("left", "Width")
        stereo_plot.setYRange(0.0, 2.0)
        window.stereo_band_plot = stereo_plot
        width_layout.addWidget(stereo_plot)
    
    # Spins compactos
    width_row = QHBoxLayout()
    for i, (label, _low, _high, _attack, _release, width) in enumerate(BAND_CONFIG):
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 3.0)
        spin.setDecimals(2)
        spin.setValue(float(width))
        spin.setMaximumWidth(60)
        spin.valueChanged.connect(window._update_stereo_band_plot)
        window.stereo_band_spins[label] = spin
        width_row.addWidget(spin)
    width_layout.addLayout(width_row)
    width_group.setLayout(width_layout)
    stereo_layout.addWidget(width_group)
    
    # Stereo Dynamic
    dyn_group = QGroupBox("🔄 Stereo Dinámico")
    window.mix_group_stereo_dynamic = dyn_group
    dyn_form = QFormLayout()
    dyn_form.addRow("", window.stereo_dynamic_cb)
    sd_row = QHBoxLayout()
    sd_row.addWidget(QLabel("Thr:"))
    sd_row.addWidget(window.stereo_dynamic_threshold_spin)
    sd_row.addWidget(QLabel("Rat:"))
    sd_row.addWidget(window.stereo_dynamic_ratio_spin)
    dyn_form.addRow("", sd_row)
    
    sd_row2 = QHBoxLayout()
    sd_row2.addWidget(QLabel("Atk:"))
    sd_row2.addWidget(window.stereo_dynamic_attack_spin)
    sd_row2.addWidget(QLabel("Rel:"))
    sd_row2.addWidget(window.stereo_dynamic_release_spin)
    dyn_form.addRow("", sd_row2)
    dyn_form.addRow("Mix:", window.stereo_dynamic_mix_spin)
    dyn_group.setLayout(dyn_form)
    stereo_layout.addWidget(dyn_group)
    
    tab_stereo.setLayout(stereo_layout)
    mix_tabs.addTab(tab_stereo, "↔️ Estéreo")
    
    # --- Tab: Color (De-esser + Saturación) ---
    tab_color = QWidget()
    color_layout = QVBoxLayout()
    
    # De-esser
    deess_group = QGroupBox("🔊 De-Esser")
    window.mix_group_deesser = deess_group
    deess_form = QFormLayout()
    deess_form.addRow("", window.deesser_cb)
    deess_form.addRow("Preset:", window.deesser_preset_combo)
    deess_form.addRow("Frecuencia:", window.deesser_freq_spin)
    deess_form.addRow("Intensidad:", window.deesser_intensity_spin)
    deess_group.setLayout(deess_form)
    color_layout.addWidget(deess_group)
    
    # Saturación
    sat_group = QGroupBox("🔥 Saturación")
    window.mix_group_saturation = sat_group
    sat_form = QFormLayout()
    sat_form.addRow("", window.saturation_enable_cb)
    sat_form.addRow("", window.saturation_per_band_cb)
    sat_form.addRow("Tipo:", window.saturation_type_combo)
    sat_form.addRow("Drive:", window.saturation_drive_spin)
    sat_form.addRow("Mix:", window.saturation_mix_spin)
    sat_group.setLayout(sat_form)
    color_layout.addWidget(sat_group)
    
    # Control de Saturación Post-Proceso
    sat_control_group = QGroupBox("🛡️ Control de Saturación Final")
    window.mix_group_saturation_control = sat_control_group
    sat_control_form = QFormLayout()
    sat_control_group.setLayout(sat_control_form)
    color_layout.addWidget(sat_control_group)
    
    # Saturación por banda (compacto)
    if hasattr(window, 'saturation_band_drive_spins'):
        band_group = QGroupBox("Por Banda (Drive / Mix)")
        window.mix_group_saturation_band = band_group
        band_layout = QVBoxLayout()
        for label, _low, _high, _attack, _release, _width in BAND_CONFIG:
            row = QHBoxLayout()
            short = label.split()[0][:6]
            row.addWidget(QLabel(f"{short}:"))
            
            drive = QDoubleSpinBox()
            drive.setRange(-24.0, 24.0)
            drive.setDecimals(1)
            drive.setValue(0.0)
            drive.setSuffix("dB")
            drive.setMaximumWidth(70)
            
            mix = QDoubleSpinBox()
            mix.setRange(0.0, 100.0)
            mix.setDecimals(0)
            mix.setValue(0.0)
            mix.setSuffix("%")
            mix.setMaximumWidth(60)
            
            row.addWidget(drive)
            row.addWidget(mix)
            row.addStretch()
            band_layout.addLayout(row)
            
            window.saturation_band_drive_spins[label] = drive
            window.saturation_band_mix_spins[label] = mix
        band_group.setLayout(band_layout)
        color_layout.addWidget(band_group)
    
    tab_color.setLayout(color_layout)
    mix_tabs.addTab(tab_color, "🔥 Color")
    
    layout.addWidget(mix_tabs)
    widget.setLayout(layout)
    return widget


def _build_master_section(window) -> QWidget:
    """Construye la sección de mastering."""
    widget = QWidget()
    layout = QVBoxLayout()
    
    # Barra de presets personalizados
    preset_group = QGroupBox("💾 Preset de Mastering")
    preset_layout = QHBoxLayout()
    preset_layout.addWidget(window.master_preset_combo, 1)
    preset_layout.addWidget(window.master_save_btn)
    preset_layout.addWidget(window.master_delete_btn)
    preset_group.setLayout(preset_layout)
    layout.addWidget(preset_group)
    
    # Loudness (ya está en panel lateral, aquí solo mediciones)
    loud_group = QGroupBox("📢 Mediciones")
    window.master_group_measurements = loud_group
    loud_form = QFormLayout()
    loud_form.addRow("Pre-proceso:", window.loudness_pre_label)
    loud_form.addRow("Post-proceso:", window.loudness_post_label)
    loud_group.setLayout(loud_form)
    layout.addWidget(loud_group)
    
    # Limiter
    lim_group = QGroupBox("🧱 Limitador")
    window.master_group_limiter = lim_group
    lim_form = QFormLayout()
    lim_form.addRow("Preset:", window.limiter_preset_combo)
    lim_form.addRow("Ceiling:", window.limiter_ceiling_spin)
    lim_form.addRow("Release:", window.limiter_release_spin)
    lim_form.addRow("", window.multiband_limiter_cb)
    for band_label, spin in window.multiband_limiter_spins.items():
        lim_form.addRow(f"  {band_label}:", spin)
    lim_group.setLayout(lim_form)
    layout.addWidget(lim_group)
    
    # Fades
    fade_group = QGroupBox("〰️ Fades")
    window.master_group_fades = fade_group
    fade_layout = QVBoxLayout()
    
    # Tabla de archivos para fades
    fade_layout.addWidget(window.waveform_table)
    
    fade_form = QFormLayout()
    fade_form.addRow("Fade In:", window.waveform_fade_in_spin)
    fade_form.addRow("Fade Out:", window.waveform_fade_out_spin)
    fade_layout.addLayout(fade_form)
    
    fade_btns = QHBoxLayout()
    fade_btns.addWidget(window.waveform_apply_btn)
    fade_btns.addWidget(window.waveform_use_global_btn)
    fade_layout.addLayout(fade_btns)
    
    # Waveform interactivo
    if PYQTGRAPH_AVAILABLE:
        window.waveform_plot = pg.PlotWidget()
        window.waveform_plot.setMinimumHeight(150)
        window.waveform_plot.showGrid(x=True, y=True, alpha=0.25)
        window.waveform_plot.setLabel("bottom", "Tiempo", units="s")
        window.waveform_plot.setYRange(-1.05, 1.05)
        window.waveform_curve = window.waveform_plot.plot([], [])
        window.fade_in_region = pg.LinearRegionItem([0.0, 0.0], brush=(80, 200, 120, 60))
        window.fade_out_region = pg.LinearRegionItem([0.0, 0.0], brush=(200, 80, 80, 60))
        window.waveform_plot.addItem(window.fade_in_region)
        window.waveform_plot.addItem(window.fade_out_region)
        fade_layout.addWidget(window.waveform_plot)
    
    fade_group.setLayout(fade_layout)
    layout.addWidget(fade_group, 1)
    
    widget.setLayout(layout)
    return widget


def _build_options_section(window) -> QWidget:
    """Construye la sección de opciones avanzadas."""
    widget = QWidget()
    layout = QVBoxLayout()
    
    # Opciones generales
    gen_group = QGroupBox("⚙️ General")
    gen_layout = QVBoxLayout()
    gen_layout.addWidget(window.analyze_only_cb)
    gen_layout.addWidget(window.auto_band_gain_cb)
    gen_group.setLayout(gen_layout)
    layout.addWidget(gen_group)
    
    # Orden de procesos mejorado
    order_group = QGroupBox("🔀 Cadena de Procesamiento")
    order_layout = QVBoxLayout()
    
    window.process_order_widget = ProcessOrderWidget()
    
    # Agregar todos los procesos en orden predeterminado
    default_order = [
        "input", "repair", "deesser", "tone_eq", "glue",
        "stereo_width", "stereo_dynamic", "saturation",
        "dynamic_eq", "loudness", "limiter", "fades", "output"
    ]
    for key in default_order:
        window.process_order_widget.add_process(key)
    
    # Vincular checkboxes existentes
    checkbox_bindings = {
        "repair": "repair_enabled_cb",
        "deesser": "deesser_cb",
        "tone_eq": None,  # EQ tonal siempre activo si hay valores
        "glue": "glue_cb",
        "stereo_width": "stereo_width_cb",
        "stereo_dynamic": "stereo_dynamic_cb",
        "saturation": "saturation_enable_cb",
        "dynamic_eq": "dynamic_eq_cb",
        "loudness": None,  # Loudness siempre activo
        "limiter": "brickwall_cb",
        "fades": None,  # Fades activo si hay valores > 0
    }
    
    for key, cb_name in checkbox_bindings.items():
        if cb_name and hasattr(window, cb_name):
            checkbox = getattr(window, cb_name)
            window.process_order_widget.bind_checkbox(key, checkbox)
    
    # Conectar señal de cambio de orden
    if hasattr(window, "_on_process_order_changed"):
        window.process_order_widget.orderChanged.connect(window._on_process_order_changed)
    
    # Conectar doble-click para navegar al proceso
    for key in default_order:
        if key in window.process_order_widget._items:
            item = window.process_order_widget._items[key]
            if hasattr(window, "_on_process_item_activated"):
                item.activated.connect(window._on_process_item_activated)
    
    order_layout.addWidget(window.process_order_widget, 1)
    order_group.setLayout(order_layout)
    layout.addWidget(order_group, 1)
    
    widget.setLayout(layout)
    return widget


# ============================================================================
# TAB RESULTADOS - Rediseñado con sub-tabs para mejorar legibilidad
# ============================================================================
def build_results_tab_new(window) -> QWidget:
    """
    Tab de resultados reorganizada en sub-tabs:
    - Resumen: métricas y sugerencias
    - Espectro: gráfica de frecuencia y diagnóstico
    - Lote: resultados por archivo
    - Logs: trazas y historial
    - Detalles: resumen textual final
    """
    results_tabs = QTabWidget()
    results_tabs.setDocumentMode(True)
    results_tabs.setMovable(False)
    window.results_tabs = results_tabs

    # ==========================================================================
    # SUBTAB: RESUMEN
    # ==========================================================================
    summary_tab = QWidget()
    summary_layout = QVBoxLayout()
    summary_layout.setSpacing(12)
    summary_layout.setContentsMargins(12, 12, 12, 12)

    metrics_group = QGroupBox("📊 Métricas Antes/Después")
    metrics_layout = QVBoxLayout()
    metrics_layout.setSpacing(8)
    
    # Tabla de resultados a ancho completo
    window.results_table.setMinimumHeight(180)
    window.results_table.setMaximumHeight(260)
    window.results_table.verticalHeader().setVisible(False)
    metrics_layout.addWidget(window.results_table)
    
    # Métricas adicionales sin comprimir en un panel lateral
    extra_metrics = QHBoxLayout()
    extra_metrics.setSpacing(16)

    input_box = QGroupBox("Entrada")
    input_box_layout = QVBoxLayout()
    input_form = QFormLayout()
    input_form.setSpacing(4)
    input_form.addRow("LUFS:", window.input_i_label)
    input_form.addRow("Peak:", window.input_tp_label)
    input_form.addRow("LRA:", window.input_lra_label)
    input_box_layout.addLayout(input_form)
    input_box.setLayout(input_box_layout)
    extra_metrics.addWidget(input_box, 1)

    analysis_box = QGroupBox("Análisis")
    analysis_box_layout = QVBoxLayout()
    other_form = QFormLayout()
    other_form.setSpacing(4)
    other_form.addRow("Threshold:", window.threshold_label)
    other_form.addRow("Offset:", window.offset_label)
    other_form.addRow("Voz:", window.voice_band_label)
    analysis_box_layout.addLayout(other_form)
    analysis_box.setLayout(analysis_box_layout)
    extra_metrics.addWidget(analysis_box, 1)

    metrics_layout.addLayout(extra_metrics)
    metrics_group.setLayout(metrics_layout)
    window.single_results_container = metrics_group
    summary_layout.addWidget(metrics_group)

    sug_group = QGroupBox("💡 Sugerencias")
    sug_layout = QVBoxLayout()
    window.eq_suggestions.setMinimumHeight(100)
    window.eq_suggestions.setMaximumHeight(160)
    sug_layout.addWidget(window.eq_suggestions)
    sug_group.setLayout(sug_layout)
    summary_layout.addWidget(sug_group)

    copy_row = QHBoxLayout()
    copy_row.addWidget(window.copy_results_btn)
    copy_row.addStretch()
    summary_layout.addLayout(copy_row)
    summary_layout.addStretch()
    summary_tab.setLayout(summary_layout)
    results_tabs.addTab(summary_tab, "📊 Resumen")

    # ==========================================================================
    # SUBTAB: ESPECTRO
    # ==========================================================================
    spectrum_tab = QWidget()
    spectrum_tab_layout = QVBoxLayout()
    spectrum_tab_layout.setSpacing(12)
    spectrum_tab_layout.setContentsMargins(12, 12, 12, 12)

    spectrum_group = QGroupBox("📊 Espectro de Frecuencias")
    spectrum_group_layout = QVBoxLayout()
    
    if PYQTGRAPH_AVAILABLE and hasattr(window, "spectrum_plot") and window.spectrum_plot:
        window.spectrum_plot.setMinimumHeight(180)
        window.spectrum_plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    window.spectrum_diag.setMinimumHeight(80)
    window.spectrum_diag.setMaximumHeight(160)
    window.spectrum_diag.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    spectrum_splitter = QSplitter(Qt.Orientation.Vertical)
    spectrum_splitter.setChildrenCollapsible(False)
    if PYQTGRAPH_AVAILABLE and hasattr(window, "spectrum_plot") and window.spectrum_plot:
        spectrum_splitter.addWidget(window.spectrum_plot)
        spectrum_splitter.setStretchFactor(0, 4)
    spectrum_splitter.addWidget(window.spectrum_diag)
    spectrum_splitter.setStretchFactor(1, 1)

    spectrum_group_layout.addWidget(spectrum_splitter, 1)
    spectrum_group.setLayout(spectrum_group_layout)
    spectrum_tab_layout.addWidget(spectrum_group, 1)
    spectrum_tab.setLayout(spectrum_tab_layout)
    results_tabs.addTab(spectrum_tab, "📈 Espectro")

    # ==========================================================================
    # SUBTAB: LOTE
    # ==========================================================================
    batch_tab = QWidget()
    batch_tab_layout = QVBoxLayout()
    batch_tab_layout.setSpacing(12)
    batch_tab_layout.setContentsMargins(12, 12, 12, 12)

    batch_group = QGroupBox("📁 Resultados del Lote")
    batch_group.setCheckable(True)
    batch_group.setChecked(True)
    window.batch_results_group = batch_group  # Referencia para mostrar/ocultar

    batch_group_layout = QVBoxLayout()
    window.batch_results_table.setMinimumHeight(180)
    window.batch_results_table.setMaximumHeight(280)
    batch_group_layout.addWidget(window.batch_results_table)
    window.batch_summary_text.setMinimumHeight(80)
    window.batch_summary_text.setMaximumHeight(140)
    batch_group_layout.addWidget(window.batch_summary_text)
    batch_group.setLayout(batch_group_layout)
    batch_tab_layout.addWidget(batch_group, 1)
    batch_tab.setLayout(batch_tab_layout)
    results_tabs.addTab(batch_tab, "📁 Lote")

    # ==========================================================================
    # SUBTAB: LOGS
    # ==========================================================================
    log_tab = QWidget()
    log_tab_layout = QVBoxLayout()
    log_tab_layout.setSpacing(12)
    log_tab_layout.setContentsMargins(12, 12, 12, 12)

    log_group = QGroupBox("📜 Log del Proceso")
    log_group.setCheckable(True)
    log_group.setChecked(True)
    window.log_group = log_group

    log_layout = QVBoxLayout()
    log_layout.setSpacing(8)

    log_btns = QHBoxLayout()
    log_btns.addWidget(window.clear_log_btn)
    log_btns.addWidget(window.copy_log_path_btn)
    log_btns.addWidget(window.log_history_load_btn)
    log_btns.addStretch()
    log_layout.addLayout(log_btns)
    
    window.log_path_label.setMaximumHeight(20)
    log_layout.addWidget(window.log_path_label)

    window.log_view.setMinimumHeight(180)
    window.log_view.setMaximumHeight(260)
    log_layout.addWidget(window.log_view)

    window.log_history_table.setMinimumHeight(140)
    window.log_history_table.setMaximumHeight(220)
    window.log_history_table.setVisible(True)
    log_layout.addWidget(window.log_history_table)

    log_group.setLayout(log_layout)
    log_tab_layout.addWidget(log_group, 1)
    log_tab.setLayout(log_tab_layout)
    results_tabs.addTab(log_tab, "📜 Logs")

    # ==========================================================================
    # SUBTAB: INSPECTOR (MTS / Decisions / Shadow)
    # ==========================================================================
    inspector_tab = QWidget()
    inspector_layout = QVBoxLayout()
    inspector_layout.setSpacing(12)
    inspector_layout.setContentsMargins(12, 12, 12, 12)

    inspector_group = QGroupBox("🧪 Inspector Adaptativo")
    inspector_group_layout = QVBoxLayout()
    inspector_controls = QHBoxLayout()
    inspector_controls.addWidget(window.inspector_mts_path_edit, 1)
    inspector_controls.addWidget(window.inspector_mts_browse_btn)
    inspector_controls.addWidget(window.inspector_mts_load_btn)
    inspector_controls.addWidget(window.inspector_mts_from_history_btn)
    inspector_group_layout.addLayout(inspector_controls)
    inspector_group_layout.addWidget(window.inspector_text, 1)
    inspector_group.setLayout(inspector_group_layout)
    inspector_layout.addWidget(inspector_group, 1)
    inspector_tab.setLayout(inspector_layout)
    results_tabs.addTab(inspector_tab, "🧪 Inspector")

    # ==========================================================================
    # SUBTAB: DETALLES
    # ==========================================================================
    details_tab = QWidget()
    details_tab_layout = QVBoxLayout()
    details_tab_layout.setSpacing(12)
    details_tab_layout.setContentsMargins(12, 12, 12, 12)

    details_group = QGroupBox("🔍 Detalles del Análisis")
    details_group.setCheckable(True)
    details_group.setChecked(True)
    window.details_group = details_group

    details_group_layout = QVBoxLayout()
    window.results_text.setMinimumHeight(160)
    window.results_text.setMaximumHeight(240)
    details_group_layout.addWidget(window.results_text)
    window.analysis_summary_text.setMinimumHeight(120)
    window.analysis_summary_text.setMaximumHeight(220)
    details_group_layout.addWidget(window.analysis_summary_text)
    details_group.setLayout(details_group_layout)
    details_tab_layout.addWidget(details_group, 1)
    details_tab.setLayout(details_tab_layout)
    results_tabs.addTab(details_tab, "🔍 Detalles")

    # Mantener referencias para compatibilidad con el código existente
    window.results_tab_single_index = 0
    window.results_tab_eq_index = 0
    window.results_tab_spectrum_index = 1
    window.results_tab_batch_index = 2
    window.results_tab_log_index = 3
    window.results_tab_inspector_index = 4
    window.results_tab_analysis_summary_index = 5
    window.results_tab_batch_summary_index = -1

    window.tab_results = results_tabs
    return results_tabs


# ============================================================================
# TAB ABOUT - Simplificado
# ============================================================================
def build_about_tab_new(window) -> QWidget:
    """Tab About simplificado."""
    from config import is_premium, get_license_display_name, LICENSE_TYPE_PREMIUM, save_license_type
    
    tab = QWidget()
    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    
    if PYSIDE_AVAILABLE and LOGO_PATH:
        logo = QSvgWidget(LOGO_PATH)
        logo.setMaximumSize(100, 100)
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
    
    # Mostrar versión y tipo de licencia
    license_text = get_license_display_name()
    license_color = "#4CAF50" if is_premium() else "#FF9800"
    
    text = QLabel(
        f"<h2>{APP_NAME} {APP_VERSION}</h2>"
        f"<p style='color: {license_color}; font-weight: bold;'>{license_text}</p>"
        f"<p>By {APP_VENDOR}</p>"
        "<hr>"
        "<p><b>Créditos:</b><br>"
        "Martín Alejandro Oviedo + Ashriel<br>"
        "Asistencia técnica y refinamiento: Nico</p>"
        "<p><b>Contacto:</b><br>"
        "martinoviedo@disroot.org</p>"
        "<p><b>Licencia:</b><br>"
        "Software de pago (donation-ware disponible)</p>"
    )
    text.setTextFormat(Qt.TextFormat.RichText)
    text.setAlignment(Qt.AlignmentFlag.AlignCenter)
    text.setWordWrap(True)
    layout.addWidget(text)
    
    # Botón de actualización a Premium (solo en modo Free)
    if not is_premium():
        upgrade_info = QLabel(
            "<p style='background: #FFF3E0; padding: 12px; border-radius: 4px;'>"
            "<b>🎯 Actualiza a Premium para desbloquear:</b><br>"
            "• Auto-Master IA para archivos individuales y lotes<br>"
            "• Modo Solo Análisis para testing<br>"
            "• Generación de textos y prompts con IA<br>"
            "</p>"
        )
        upgrade_info.setTextFormat(Qt.TextFormat.RichText)
        upgrade_info.setWordWrap(True)
        layout.addWidget(upgrade_info)
        
        # Botón temporal de desarrollo para activar Premium
        dev_btn = QPushButton("🔓 Activar Premium (Dev)")
        def activate_premium():
            if save_license_type(LICENSE_TYPE_PREMIUM):
                QMessageBox.information(
                    window, 
                    "Premium Activado", 
                    "ToneFinish Premium ha sido activado.\\n\\nPor favor reinicia la aplicación para aplicar los cambios."
                )
        dev_btn.clicked.connect(activate_premium)
        layout.addWidget(dev_btn)
    
    layout.addStretch()
    tab.setLayout(layout)
    return tab


# ============================================================================
# TAB AUTO-MASTER + PREVIEW - Nueva tab unificada
# ============================================================================
def build_auto_master_preview_tab(window) -> QWidget:
    """
    Tab unificada de Auto-Master y Preview.
    
    Combina:
    - Selección de estilo Auto-Master
    - Análisis inteligente con notas
    - Controles de preview/reproducción A/B
    - Forma de onda comparativa (original vs procesado)
    """
    tab = QWidget()
    main_layout = QVBoxLayout()
    main_layout.setSpacing(12)
    main_layout.setContentsMargins(12, 12, 12, 12)
    
    # ========== SECCIÓN SUPERIOR: Auto-Master ==========
    auto_group = QGroupBox("🎯 Auto-Master")
    auto_layout = QVBoxLayout()
    auto_layout.setSpacing(8)
    
    # Fila de estilo y opciones
    style_row = QHBoxLayout()
    style_row.addWidget(QLabel("Estilo:"))
    style_row.addWidget(window.auto_master_style_combo_tab, 1)
    auto_layout.addLayout(style_row)
    
    # Checkboxes
    cb_row = QHBoxLayout()
    cb_row.addWidget(window.auto_master_intelligent_cb)
    cb_row.addWidget(window.auto_master_ai_assist_cb_tab)
    cb_row.addWidget(window.auto_master_enable_process_cb)
    cb_row.addStretch()
    auto_layout.addLayout(cb_row)

    auto_layout.addWidget(window.auto_master_profile_label)

    thresholds_form = QFormLayout()
    thresholds_form.addRow("LRA mínimo:", window.auto_master_min_lra_spin)
    thresholds_form.addRow("Crest mínimo:", window.auto_master_min_crest_spin)
    thresholds_form.addRow("Preset movimiento:", window.auto_master_motion_preset_combo)
    thresholds_form.addRow("Perfil movimiento:", window.auto_master_motion_profile_combo)
    thresholds_form.addRow("Cantidad movimiento:", window.auto_master_motion_amount_spin)
    auto_layout.addLayout(thresholds_form)
    
    # Botones de acción
    action_row = QHBoxLayout()
    action_row.addWidget(window.auto_master_apply_btn)
    action_row.addStretch()
    auto_layout.addLayout(action_row)
    
    auto_group.setLayout(auto_layout)
    main_layout.addWidget(auto_group)
    
    # ========== SECCIÓN CENTRAL: Notas del Análisis ==========
    notes_group = QGroupBox("📋 Análisis y Sugerencias")
    notes_layout = QVBoxLayout()
    window.auto_master_notes.setMinimumHeight(100)
    window.auto_master_notes.setMaximumHeight(150)
    notes_layout.addWidget(window.auto_master_notes)
    notes_group.setLayout(notes_layout)
    main_layout.addWidget(notes_group)
    
    # ========== SECCIÓN DE PREVIEW ==========
    preview_group = QGroupBox("🎧 Preview y Comparación A/B")
    preview_layout = QVBoxLayout()
    preview_layout.setSpacing(8)
    
    # Botones de reproducción
    play_row = QHBoxLayout()
    play_row.addWidget(window.preview_btn)
    play_row.addWidget(window.play_original_btn)
    play_row.addWidget(window.play_processed_btn)
    play_row.addWidget(window.stop_preview_btn)
    play_row.addStretch()
    preview_layout.addLayout(play_row)
    
    # Barra de progreso de reproducción (si existe)
    if hasattr(window, 'preview_progress_bar'):
        preview_layout.addWidget(window.preview_progress_bar)
    
    # Forma de onda comparativa
    if PYQTGRAPH_AVAILABLE:
        wave_label = QLabel("〰️ Forma de Onda Comparativa:")
        wave_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        preview_layout.addWidget(wave_label)
        
        # Crear nuevo plot para comparación si no existe
        if not hasattr(window, 'preview_waveform_plot') or window.preview_waveform_plot is None:
            window.preview_waveform_plot = pg.PlotWidget()
            window.preview_waveform_plot.setMinimumHeight(180)
            window.preview_waveform_plot.showGrid(x=True, y=True, alpha=0.25)
            window.preview_waveform_plot.setLabel("bottom", "Tiempo", units="s")
            window.preview_waveform_plot.setLabel("left", "Amplitud")
            window.preview_waveform_plot.setYRange(-1.05, 1.05)
            # Curva original (gris)
            window.preview_waveform_original = window.preview_waveform_plot.plot(
                [], [], pen=pg.mkPen(color=(100, 100, 100, 150), width=1), name="Original"
            )
            # Curva procesada (verde)
            window.preview_waveform_processed = window.preview_waveform_plot.plot(
                [], [], pen=pg.mkPen(color=(80, 200, 120, 200), width=1), name="Procesado"
            )
            # Leyenda
            window.preview_waveform_plot.addLegend()
        
        preview_layout.addWidget(window.preview_waveform_plot, 1)
        
        # Info de comparación
        if not hasattr(window, 'preview_info_label'):
            window.preview_info_label = QLabel("Selecciona un audio y genera un preview para comparar.")
            window.preview_info_label.setStyleSheet("color: #fff; font-style: italic;")
        preview_layout.addWidget(window.preview_info_label)
    
    preview_group.setLayout(preview_layout)
    main_layout.addWidget(preview_group, 1)
    
    # ========== SECCIÓN INFERIOR: Acciones ==========
    actions_row = QHBoxLayout()
    
    # Botón de procesar (referencia al existente)
    if hasattr(window, 'process_btn'):
        actions_row.addWidget(window.process_btn)
    
    actions_row.addStretch()
    main_layout.addLayout(actions_row)
    
    tab.setLayout(main_layout)
    window.tab_auto_master_preview = tab
    return tab


# ============================================================================
# TAB DIAGNÓSTICO - Análisis antes/después del procesamiento
# ============================================================================
def build_diagnostic_tab(window) -> QWidget:
    """
    Tab de Auto-Diagnóstico para evaluar el desempeño del procesamiento.
    
    Compara métricas de audio antes y después del procesamiento
    para detectar problemas y sugerir mejoras.
    """
    from ui.qt_compat import (
        QPlainTextEdit, QPushButton, QCheckBox, QLabel, 
        QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
        QTableWidgetItem, QHeaderView, QApplication, QProgressBar
    )
    
    tab = QWidget()
    main_layout = QVBoxLayout()
    main_layout.setSpacing(12)
    main_layout.setContentsMargins(16, 16, 16, 16)
    
    # === Título y descripción ===
    title = QLabel("🔬 Auto-Diagnóstico")
    title.setStyleSheet("font-size: 18px; font-weight: bold;")
    main_layout.addWidget(title)
    
    desc = QLabel(
        "Analiza un audio antes y después del procesamiento para evaluar "
        "el desempeño de la aplicación y detectar posibles mejoras."
    )
    desc.setWordWrap(True)
    desc.setStyleSheet("color: #fff; margin-bottom: 8px;")
    main_layout.addWidget(desc)
    
    # === Barra de progreso ===
    progress_layout = QHBoxLayout()
    
    if getattr(window, 'diagnostic_progress_bar', None) is None:
        window.diagnostic_progress_bar = QProgressBar()
        window.diagnostic_progress_bar.setRange(0, 100)
        window.diagnostic_progress_bar.setValue(0)
        window.diagnostic_progress_bar.setTextVisible(True)
        window.diagnostic_progress_bar.setFormat("%p% - %v de 100")
        window.diagnostic_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
    
    if getattr(window, 'diagnostic_progress_label', None) is None:
        window.diagnostic_progress_label = QLabel("Listo")
        window.diagnostic_progress_label.setStyleSheet("color: #fff; font-size: 11px;")
    
    progress_layout.addWidget(window.diagnostic_progress_bar, 1)
    progress_layout.addWidget(window.diagnostic_progress_label)
    main_layout.addLayout(progress_layout)
    
    # === Controles superiores ===
    controls_layout = QHBoxLayout()
    
    # Botón ejecutar diagnóstico
    if getattr(window, 'diagnostic_run_btn', None) is None:
        window.diagnostic_run_btn = QPushButton("▶ Ejecutar Diagnóstico")
        window.diagnostic_run_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #888; }"
        )
    controls_layout.addWidget(window.diagnostic_run_btn)

    if getattr(window, 'diagnostic_benchmark_btn', None) is None:
        window.diagnostic_benchmark_btn = QPushButton("⚙ Benchmark Espectro")
        window.diagnostic_benchmark_btn.setToolTip("Mide CPU vs GPU para el análisis espectral del archivo seleccionado.")
        window.diagnostic_benchmark_btn.setStyleSheet(
            "QPushButton { background-color: #5a67d8; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4c57c0; }"
            "QPushButton:disabled { background-color: #888; }"
        )
    controls_layout.addWidget(window.diagnostic_benchmark_btn)
    
    # Checkbox para formato Markdown
    if getattr(window, 'diagnostic_markdown_cb', None) is None:
        window.diagnostic_markdown_cb = QCheckBox("Formato Markdown")
        window.diagnostic_markdown_cb.setToolTip("Usar formato Markdown al copiar (ideal para GitHub, etc.)")
    controls_layout.addWidget(window.diagnostic_markdown_cb)
    
    controls_layout.addStretch()
    
    # Botón copiar al portapapeles
    if getattr(window, 'diagnostic_copy_btn', None) is None:
        window.diagnostic_copy_btn = QPushButton("📋 Copiar al Portapapeles")
        window.diagnostic_copy_btn.setEnabled(False)
    controls_layout.addWidget(window.diagnostic_copy_btn)
    
    main_layout.addLayout(controls_layout)
    
    # === Tabla de métricas generales ===
    metrics_group = QGroupBox("📊 Métricas Generales")
    metrics_layout = QVBoxLayout()
    
    if getattr(window, 'diagnostic_metrics_table', None) is None:
        window.diagnostic_metrics_table = QTableWidget()
        window.diagnostic_metrics_table.setColumnCount(4)
        window.diagnostic_metrics_table.setHorizontalHeaderLabels(["Métrica", "Entrada", "Salida", "Diferencia"])
        window.diagnostic_metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        window.diagnostic_metrics_table.setAlternatingRowColors(True)
        window.diagnostic_metrics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        window.diagnostic_metrics_table.setMinimumHeight(180)
    
    metrics_layout.addWidget(window.diagnostic_metrics_table)
    metrics_group.setLayout(metrics_layout)
    main_layout.addWidget(metrics_group)
    
    # === Tabla de análisis por bandas ===
    bands_group = QGroupBox("🎚️ Análisis por Bandas (RMS)")
    bands_layout = QVBoxLayout()
    
    if getattr(window, 'diagnostic_bands_table', None) is None:
        window.diagnostic_bands_table = QTableWidget()
        window.diagnostic_bands_table.setColumnCount(4)
        window.diagnostic_bands_table.setHorizontalHeaderLabels(["Banda", "RMS Entrada (dB)", "RMS Salida (dB)", "Δ (dB)"])
        window.diagnostic_bands_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        window.diagnostic_bands_table.setAlternatingRowColors(True)
        window.diagnostic_bands_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        window.diagnostic_bands_table.setMinimumHeight(160)
    
    bands_layout.addWidget(window.diagnostic_bands_table)
    bands_group.setLayout(bands_layout)
    main_layout.addWidget(bands_group)
    
    # === Evaluación (successes, warnings, errors) ===
    eval_group = QGroupBox("✅ Evaluación")
    eval_layout = QVBoxLayout()
    
    if getattr(window, 'diagnostic_eval_text', None) is None:
        window.diagnostic_eval_text = QPlainTextEdit()
        window.diagnostic_eval_text.setReadOnly(True)
        window.diagnostic_eval_text.setMaximumHeight(120)
        window.diagnostic_eval_text.setStyleSheet("font-family: monospace;")
    
    eval_layout.addWidget(window.diagnostic_eval_text)
    eval_group.setLayout(eval_layout)
    main_layout.addWidget(eval_group)
    
    # === Reporte completo (para copiar) ===
    report_group = QGroupBox("📄 Reporte Completo")
    report_layout = QVBoxLayout()
    
    if getattr(window, 'diagnostic_report_text', None) is None:
        window.diagnostic_report_text = QPlainTextEdit()
        window.diagnostic_report_text.setReadOnly(True)
        window.diagnostic_report_text.setStyleSheet("font-family: monospace; font-size: 11px;")
        window.diagnostic_report_text.setMinimumHeight(200)
    
    report_layout.addWidget(window.diagnostic_report_text)
    report_group.setLayout(report_layout)
    main_layout.addWidget(report_group, 1)  # Stretch
    
    # === Estado ===
    if getattr(window, 'diagnostic_status_label', None) is None:
        window.diagnostic_status_label = QLabel("Listo. Procesa un audio primero y luego ejecuta el diagnóstico.")
        window.diagnostic_status_label.setStyleSheet("color: #fff; font-style: italic;")
    main_layout.addWidget(window.diagnostic_status_label)
    
    tab.setLayout(main_layout)
    window.tab_diagnostic = tab
    return tab
