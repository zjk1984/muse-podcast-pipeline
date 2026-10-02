#!/usr/bin/env python3
"""合成整点快报的新版片头曲 (intro.mp3) 和背景音乐 (bed.mp3)。

风格借鉴专业新闻播客：
- 片头：6 秒新闻 jingle —— 强起拍 logo 音 + 128BPM 级别的驱动鼓组 + 明亮 synth 动机，
  目标：响亮、有记忆点、收尾干净（新闻播客式，不是 fade out）。
- 背景：96 秒无缝循环 ambient pad（Am-F-C-G），只铺底、不抢人声，目标均值 -35dB。

用法: python3 synth-music.py
输出: /tmp/new-intro.mp3 /tmp/new-bed.mp3（检查通过后再手动装到 assets/）
"""
import numpy as np
import subprocess
import os

SR = 44100


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def env_ad(n, a, d, s_level=0.0):
    """attack-decay 包络（a/d 为秒）"""
    na = max(1, int(a * SR))
    nd = max(1, int(d * SR))
    e = np.ones(n)
    e[:na] = np.linspace(0, 1, na)
    if na + nd <= n:
        e[na:na + nd] = np.linspace(1, s_level, nd)
        e[na + nd:] = s_level
    else:
        e[na:] = np.linspace(1, s_level, n - na)
    return e


def lowpass(x, cutoff):
    """一阶低通，柔化锯齿波毛刺"""
    rc = 1.0 / (2 * np.pi * cutoff)
    dt = 1.0 / SR
    alpha = dt / (rc + dt)
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha * (x[i] - acc)
        y[i] = acc
    return y


def highpass(x, cutoff):
    return x - lowpass(x, cutoff)


def saw(f, n, detune_cents=(0, 5, -5)):
    t = np.arange(n) / SR
    y = np.zeros(n)
    for c in detune_cents:
        ff = f * 2 ** (c / 1200.0)
        y += 2 * ((ff * t) % 1.0) - 1.0
    return y / len(detune_cents)


def kick(n):
    t = np.arange(n) / SR
    f = 45 + (160 - 45) * np.exp(-t * 40)
    ph = np.cumsum(f) / SR
    y = np.sin(2 * np.pi * ph) * np.exp(-t * 14)
    y += 0.4 * np.random.randn(n) * np.exp(-t * 120)  # click
    return y


def clap(n):
    y = highpass(np.random.randn(n), 1200)
    return y * env_ad(n, 0.002, 0.16)


def hat(n, open_=False):
    y = highpass(np.random.randn(n), 7500)
    return y * env_ad(n, 0.001, 0.035 if not open_ else 0.25)


def crash(n):
    y = highpass(np.random.randn(n), 4500)
    return y * env_ad(n, 0.002, 1.1)


def riser(n):
    y = np.random.randn(n)
    # 截止频率随时间上升的扫频感（分段近似）
    segs = 8
    out = np.zeros(n)
    chunk = n // segs
    for i in range(segs):
        c = 500 * (2 ** (i * 0.55))
        s = slice(i * chunk, (i + 1) * chunk if i < segs - 1 else n)
        out[s] = lowpass(y[s], c)
    return out * np.linspace(0.1, 1.0, n) ** 2


def simple_verb(x, delays=(0.09, 0.17, 0.29), gains=(0.35, 0.22, 0.13)):
    y = x.copy()
    for d, g in zip(delays, gains):
        nd = int(d * SR)
        if nd < len(x):
            y[nd:] += g * x[:-nd]
    return y


def place(track, y, t0):
    i0 = int(t0 * SR)
    i1 = min(len(track), i0 + len(y))
    if i1 > i0:
        track[i0:i1] += y[:i1 - i0]


def normalize_peak(x, db):
    peak = np.max(np.abs(x)) + 1e-9
    return x / peak * 10 ** (db / 20.0)


def normalize_mean(x, db):
    rms = np.sqrt(np.mean(x ** 2)) + 1e-9
    return x / rms * 10 ** (db / 20.0)


def to_mp3(x, path):
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype(np.int16)
    # 立体声（左右微差，增加宽度）
    stereo = np.stack([pcm, pcm], axis=1)
    raw = "/tmp/_synth.raw"
    stereo.tofile(raw)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", raw,
         "-c:a", "libmp3lame", "-b:a", "128k", path],
        check=True,
    )
    os.remove(raw)


# ---------------- 片头 6 秒 ----------------
def make_intro():
    dur = 6.0
    n = int(dur * SR)
    t = np.zeros(n)
    bpm = 132.0
    beat = 60.0 / bpm
    eighth = beat / 2

    # 0.0 强起拍 logo
    place(t, kick(int(0.3 * SR)), 0.0)
    place(t, crash(int(1.2 * SR)) * 0.7, 0.0)
    stab = sum(saw(midi(m), int(0.5 * SR)) for m in (57, 60, 64)) / 3
    place(t, lowpass(stab, 2500) * env_ad(int(0.5 * SR), 0.005, 0.4) * 0.8, 0.0)

    # 0.2–3.6 groove：kick 四拍、反拍 hat、2/4 拍 clap
    nb = 8  # 8 拍
    for b in range(nb):
        bt = 0.2 + b * beat
        place(t, kick(int(0.25 * SR)) * 0.9, bt)
        place(t, hat(int(0.05 * SR)) * 0.35, bt + eighth)
        if b % 4 == 1 or b % 4 == 3:
            place(t, clap(int(0.2 * SR)) * 0.6, bt)
    # bass 8 分音符：A1 x4, F1 x4
    for i in range(16):
        bt = 0.2 + i * eighth
        root = 33 if i < 8 else 29  # A1 / F1
        bl = int(0.19 * SR)
        b = lowpass(saw(midi(root), bl), 500) * env_ad(bl, 0.005, 0.15) * 0.55
        place(t, b, bt)
    # lead 动机（新闻感上扬乐句）
    motif = [69, 76, 79, 81, 84, 83, 81, 79]  # A4 E5 G5 A5 C6 B5 A5 G5
    for i, m in enumerate(motif):
        bt = 0.2 + i * eighth
        ln = int(0.21 * SR)
        lead = lowpass(saw(midi(m), ln), 3200) * env_ad(ln, 0.008, 0.18) * 0.5
        place(t, lead, bt)

    # 3.8–4.5 riser + snare roll
    place(t, riser(int(0.7 * SR)) * 0.5, 3.8)
    for i in range(6):
        place(t, clap(int(0.12 * SR)) * (0.3 + 0.1 * i), 3.8 + i * 0.115)

    # 4.55 最终 logo hit：大鼓 + crash + Am 和弦 sustain
    place(t, kick(int(0.4 * SR)) * 1.0, 4.55)
    place(t, crash(int(1.4 * SR)) * 0.8, 4.55)
    chn = int(1.4 * SR)
    chord = sum(saw(midi(m), chn) for m in (57, 60, 64, 69)) / 4
    chord = lowpass(chord, 2800) * env_ad(chn, 0.01, 1.2) * 0.85
    chord = simple_verb(chord)
    place(t, chord, 4.55)

    t = normalize_peak(t, -3.0)
    # 结尾 0.15 秒淡出，避免截断爆音
    nf = int(0.15 * SR)
    t[-nf:] *= np.linspace(1, 0, nf)
    return t


# ---------------- 背景 96 秒无缝循环 ----------------
def make_bed(chords=None, arp_notes=None, arp_step=0.3, arp_gain=0.10,
             lp_cutoff=750, level_db=-35.0):
    block = 8.0
    if chords is None:
        chords = [  # Am F C G x3 = 96s（默认沉稳新闻垫）
            (57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62),
        ] * 3
    if arp_notes is None:
        arp_notes = [69, 72, 74, 76, 79, 81, 79, 76, 74, 72]
    total = block * len(chords)
    # 多渲染 2 秒：让最后一块和弦的 release 包络绕回到开头，保证无缝循环
    n = int((total + 2.0) * SR)
    t = np.zeros(n)

    # pad：每块和弦，2.5s 慢 attack，与下一块 2s 交叉淡化
    for ci, ch in enumerate(chords):
        bn = int((block + 2.0) * SR)
        pad = np.zeros(bn)
        for m in ch:
            for octv in (0, 12):
                pad += saw(midi(m + octv), bn, detune_cents=(0, 6, -6))
        pad = pad / (len(ch) * 2)
        pad = lowpass(pad, lp_cutoff)
        na = int(2.5 * SR)
        e = np.ones(bn)
        e[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)  # raised cosine
        e[-int(2.0 * SR):] = 0.5 + 0.5 * np.cos(np.pi * np.arange(int(2.0 * SR)) / int(2.0 * SR))
        pad *= e * 0.5
        place(t, pad, ci * block)

    # arp：五声音阶轻拨，音量很低
    penta = arp_notes
    step = arp_step
    nsteps = int(total / step)
    for i in range(nsteps):
        m = penta[i % len(penta)]
        ln = int(0.28 * SR)
        tt = np.arange(ln) / SR
        pluck = (np.sin(2 * np.pi * midi(m) * tt)
                 + 0.3 * np.sin(2 * np.pi * midi(m) * 2 * tt)
                 + 0.12 * np.sin(2 * np.pi * midi(m) * 3 * tt))
        pluck = lowpass(pluck, 1800) * np.exp(-tt * 9) * arp_gain
        # 每 4.8s 一个呼吸起伏，避免机械感
        ph = (i * step) % 4.8 / 4.8
        pluck *= 0.7 + 0.3 * np.sin(2 * np.pi * ph)
        place(t, pluck, i * step)

    t = normalize_mean(t, level_db)
    # 绕回：96–98s 的尾巴叠到 0–2s，再截到 96s
    wrap = int(2.0 * SR)
    t[:wrap] += t[int(total * SR):int(total * SR) + wrap]
    t = t[:int(total * SR)]
    return t


def make_bed_variants():
    """生成 bed2/3/4 三种情绪变体（与 bed1 同响度 -35dB，同为 96s 无缝循环）。"""
    tense_chords = [(57, 60, 64), (57, 60, 64), (53, 57, 60), (52, 56, 59)] * 3  # Am Am F E
    upbeat_chords = [(48, 52, 55), (55, 59, 62), (57, 60, 64), (53, 57, 60)] * 3  # C G Am F
    warm_chords = [(53, 57, 60), (48, 52, 55), (55, 59, 62), (57, 60, 64)] * 3  # F C G Am
    to_mp3(make_bed(chords=tense_chords, arp_notes=[57, 60, 62, 64, 67, 69, 67, 64, 62, 60],
                    arp_step=0.45, arp_gain=0.05, lp_cutoff=600), "/tmp/new-bed2.mp3")
    to_mp3(make_bed(chords=upbeat_chords, arp_step=0.25, arp_gain=0.11,
                    lp_cutoff=950), "/tmp/new-bed3.mp3")
    to_mp3(make_bed(chords=warm_chords, arp_step=0.35, arp_gain=0.08,
                    lp_cutoff=700), "/tmp/new-bed4.mp3")
    print("done: /tmp/new-bed2.mp3 /tmp/new-bed3.mp3 /tmp/new-bed4.mp3")


# ---------------- 片尾 90 秒 ----------------
# 新闻播客式片尾：温暖收束，把片头的动机用柔和的"钢琴"音色再陈述一遍，
# 同一和声进行（Am-F-C-G）保证和正片 bed 的连贯感，最后 logo 和弦 + 长尾淡出。
def piano_note(f, n):
    t = np.arange(n) / SR
    y = (np.sin(2 * np.pi * f * t)
         + 0.35 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 3)
         + 0.15 * np.sin(2 * np.pi * f * 3 * t) * np.exp(-t * 5)
         + 0.06 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 7))
    return y * env_ad(n, 0.008, 1.6) * 0.5


def shaker(n):
    y = highpass(np.random.randn(n), 6000)
    return y * env_ad(n, 0.002, 0.06) * 0.10


def make_outro():
    dur = 90.0
    n = int(dur * SR)
    t = np.zeros(n)
    bpm = 100.0
    beat = 60.0 / bpm

    # 和声：Am F C G Am F C G Am，每块 10 秒
    prog = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62),
            (57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62),
            (57, 60, 64)]
    block = 10.0
    for ci, ch in enumerate(prog):
        bn = int((block + 3.0) * SR)
        pad = np.zeros(bn)
        for m in ch:
            for octv in (0, 12):
                pad += saw(midi(m + octv), bn, detune_cents=(0, 6, -6))
        pad = pad / (len(ch) * 2)
        pad = lowpass(pad, 650)
        na = int(3.0 * SR)
        e = np.ones(bn)
        e[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
        e[-int(3.0 * SR):] = 0.5 + 0.5 * np.cos(np.pi * np.arange(int(3.0 * SR)) / int(3.0 * SR))
        pad *= e * 0.42
        place(t, pad, ci * block)
        # 每块根音贝斯（正弦，柔和）
        bl = int(9.0 * SR)
        bt = np.arange(bl) / SR
        bass = np.sin(2 * np.pi * midi(ch[0] - 24) * bt) * env_ad(bl, 0.05, 8.0) * 0.30
        place(t, lowpass(bass, 300), ci * block + 0.5)

    # 动机再陈述：片头的上扬乐句，慢速、柔和（每块一次，0–70s）
    motif = [69, 76, 79, 81, 84, 83, 81, 79]
    for ci in range(7):
        base = ci * block + 1.0
        for i, m in enumerate(motif):
            ln = int(0.9 * SR)
            place(t, piano_note(midi(m), ln), base + i * 0.62)

    # 轻 shaker：20–70s，8 分音符，很轻
    st = int(20.0 * SR)
    en = int(70.0 * SR)
    i = st
    while i < en:
        ln = int(0.09 * SR)
        if i + ln <= len(t):
            t[i:i + ln] += shaker(ln)
        i += int(beat / 2 * SR)

    # 78s 起收束：稀疏的动机碎片 + 最终 logo 和弦
    for k, m in enumerate([81, 79, 76, 72]):
        place(t, piano_note(midi(m), int(1.4 * SR)) * 0.8, 74.0 + k * 1.1)
    chn = int(11.0 * SR)
    chord = sum(saw(midi(m), chn) for m in (45, 57, 60, 64, 71)) / 5  # Am(add9)
    chord = lowpass(chord, 2200) * env_ad(chn, 0.02, 9.0) * 0.7
    chord = simple_verb(chord)
    place(t, chord, 78.0)

    # 开头 3s 淡入（混音脚本还会再加 4s 淡入，双保险防爆音）
    nf = int(3.0 * SR)
    t[:nf] *= np.linspace(0, 1, nf)
    # 结尾 8s 淡出到数字静音
    nf = int(8.0 * SR)
    t[-nf:] *= np.linspace(1, 0, nf) ** 1.5

    t = normalize_mean(t, -30.0)
    return t


def make_outro_5():
    dur = 5.0
    n = int(dur * SR)
    t = np.zeros(n)

    # 温暖 pad：Am，0–3.4s
    bn = int(3.4 * SR)
    pad = np.zeros(bn)
    for m in (57, 60, 64):
        for octv in (0, 12):
            pad += saw(midi(m + octv), bn, detune_cents=(0, 6, -6))
    pad = pad / 6
    pad = lowpass(pad, 650)
    na = int(0.3 * SR)
    e = np.ones(bn)
    e[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    e[-int(1.0 * SR):] = 0.5 + 0.5 * np.cos(np.pi * np.arange(int(1.0 * SR)) / int(1.0 * SR))
    pad *= e * 0.42
    place(t, pad, 0.0)
    # 根音贝斯（正弦，柔和）
    bl = int(3.0 * SR)
    bt = np.arange(bl) / SR
    bass = np.sin(2 * np.pi * midi(57 - 24) * bt) * env_ad(bl, 0.05, 2.8) * 0.30
    place(t, lowpass(bass, 300), 0.2)

    # 动机陈述（缩短版）：0.5s 起
    motif = [69, 76, 79, 81, 84, 81, 79]
    for i, m in enumerate(motif):
        ln = int(0.6 * SR)
        place(t, piano_note(midi(m), ln), 0.5 + i * 0.42)

    # 收束：2.6s 起 logo 和弦 Am(add9)
    chn = int(2.4 * SR)
    chord = sum(saw(midi(m), chn) for m in (45, 57, 60, 64, 71)) / 5
    chord = lowpass(chord, 2200) * env_ad(chn, 0.02, 2.2) * 0.7
    chord = simple_verb(chord)
    place(t, chord, 2.6)

    # 开头 0.3s 淡入
    nf = int(0.3 * SR)
    t[:nf] *= np.linspace(0, 1, nf)
    # 结尾 1.5s 淡出到数字静音
    nf = int(1.5 * SR)
    t[-nf:] *= np.linspace(1, 0, nf) ** 1.5

    t = normalize_mean(t, -30.0)
    return t


# ---------------- 片尾 10 秒（短版） ----------------
# 新闻播客式短片尾：温暖 pad（Am）＋动机陈述一次（柔和钢琴）＋收束 logo 和弦，
# 末 2.5s 淡出到静音。接在正片后、推荐歌曲前。
def make_outro_short():
    dur = 10.0
    n = int(dur * SR)
    t = np.zeros(n)

    # 温暖 pad：Am，0–7s
    bn = int(7.5 * SR)
    pad = np.zeros(bn)
    for m in (57, 60, 64):
        for octv in (0, 12):
            pad += saw(midi(m + octv), bn, detune_cents=(0, 6, -6))
    pad = pad / 6
    pad = lowpass(pad, 650)
    na = int(0.5 * SR)
    e = np.ones(bn)
    e[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    e[-int(1.5 * SR):] = 0.5 + 0.5 * np.cos(np.pi * np.arange(int(1.5 * SR)) / int(1.5 * SR))
    pad *= e * 0.42
    place(t, pad, 0.0)
    # 根音贝斯（正弦，柔和）
    bl = int(7.0 * SR)
    bt = np.arange(bl) / SR
    bass = np.sin(2 * np.pi * midi(57 - 24) * bt) * env_ad(bl, 0.05, 6.5) * 0.30
    place(t, lowpass(bass, 300), 0.3)

    # 动机陈述一次：0.8s 起（片头的上扬乐句，慢速柔和）
    motif = [69, 76, 79, 81, 84, 83, 81, 79]
    for i, m in enumerate(motif):
        ln = int(0.9 * SR)
        place(t, piano_note(midi(m), ln), 0.8 + i * 0.62)

    # 收束：6.8s 起 logo 和弦 Am(add9)
    chn = int(3.2 * SR)
    chord = sum(saw(midi(m), chn) for m in (45, 57, 60, 64, 71)) / 5
    chord = lowpass(chord, 2200) * env_ad(chn, 0.02, 3.0) * 0.7
    chord = simple_verb(chord)
    place(t, chord, 6.8)

    # 开头 0.5s 淡入（混音脚本还会再加 4s 淡入，双保险防爆音）
    nf = int(0.5 * SR)
    t[:nf] *= np.linspace(0, 1, nf)
    # 结尾 2.5s 淡出到数字静音
    nf = int(2.5 * SR)
    t[-nf:] *= np.linspace(1, 0, nf) ** 1.5

    t = normalize_mean(t, -30.0)
    return t


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "variants":
        make_bed_variants()
    elif len(sys.argv) > 1 and sys.argv[1] == "outro10":
        outro10 = make_outro_short()
        to_mp3(outro10, "/tmp/new-outro10.mp3")
        print("done: /tmp/new-outro10.mp3")
    elif len(sys.argv) > 1 and sys.argv[1] == "outro5":
        outro5 = make_outro_5()
        to_mp3(outro5, "/tmp/new-outro5.mp3")
        print("done: /tmp/new-outro5.mp3")
    else:
        intro = make_intro()
        to_mp3(intro, "/tmp/new-intro.mp3")
        bed = make_bed()
        to_mp3(bed, "/tmp/new-bed.mp3")
        outro = make_outro()
        to_mp3(outro, "/tmp/new-outro.mp3")
        print("done: /tmp/new-intro.mp3 /tmp/new-bed.mp3 /tmp/new-outro.mp3")
