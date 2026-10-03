#!/usr/bin/env python3
"""按时间线构建整期 bed 轨道：各版块用不同 bed，短视频原声时段 bed 静音。

输入（均由定时任务 worker 生成）：
  --bed-map    /tmp/bed-insert.json   {"剥离后行号": bed编号(1-4)}，无 marker 则 {} 或文件不存在
  --line-times /tmp/line-times.json   [{"line":1,"start":0.0,"dur":3.2}, ...]（剥离后脚本行顺序）
  --clip-times /tmp/clip-times.json   [{"n":1,"start":300.0,"dur":28.5}, ...]（原声起止）
  --voice      干声 mp3（质检收紧后的最终版），用于取目标时长
  --offset     /tmp/trim-offset.json  {"shift": L}（质检 silenceremove 删掉的片头静音秒数）
输出：与干声等长的 bed 轨道 mp3。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ASSETS = os.path.dirname(os.path.abspath(__file__))  # bed/intro/outro 与脚本同目录
BED_FILES = {1: "bed.mp3", 2: "bed2.mp3", 3: "bed3.mp3", 4: "bed4.mp3"}
# 音乐套装轮换：MUSIC_PACK=v0..v6 时用 <assets>/music/$MUSIC_PACK/bed1-4.mp3；
# 未设置或文件不存在时回退默认 bed。
_MPACK = os.environ.get("MUSIC_PACK", "")


def bed_path(assets_dir, n):
    if _MPACK:
        p = os.path.join(assets_dir, "music", _MPACK, f"bed{n}.mp3")
        if os.path.exists(p):
            return p
    return os.path.join(assets_dir, BED_FILES[n])
FADE_BED = 0.8   # bed 切换淡入淡出
FADE_MUTE = 0.4  # 原声前后 bed 收放


def ffprobe_dur(path):
    out = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "error",
         "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bed-map", required=True)
    ap.add_argument("--line-times", required=True)
    ap.add_argument("--clip-times", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--offset", required=True)
    ap.add_argument("--assets", default=ASSETS)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    bed_map = load_json(a.bed_map, {})
    line_times = load_json(a.line_times, [])
    clip_times = load_json(a.clip_times, [])
    shift = float(load_json(a.offset, {}).get("shift", 0) or 0)
    if not line_times:
        print("line-times 为空，无法构建 bed 时间线", file=sys.stderr)
        return 2

    line_start = {r["line"]: float(r["start"]) for r in line_times}
    total_pre = max(float(r["start"]) + float(r["dur"]) for r in line_times)
    for c in clip_times:
        total_pre = max(total_pre, float(c["start"]) + float(c["dur"]))

    # bed 切换点：行号 -> 时间
    changes = []
    for lineno_s, bed in bed_map.items():
        try:
            lineno, bedn = int(lineno_s), int(bed)
        except (ValueError, TypeError):
            continue
        if lineno in line_start and bedn in BED_FILES:
            changes.append((line_start[lineno], bedn))
    changes.sort()

    segments = []  # (start, end, bed)
    cur_t, cur_bed = 0.0, 1
    for t, b in changes:
        if t > cur_t:
            segments.append((cur_t, t, cur_bed))
        cur_t, cur_bed = t, b
    if total_pre > cur_t:
        segments.append((cur_t, total_pre, cur_bed))

    # 减去质检删掉的片头静音
    def adj(s, e):
        s2, e2 = max(0.0, s - shift), max(0.0, e - shift)
        return (s2, e2) if e2 > s2 + 0.01 else None

    segments = [(*adj(s, e), b) for s, e, b in segments]
    segments = [x for x in segments if x is not None]
    mutes = []
    for c in clip_times:
        m = adj(float(c["start"]), float(c["start"]) + float(c["dur"]))
        if m:
            mutes.append(m)
    mutes.sort()

    # 从 sounding 段里挖掉 mute 区间
    pieces = []  # (start, end, bed|None)
    for s, e, b in segments:
        cur = s
        for ms, me in mutes:
            if me <= cur or ms >= e:
                continue
            if ms > cur:
                pieces.append((cur, min(ms, e), b))
            cur = max(cur, me)
            if cur >= e:
                break
        if cur < e:
            pieces.append((cur, e, b))
    for ms, me in mutes:
        pieces.append((ms, me, None))
    pieces.sort()

    D = ffprobe_dur(a.voice)
    # 覆盖 [0, D]：末尾不够用 bed1 补，超出则截
    if pieces:
        if pieces[-1][1] < D - 0.05:
            pieces.append((pieces[-1][1], D, 1))
        if pieces[-1][1] > D:
            s, e, b = pieces[-1]
            pieces[-1] = (s, D, b)
    else:
        pieces = [(0.0, D, 1)]

    tmpd = tempfile.mkdtemp(prefix="bedtrack-")
    list_path = os.path.join(tmpd, "list.txt")

    def render_piece(i, s, e, bed):
        dur = e - s
        p = os.path.join(tmpd, f"p{i:03d}.mp3")
        if bed is None:
            fd = min(FADE_MUTE, dur / 2)
            af = (f"afade=t=in:st=0:d={fd:.3f},"
                  f"afade=t=out:st={dur - fd:.3f}:d={fd:.3f}") if fd > 0.01 else "anull"
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                 "-t", f"{dur:.3f}", "-af", af,
                 "-c:a", "libmp3lame", "-b:a", "128k", p], check=True)
        else:
            src = bed_path(a.assets, bed)
            if not os.path.exists(src):
                src = bed_path(a.assets, 1)
            fd = min(FADE_BED, dur / 2)
            af = (f"aloop=loop=-1:size=2e9,atrim=duration={dur:.3f},"
                  f"afade=t=in:st=0:d={fd:.3f},"
                  f"afade=t=out:st={dur - fd:.3f}:d={fd:.3f}") if fd > 0.01 else \
                 f"aloop=loop=-1:size=2e9,atrim=duration={dur:.3f}"
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", src, "-t", f"{dur:.3f}", "-af", af,
                 "-c:a", "libmp3lame", "-b:a", "128k", p], check=True)
        return p

    with open(list_path, "w", encoding="utf-8") as f:
        for i, (s, e, b) in enumerate(pieces):
            p = render_piece(i, s, e, b)
            f.write(f"file '{p}'\n")

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:a", "libmp3lame", "-b:a", "128k", a.out], check=True)
    out_dur = ffprobe_dur(a.out)
    print(f"bed-track: {len(pieces)} pieces, {out_dur:.1f}s (voice {D:.1f}s), "
          f"{sum(1 for _,_,b in pieces if b is None)} mute(s)")
    if abs(out_dur - D) > 1.0:
        print(f"警告：bed 轨道时长 {out_dur:.1f}s 与干声 {D:.1f}s 差超 1s",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
