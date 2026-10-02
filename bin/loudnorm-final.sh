#!/bin/bash
# loudnorm-final.sh <in.mp3> <out.mp3>
# 终混响度标准化：双 pass EBU R128，目标 -16 LUFS（播客行业标准），
# true peak -1.5dB。linear=true 保证只做静态增益，不动态抽泵。
# 失败时原样复制输入，不阻塞。
set -uo pipefail
IN="$1"; OUT="$2"

MEASURED_JSON=$(ffmpeg -hide_banner -i "$IN" \
  -af loudnorm=I=-16:TP=-2.0:LRA=11:print_format=json \
  -f null - 2>&1 | sed -n '/^{/,/^}/p')

parse() {
  echo "$MEASURED_JSON" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin)['$1'])
except Exception:
    sys.exit(1)"
}

if I=$(parse input_i) && TP=$(parse input_tp) && LRA=$(parse input_lra) \
   && THRESH=$(parse input_thresh) && OFF=$(parse target_offset); then
  if ffmpeg -hide_banner -loglevel error -y -i "$IN" \
    -af "loudnorm=I=-16:TP=-2.0:LRA=11:measured_I=$I:measured_TP=$TP:measured_LRA=$LRA:measured_thresh=$THRESH:offset=$OFF:linear=true" \
    -c:a libmp3lame -b:a 128k -ar 44100 "$OUT"; then
    echo "loudnorm -> $OUT (target -16 LUFS, TP -2.0dB pre-encode)" >&2
    exit 0
  fi
fi
echo "loudnorm 失败，原样保留输入" >&2
cp "$IN" "$OUT"
