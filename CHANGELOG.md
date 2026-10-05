# Changelog

skill 规则与脚本的进化记录（脱敏，只记已采纳的变更）。每周复盘提案经确认后应用，在此追加条目。

## 2026-10-06（cosplay 选材扩容）
- `references/writing-guide.md` cosplay 小剧场选材三路：①紧跟潮流——优先从本期调研素材里找当下正火的故事（热播剧/热映电影/新番/社媒热梗事件）直接 cos，角色选观众一听就知道的；②经典复刻——经典作品的经典剧情/名场面做搞笑改编后演（把原台词接到当天新闻上玩梗）；③保底库——哈利波特/名侦探柯南/樱桃小丸子/海贼王/哆啦A梦/哪吒/罗小黑战记/黑神话悟空/加勒比海盗/漫威 10 部作品随时可用。不再只从固定 10 部作品里随机选。

## 2026-10-06（推荐歌选歌逻辑）
- `bin/rank-song-candidates.py`（新增）：候选排序脚本——自动跳过已出现过的 video id、近 N 期出现过的歌手（歌手去重窗口，默认 4 期）、坏标题（现场/live/翻唱/cover/合集/精选/串烧/纯音乐类）和非官方渠道；排序"每日新歌源 ＞ upload_date 近 2 年的新歌 ＞ 中文人声优先"（upload_date 用 `yt-dlp --dump-json --skip-download` 批量取，失败则降权不剔除）。
- `bin/fresh-song-from-spotify.py`（新增）：从每日新歌歌单取新鲜候选（非 explicit、中文标题优先、去重 log 里出现过的不取；只读，不改歌单；通过 `SPOTIFY_REFRESH_STATE` 指定歌单 state 文件）。
- 选歌 query 池扩容：4 个时段词 → 24 个情绪/场景/语种细分 query（带"新歌/2026"词），按 `((date +%j - 1) * 4 + (H-8)/4) % 24` 轮换，约 7 天不撞。
- `youtube-songs.log` 新格式追加歌手字段（`日期 - 标题 - 歌手 - url`），旧行（无歌手字段）解析兼容。
- 2026-10-06 追加：现场/live 版放行——`bin/rank-song-candidates.py` 的坏标题过滤去掉 现场/live（仍跳过翻唱/cover/合集/精选/串烧与纯音乐类），搜索 query 不再强制 `official audio`；官方渠道要求不变（现场版也要求 VEVO/官方/Official/-Topic 等官方来源）。
- 2026-10-06 追加：热度排序——`bin/rank-song-candidates.py` 取 `upload_date` 的同一批 `--dump-json` 数据里已有播放量/点赞/评论数，排序加一档"热度（播放量＋点赞×10＋评论×50，从高到低）"，位于"近 2 年新歌"之后、"中文人声优先"之前（老歌即使热度再高也不反超新歌档）；取不到数据（限流等）时自动降级为之前的排序。

## 2026-10-04（多音字预检）
- `bin/prescan-chunks.py` 新增第 5 项检查：多音字纯文本预检（`POLYPHONES` watchlist）。TTS 按文本原样合成、无注音干预，误读确定性复现，只能改写成无歧义的词修复；命中即 flag 并给出改写建议。首批收录：觉字家族（睡觉/睡午觉/这觉/睡着→jiào/zháo，实测曾被误读为 jué）、表必须的"得"（děi）、一行人/行家（háng）、差不多/差点（chà）、便宜（pián）、倒闭（dǎo）、打扫（sǎo）、爱好（hào）、埋单（mái）。
- `references/writing-guide.md` "发音安全"节：多音字改写对照表（拿不准就换无歧义说法，不赌 TTS 猜对）。

## 2026-10-04（音乐轮换）
- `bin/synth-music.py` 新增 `musicpacks` 命令：预生成 7 套音乐（v0–v6），每套含片头/片尾/4 种情绪 bed；同套内整体转调＋片头变速，时长与电平和默认版严格一致（intro peak -3dB / bed 均值 -35dB / outro 均值 -30dB），混音淡入淡出时序不用改；`make_intro(shift, bpm)` / `make_outro_5(shift)` / `make_bed(transpose)` 已参数化。
- `bin/mix-episode.sh` 与 `bin/build-bed-track.py` 支持 `MUSIC_PACK` 环境变量：设置时选用对应套装的 intro/outro/bed，未设置或文件缺失时回退默认音乐，不阻塞出品。
- 定时任务模板（`references/cron-prompt-template.md`）第 9b/11 步：每期按 `V=(date +%j + 期号) % 7` 选一套，记"音乐：vN"入 topics 日志。

## 2026-10-04
- `bin/find-climax.py` 新增 `--mode event|music` 双模式：音乐类用能量最高连续段定位副歌，事件类用"能量×噪度"加权定位现场声并跳过前 10 秒片头 BGM。
- 片尾推荐歌改为必备项：取前 3 候选依次下载（android → tv_embedded → sleep 90s 后 android），3 首全失败换 query 重搜一轮，两轮 6 首全失败才记"本期无歌"；去重 log 只写最终播出的那首。
- `clip-urls.json` 新增必填 `mode` 字段（event=夺冠/欢呼/采访类，music=副歌/演唱类）。
- 人设模板新增个人偏好字段：爱好/明星/影视/歌手/运动/游戏/技能/爱吃/酒量/剁手/宠物/恋爱观/雷区。
- 人设模板新增"剧情演绎库"：10 种事件卡式小剧情（撒狗粮/反串/修罗场/吃醋/守护/回忆杀/养成打卡/贴贴/童年趣事/互相揭短），每期最多 1 个；铁律：狗粮只给官配、不拉郎配、不 OOC、揭短必须给反杀机会。

## 2026-10-06（推荐歌防旧歌升级，Jack 反馈"6年前的太老了"）
- `bin/rank-song-candidates.py`：新增年龄 veto——upload_date 超过 3 年（`--max-age-years`，默认 3）的非 fresh 候选直接淘汰；统计数据抓取加客户端 fallback（default → android → tv_embedded），默认客户端 429 限流时自动切换。
- `bin/fresh-song-from-spotify.py`：当日歌单缺失时自动回退 7 天内最新一期（之前直接报错跳过）。
- 选歌流程：fresh 候选要求 YouTube 结果标题含歌名核心词（防搜到同歌手别的歌）；query 池搜索加 `--match-filter "upload_date > 6个月前"` 只搜近 6 个月上传；query 池去掉 2 个翻唱类 query（`acoustic cover 2026`→`华语live现场新歌`、`华语翻唱新歌`→`华语打歌舞台新歌`）；rank 不足 3 个时换下一个 query 补候选重 rank，24 个 query 用完仍不足则 `--max-age-years 99` 取最优保底。
