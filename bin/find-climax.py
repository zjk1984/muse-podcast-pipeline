#!/usr/bin/env python3
"""定位音频中能量最高的一段（高潮段），用于短视频原声截取。

原理：音乐类视频的高潮（副歌/唱歌段落）通常是全曲能量最高的部分；
搞笑/现场类视频的高潮（包袱、欢呼）也往往伴随能量峰值。
按 1 秒窗口算 RMS，能量最高的连续 <duration> 秒即为高潮段。

用法：
    find-climax.py <input.mp3> [--duration 45] [--json]
输出 JSON：{"start": 秒, "end": 秒, "total": 总时长秒}
退出码 2 表示音频为空/解码失败。
"""
import argparse
import json
import subprocess
import sys

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--duration", type=float, default=45,
                    help="高潮段目标时长（秒），默认 45")
    args = ap.parse_args()

    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", args.input,
         "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        print(json.dumps({"error": "decode failed"}))
        sys.exit(2)
    pcm = np.frombuffer(proc.stdout, dtype=np.float32)
    sr = 16000
    total = len(pcm) / sr
    if total <= 0:
        print(json.dumps({"error": "empty audio"}))
        sys.exit(2)

    dur = min(args.duration, total)

    # 每 1 秒一个 RMS
    win = sr
    n = max(1, len(pcm) // win)
    rms = np.sqrt(np.mean(pcm[:n * win].reshape(n, win) ** 2, axis=1) + 1e-12)
    # 3 秒滑动平均，平滑毛刺
    sm = np.convolve(rms, np.ones(3) / 3, mode="same")

    L = max(1, int(round(dur)))
    if L >= n:
        start = 0
        end = n
    else:
        sums = np.convolve(sm, np.ones(L), mode="valid")
        start = int(np.argmax(sums))
        end = start + L
        # 修剪：起点往前最多 4 秒找一个能量局部低点，避免一刀切在字/音符中间
        lo = max(0, start - 4)
        seg = sm[lo:start + 1]
        dip = lo + int(np.argmin(seg))
        # 只有低点明显低于起点能量才采用（至少低 25%），否则保持原起点
        if sm[dip] < sm[start] * 0.75:
            shift = start - dip
            start = dip
            end = min(n, end - shift)

    print(json.dumps({
        "start": round(float(start), 1),
        "end": round(float(end), 1),
        "total": round(float(total), 1),
    }))


if __name__ == "__main__":
    main()
