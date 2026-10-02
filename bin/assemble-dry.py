#!/usr/bin/env python3
"""整点快报干声组装：预扫缓存 → 逐行电平补偿 → 拼接淡化 → clip 插入 → concat。

替代原来每期 worker 手写的拼接脚本（逻辑固定下来，避免每期重写出错）。

- 电平补偿：以本期所有行 mean_volume 中位数为目标，单行增益封顶 ±6dB。
  解决五个 TTS 音色最大 8.4dB 落差、买买提单音色内部近 10dB 起伏导致的
  "忽高忽低"。预扫负责把真正的异常行改写掉，这里只做温和的相对拉平。
- 拼接淡化：每段首尾 8ms afade，消除 concat 硬切的咔哒声。
- clip 原声：只做淡化（电平已在抓取步骤归一化到约 -20 LUFS），不做增益。

用法：
  python3 assemble-dry.py --script /tmp/hourly-script.txt \\
      --clip-insert /tmp/clip-insert.json \\
      --out /tmp/hourly-dry.mp3 \\
      --line-times /tmp/line-times.json --clip-times /tmp/clip-times.json

clip-insert.json 格式：{"1": 42} 表示 clip1 插在第 42 行之后
（行号为剥离后脚本的行顺序，从 1 开始）。
缺失缓存的行会报错退出（exit 2），worker 应先重跑 prescan-chunks.py 补齐。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

def _load_voices():
    """说话人名字 -> TTS 音色 ID，从同目录 voices.json 加载。

    不在代码里硬编码：复制 voices.example.json 为 voices.json 并填入
    你自己的音色。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "voices.json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    # 跳过 "_" 开头的说明键
    return {k: v for k, v in raw.items() if not k.startswith("_")}

DEFAULT_VOICES = _load_voices()
CACHE_DEFAULT = os.environ.get("PODCAST_CACHE", "./cache/prescan-cache.json")
MAX_GAIN_DB = 6.0
FADE_SEC = 0.008  # 拼接淡化 8ms


def cache_key(voice, text):
    return hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()[:16]


def parse_script(path):
    # 说话人名单取自 voices.json（_load_voices），换人设时只需改 voices.json，无需改代码
    names = sorted(DEFAULT_VOICES.keys(), key=len, reverse=True)
    pattern = r"^(" + "|".join(re.escape(n) for n in names) + r")\s*[:：]\s*(.*)$"
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        m = re.match(pattern, line)
        if m and m.group(2):
            rows.append((m.group(1), m.group(2)))
    return rows


def ffprobe_dur(path):
    out = subprocess.run(
        ["ffprobe", "-hide_banner", "-v", "error",
         "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip().split()[0])


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def fade_chain(dur):
    """返回该段的 afade 子句；太短的段跳过淡化。"""
    if dur is None or dur <= 2 * FADE_SEC + 0.002:
        return ""
    return (f",afade=t=in:st=0:d={FADE_SEC}"
            f",afade=t=out:st={dur - FADE_SEC:.3f}:d={FADE_SEC}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--cache", default=CACHE_DEFAULT)
    ap.add_argument("--clip-insert", default="/tmp/clip-insert.json")
    ap.add_argument("--clips-dir", default="/tmp")
    ap.add_argument("--out", required=True)
    ap.add_argument("--line-times", required=True)
    ap.add_argument("--clip-times", required=True)
    ap.add_argument("--target-db", type=float, default=None,
                    help="目标 mean_volume，不指定则用本期中位数")
    ap.add_argument("--max-gain", type=float, default=MAX_GAIN_DB)
    a = ap.parse_args()

    rows = parse_script(a.script)
    if not rows:
        print("脚本里没有可解析的台词行", file=sys.stderr)
        return 2
    try:
        with open(a.cache, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception as e:
        print(f"读缓存失败 {a.cache}: {e}", file=sys.stderr)
        return 2

    try:
        with open(a.clip_insert, encoding="utf-8") as f:
            clip_map = json.load(f)  # {"clip_n": line_no}
    except Exception:
        clip_map = {}
    # 行号 -> [clip 编号]
    by_line = {}
    for cn, ln in clip_map.items():
        try:
            by_line.setdefault(int(ln), []).append(int(cn))
        except (ValueError, TypeError):
            pass
    for v in by_line.values():
        v.sort()

    # 解析每行 → 缓存条目
    line_segs = []  # (line_no, speaker, key, hit)
    missing = []
    for i, (sp, text) in enumerate(rows, 1):
        key = cache_key(DEFAULT_VOICES[sp], text)
        hit = cache.get(key)
        if not hit or not os.path.exists(hit.get("path", "")):
            missing.append((i, sp, text[:30]))
        else:
            line_segs.append((i, sp, key, hit))
    if missing:
        print(f"缺失 {len(missing)} 行的预扫缓存（先重跑 prescan-chunks.py 补齐）：",
              file=sys.stderr)
        for i, sp, t in missing[:10]:
            print(f"  L{i} [{sp}] {t}", file=sys.stderr)
        return 2

    dbs = [h["db"] for _, _, _, h in line_segs
           if isinstance(h.get("db"), (int, float))]
    if not dbs:
        print("缓存里没有可用的电平数据", file=sys.stderr)
        return 2
    target = a.target_db if a.target_db is not None else median(dbs)
    print(f"电平补偿：本期 {len(dbs)} 行中位数 {target:.1f}dB 为目标，"
          f"单行封顶 ±{a.max_gain:.0f}dB", file=sys.stderr)

    # 组装输入序列：行音频 + 插入点 clip
    seq = []  # dict(kind, path, gain_db, dur, label, line_no/clip_n)
    for line_no, sp, key, hit in line_segs:
        db = hit["db"]
        gain = max(-a.max_gain, min(a.max_gain, target - db))
        seq.append({"kind": "line", "path": hit["path"], "gain_db": gain,
                    "dur": hit["dur"], "label": f"L{line_no}{sp}",
                    "line_no": line_no})
        for cn in by_line.get(line_no, []):
            cp = os.path.join(a.clips_dir, f"clip{cn}-norm.mp3")
            if not os.path.exists(cp):
                print(f"警告：clip{cn} 音频 {cp} 不存在，跳过", file=sys.stderr)
                continue
            seq.append({"kind": "clip", "path": cp, "gain_db": 0.0,
                        "dur": ffprobe_dur(cp), "label": f"clip{cn}",
                        "clip_n": cn})

    # 一次 ffmpeg：每输入独立 volume+afade，再 concat
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for s in seq:
        cmd += ["-i", s["path"]]
    filters = []
    for j, s in enumerate(seq):
        parts = []
        if s["kind"] == "line" and abs(s["gain_db"]) >= 0.05:
            parts.append(f"volume={s['gain_db']:.2f}dB")
        fades = fade_chain(s["dur"])
        if fades:
            parts.append(fades[1:])  # 去掉开头的逗号
        filt = ",".join(parts) if parts else "anull"
        filters.append(f"[{j}:a]{filt}[s{j}]")
        if s["kind"] == "line":
            print(f"  {s['label']}: {s['gain_db']:+.1f}dB", file=sys.stderr)
    concat_inputs = "".join(f"[s{j}]" for j in range(len(seq)))
    filters.append(f"{concat_inputs}concat=n={len(seq)}:v=0:a=1[aout]")
    cmd += ["-filter_complex", ";".join(filters),
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "128k", a.out]
    subprocess.run(cmd, check=True)

    # 时间线
    t = 0.0
    line_times, clip_times = [], []
    for s in seq:
        d = s["dur"]
        if s["kind"] == "line":
            line_times.append({"line": s["line_no"], "start": round(t, 3),
                               "dur": round(d, 3)})
        else:
            clip_times.append({"n": s["clip_n"], "start": round(t, 3),
                               "dur": round(d, 3)})
        t += d
    with open(a.line_times, "w", encoding="utf-8") as f:
        json.dump(line_times, f)
    with open(a.clip_times, "w", encoding="utf-8") as f:
        json.dump(clip_times, f)
    print(f"干声组装完成：{len(seq)} 段（含 {len(clip_times)} clip），"
          f"{t:.1f}s -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
