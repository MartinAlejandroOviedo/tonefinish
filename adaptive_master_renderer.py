"""Render adaptativo temporal, transaccional y con fallback al master estático."""
from __future__ import annotations
import os, pathlib, shutil, subprocess, tempfile, uuid
from typing import Any, Dict
from alternative_tools import analyze_loudness_ffmpeg

BAND_FILTERS = {
    "subbass_db": (45.0, 0.7, "lowshelf"), "bass_db": (120.0, 0.8, "bell"),
    "mid_db": (1000.0, 0.7, "bell"), "high_mid_db": (3800.0, 0.9, "bell"),
    "air_db": (9000.0, 0.7, "highshelf"),
}

def _envelope(start: float, end: float, ramp: float) -> str:
    ramp = min(ramp, max(0.01, (end-start)/2.0))
    return (f"if(lt(t,{start:.4f}),0,if(lt(t,{start+ramp:.4f}),(t-{start:.4f})/{ramp:.4f},"
            f"if(lt(t,{end-ramp:.4f}),1,if(lt(t,{end:.4f}),({end:.4f}-t)/{ramp:.4f},0))))")

def build_adaptive_filter(decisions: Dict[str, Any]) -> tuple[str, str, list[Dict[str, Any]]]:
    current="0:a"; parts=[]; executed=[]; counter=0
    for section in decisions.get("section_decisions", []):
        start=float(section.get("start_s",0)); end=float(section.get("end_s",start))
        smoothing=max(150.0,min(500.0,float((section.get("guards") or {}).get("smoothing_ms",180))))/1000.0
        for band, raw in ((section.get("actions") or {}).get("eq_db") or {}).items():
            if band not in BAND_FILTERS: continue
            requested=float(raw); gain=max(-0.8,min(0.8,requested))
            if abs(gain)<0.01 or end<=start: continue
            counter+=1; carry=f"ad_carry_{counter}"; original=f"ad_orig_{counter}"; eqin=f"ad_eqin_{counter}"
            inverted=f"ad_inverted_{counter}"; eqout=f"ad_eq_{counter}"; delta=f"ad_delta_{counter}"; scaled=f"ad_scaled_{counter}"; out=f"ad_out_{counter}"
            freq,q,kind=BAND_FILTERS[band]
            eq=(f"equalizer=f={freq}:t=q:w={q}:g={gain}" if kind=="bell" else f"{kind}=f={freq}:g={gain}")
            parts += [f"[{current}]asplit=3[{carry}][{original}][{eqin}]", f"[{eqin}]{eq}[{eqout}]",
                      f"[{original}]volume=-1[{inverted}]",
                      f"[{inverted}][{eqout}]amix=inputs=2:weights=1 1:normalize=0[{delta}]",
                      f"[{delta}]volume='{_envelope(start,end,smoothing)}':eval=frame[{scaled}]",
                      f"[{carry}][{scaled}]amix=inputs=2:weights=1 1:normalize=0[{out}]"]
            current=out
            executed.append({"section_id":section.get("section_id"),"label":section.get("label"),"band":band,
                             "function_id":"audio.dynamic_eq.motion", "operation":"boost" if gain>0 else "cut",
                             "start_s":start,"end_s":end,"requested_db":requested,"applied_db":gain,
                             "smoothing_ms":round(smoothing*1000,1)})
    return ";".join(parts), current, executed

def render_adaptive_candidate(source: pathlib.Path, decisions: Dict[str,Any], target_lufs: float,
                              true_peak: float) -> Dict[str,Any]:
    graph,out,executed=build_adaptive_filter(decisions)
    report={"status":"not_applied","executed_automations":executed,"fallback":"static_master"}
    if not executed:
        report["reason"]="no_executable_automation"; return report
    temp_dir=pathlib.Path(tempfile.mkdtemp(prefix="tonefinish-adaptive-"))
    raw=temp_dir/"automation.wav"; final=temp_dir/("candidate"+source.suffix.lower())
    try:
        cmd=["ffmpeg","-y","-v","error","-i",str(source),"-filter_complex",graph,"-map",f"[{out}]",
             "-map_metadata","0",str(raw)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
        if result.returncode: raise RuntimeError(result.stderr.strip() or "FFmpeg adaptive render failed")
        stats=analyze_loudness_ffmpeg(str(raw))
        if stats is None: raise RuntimeError("No se pudo medir candidato adaptativo")
        gain=max(-3.0,min(3.0,float(target_lufs)-stats.input_i))
        limit=10**(float(true_peak)/20.0)
        calibration=f"volume={gain:.4f}dB,alimiter=limit={limit:.8f}:level=false"
        result=subprocess.run(["ffmpeg","-y","-v","error","-i",str(raw),"-af",calibration,
                               "-map_metadata","0",str(final)],capture_output=True,text=True,timeout=600)
        if result.returncode: raise RuntimeError(result.stderr.strip() or "FFmpeg adaptive calibration failed")
        measured=analyze_loudness_ffmpeg(str(final))
        if measured is None: raise RuntimeError("No se pudo validar candidato adaptativo")
        report.update({"status":"candidate_ready","candidate_path":str(final),"temporary_dir":str(temp_dir),"calibration_gain_db":round(gain,3),
                       "post_stats":{"input_i":measured.input_i,"input_tp":measured.input_tp,
                                     "input_lra":measured.input_lra,"input_thresh":measured.input_thresh,
                                     "target_offset":measured.target_offset}})
        return report
    except Exception as exc:
        report["reason"]=str(exc); return report

def publish_adaptive_candidate(source: pathlib.Path, render_report: Dict[str,Any]) -> bool:
    candidate=pathlib.Path(str(render_report.get("candidate_path","")))
    if render_report.get("status")!="candidate_ready" or not candidate.is_file(): return False
    sibling = source.parent / f".{source.stem}.adaptive-{uuid.uuid4().hex}{source.suffix}"
    try:
        # /tmp y el destino pueden estar en filesystems distintos. Primero copiamos
        # dentro del destino y sólo allí hacemos el replace atómico.
        shutil.copy2(candidate, sibling)
        os.replace(sibling, source)
        render_report["status"]="applied"; render_report["published_path"]=str(source)
        return True
    finally:
        try:
            if sibling.exists(): sibling.unlink()
        except OSError:
            pass
        shutil.rmtree(str(render_report.get("temporary_dir", "")), ignore_errors=True)
        render_report.pop("candidate_path", None); render_report.pop("temporary_dir", None)

def discard_adaptive_candidate(render_report: Dict[str,Any]) -> None:
    temp_dir=str(render_report.get("temporary_dir", ""))
    if temp_dir: shutil.rmtree(temp_dir, ignore_errors=True)
