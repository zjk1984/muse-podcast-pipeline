# podcast-pipeline

中文定时新闻播客生产流水线：多版块调研 → 脱口秀式写稿 → TTS 预扫质检 → 干声组装 → 混音 → 发布。

每个整点产出两样东西：一批多版块新闻短帖，一期多主持人脱口秀式播客（开场音乐＋暖场＋版块串联＋背景音乐＋片尾＋推荐歌曲）。

## 依赖说明（必读）

本流水线**依赖 Meta 内部工具**，在外部环境不可用：
- `podcast-helper`（播客目录管理、TTS 合成、Spotify 同步）
- `tts` CLI（avocado 系列音色）
- `feed.unit_create`（动态短帖发布接口）

没有这些工具，流水线跑不通。**可移植的价值**是：
- `references/writing-guide.md`：脱口秀式播客写作方法论（热梗机制、节奏、口头禅节制、callback 钩子、短视频原声三段式）
- `references/character-bible-template.md`：多人设播客人设圣经模板（主场版块、团梗库、人物弧光、飞行嘉宾三原则）
- `bin/` 下的质检与混音脚本：`prescan-chunks.py`（TTS 预扫 4 项检查）、`check-script.py`（文本质检）、`assemble-dry.py`（干声组装＋电平补偿）、`find-climax.py`（短视频高潮定位）、`mix-episode.sh`（ducking 混音）、`loudnorm-final.sh`（-16 LUFS 终混）、`synth-music.py`（合成片头/背景/片尾音乐）、`build-bed-track.py`（分段 bed 轨道）

其中 `prescan-chunks.py` / `assemble-dry.py` 依赖 tts CLI 做逐行合成；`check-script.py` / `find-climax.py` / 混音脚本只依赖 ffmpeg，可独立使用。

## 目录结构

```
podcast-pipeline/
├── SKILL.md                        # 技能正文：Purpose / Workflow（15 步）/ Output Contract / Operating Rules
├── README.md
├── .gitignore
├── bin/
│   ├── prescan-chunks.py           # TTS 预扫：逐行合成＋4 项检查（截断/异常安静/时长异常/长静音）
│   ├── assemble-dry.py             # 干声组装：查缓存、逐行电平补偿±6dB、8ms 淡化、clip 插入
│   ├── check-script.py             # 文本质检：重复句/空话/长句/全角冒号
│   ├── find-climax.py              # 短视频高潮定位：能量最高的连续 45 秒
│   ├── build-bed-track.py          # 分段背景音乐轨道（原声时段自动静音）
│   ├── mix-episode.sh              # 混音：intro＋干声（sidechain ducking bed）＋outro
│   ├── loudnorm-final.sh           # 终混响度：双 pass 到 -16 LUFS
│   ├── synth-music.py              # 合成片头/背景/片尾音乐（intro 6s / bed 96s / outro 5s）
│   ├── voices.example.json         # 说话人→音色映射示例
│   └── voices.json                 # （自己创建）说话人→音色映射，见下
├── references/
    ├── writing-guide.md            # 播客写作指南
    ├── character-bible-template.md # 人物圣经模板＋示例人设
    ├── qa-pipeline.md              # TTS 预扫、质检、自检、ffmpeg 坑
    ├── cron-prompt-template.md     # 定时任务提示词模板（带 {{占位符}}）
└── examples/
    ├── README.md                   # 示例说明
    └── sample-script.txt           # 2 分钟迷你脚本：说话人标签 / bed / clip marker 格式演示
```

## 快速开始

1. **配音色**：复制 `bin/voices.example.json` 为 `bin/voices.json`，填入说话人名字→你的 TTS 音色 ID。脚本里的说话人标签（`名字: 台词`）须与 `voices.json` 的键一致，组装脚本会自动识别。
2. **配缓存**（可选）：设置环境变量 `PODCAST_CACHE` 指向你的缓存 json 路径（默认 `./cache/prescan-cache.json`；行音频缓存在同目录 `prescan-audio/`）。
3. **生成音乐素材**：`python3 bin/synth-music.py` 生成 intro/bed/outro（或用自己的音乐，电平要求见 `references/qa-pipeline.md`）。
4. **填模板**：按 `references/cron-prompt-template.md` 把 `{{占位符}}` 换成你的版块、时段、时区、节目名，得到定时任务正文。
5. **跑流程**：按 `SKILL.md` 的 Workflow 跑 15 步；写作看 `writing-guide.md`，人设看 `character-bible-template.md`。

## 示例

`examples/` 里有一个 2 分钟迷你脚本 `sample-script.txt`，演示脚本格式（说话人标签、bed/clip marker），可直接拿去跑 `check-script.py` 做文本质检。

## 脱敏说明

本仓库不含任何真实用户数据：无音频文件（`.mp3` 均由 `synth-music.py` 重新生成）、无日志、无内部 ID、无真实行程。示例人设为虚构人物，可整体替换。
