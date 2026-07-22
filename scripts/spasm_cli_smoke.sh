#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="${FINISHER_SPASM_CLI:-$ROOT_DIR/scripts/finisher_spasm_cli}"
WAV="${1:-$ROOT_DIR/test_input.wav}"

run() {
  local req="$1"
  local out
  out="$(echo "$req" | "$CLI" call --json)"
  echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("ok") is True, d'
}

# `health` existe en finisher_spasm_cli; en spasm_cli_adapter puede no existir.
if ! run '{"method":"health","args":[],"kwargs":{}}' 2>/dev/null; then
  true
fi
run '{"method":"ensure_output_path","args":[{"__type__":"path","value":"/tmp/phase6_out"},"wav"],"kwargs":{}}'
run "{\"method\":\"analyze_audio\",\"args\":[{\"__type__\":\"path\",\"value\":\"$WAV\"},-14.0,-1.0,false],\"kwargs\":{}}"
run "{\"method\":\"analyze_eq_bands\",\"args\":[{\"__type__\":\"path\",\"value\":\"$WAV\"},false,8.0],\"kwargs\":{}}"
run "{\"method\":\"analyze_voice_band\",\"args\":[{\"__type__\":\"path\",\"value\":\"$WAV\"},false],\"kwargs\":{}}"
run '{"method":"evaluate_mix","args":[{"input_i":-12.5,"input_tp":-0.9,"input_lra":5.0,"target_offset":0.5},-14.0,-1.0],"kwargs":{}}'
run '{"method":"resolve_repair_levels","args":[{"input_tp":-0.02,"input_thresh":-18.0},"Auto","Auto","Auto"],"kwargs":{}}'

echo "[OK] spasm_cli_smoke"
