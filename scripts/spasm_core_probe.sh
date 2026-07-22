#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPASM_BIN="${FINISHER_SPASM_BIN:-/home/martin/Documentos/SpASM/spasm}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

run_case() {
  local name="$1"
  local script_body="$2"
  local stdin_payload="${3:-health}"
  local f="$TMP_DIR/$name.spasm"
  printf '%s\n' "$script_body" > "$f"

  local out
  local rc=0
  out="$(printf '%s\n' "$stdin_payload" | "$SPASM_BIN" "$f" 2>&1)" || rc=$?
  if [[ $rc -eq 0 ]]; then
    printf '[OK]   %s\n' "$name"
  else
    printf '[FAIL] %s (rc=%s)\n' "$name" "$rc"
    printf '       %s\n' "$(echo "$out" | head -n 2 | tr '\n' ' ')"
  fi
}

BASE_PREFIX='var method = ""; input(str) method; method = str_trim(method);'
BASE_SUFFIX='print "OK"; end;'

run_case "minimal" "$BASE_PREFIX $BASE_SUFFIX"

run_case "if-branch" "$BASE_PREFIX if (str_equals(method, \"health\") == 1) { print \"OK\"; } print \"ERR\"; end;"

run_case "long-string-1" "$BASE_PREFIX print \"[0:a]volume=-17.0dB[hr];[hr]dynaudnorm=peak=0.708:maxgain=2.0:targetrms=0:gausssize=31[agfinal]\"; end;"

run_case "long-string-2" "$BASE_PREFIX print \"[0:a]volume=-17.0dB[hr];[hr]deesser=i=0.55:f=6200[mx1];[mx1]equalizer=f=1000:g=0.10[mx2];[mx2]dynaudnorm=peak=0.708:maxgain=2.0:targetrms=0:gausssize=31[agfinal]\"; end;"

run_case "multi-inputs" "$BASE_PREFIX var a=\"\"; var b=\"\"; var c=\"\"; input(str) a; input(str) b; input(str) c; print a; print b; print c; end;" $'x\ny\nz'

run_case "int-inputs" "$BASE_PREFIX var a=0; var b=0; input(int) a; input(int) b; if (a == 1) { if (b == 1) { print \"BOTH\"; } } if (a != 1) { print \"NO\"; } else { if (b != 1) { print \"NO\"; } } end;" $'_\n1\n1'

run_case "comments" "$BASE_PREFIX // comment only ascii\nprint \"OK\"; end;"

echo "Probe terminado."
