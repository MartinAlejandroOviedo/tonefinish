#!/usr/bin/env python3
"""
Demo del sistema inteligente de Auto-Master.

Este script simula el análisis y muestra cómo el sistema adapta
los presets según las características del audio.
"""

from auto_master_intelligence import (
    AudioCharacteristics,
    adapt_preset_to_audio,
)


def demo_vocal_track():
    """Simula una pista con vocales prominentes."""
    print("=" * 70)
    print("CASO 1: Pista con Vocales Prominentes")
    print("=" * 70)
    
    # Simular características de una pista vocal
    band_stats = {
        "Subbass (20-60 Hz)": -25.0,
        "Bass (60-250 Hz)": -18.0,
        "Low-Mid (250-500 Hz)": -14.0,
        "Mid (500-2k Hz)": -12.0,
        "High-Mid (2k-6k Hz)": -8.5,   # Vocales fuertes
        "Air (6k-16k Hz)": -15.0,
    }
    voice_rms = -10.5  # Vocales prominentes
    
    characteristics = AudioCharacteristics(band_stats, voice_rms)
    
    print(f"\n📊 Análisis:")
    print(f"  Vocales: {'✓ Sí' if characteristics.has_vocals else '✗ No'}")
    print(f"  Bajos fuertes: {'✓ Sí' if characteristics.has_strong_bass else '✗ No'}")
    print(f"  Agudos fuertes: {'✓ Sí' if characteristics.has_strong_highs else '✗ No'}")
    print(f"  Dinámico: {'✓ Sí' if characteristics.is_dynamic else '✗ No'}")
    print(f"  Riesgo sibilancia: {'⚠ Sí' if characteristics.needs_deess else '✓ No'}")
    print(f"  Balance espectral: {characteristics.balance_score:.0f}/100")
    
    # Probar diferentes presets
    presets = ["Cinta (Jazz, Alternativa, Indie)", "Natural (Acústico, Jazz, Folk)", "Universal (Rock, Pop, Electrónica)"]
    
    for preset_name in presets:
        print(f"\n{'─' * 70}")
        print(f"Preset: {preset_name}")
        print(f"{'─' * 70}")
        
        adjustments = adapt_preset_to_audio(preset_name, characteristics)
        
        print(f"\nMultiplicadores:")
        print(f"  De-esser: {adjustments['deesser_intensity_mult']:.2f}x")
        print(f"  Saturación Drive: {adjustments['saturation_drive_mult']:.2f}x")
        print(f"  Saturación Mix: {adjustments['saturation_mix_mult']:.2f}x")
        print(f"  Glue Threshold: {adjustments['glue_threshold_offset']:+.1f} dB")
        print(f"  Glue Ratio: {adjustments['glue_ratio_mult']:.2f}x")
        
        print(f"\nNotas de Configuración:")
        for note in adjustments['notes']:
            print(f"  {note}")
    
    print("\n" + "=" * 70 + "\n")


def demo_edm_track():
    """Simula una pista EDM con bajos y agudos fuertes."""
    print("=" * 70)
    print("CASO 2: Pista EDM (Bajos y Agudos Fuertes)")
    print("=" * 70)
    
    # Simular características de EDM
    band_stats = {
        "Subbass (20-60 Hz)": -8.0,    # Muy fuerte
        "Bass (60-250 Hz)": -10.0,     # Muy fuerte
        "Low-Mid (250-500 Hz)": -18.0,
        "Mid (500-2k Hz)": -20.0,
        "High-Mid (2k-6k Hz)": -9.0,   # Fuerte
        "Air (6k-16k Hz)": -7.5,       # Muy fuerte (hi-hats)
    }
    voice_rms = -30.0  # Sin vocales
    
    characteristics = AudioCharacteristics(band_stats, voice_rms)
    
    print(f"\n📊 Análisis:")
    print(f"  Vocales: {'✓ Sí' if characteristics.has_vocals else '✗ No'}")
    print(f"  Bajos fuertes: {'✓ Sí' if characteristics.has_strong_bass else '✗ No'}")
    print(f"  Agudos fuertes: {'✓ Sí' if characteristics.has_strong_highs else '✗ No'}")
    print(f"  Dinámico: {'✓ Sí' if characteristics.is_dynamic else '✗ No'}")
    print(f"  Riesgo sibilancia: {'⚠ Sí' if characteristics.needs_deess else '✓ No'}")
    print(f"  Balance espectral: {characteristics.balance_score:.0f}/100")
    
    # Presets apropiados para EDM
    presets = ["Empuje (EDM, Dubstep, Bass Music)", "Fuego (Trap, Reguetón, Hip-Hop)"]
    
    for preset_name in presets:
        print(f"\n{'─' * 70}")
        print(f"Preset: {preset_name}")
        print(f"{'─' * 70}")
        
        adjustments = adapt_preset_to_audio(preset_name, characteristics)
        
        print(f"\nMultiplicadores:")
        print(f"  De-esser: {adjustments['deesser_intensity_mult']:.2f}x")
        print(f"  Saturación Drive: {adjustments['saturation_drive_mult']:.2f}x")
        print(f"  Saturación Mix: {adjustments['saturation_mix_mult']:.2f}x")
        
        if adjustments['band_saturation_adjustments']:
            print(f"\nAjustes por Banda:")
            for band, adj in adjustments['band_saturation_adjustments'].items():
                print(f"  {band}:")
                print(f"    Drive: {adj['drive_mult']:.2f}x")
                print(f"    Mix: {adj['mix_mult']:.2f}x")
        
        if adjustments.get('warnings'):
            print(f"\n⚠️  Advertencias:")
            for warning in adjustments['warnings']:
                print(f"  {warning}")
        
        if adjustments.get('suggestions'):
            print(f"\n💡 Sugerencias:")
            for suggestion in adjustments['suggestions']:
                print(f"  {suggestion}")
        
        print(f"\nNotas de Configuración:")
        for note in adjustments['notes']:
            print(f"  {note}")
    
    print("\n" + "=" * 70 + "\n")


def demo_balanced_track():
    """Simula una pista bien balanceada (jazz, acústico)."""
    print("=" * 70)
    print("CASO 3: Pista Balanceada (Jazz/Acústico)")
    print("=" * 70)
    
    # Simular características balanceadas
    band_stats = {
        "Subbass (20-60 Hz)": -22.0,
        "Bass (60-250 Hz)": -16.0,
        "Low-Mid (250-500 Hz)": -14.0,
        "Mid (500-2k Hz)": -13.0,
        "High-Mid (2k-6k Hz)": -14.5,
        "Air (6k-16k Hz)": -17.0,
    }
    voice_rms = -15.0  # Vocales moderadas
    
    characteristics = AudioCharacteristics(band_stats, voice_rms)
    
    print(f"\n📊 Análisis:")
    print(f"  Vocales: {'✓ Sí' if characteristics.has_vocals else '✗ No'}")
    print(f"  Bajos fuertes: {'✓ Sí' if characteristics.has_strong_bass else '✗ No'}")
    print(f"  Agudos fuertes: {'✓ Sí' if characteristics.has_strong_highs else '✗ No'}")
    print(f"  Dinámico: {'✓ Sí' if characteristics.is_dynamic else '✗ No'}")
    print(f"  Riesgo sibilancia: {'⚠ Sí' if characteristics.needs_deess else '✓ No'}")
    print(f"  Balance espectral: {characteristics.balance_score:.0f}/100")
    
    # Presets apropiados para acústico
    presets = ["Claridad (Clásica, R&B, Cantautor)", "Natural (Acústico, Jazz, Folk)", "Cinemático (Orquestal, Soundtrack)"]
    
    for preset_name in presets:
        print(f"\n{'─' * 70}")
        print(f"Preset: {preset_name}")
        print(f"{'─' * 70}")
        
        adjustments = adapt_preset_to_audio(preset_name, characteristics)
        
        print(f"\nMultiplicadores:")
        print(f"  De-esser: {adjustments['deesser_intensity_mult']:.2f}x")
        print(f"  Saturación Drive: {adjustments['saturation_drive_mult']:.2f}x")
        print(f"  Saturación Mix: {adjustments['saturation_mix_mult']:.2f}x")
        print(f"  Glue Threshold: {adjustments['glue_threshold_offset']:+.1f} dB")
        print(f"  Glue Ratio: {adjustments['glue_ratio_mult']:.2f}x")
        
        print(f"\nNotas de Configuración:")
        for note in adjustments['notes']:
            print(f"  {note}")
    
    print("\n" + "=" * 70 + "\n")


def demo_incompatible_preset():
    """Simula el caso del usuario: preset Club con audio sin bajos y desbalanceado."""
    print("=" * 70)
    print("CASO 4: Incompatibilidad Preset-Contenido (Caso Real)")
    print("=" * 70)
    
    # Simular el caso del usuario: preset Club con audio desbalanceado
    band_stats = {
        "Subbass (20-60 Hz)": -30.0,   # Muy débil (falta)
        "Bass (60-250 Hz)": -22.0,     # Débil (falta)
        "Low-Mid (250-500 Hz)": -20.0, # Débil (falta)
        "Mid (500-2k Hz)": -8.0,       # Muy fuerte (exceso)
        "High-Mid (2k-6k Hz)": -7.5,   # Muy fuerte (exceso)
        "Air (6k-16k Hz)": -9.0,       # Fuerte (exceso)
    }
    voice_rms = -30.0  # Sin vocales prominentes
    
    characteristics = AudioCharacteristics(band_stats, voice_rms)
    
    print(f"\n📊 Análisis del Audio:")
    print(f"  Vocales: {'✓ Sí' if characteristics.has_vocals else '✗ No'}")
    print(f"  Bajos fuertes: {'✓ Sí' if characteristics.has_strong_bass else '✗ No'}")
    print(f"  Agudos fuertes: {'✓ Sí' if characteristics.has_strong_highs else '✗ No'}")
    print(f"  Dinámico: {'✓ Sí' if characteristics.is_dynamic else '✗ No'}")
    print(f"  Balance espectral: {characteristics.balance_score:.0f}/100")
    
    print(f"\n🎛️  Niveles por Banda:")
    for band, level in band_stats.items():
        status = "❌ FALTA" if level < -20 else "⚠️ EXCESO" if level > -12 else "✓"
        print(f"  {band}: {level:.1f} dB {status}")
    
    preset_name = "Fuego (Trap, Reguetón, Hip-Hop)"
    print(f"\n{'─' * 70}")
    print(f"Preset Seleccionado: {preset_name}")
    print(f"{'─' * 70}")
    
    adjustments = adapt_preset_to_audio(preset_name, characteristics)
    
    # Mostrar ADVERTENCIAS primero
    if adjustments.get('warnings'):
        print(f"\n🚨 === ADVERTENCIAS DEL SISTEMA ===")
        for warning in adjustments['warnings']:
            print(f"  {warning}")
    
    # Mostrar PRESETS ALTERNATIVOS
    if adjustments.get('alternative_presets'):
        print(f"\n💡 === PRESETS ALTERNATIVOS SUGERIDOS ===")
        for alt_preset in adjustments['alternative_presets']:
            print(f"  ✓ {alt_preset}")
    
    # Mostrar SUGERENCIAS DE EQ
    if adjustments.get('suggestions'):
        print(f"\n🎛️  === SUGERENCIAS DE CORRECCIÓN ===")
        for suggestion in adjustments['suggestions']:
            print(f"  {suggestion}")
    
    # Mostrar ajustes de EQ específicos
    if adjustments.get('eq_adjustments'):
        print(f"\n📊 === AJUSTES DE EQ CALCULADOS ===")
        for band, adjustment in adjustments['eq_adjustments'].items():
            sign = "+" if adjustment > 0 else ""
            print(f"  {band}: {sign}{adjustment:.1f} dB")
    
    print(f"\n⚙️  === MULTIPLICADORES APLICADOS ===")
    print(f"  De-esser: {adjustments['deesser_intensity_mult']:.2f}x")
    print(f"  Saturación Drive: {adjustments['saturation_drive_mult']:.2f}x")
    print(f"  Saturación Mix: {adjustments['saturation_mix_mult']:.2f}x")
    print(f"  Glue Threshold: {adjustments['glue_threshold_offset']:+.1f} dB")
    
    print(f"\n📝 === NOTAS ADICIONALES ===")
    for note in adjustments['notes']:
        print(f"  {note}")
    
    print("\n" + "=" * 70)
    print("CONCLUSIÓN:")
    print("=" * 70)
    print("""
El sistema detectó que el preset "Fuego" NO es compatible con este audio:
  • Requiere bajos fuertes, pero el audio tiene bajos débiles
  • Balance espectral crítico (15/100)
  • Exceso en medios y agudos, falta en graves

RECOMENDACIONES:
  1. Usar uno de los presets alternativos sugeridos
  2. Aplicar EQ correctivo antes de masterizar
  3. Considerar remezcla si es posible
    """)
    print("=" * 70 + "\n")


def main():
    """Ejecuta todas las demos."""
    print("\n" + "=" * 70)
    print(" TONEFINISH - SISTEMA INTELIGENTE DE AUTO-MASTER")
    print(" Demostración de Adaptación Automática de Presets")
    print("=" * 70 + "\n")
    
    demo_vocal_track()
    demo_edm_track()
    demo_balanced_track()
    demo_incompatible_preset()  # Nuevo caso
    
    print("=" * 70)
    print("RESUMEN DEL SISTEMA INTELIGENTE")
    print("=" * 70)
    print("""
El sistema analiza:
  ✓ Presencia de vocales (banda 300-3kHz)
  ✓ Nivel de bajos (20-250 Hz)
  ✓ Nivel de agudos (2k-16kHz)
  ✓ Rango dinámico
  ✓ Riesgo de sibilancia
  ✓ Balance espectral

Y adapta automáticamente:
  🎚️ Intensidad del de-esser
  🔊 Drive y mix de saturación
  🎛️ Threshold y ratio de compresión glue
  🔒 Protección en bandas sensibles
  ⚖️ EQ dinámico según necesidad

Ventajas:
  • Los presets se adaptan al contenido del audio
  • Protección automática contra saturación
  • Configuración óptima sin intervención manual
  • Advertencias sobre incompatibilidades
    """)
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
