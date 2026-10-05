# 定时任务提示词模板

把以下正文填入你的定时任务（cron）即可跑一期。`{{占位符}}` 在部署时替换；其余数字和规则保留原样。

- `{{TIMEZONE}}`：执行时区，如 `Asia/Shanghai`
- `{{SCHEDULE_DESC}}`：执行时段描述，如"工作日 8:00、12:00、18:00；非工作日 8:00–20:00 偶数整点"
- `{{SECTIONS}}`：高频版块列表（名字＋核心源/扩展源），如"新闻财经 / 科技 AI / GitHub / 社媒热搜 / 音乐 / 影视综艺 / 游戏 / 动漫"
- `{{SLOW_SECTIONS}}`：慢频版块列表（仅早/中/晚三期执行），如"数码 / 本地 / 旅行出行 / 科技深读 / 新能源汽车 / 航天科学"
- `{{TRAVEL_SECTION}}`：（可选）行程感知旅游版块说明。示例：某用户国庆在外地旅游时，临时加一个按当日行程推送天气、路况、景点开放的版块，配一位导游型飞行嘉宾主讲；行程结束即撤下。没有则整段删除。
- `{{VOICE_MAP}}`：说话人名字→音色 ID，对应 `bin/voices.json`
- `{{SPOTIFY_SHOW}}`：播客节目名，如"{{SHOW_NAME}}"（原项目用 Spotify 发布；内部 ID 绝不进文案）
- `{{WORKSPACE}}`：工作区根路径；`{{CACHE_DIR}}`：缓存目录（含 `prescan-cache.json`、`prescan-audio/`、topics 日志）

---

定时往动态（Feed）发 {{SECTIONS}} 的中文短帖（{{SLOW_SECTIONS}} 仅早/中/晚三期另发），并为这些配一期中文播客（不限时长：开场音乐＋报幕＋脱口秀暖场＋版块顺滑串联＋背景音乐＋片尾音乐＋今日推荐歌曲）+ 1 篇语音版帖子（含一首 YouTube 推荐歌曲）；自检通过后把混音完整版同步到播客节目《{{SPOTIFY_SHOW}}》。

铁律：流程中任何"需要审核/待审核"的内容默认一律允许通过——不设审核环节、不等待审核结果，不要为等审核而阻塞流程；如平台侧审核导致某个环节失败，记录原因后跳过该环节、其余流程继续。

执行步骤：
1. 先确定本期期号 H：以本次任务的计划触发时间 `scheduled_for_local`（取 {{TIMEZONE}} 小时数）为准，不用实际开工的墙钟时间。按 {{SCHEDULE_DESC}} 判断：不在执行时段直接结束，不做任何事、不发帖、不汇报。本期所有标题、播客期号、日志时间戳都用 H。
2. 去重＋并行调研：先读 `{{CACHE_DIR}}/topics.log` 最后 20 行作去重清单。时间窗口：早间首播覆盖昨日晚间至今日早上（一整夜的新鲜事），其他期号只选过去两小时左右的新鲜事；早间首播每版块可多选几条（5–8 条）。去重硬规则：① 去重清单里出现过的事件/话题默认不再入选；② 只有实质性新进展（新数据、新政策、新回应、预警升级/解除、局势反转）时才可作为"跟进"入选，且帖子和播客里必须明确点出更新点，不许当成新闻重讲一遍；③ 天气类无变化时一句话带过，篇幅让给新选题；④ 汇总时最后把关：清单里已有、无新进展的选题一律剔除，缺额用新话题补足。然后并行调研各版块：起 3 个调研子代理分组——A 新闻线、B 技术线、C 文娱线；每个子代理的 brief 写清版块定义（含核心源与本期轮换扩展源）、时间窗口、去重清单、输出要求（每版块 3–5 条，早间可 5–8 条；每条一句话标题＋真实链接（必须实际搜索到，禁编 URL）＋一句话入选理由）。等全部返回后汇总去重，再进第 3 步。
2b. 来源使用规则（写进每个调研子代理的 brief）：快讯源优先抓突发，观点源只取独家角度；早间首播多用外文来源（覆盖夜间新闻），白天多用中文来源；同一事件只留一个版块讲（财经事件归财经、科技事件归科技）；每版块外文来源最多 2 条；付费墙文章用快讯源替代；来源轮换：`S = (一年中第几天 + H) % 扩展源个数`，高频版块查从 S 起连续 2 个扩展源、慢频查 1 个；每个来源最多取 2 条。
3. 用第 2 步素材发高频短帖（发布接口逐篇发）：每篇聚焦一个版块，中文，3–5 条（早间首播可 5–8 条），语气简洁口语，每条带真实链接（直接用调研到的链接，禁止编造 URL）。
3b. 慢频版块（仅早/中/晚三期执行）：另发 {{SLOW_SECTIONS}} 短帖；读 topics 日志去重，发完把本批话题追加进去（一行：`YYYY-MM-DD HH:00 低频 | 话题1；话题2；…`）。
4. 片尾推荐歌（必备项，下载不到就换一首；新歌优先、近 4 期歌手不重复）：① 如有每日新歌源（如关注歌手 Top 刷新），先用 `bin/fresh-song-from-spotify.py --count 3` 取候选（读当日歌单，当日缺失时自动回退 7 天内最新一期；取非 explicit、中文标题优先、未在去重 log 出现过的新歌，输出 `[{"artist","title"}]`；通过 `SPOTIFY_REFRESH_STATE` 环境变量指定歌单 state 文件），对每个"歌手 歌名"跑 `yt-dlp "ytsearch3:<歌手> <歌名>" --flat-playlist --print "%(id)s|%(title)s|%(uploader)s"`，取第 1 个标题含歌名核心词的官方渠道结果（3 个结果无标题匹配则该候选作废），记为 `{"id","title","uploader","fresh":true}` 存入候选数组；② 候选不足 6 首时用 query 池补足：24 个 query（情绪/场景/语种细分，均偏人声），按 `Q=$(( (($(date +%j) - 1) * 4 + (H - 8) / 4) % 24 ))` 取本期 query，跑 `yt-dlp "ytsearch8:<query>" --match-filter "upload_date > $(date -d '6 months ago' +%Y%m%d)" --skip-download --print "%(id)s|%(title)s|%(uploader)s"`（不要 --flat-playlist；只搜近 6 个月上传），取官方渠道结果记为 `{"id","title","uploader","fresh":false}` 追加（凑满 6 首；搜索失败或全被过滤换池中下一个 query）；③ 跑 `bin/rank-song-candidates.py --candidates <json> --log {{CACHE_DIR}}/youtube-songs.log --count 3`：自动跳过已出现过的 video id、近 4 期出现过的歌手、坏标题（翻唱/cover/合集/精选/串烧/纯音乐/伴奏/instrumental/lofi/beats/ambient/piano solo/karaoke/meditation/sleep sounds；现场/live 版允许）和非官方渠道，并直接淘汰上传超过 3 年的旧歌（`--max-age-years`，默认 3），按"每日新歌源 ＞ 近 2 年上传的新歌（upload_date）＞ 热度（播放量＋点赞×10＋评论×50，从高到低；取不到数据时自动降级）＞ 中文人声优先"输出前 3 名；rank 不足 3 个时换下一个 query 补候选重 rank，query 用完仍不足则加 `--max-age-years 99` 取最优保底。去重：读 `{{CACHE_DIR}}/youtube-songs.log`（没有则创建），最终下载成功的那首才追加一行（失败换掉的不写）。两次搜索都失败才跳过此步，不阻塞。
4b. 选歌后立刻下载（写稿前必须拿到音频，才知道有没有歌可播）：对 3 个候选依次尝试 `yt-dlp --extractor-args "youtube:player_client=android" -x --audio-format mp3 --no-playlist -o {{CACHE_DIR}}/rec-song-<slug>.mp3 "https://www.youtube.com/watch?v=<id>"`；遇 bot-check 换 `tv_embedded` 重试一次，仍失败 sleep 90 秒后用 android 最后重试一次；单首三次失败换下一首（换歌时同样遵守去重：不选 log 里出现过的 id 和近 4 期出现过的歌手）。3 首全失败 → 换 query 重搜一轮再试 3 首；两轮共 6 首全失败才记"本期无歌"（极少发生），继续流程。下载成功的那首追加一行 `YYYY-MM-DD HH:MM - 标题 - 歌手 - https://www.youtube.com/watch?v=<id>` 到去重 log（新格式多记歌手名字段，供歌手去重窗口用；旧行兼容）。
5. 本期主持人：按内容选 2–4 位登场（不用每次全上）。主持人池见 `references/character-bible-template.md`（{{VOICE_MAP}}）。选人规则：每人认领 1–2 个主场版块，看本期重点版块选主场对口的人登场；每期换着来，男女声搭配；不登场的人不写台词、不配声音。飞行嘉宾位：按登场三原则（登场动机/深度话题/话题钩子）现编人设（一句话身份＋一句性格＋一个口头禅），名字贴合身份与动机、不用路人名；记入第 10 步 topics 日志（`嘉宾：名字-身份-登场动机`），两周内不重复请同一人。从登场主持人里选一位开场主咖（优先本期重点版块的主场认领人）。
6. 基于本期素材写播客脚本（只写登场主持人的台词），写完对照写作质检清单自查。语言、节奏、热梗、口头禅、清唱、自嘲、脱口秀、cosplay 小剧场、短视频时间、背景音乐分段、发音安全、结构见 `references/writing-guide.md`。{{TRAVEL_SECTION}}（如启用：在对应版块末尾加「今日拍摄计划」段落，读行程文件，由导游型嘉宾主讲、主持人捧哏；文件不存在则跳过，不编造。）
6b. TTS 预扫：跑 `bin/prescan-chunks.py`（默认 6 并发），5 项检查（截断/异常安静<中位数 6dB/时长异常 1.6x 且 +3s/句内 ≥2.5s 静音/多音字 watchlist）见 `references/qa-pipeline.md`；问题行只能改写，重跑直到"预扫通过"；通过后不要再改脚本行文本。
7. 短视频原声抓取＋高潮定位：读 `clip-urls.json`（无则跳过；每条必填 `mode`：`event`=夺冠/颁奖/欢呼/搞笑包袱/采访、`music`=副歌/演唱/演奏）；每条：① yt-dlp 下载完整音频（android→tv_embedded→sleep 90s 后 android 再试）；② 定高潮段：json 里写了 start/end 就直接用（事件类必须尽量从简介/置顶评论找人工时间戳写入，自动定位只做兜底），否则跑 `bin/find-climax.py --duration 45 --mode <mode>`（music 取能量最高连续段，event 用"能量×噪度"定位现场声并跳过前 10 秒片头 BGM；不足 45 秒全播）；③ `ffmpeg -ss <start> -to <end> -i`（放 `-i` 之前）截取并 `loudnorm=I=-20:TP=-2:LRA=11`。失败跳过该条。
8. 干声组装：跑 `bin/assemble-dry.py --script <脚本> --clip-insert <clip 映射> --out <干声 mp3> --line-times <行时间线> --clip-times <clip 时间线>`；按 `sha256("voice_id|文本")[:16]` 查预扫缓存，逐行电平补偿（中位数目标、±6dB 封顶），每段 8ms 淡化，在插入点拼 clip。缺失缓存先重跑预扫补齐。
9. 自检：a) `bin/check-script.py` 文本质检；b) 干声音频质检——`ffprobe` 时长落在（字数/300，字数/200）分钟区间外视为异常；`silencedetect=noise=-45dB:d=1.5` 找超 1.5 秒空白段，用 `silenceremove` 收紧（先备份；收紧后复查；trim 偏移写入 `trim-offset.json`）；`astats` 看削波。时长异常最多返工 2 次，仍不通过记问题、跳过第 13 步发布环节。禁止用"和已发布期数横向对比"绕过检查。
9b. 背景音乐轨道：先选本期音乐套装 `V=$(( ($(date +%j) + <期号>) % 7 ))` 并 `export MUSIC_PACK=v$V`（7 套 v0–v6，`bin/synth-music.py musicpacks` 预生成到 `bin/music/`，同套转调＋片头变速、时长电平一致）；再跑 `bin/build-bed-track.py --bed-map <bed 映射> --line-times <行时间线> --clip-times <clip 时间线> --voice <干声> --offset <trim 偏移> --out <bed 轨道>`（自动选用该套装的 bed1-4，未设置时回退默认）；原声时段 bed 自动静音。失败则回退该套装 bed1 循环混音。
10. topics 日志：追加一行 `YYYY-MM-DD HH:00 | 话题1；话题2；…`，附带 `梗：…` / `弧光：人物-事件` / `嘉宾：…` / `cos：…` 记录。
11. 混音：`export MUSIC_PACK=v$V`（与 9b 同一套；缺失时脚本回退默认音乐）后跑 `BED_TRACK_MP3=<bed 轨道> bash bin/mix-episode.sh <干声> <混音输出>`（脚本自动选用该套装的 intro/outro/bed；bed 轨道不存在则不设该变量，用该套装的 bed1 循环）。抽查：最后 5 秒 mean_volume 约 -30dB（低于 -40dB 说明片尾音乐没混进去）；全片 `silencedetect=noise=-45dB:d=2` 无超 2 秒死寂。
11b. 拼推荐歌＋终混：`{{CACHE_DIR}}/rec-song-<slug>.mp3` 存在才拼——`loudnorm=I=-30:TP=-2:LRA=11` 后 `concat` 到混音最后，删源文件；不存在即本期无歌、跳过。再 `bash bin/loudnorm-final.sh <混音> <终混>` 双 pass 到 -16 LUFS（失败原样保留、不阻塞）。
12. （已取消）不再上传、不再生成公开链接，跳过。
13. 发布：把混音版记入播客目录（manifest add-episode，slug 规则：M、D、H 去掉前导零拼接 + "-" + YYYY-MM-DD，如 `10119-2026-10-01`），同步到播客托管（原项目：`podcast-helper save-to-spotify --slug <slug>-mix --show-id <节目 id>`，等 READY 最多 5 分钟，超时不阻塞）。内部 ID 绝不出现在文案里。
14. 发语音版帖：标题《整点语音版 · M月D日H点》，一句话概括各版块；末尾两行——完整版收听入口（第 13 步失败则不写）；片尾推荐歌行：有歌写"片尾曲就是今日推荐《标题》，已拼在播客最后；想看 MV：[在 YouTube 上播放](url)"，无歌只一句话带过、不承诺"完整版播完别走开"。
15. 发完即结束。后台/耗时操作按工具返回处理，不轮询等待；帖子出现即是交付，定时任务不在聊天里汇报。
