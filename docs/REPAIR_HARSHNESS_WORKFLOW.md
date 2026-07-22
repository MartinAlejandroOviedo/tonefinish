# Reparación de Material "Roto" en Media / Media-Aguda

## Objetivo
Estabilizar material percibido como "roto" o "áspero" en medios y medios-agudos, priorizando conservar musicalidad y evitando sobreproceso.

## Diagnóstico Rápido
1. Verificar clipping digital duro:
   - `ffmpeg -i "<audio>.wav" -af astats=metadata=1:reset=0 -f null -`
   - Revisar `Peak level dB` y si hay evidencia de muestras recortadas.
2. Revisar eventos espectrales:
   - MTS (`*.mts.json`) y `harshness_risk` por tiempo.
   - `master_decisions` para confirmar mitigaciones en `high_mid`/`air` y de-esser.
3. Conclusión técnica:
   - Si no hay clipping duro y sí hay `harshness_risk`, tratar como dureza espectral impresa.

## Cadena Recomendada (Conservadora)
Referencia de procesamiento:
- `adeclip` suave (si aplica)
- EQ dinámica en ~3 kHz y ~5.4-5.8 kHz
- `deesser` moderado
- `alimiter` suave con `level=0` (sin autolevel)

Ejemplo base:
```bash
ffmpeg -y -i "in.wav" -af "adeclip=w=55:o=75:a=8:t=7,\
adynamicequalizer=threshold=5:dfrequency=3050:dqfactor=1.1:tfrequency=3050:tqfactor=1.05:attack=6:release=155:ratio=3.5:range=7:mode=cutabove:auto=adaptive,\
adynamicequalizer=threshold=4.5:dfrequency=5400:dqfactor=1.0:tfrequency=5400:tqfactor=1.0:attack=5:release=125:ratio=2.9:range=6:mode=cutabove:auto=adaptive,\
deesser=i=0.42:m=0.6:f=0.565,\
alimiter=limit=0.79:attack=4.5:release=45:asc=1:asc_level=0.55:level=0" \
-c:a pcm_s24le "out_repaired.wav"
```

## Ajuste de Nivel Final
Si se busca un RMS concreto (ej: ~`-13.38 dB`):
1. Medir salida:
   - `ffmpeg -i "out_repaired.wav" -af astats=metadata=1:reset=0 -f null -`
2. Aplicar trim simple:
   - `ffmpeg -y -i "out_repaired.wav" -af "volume=-0.53dB" -c:a pcm_s24le "out_repaired_trim.wav"`

## Criterios de Aceptación
- RMS objetivo alcanzado (+/- 0.1 dB).
- True Peak con margen de seguridad (recomendado <= `-2.0 dBTP` en este flujo).
- Sin pérdida audible excesiva de brillo ni bombeo.
- Mejora perceptible del tramo conflictivo en A/B.
