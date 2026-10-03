# Changelog

skill 规则与脚本的进化记录（脱敏，只记已采纳的变更）。每周复盘提案经确认后应用，在此追加条目。

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
