#!/usr/bin/env python3
"""整点快报 TTS 预扫：逐行合成，查截断和异常安静。

TTS 对同一文本的输出是确定性的——某行合成出来是截断/特别轻，
整篇生成时也会一样。预扫在整篇生成前把问题行揪出来改写，
避免整篇返工。

用法: python3 prescan-chunks.py <script.txt> [--voices 周周=avoice,小夏=bvoice...] [--workers 6]
默认音色：周周=avocado_v2:MAI_01 小夏=avocado_v2:MAI_03 阿飒=avocado_v2:rumi
          悠悠=avocado_v2:ronan 买买提=avocado_v2:briggs

合成阶段用线程池并行（默认 6 并发），150 行左右的脚本从 ~10 分钟压到 ~2 分钟。

检查每行：
1. 截断：输出字节数 < 2000 或 tts 返回非 ok → 触发词问题，需改写。
   注意区分确定性截断（约 576 字节，重试无用）与瞬态失败（网络/超时，
   会自动重试 2 次）。
2. 音量：mean_volume 比该说话人中位数低 6dB 以上 → 异常安静，需改写。
3. 时长：实际音频时长超过期望时长 1.6 倍、且多出 3 秒以上
   → TTS 循环/口吃（整句被重复合成），需改写（通常是英文词或特殊
   组合触发，改法：把英文词换成中文描述，或拆短句）。
   期望时长用 expected_dur() 估算：中文 4.5 字/秒，英文单词折 2 字，
   空格分隔的孤立字母（如 B T S）每字母计 1 字——直接用字数/4.5 会
   高估英文行的期望时长，让循环从阈值漏网（2026-10-01 21 点期实测）。
4. 句内静音：单行音频里出现 ≥2.5 秒的静音（句首/句中/句尾）→ TTS 停顿
   注入或把句子切碎（2026-10-01 实测：小夏一句 30 字合成出 2.7 秒语音
   + 8.5 秒尾部静音，时长比 1.67x、音量只低 5dB，两项检查都漏过，
   RSS 里 4:13–4:20 整整 7 秒没对白），需改写。

缓存：(voice, text) 的合成结果缓存在 prescan-cache.json（7 天有效），
改写后重跑只测改过的行。

通过打印"预扫通过。" exit 0；否则打印问题清单 exit 1。
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_VOICES = {
    "周周": "avocado_v2:MAI_01",
    "小夏": "avocado_v2:MAI_03",
    "阿飒": "avocado_v2:rumi",
    "悠悠": "avocado_v2:ronan",
    "买买提": "avocado_v2:briggs",
}
THRESHOLD_DB = 6.0
MIN_BYTES = 2000
CHARS_PER_SEC = 4.5  # 中文 TTS 语速，用于估算期望时长
DUR_RATIO = 1.6  # 实际时长超过期望 1.6 倍且多出 3 秒以上，视为 TTS 循环/口吃
# （实测：某期 12:10–12:20 段落重复：根因是英文行
#  用"字数/4.5"估算期望时长会高估——"Billboard Boxscore"18 个字母被当成
#  18 个中文字，期望 11.6s、实际循环 19.5s 才 1.68x，从 1.8x 阈值漏网；
#  改用 expected_dur() 按中英分别估算后真值约 2.3x，1.6x 可靠拦截。
#  全期 152 行实测：除该行 1.69x（新估算 2.24x）外最高仅 1.42x，阈值 1.6 有裕量。）
MAX_SILENCE = 2.5  # 单行音频里单段静音 ≥2.5 秒，视为 TTS 停顿注入/切碎
TTS_TIMEOUT = 90  # 单行合成超时（秒），防 hang
FF_TIMEOUT = 30
RETRIES = 2  # 瞬态失败重试次数（576 字节确定性截断不重试）
CACHE_TTL = 7 * 24 * 3600
MAX_WORKERS = 6  # 合成并发数
# 缓存位置：PODCAST_CACHE 环境变量优先，默认 ./cache/prescan-cache.json
# （行音频缓存在同目录下的 prescan-audio/）
CACHE_PATH = os.environ.get("PODCAST_CACHE", "./cache/prescan-cache.json")


def run(cmd, timeout=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "")
        return out + "\n[TIMEOUT]", -1


def cache_key(voice, text):
    return hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()[:16]


def load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        # 丢弃过期条目
        return {k: v for k, v in data.items()
                if now - v.get("ts", 0) < CACHE_TTL}
    except Exception:
        return {}


def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def parse_script(path):
    rows = []
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(周周|小夏|阿飒|悠悠|买买提)\s*[:：]\s*(.*)$", line)
        if m:
            rows.append((i, m.group(1), m.group(2)))
    return rows


def synth(voice, text, outpath):
    """合成一行。返回 (result_dict, is_transient_failure)。
    576 字节级截断是确定性的，不重试；超时/网络类失败重试。"""
    last = {}
    for attempt in range(RETRIES + 1):
        out, _ = run(
            ["tts", "speak", "--voice", voice, "--text", text,
             "--output", outpath, "--language", "zh"],
            timeout=TTS_TIMEOUT,
        )
        # 取最后一行 JSON
        r = {}
        for line in reversed(out.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    r = json.loads(line)
                    break
                except Exception:
                    pass
        last = r
        ok = r.get("ok") is True
        nbytes = r.get("bytes", 0)
        if ok and nbytes >= MIN_BYTES:
            return r, False
        # 确定性截断（~576 字节）：重试无用，直接返回
        if 400 <= nbytes <= 800:
            return r, False
        # 瞬态失败：超时标记、空输出、非 ok，睡一下再试
        if attempt < RETRIES:
            time.sleep(2 * (attempt + 1))
    return last, True


def mean_volume(mp3):
    out, _ = run(
        ["ffmpeg", "-hide_banner", "-i", mp3,
         "-af", "volumedetect", "-f", "null", "-"],
        timeout=FF_TIMEOUT,
    )
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", out)
    return float(m.group(1)) if m else None


def expected_dur(text):
    """估算 TTS 时长（秒）：中文按 4.5 字/秒；英文单词折 2 个字
    （如 Billboard→2，TTS 读英文词比逐字快）；空格分隔的孤立字母
    （如 B T S）按每字母 1 个字计（TTS 逐字母慢读）。"""
    t = text
    units = 0
    spaced = r"(?<![A-Za-z'])[A-Za-z](?: [A-Za-z])+(?![A-Za-z])"
    for m in re.findall(spaced, t):
        units += len(m.replace(" ", ""))
    t = re.sub(spaced, "", t)
    words = re.findall(r"[A-Za-z]+", t)
    units += 2 * len(words)
    t = re.sub(r"[A-Za-z]+", "", t)
    units += len(t)
    return units / CHARS_PER_SEC


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def silence_gaps(mp3):
    """返回行音频里的静音段 [(start, end, dur)]（阈值 -45dB，≥1.0 秒才记录）。"""
    out, _ = run(
        ["ffmpeg", "-hide_banner", "-i", mp3,
         "-af", "silencedetect=noise=-45dB:d=1.0", "-f", "null", "-"],
        timeout=FF_TIMEOUT,
    )
    gaps = []
    starts = re.findall(r"silence_start:\s*([\d.]+)", out)
    ends = re.findall(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", out)
    for s, (e, d) in zip(starts, ends):
        gaps.append((float(s), float(e), float(d)))
    return gaps


def duration(mp3):
    out, _ = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", mp3],
        timeout=FF_TIMEOUT,
    )
    try:
        return float(out.strip().split()[0])
    except Exception:
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python3 prescan-chunks.py <script.txt> [--workers 6]")
        return 2
    script = sys.argv[1]
    voices = dict(DEFAULT_VOICES)
    workers = MAX_WORKERS
    for arg in sys.argv[2:]:
        if arg.startswith("--voices"):
            for pair in arg.split("=", 1)[1].split(","):
                k, v = pair.split("=", 1)
                voices[k] = v
        elif arg.startswith("--workers"):
            try:
                workers = max(1, int(arg.split("=", 1)[1]))
            except Exception:
                pass
    rows = parse_script(script)
    if not rows:
        print("脚本里没有可解析的台词行")
        return 2
    cache = load_cache()
    lock = threading.Lock()
    tmpd = tempfile.mkdtemp(prefix="prescan-")
    total = len(rows)
    results = [None] * total  # 按行号顺序：(lineno, speaker, text, ok, bytes, db, dur, note, audiopath)
    cache_hits = [0]
    done = [0]

    def process(idx, lineno, speaker, text):
        """处理一行：查缓存或并行合成。返回结果元组（末位为是否缓存命中）。"""
        if not text:
            return (lineno, speaker, text, False, 0, None, None, "空台词", None, False)
        voice = voices.get(speaker)
        if not voice:
            return (lineno, speaker, text, False, 0, None, None, "未知说话人", None, False)
        key = cache_key(voice, text)
        with lock:
            hit = cache.get(key)
        if hit and os.path.exists(hit.get("path", "")):
            with lock:
                cache_hits[0] += 1
            return (lineno, speaker, text, True, hit["bytes"], hit["db"],
                    hit["dur"], "", hit.get("path"), True)
        outpath = os.path.join(tmpd, f"c{idx}.mp3")
        r, transient = synth(voice, text, outpath)
        ok = r.get("ok") is True
        nbytes = r.get("bytes", 0)
        if transient:
            return (lineno, speaker, text, False, nbytes, None, None,
                    "瞬态失败（已重试)，请稍后重跑预扫", None, False)
        db = mean_volume(outpath) if ok and os.path.exists(outpath) else None
        dur = duration(outpath) if ok and os.path.exists(outpath) else None
        note = ""
        audiopath = None
        good = ok and nbytes >= MIN_BYTES
        if not good:
            note = f"截断/失败(bytes={nbytes})"
        elif db is not None and dur is not None:
            cdir = os.path.join(os.path.dirname(CACHE_PATH), "prescan-audio")
            os.makedirs(cdir, exist_ok=True)
            cpath = os.path.join(cdir, f"{key}.mp3")
            try:
                shutil.move(outpath, cpath)
            except Exception:
                cpath = outpath
            with lock:
                cache[key] = {"bytes": nbytes, "db": db, "dur": dur,
                              "path": cpath, "ts": time.time()}
            audiopath = cpath
        return (lineno, speaker, text, good, nbytes, db, dur, note, audiopath, False)

    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(process, idx, lineno, speaker, text): idx
                    for idx, (lineno, speaker, text) in enumerate(rows)}
            for fut in as_completed(futs):
                res = fut.result()
                idx = futs[fut]
                results[idx] = res
                (lineno, speaker, text, ok, nbytes, db, dur,
                 note, audiopath, cached) = res
                with lock:
                    done[0] += 1
                    n = done[0]
                exp = expected_dur(text)
                dur_s = f"{dur:.1f}s" if dur else "-"
                cmark = " [缓存]" if cached else ""
                print(f"[{n}/{total}] L{lineno} {speaker} {db if db else '-'}dB "
                      f"{dur_s}(期望~{exp:.0f}s){cmark} {note}", flush=True)
    finally:
        for f in os.listdir(tmpd):
            try:
                os.remove(os.path.join(tmpd, f))
            except Exception:
                pass
        try:
            os.rmdir(tmpd)
        except Exception:
            pass
        save_cache(cache)
    if cache_hits[0]:
        print(f"（{cache_hits[0]} 行命中缓存，未重新合成）")

    by_speaker_db = {}
    for (lineno, speaker, text, ok, nbytes, db, dur,
         note, audiopath, cached) in results:
        if db is not None and db > -60:
            by_speaker_db.setdefault(speaker, []).append(db)
    med = {sp: median(v) for sp, v in by_speaker_db.items() if len(v) >= 3}

    bad = []  # (lineno, speaker, text, reason)
    gap_targets = []  # 需要跑句内静音检查的行
    for (lineno, speaker, text, ok, nbytes, db, dur,
         note, audiopath, cached) in results:
        if not ok:
            bad.append((lineno, speaker, text, f"合成截断/失败：{note}"))
            continue
        if db is not None and speaker in med and med[speaker] - db > THRESHOLD_DB:
            bad.append((lineno, speaker, text,
                        f"异常安静 {db:.1f}dB（{speaker}中位数 {med[speaker]:.1f}dB）"))
        exp = expected_dur(text)
        if dur is not None and dur > exp * DUR_RATIO and dur - exp > 3.0:
            bad.append((lineno, speaker, text,
                        f"时长异常 {dur:.1f}s（期望~{exp:.0f}s），疑似 TTS 循环重复"))
        if audiopath and os.path.exists(audiopath):
            gap_targets.append((lineno, speaker, text, dur, audiopath))

    # 句内静音检查（并行，行音频小文件，ffmpeg 很快）
    def check_gap(item):
        lineno, speaker, text, dur, audiopath = item
        gaps = silence_gaps(audiopath)
        long_gaps = [g for g in gaps if g[2] >= MAX_SILENCE]
        if not long_gaps:
            return None
        s, e, d = max(long_gaps, key=lambda g: g[2])
        total_d = dur or 0
        pos = "句首" if s < 0.5 else ("句尾" if e > total_d - 0.5 else "句中")
        return (lineno, speaker, text, f"句内{pos}静音 {d:.1f}s，疑似 TTS 停顿注入/切碎")

    if gap_targets:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(check_gap, gap_targets):
                if r:
                    bad.append(r)

    bad.sort(key=lambda b: b[0])
    if not bad:
        print("预扫通过。")
        return 0
    print(f"\n发现 {len(bad)} 个问题行：")
    for lineno, sp, text, reason in bad:
        print(f" - L{lineno} [{sp}] {reason}: {text[:50]}")
    print("处理：最小改写这些行（换词/拆句，不改原意），跑 check-script.py，再跑本预扫，直到通过。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
