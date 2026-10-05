#!/usr/bin/env python3
"""播客片尾推荐歌候选排序。

输入: --candidates JSON 文件，元素为 {"id", "title", "uploader", "fresh"}
      fresh=true 表示来自每日新歌源的新歌候选。
输出: stdout JSON [{"id", "title", "singer"}]，最多 --count 条。

规则（顺序执行）：
  1. 跳过 youtube-songs.log 里已出现过的 video id
  2. 跳过近 --singer-window 行 log 里出现过的歌手（歌手去重窗口）
  3. 跳过坏标题（含 翻唱/cover/合集/精选/串烧/instrumental/lofi/
     beats/ambient/piano solo/karaoke/meditation/sleep sounds；
     现场/live 版允许，不跳过）
  4. 必须官方渠道：uploader 含 VEVO/官方/Official/-Topic，或标题含
     Official Music Video/官方完整版
  5. 排序：每日新歌源(fresh) ＞ upload_date 近 2 年的新歌 ＞
     热度（播放量 + 点赞×10 + 评论×50，从高到低；YouTube 不公开收藏数，
     用这三项代替）＞ 中文标题优先
  6. 年龄 veto：upload_date 已知且超过 --max-age-years（默认 3 年）的
     非 fresh 候选直接淘汰（太老的歌不选）；若全被淘汰则输出空列表，
     调用方继续换 query 补候选再 rank；24 个 query 用完仍不足时，
     调用方可用 --max-age-years 99 关闭 veto 取最优保底。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=8))

BAD_TITLE = re.compile(
    r"翻唱|cover|合集|精选|串烧|instrumental|lofi|beats|ambient|"
    r"piano solo|karaoke|meditation|sleep sounds", re.IGNORECASE)
CJK = re.compile(r"[\u4e00-\u9fff]")
NEWNESS_DAYS = 730  # upload_date 近 2 年算新歌


def parse_log_line(line):
    """解析 youtube-songs.log 行。返回 (date, title, singer, url) 或 None。"""
    line = line.strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) - (.*) - (https?://\S+)$", line)
    if not m:
        return None
    datepart, middle, url = m.groups()
    if " - " in middle:
        title, singer = middle.rsplit(" - ", 1)
    else:
        title, singer = middle, ""
    return datepart, title.strip(), singer.strip(), url


def singer_of(uploader):
    s = (uploader or "").strip()
    s = re.sub(r"\s*-\s*Topic$", "", s)
    s = re.sub(r"VEVO$", "", s)
    return s.strip()


def is_official(uploader, title):
    u, t = (uploader or ""), (title or "")
    return ("VEVO" in u or "官方" in u or "Official" in u
            or re.search(r"-\s*Topic", u)  # "歌手 - Topic"（含空格）也要算
            or "Official Music Video" in t or "官方完整版" in t)


def fetch_stats(ytdlp, ids):
    """批量取 upload_date / view_count / like_count / comment_count。
    客户端按 default → android → tv_embedded 顺序 fallback（默认客户端
    偶发 429 限流时换客户端重试）。全部失败返回 {}。"""
    if not ids:
        return {}
    urls = ["https://www.youtube.com/watch?v=%s" % i for i in ids]
    clients = [None, "android", "tv_embedded"]
    for client in clients:
        args = [ytdlp, "--dump-json", "--skip-download", "--no-playlist",
                "--no-warnings"]
        if client:
            args += ["--extractor-args", "youtube:player_client=%s" % client]
        try:
            p = subprocess.run(args + urls, capture_output=True,
                               text=True, timeout=180)
        except Exception:
            continue
        out = {}
        for line in p.stdout.splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            vid = d.get("id")
            if not vid:
                continue
            out[vid] = {
                "upload_date": d.get("upload_date") or "",
                "view_count": d.get("view_count") or 0,
                "like_count": d.get("like_count") or 0,
                "comment_count": d.get("comment_count") or 0,
            }
        if out:
            return out
    return {}


def engagement(stats):
    """热度分：播放量 + 点赞×10 + 评论×50。"""
    return (stats.get("view_count", 0)
            + 10 * stats.get("like_count", 0)
            + 50 * stats.get("comment_count", 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--singer-window", type=int, default=4,
                    help="近 N 行 log 出现过的歌手不再选")
    ap.add_argument("--max-age-years", type=int, default=3,
                    help="upload_date 超过 N 年的非 fresh 候选直接淘汰")
    ap.add_argument("--ytdlp", default=os.environ.get(
        "YTDLP", os.path.expanduser("~/.local/bin/yt-dlp")))
    args = ap.parse_args()

    cands = json.load(open(args.candidates, encoding="utf-8"))
    if not isinstance(cands, list):
        cands = []

    used_ids, recent_singers = set(), set()
    if os.path.exists(args.log):
        with open(args.log, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        for line in lines:
            parsed = parse_log_line(line)
            if parsed:
                used_ids.add(parsed[3].rsplit("v=", 1)[-1].split("&")[0])
        for line in lines[-args.singer_window:]:
            parsed = parse_log_line(line)
            if parsed and parsed[2]:
                recent_singers.add(parsed[2].lower())

    kept = []
    for c in cands:
        vid = (c.get("id") or "").strip()
        title = c.get("title") or ""
        uploader = c.get("uploader") or ""
        if not vid or vid in used_ids:
            continue
        singer = singer_of(uploader)
        if singer and singer.lower() in recent_singers:
            continue
        if BAD_TITLE.search(title):
            continue
        if not is_official(uploader, title):
            continue
        kept.append({"id": vid, "title": title.strip(),
                     "singer": singer, "fresh": bool(c.get("fresh"))})

    stats = {}
    ytdlp = args.ytdlp if os.path.exists(args.ytdlp) else shutil.which("yt-dlp")
    if ytdlp:
        stats = fetch_stats(ytdlp, [c["id"] for c in kept])
    now = datetime.now(LOCAL_TZ)
    cutoff = (now - timedelta(days=NEWNESS_DAYS)).strftime("%Y%m%d")
    veto_cutoff = (now - timedelta(days=365 * args.max_age_years)).strftime("%Y%m%d")

    def sortkey(c):
        st = stats.get(c["id"], {})
        ud = st.get("upload_date", "")
        is_new = bool(ud and ud >= cutoff)
        is_chinese = bool(CJK.search(c["title"]) or CJK.search(c["singer"]))
        return (0 if c["fresh"] else 1,
                0 if is_new else 1,
                -engagement(st),
                0 if is_chinese else 1)

    def too_old(c):
        if c["fresh"]:
            return False
        ud = stats.get(c["id"], {}).get("upload_date", "")
        return bool(ud and ud < veto_cutoff)

    # 年龄 veto：太老的直接淘汰；全被淘汰则输出空列表，
    # 调用方换 query 补候选再 rank（24 个 query 用完仍不足时可用
    # --max-age-years 99 关闭 veto 取最优保底）
    kept = [c for c in kept if not too_old(c)]

    kept.sort(key=sortkey)
    out = [{"id": c["id"], "title": c["title"], "singer": c["singer"]}
           for c in kept[:args.count]]
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
