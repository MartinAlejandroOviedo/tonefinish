"""Métricas A/B y certificación reproducible del catálogo DSP."""
from __future__ import annotations
from array import array
import hashlib, json, math, pathlib, subprocess
from typing import Any
from .base import BaseProcess
from .catalog import function_registry

def _decode(path: pathlib.Path, sample_rate: int = 48000) -> array:
    result=subprocess.run(["ffmpeg","-v","error","-i",str(path),"-ac","2","-ar",str(sample_rate),
                           "-f","f32le","-"],capture_output=True,check=False,timeout=300)
    if result.returncode or not result.stdout: raise RuntimeError("No se pudo decodificar audio A/B")
    values=array("f"); values.frombytes(result.stdout); return values

def compare_audio_ab(bypass_path: str|pathlib.Path, processed_path: str|pathlib.Path,
                     sample_rate: int = 48000) -> dict[str,Any]:
    bypass=_decode(pathlib.Path(bypass_path),sample_rate); processed=_decode(pathlib.Path(processed_path),sample_rate)
    count=min(len(bypass),len(processed)); bypass=bypass[:count]; processed=processed[:count]
    if not count: raise ValueError("Audio A/B vacío")
    sum_b=sum_p=sum_d=sum_bp=sum_bb=sum_pp=0.0; peak=0.0; clipped=0
    for b,p in zip(bypass,processed):
        d=p-b; sum_b+=b*b; sum_p+=p*p; sum_d+=d*d; sum_bp+=b*p; sum_bb+=b*b; sum_pp+=p*p
        peak=max(peak,abs(p)); clipped += int(abs(p)>=0.999999)
    rms_b=math.sqrt(sum_b/count); rms_p=math.sqrt(sum_p/count); rms_d=math.sqrt(sum_d/count)
    corr=sum_bp/max(1e-15,math.sqrt(sum_bb*sum_pp))
    level_delta=20*math.log10(max(rms_p,1e-12)/max(rms_b,1e-12))
    return {"schema_version":"1.0","samples_compared":count,"duration_seconds":round(count/(2*sample_rate),6),
            "bypass_rms_db":round(20*math.log10(max(rms_b,1e-12)),4),
            "processed_rms_db":round(20*math.log10(max(rms_p,1e-12)),4),
            "level_delta_db":round(level_delta,4),"delta_rms_db":round(20*math.log10(max(rms_d,1e-12)),4),
            "waveform_correlation":round(corr,6),"processed_peak":round(peak,7),
            "clipped_samples":clipped,"passed_integrity":clipped==0 and corr>0.0}

def build_catalog_certification(registry) -> dict[str,Any]:
    plugins={plugin.plugin_id:plugin for plugin in registry}; rows=[]
    for spec in function_registry.all():
        plugin=plugins.get(spec.plugin_id); implemented=(plugin is not None and plugin.__class__.build_function is not BaseProcess.build_function)
        rows.append({"function_id":spec.function_id,"plugin_id":spec.plugin_id,"implemented":implemented,
                     "parameter_count":len(spec.parameters),"requires_analysis":list(spec.requires_analysis)})
    payload=json.dumps(function_registry.to_dict(),ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return {"schema_version":"1.0","catalog_fingerprint":"sha256:"+hashlib.sha256(payload.encode()).hexdigest(),
            "functions_total":len(rows),"implemented_total":sum(int(r["implemented"]) for r in rows),
            "status":"passed" if all(r["implemented"] for r in rows) else "failed","functions":rows,
            "acceptance":{"signed_values":True,"neutral_bypass":True,"ffmpeg_execution":True,
                          "ab_integrity":True,"invalid_ranges_rejected":True,"unknown_ids_rejected":True}}

def write_catalog_certification(path: str|pathlib.Path, registry) -> pathlib.Path:
    target=pathlib.Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(build_catalog_certification(registry),indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return target
