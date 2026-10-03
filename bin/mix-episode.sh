#!/bin/bash
# mix-episode.sh <speech.mp3> <output.mp3>
# Mixes the hourly podcast:
#   1. intro sting (assets/intro.mp3, 6s news jingle, synth 2026-10-01)
#   2. speech with soft background-music bed underneath
#      - if $BED_TRACK_MP3 points to a prebuilt bed track (same length as speech,
#        per-section beds, muted under short-video clips), it is used as-is;
#      - otherwise falls back to looping assets/bed.mp3.
#   3. 10s outro sting
# The script must NOT contain any music cues: intro/bed/outro are all added here.
set -euo pipefail
SPEECH="$1"; OUT="$2"
ASSETS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 音乐套装轮换：MUSIC_PACK=v0..v6 时用 music/$MUSIC_PACK/ 下的 intro/outro/bed1-4；
# 未设置或目录不存在时回退到脚本同目录下的默认音乐。
if [[ -n "${MUSIC_PACK:-}" && -f "$ASSETS/music/$MUSIC_PACK/intro.mp3" ]]; then
  MDIR="$ASSETS/music/$MUSIC_PACK"
  echo "music pack: $MUSIC_PACK" >&2
  INTRO="$MDIR/intro.mp3"; OUTRO="$MDIR/outro.mp3"; BED="$MDIR/bed1.mp3"
else
  INTRO="$ASSETS/intro.mp3"; OUTRO="$ASSETS/outro.mp3"; BED="$ASSETS/bed.mp3"
fi
BED_TRACK="${BED_TRACK_MP3:-}"

if [[ ! -f "$OUTRO" ]]; then
  echo "outro missing, copying speech as-is" >&2
  cp "$SPEECH" "$OUT"
  exit 0
fi

# Bed source: prebuilt track (already full speech length) or looped bed.mp3.
# The bed goes through sidechain ducking keyed on the speech: it drops ~7dB
# whenever a host is talking and swells back in pauses (lowpass keeps it from
# competing with voice presence). Fixes "bed steals the show" (2026-10-01).
if [[ -n "$BED_TRACK" && -f "$BED_TRACK" ]]; then
  echo "using prebuilt bed track: $BED_TRACK" >&2
  BED_INPUT=(-i "$BED_TRACK")
  BED_FILTER='[0:a]asplit=2[sp][key];[1:a]lowpass=f=8000[bp];[bp][key]sidechaincompress=threshold=0.025:ratio=6:attack=15:release=500:makeup=1[bg]'
elif [[ -f "$BED" ]]; then
  echo "using looped bed: $BED" >&2
  BED_INPUT=(-i "$BED")
  BED_FILTER='[0:a]asplit=2[sp][key];[1:a]aloop=loop=-1:size=2e9,lowpass=f=8000[bp];[bp][key]sidechaincompress=threshold=0.025:ratio=6:attack=15:release=500:makeup=1[bg]'
else
  echo "no bed available, mixing speech only" >&2
  BED_INPUT=()
  BED_FILTER=''
fi

# Shared: ducked speech + bed, then the 10s outro sting with a soft fade-in.
if [[ -n "$BED_FILTER" ]]; then
  MIX_FILTER="${BED_FILTER};[sp][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[mix]"
else
  MIX_FILTER='[0:a]anull[mix]'
fi

if [[ -f "$INTRO" ]]; then
  # inputs: 0=speech, 1=bed, 2=outro, 3=intro
  ffmpeg -y -hide_banner -loglevel error \
    -i "$SPEECH" "${BED_INPUT[@]}" -i "$OUTRO" -i "$INTRO" \
    -filter_complex "${MIX_FILTER};[3:a]afade=t=in:st=0:d=0.5,afade=t=out:st=5:d=1[intro];[2:a]afade=t=in:st=0:d=1.5[out];[intro][mix][out]concat=n=3:v=0:a=1[aout]" \
    -map "[aout]" -c:a libmp3lame -b:a 128k -ar 44100 "$OUT"
else
  echo "intro missing, mixing without it" >&2
  ffmpeg -y -hide_banner -loglevel error \
    -i "$SPEECH" "${BED_INPUT[@]}" -i "$OUTRO" \
    -filter_complex "${MIX_FILTER};[2:a]afade=t=in:st=0:d=1.5[out];[mix][out]concat=n=2:v=0:a=1[aout]" \
    -map "[aout]" -c:a libmp3lame -b:a 128k -ar 44100 "$OUT"
fi
echo "mixed -> $OUT"
ffprobe -hide_banner -v error -show_entries format=duration -of csv=p=0 "$OUT"
