#!/usr/bin/env python3
"""
Script de ejemplo para probar el nuevo control de saturación en bandas sensibles.

Este script demuestra cómo usar las nuevas funcionalidades de ToneFinish
para controlar la saturación en bandas vocales y de metales.
"""

import pathlib
from audio_analysis import analyze_eq_bands, validate_saturation_settings
from audio_processing import normalize_audio, build_preprocess_chain
from config import BAND_CONFIG, BAND_HEADROOM_DB, MAX_SATURATION_DRIVE_DB

def example_vocal_processing():
    """Ejemplo de procesamiento para pista con vocales prominentes."""
    print("=" * 70)
    print("EJEMPLO 1: Procesamiento de Vocales con Control de Saturación")
    print("=" * 70)
    
    # Configuración para vocales
    saturation_band_drive_db = {
        "High-Mid (2k-6k Hz)": 8.0,   # Presencia vocal moderada
        "Air (6k-16k Hz)": 4.0,        # Brillo suave
    }
    
    saturation_band_mix = {
        "High-Mid (2k-6k Hz)": 0.4,   # 40% de saturación
        "Air (6k-16k Hz)": 0.3,        # 30% de saturación
    }
    
    # Simular estadísticas de análisis
    band_stats = {
        "High-Mid (2k-6k Hz)": -10.5,  # RMS típico para vocales
        "Air (6k-16k Hz)": -18.2,      # RMS típico para brillo
    }
    
    # Validar configuración
    warnings = validate_saturation_settings(
        band_stats=band_stats,
        saturation_band_drive_db=saturation_band_drive_db,
        saturation_band_mix=saturation_band_mix,
    )
    
    print("\n📊 Configuración de Saturación:")
    print(f"  High-Mid Drive: {saturation_band_drive_db['High-Mid (2k-6k Hz)']} dB")
    print(f"  High-Mid Mix: {saturation_band_mix['High-Mid (2k-6k Hz)'] * 100}%")
    print(f"  Air Drive: {saturation_band_drive_db['Air (6k-16k Hz)']} dB")
    print(f"  Air Mix: {saturation_band_mix['Air (6k-16k Hz)'] * 100}%")
    
    print("\n🔒 Protecciones Aplicadas:")
    print(f"  High-Mid Headroom: {BAND_HEADROOM_DB['High-Mid (2k-6k Hz)']} dB")
    print(f"  Air Headroom: {BAND_HEADROOM_DB['Air (6k-16k Hz)']} dB")
    print(f"  High-Mid Max Drive: {MAX_SATURATION_DRIVE_DB['High-Mid (2k-6k Hz)']} dB")
    print(f"  Air Max Drive: {MAX_SATURATION_DRIVE_DB['Air (6k-16k Hz)']} dB")
    
    if warnings:
        print("\n⚠️  Advertencias del Sistema:")
        for warning in warnings:
            print(f"  {warning}")
    else:
        print("\n✅ Configuración segura - sin advertencias")
    
    print("\n" + "=" * 70 + "\n")


def example_hihats_processing():
    """Ejemplo de procesamiento para pista con hi-hats prominentes."""
    print("=" * 70)
    print("EJEMPLO 2: Procesamiento de Hi-Hats con Control de Saturación")
    print("=" * 70)
    
    # Configuración para hi-hats/metales
    saturation_band_drive_db = {
        "High-Mid (2k-6k Hz)": 3.0,   # Mínimo para no afectar ataques
        "Air (6k-16k Hz)": 6.0,        # Cuerpo a los metales
    }
    
    saturation_band_mix = {
        "High-Mid (2k-6k Hz)": 0.2,   # 20% de saturación
        "Air (6k-16k Hz)": 0.45,       # 45% de saturación
    }
    
    # Simular estadísticas de análisis
    band_stats = {
        "High-Mid (2k-6k Hz)": -15.8,  # Moderado
        "Air (6k-16k Hz)": -8.5,       # Fuerte (hi-hats)
    }
    
    # Validar configuración
    warnings = validate_saturation_settings(
        band_stats=band_stats,
        saturation_band_drive_db=saturation_band_drive_db,
        saturation_band_mix=saturation_band_mix,
    )
    
    print("\n📊 Configuración de Saturación:")
    print(f"  High-Mid Drive: {saturation_band_drive_db['High-Mid (2k-6k Hz)']} dB")
    print(f"  High-Mid Mix: {saturation_band_mix['High-Mid (2k-6k Hz)'] * 100}%")
    print(f"  Air Drive: {saturation_band_drive_db['Air (6k-16k Hz)']} dB")
    print(f"  Air Mix: {saturation_band_mix['Air (6k-16k Hz)'] * 100}%")
    
    print("\n📈 Análisis de Bandas:")
    print(f"  High-Mid RMS: {band_stats['High-Mid (2k-6k Hz)']} dB")
    print(f"  Air RMS: {band_stats['Air (6k-16k Hz)']} dB")
    
    if warnings:
        print("\n⚠️  Advertencias del Sistema:")
        for warning in warnings:
            print(f"  {warning}")
    else:
        print("\n✅ Configuración segura - sin advertencias")
    
    print("\n" + "=" * 70 + "\n")


def example_extreme_settings():
    """Ejemplo de configuración extrema que genera advertencias."""
    print("=" * 70)
    print("EJEMPLO 3: Configuración Extrema (Genera Advertencias)")
    print("=" * 70)
    
    # Configuración extrema - NO RECOMENDADA
    saturation_band_drive_db = {
        "High-Mid (2k-6k Hz)": 18.0,  # EXCEDE límite de 12 dB
        "Air (6k-16k Hz)": 12.0,       # EXCEDE límite de 8 dB
    }
    
    saturation_band_mix = {
        "High-Mid (2k-6k Hz)": 0.85,  # 85% - muy alto
        "Air (6k-16k Hz)": 0.9,        # 90% - muy alto
    }
    
    # Simular estadísticas de análisis con nivel alto
    band_stats = {
        "High-Mid (2k-6k Hz)": -5.0,   # RMS muy alto
        "Air (6k-16k Hz)": -4.5,       # RMS muy alto
    }
    
    # Validar configuración
    warnings = validate_saturation_settings(
        band_stats=band_stats,
        saturation_band_drive_db=saturation_band_drive_db,
        saturation_band_mix=saturation_band_mix,
    )
    
    print("\n📊 Configuración de Saturación:")
    print(f"  High-Mid Drive: {saturation_band_drive_db['High-Mid (2k-6k Hz)']} dB ❌ EXCEDE LÍMITE")
    print(f"  High-Mid Mix: {saturation_band_mix['High-Mid (2k-6k Hz)'] * 100}% ❌ MUY ALTO")
    print(f"  Air Drive: {saturation_band_drive_db['Air (6k-16k Hz)']} dB ❌ EXCEDE LÍMITE")
    print(f"  Air Mix: {saturation_band_mix['Air (6k-16k Hz)'] * 100}% ❌ MUY ALTO")
    
    print("\n🚨 SISTEMA DE PROTECCIÓN ACTIVADO:")
    print(f"  High-Mid Drive limitado a: {MAX_SATURATION_DRIVE_DB['High-Mid (2k-6k Hz)']} dB")
    print(f"  Air Drive limitado a: {MAX_SATURATION_DRIVE_DB['Air (6k-16k Hz)']} dB")
    print(f"  Headroom aplicado automáticamente")
    
    if warnings:
        print("\n⚠️  Advertencias del Sistema:")
        for warning in warnings:
            print(f"  {warning}")
    
    print("\n" + "=" * 70 + "\n")


def show_band_configuration():
    """Muestra la configuración de bandas del sistema."""
    print("=" * 70)
    print("CONFIGURACIÓN DE BANDAS DE FRECUENCIA")
    print("=" * 70)
    
    print("\n📻 Bandas Configuradas:")
    for idx, (label, low_hz, high_hz, attack, release, width) in enumerate(BAND_CONFIG):
        sensitive = "⚠️  SENSIBLE" if idx in [4, 5] else ""
        print(f"\n  {idx + 1}. {label} {sensitive}")
        print(f"     Rango: {low_hz} - {high_hz} Hz")
        print(f"     Attack: {attack*1000:.1f} ms")
        print(f"     Release: {release*1000:.0f} ms")
        print(f"     Stereo Width: {width}")
        
        if label in BAND_HEADROOM_DB:
            print(f"     🔒 Headroom: {BAND_HEADROOM_DB[label]} dB")
        if label in MAX_SATURATION_DRIVE_DB:
            print(f"     🔒 Max Drive: {MAX_SATURATION_DRIVE_DB[label]} dB")
    
    print("\n" + "=" * 70 + "\n")


def main():
    """Ejecuta todos los ejemplos."""
    print("\n" + "=" * 70)
    print(" TONEFINISH - CONTROL DE SATURACIÓN EN BANDAS SENSIBLES")
    print(" Ejemplos de Uso y Configuración")
    print("=" * 70 + "\n")
    
    show_band_configuration()
    example_vocal_processing()
    example_hihats_processing()
    example_extreme_settings()
    
    print("=" * 70)
    print("RESUMEN DE MEJORAS")
    print("=" * 70)
    print("""
✅ Limitadores soft-knee en bandas sensibles
✅ Control de drive máximo por banda
✅ Headroom automático para prevenir clipping
✅ Validación con advertencias inteligentes
✅ Detección de picos en análisis de bandas
✅ Configuración retrocompatible

📚 Ver docs/SATURATION_CONTROL.md para más información
    """)
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
