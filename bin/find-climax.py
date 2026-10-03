#!/usr/bin/env python3
"""定位音频中能量最高的一段（高潮段），用于短视频原声截取。

两种模式（--mode）：
- music（默认）：找"能量最高的连续 N 秒"——音乐类视频的副歌/演唱段落
  通常是全曲能量最高的部分；搞笑/现场类同理。
- event：找"最响的人群/现场声时刻"——体育夺冠、颁奖、现场欢呼、搞笑
  包袱这类视频，BGM（常是 sustained 的钢琴/弦乐）可能比事件声还响，
  纯能量检测会被带偏（2026-10-03 实测：16 点期"黄泽林亚运夺金"原声被
  截成了钢琴曲）。event 模式用"能量 × 噪度（过零率）"加权：人群欢呼/
  掌声/哨声是宽带噪声（噪度高），钢琴/弦乐是谐波声（噪度低）；再找
  加权能量跃升最大的时刻为锚，窗口以锚为中心前后取；自动跳过前 10 秒
  （常见片头 BGM），无明显跃升时回退到加权能量最大窗口。

注意：纯音频检测仍有极限——事件类视频尽量从视频简介/置顶评论找明确
高潮时间戳写入 clip-urls.json 的 start/end，自动定位只做兜底。

用法：
    find-climax.py <input.mp3> [--duration 45] [--mode music|event] [--json]
输出 JSON：{"start": 秒, "end": 秒, "total": 总时长秒, "mode": ..., "method": ...}
退出码 2 表示音频为空/解码失败。
"""
import argparse
import json
import subprocess
import sys

import numpy as np


def decode_mono_16k(path):
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", path,
         "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, dtype=np.float32)


def rms_per_sec(pcm, sr=16000):
    win = sr
    n = max(1, len(pcm) // win)
    rms = np.sqrt(np.mean(pcm[:n * win].reshape(n, win) ** 2, axis=1) + 1e-12)
    return rms, n


def noisiness_per_sec(pcm, sr=16000):
    """每 1 秒的噪度（0~1）：基于过零率。宽带噪声（人群欢呼/掌声/哨声）
    过零率高（0.2+），谐波乐音（钢琴/弦乐）过零率低（<0.08）。"""
    n = max(1, len(pcm) // sr)
    z = np.zeros(n)
    for i in range(n):
        x = pcm[i * sr:(i + 1) * sr]
        if len(x) < 2:
            continue
        zc = np.sum(np.abs(np.diff(np.sign(x)))) / 2.0
        z[i] = zc / len(x)
    return np.clip((z - 0.04) / 0.20, 0.0, 1.0)


def smooth(x, w=3):
    return np.convolve(x, np.ones(w) / w, mode="same")


def dip_trim(sm, start, end, n):
    """起点往前最多 4 秒找一个能量局部低点，避免一刀切在字/音符中间。"""
    lo = max(0, start - 4)
    seg = sm[lo:start + 1]
    dip = lo + int(np.argmin(seg))
    if sm[dip] < sm[start] * 0.75:  # 低点明显低于起点能量才采用
        shift = start - dip
        start = dip
        end = min(n, end - shift)
    return start, end


def locate_music(sm, n, dur):
    """v1 逻辑：能量最高的连续 dur 秒窗口。"""
    L = max(1, int(round(dur)))
    if L >= n:
        return 0, n, "energy-max-full"
    sums = np.convolve(sm, np.ones(L), mode="valid")
    start = int(np.argmax(sums))
    end = start + L
    start, end = dip_trim(sm, start, end, n)
    return start, end, "energy-max"


def locate_event(sm, nz, n, dur):
    """能量 × 噪度加权，找加权能量跃升最大的时刻为锚。"""
    nz_s = smooth(nz, 3)
    score = sm * (0.25 + nz_s)
    sscore = smooth(score, 3)

    L = max(1, int(round(dur)))
    # 跃升：当前秒 vs 前 5 秒均值
    rise = np.zeros(n)
    for i in range(n):
        base = sscore[max(0, i - 5):i]
        rise[i] = sscore[i] - (float(np.mean(base)) if len(base) else 0.0)

    lo = 10 if n > 25 else 0          # 跳过前 10 秒片头 BGM
    hi = max(lo + 1, n - 5)
    anchor = lo + int(np.argmax(rise[lo:hi]))
    method = "rise-anchor"
    if rise[anchor] < 0.2 * (float(np.mean(sscore)) + 1e-9):
        # 无明显跃升：回退到加权能量最大时刻
        anchor = lo + int(np.argmax(sscore[lo:hi]))
        method = "weighted-energy-fallback"

    start = max(0, anchor - 5)        # 事件前留 5 秒前摇
    end = start + L
    if end > n:
        end = n
        start = max(0, end - L)
    if L >= n:
        return 0, n, "event-full"
    start, end = dip_trim(sm, start, end, n)
    return start, end, method


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--duration", type=float, default=45,
                    help="高潮段目标时长（秒），默认 45")
    ap.add_argument("--mode", choices=["music", "event"], default="music",
                    help="music=能量最大窗口（副歌）；event=人群/现场声锚定（夺冠/欢呼）")
    ap.add_argument("--json", action="store_true", help="保留参数，输出恒为 JSON")
    args = ap.parse_args()

    pcm = decode_mono_16k(args.input)
    if pcm is None or len(pcm) == 0:
        print(json.dumps({"error": "decode failed"}))
        sys.exit(2)
    sr = 16000
    total = len(pcm) / sr

    dur = min(args.duration, total)
    sm_raw, n = rms_per_sec(pcm, sr)
    sm = smooth(sm_raw, 3)

    if args.mode == "event":
        nz = noisiness_per_sec(pcm, sr)
        # 尾部不足 1 秒时补齐
        if len(nz) < n:
            nz = np.pad(nz, (0, n - len(nz)), constant_values=nz[-1] if len(nz) else 0.0)
        else:
            nz = nz[:n]
        start, end, method = locate_event(sm, nz, n, dur)
    else:
        start, end, method = locate_music(sm, n, dur)

    print(json.dumps({
        "start": round(float(start), 1),
        "end": round(float(end), 1),
        "total": round(float(total), 1),
        "mode": args.mode,
        "method": method,
    }))


if __name__ == "__main__":
    main()
