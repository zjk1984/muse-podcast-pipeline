# 示例

`sample-script.txt` 是一个 2 分钟左右的迷你播客脚本，演示脚本文件的格式规范：

- **说话人标签**：`名字: 台词`（半角冒号＋空格），名字须与 `bin/voices.json` 的键一致
- **数字时间中文读法**：`十月三日早上八点`，不要写 `10-03 08:00`
- **短句**：每句只讲一个意思，TTS 友好
- **marker 行**（写完后剥离，不进入合成）：
  - `===BED:2===`：从此处切换背景音乐情绪（1 沉稳 / 2 紧张 / 3 轻快 / 4 温暖）
  - `===CLIP1===`：短视频原声插入点（"介绍 → 插入点 → 反应"三段式，见 `references/writing-guide.md`）

## 跑一遍质检

```bash
# 文本质检（只依赖 python）
python3 bin/check-script.py examples/sample-script.txt

# TTS 预扫（需要配好 tts CLI 和 bin/voices.json）
python3 bin/prescan-chunks.py examples/sample-script.txt
```
