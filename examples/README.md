# 示例

`sample-script.txt` 是一个 2 分钟左右的迷你播客脚本，演示脚本文件的格式规范：

- **说话人标签**：`名字: 台词`（半角冒号＋空格），名字须与 `bin/voices.json` 的键一致
- **数字时间中文读法**：`十月三日早上八点`，不要写 `10-03 08:00`
- **短句**：每句只讲一个意思，TTS 友好
- **marker 行**（写完后剥离，不进入合成）：
  - `===BED:2===`：从此处切换背景音乐情绪（1 沉稳 / 2 紧张 / 3 轻快 / 4 温暖）
  - `===CLIP1===`：短视频原声插入点（"介绍 → 插入点 → 反应"三段式，见 `references/writing-guide.md`）

## 音频示例

`demo-episode.mp3`（18 秒）是 `sample-script.txt` 开场 5 句用 `tts synthesize-script` 合成的演示音频（双主持人对话），可直接在 GitHub 页面点击播放试听：

```bash
tts synthesize-script \
  --script opener.txt \
  --speaker 示例-女主持A=avocado_v2:MAI_01 \
  --speaker 示例-男主持B=avocado_v2:MAI_03 \
  --language zh --output demo-episode.mp3
```

注意：合成前先剥离 `===BED:n===` / `===CLIPn===` 这类 marker 行。

## 跑一遍质检

```bash
# 文本质检（只依赖 python）
python3 bin/check-script.py examples/sample-script.txt

# TTS 预扫（需要配好 tts CLI 和 bin/voices.json）
python3 bin/prescan-chunks.py examples/sample-script.txt
```
