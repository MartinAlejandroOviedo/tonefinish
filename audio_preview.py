"""
Sistema de preview de audio para comparación antes/después.

Permite generar previews temporales y reproducirlas sin procesar el archivo completo.
"""

import subprocess
import pathlib
import tempfile
import os
from typing import Optional


class AudioPreview:
    """Maneja la generación y reproducción de previews de audio."""
    
    def __init__(self):
        self.preview_file: Optional[pathlib.Path] = None
        self.player_process: Optional[subprocess.Popen] = None
        
    def generate_preview(
        self,
        input_path: pathlib.Path,
        filter_complex: str,
        duration: float = 30.0,
        start_time: Optional[float] = None,
        verbose: bool = False
    ) -> pathlib.Path:
        """
        Genera un preview temporal aplicando los filtros especificados.
        
        Args:
            input_path: Archivo de audio original
            filter_complex: Cadena de filtros ffmpeg
            duration: Duración del preview en segundos
            start_time: Tiempo de inicio (None = centro del audio)
            verbose: Mostrar comandos
            
        Returns:
            Ruta al archivo temporal de preview
        """
        # Limpiar preview anterior
        self.cleanup()
        
        # Crear archivo temporal
        temp_dir = tempfile.gettempdir()
        self.preview_file = pathlib.Path(temp_dir) / f"tonefinish_preview_{os.getpid()}.wav"
        
        # Si no se especifica start_time, usar el centro del audio
        if start_time is None:
            # Obtener duración total
            probe_cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(input_path)
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            import json
            probe_data = json.loads(result.stdout)
            total_duration = float(probe_data["format"]["duration"])
            start_time = max(0, (total_duration / 2.0) - (duration / 2.0))
        
        # Generar preview con filtros aplicados (o copia directa si no hay filtros)
        if filter_complex and filter_complex.strip():
            # Con filtros
            cmd = [
                "ffmpeg",
                "-y",  # Sobrescribir sin preguntar
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", str(input_path),
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-ar", "44100",
                "-ac", "2",
                str(self.preview_file)
            ]
        else:
            # Sin filtros - copia directa del segmento
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", str(input_path),
                "-ar", "44100",
                "-ac", "2",
                str(self.preview_file)
            ]
        
        if not verbose:
            cmd.insert(1, "-v")
            cmd.insert(2, "quiet")
        else:
            print(f"$ {' '.join(cmd)}")
        
        subprocess.run(cmd, check=True)
        return self.preview_file
    
    def play(self, audio_file: Optional[pathlib.Path] = None) -> None:
        """
        Reproduce un archivo de audio usando el reproductor del sistema.
        
        Args:
            audio_file: Archivo a reproducir (None = usar preview generado)
        """
        if audio_file is None:
            audio_file = self.preview_file
        
        if audio_file is None or not audio_file.exists():
            raise ValueError("No hay archivo de preview para reproducir")
        
        # Detener reproducción anterior
        self.stop()
        
        # Detectar reproductor disponible
        # Intentar: ffplay, aplay, paplay, play (sox)
        players = [
            ["ffplay", "-nodisp", "-autoexit", "-v", "quiet"],
            ["aplay"],
            ["paplay"],
            ["play"]
        ]
        
        for player_cmd in players:
            try:
                cmd = player_cmd + [str(audio_file)]
                self.player_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except FileNotFoundError:
                continue
        
        raise RuntimeError(
            "No se encontró reproductor de audio (ffplay, aplay, paplay, play)"
        )
    
    def stop(self) -> None:
        """Detiene la reproducción actual."""
        if self.player_process is not None:
            try:
                self.player_process.terminate()
                self.player_process.wait(timeout=1.0)
            except:
                try:
                    self.player_process.kill()
                except:
                    pass
            self.player_process = None
    
    def is_playing(self) -> bool:
        """Verifica si hay reproducción en curso."""
        if self.player_process is None:
            return False
        return self.player_process.poll() is None
    
    def cleanup(self) -> None:
        """Limpia archivos temporales y procesos."""
        self.stop()
        if self.preview_file and self.preview_file.exists():
            try:
                os.remove(self.preview_file)
            except:
                pass
            self.preview_file = None
    
    def __del__(self):
        """Limpieza al destruir el objeto."""
        self.cleanup()
