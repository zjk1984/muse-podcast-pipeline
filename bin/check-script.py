#!/usr/bin/env python3
"""整点快报脚本文字质检。

查：空话（标签后无内容）、全角冒号、重复句、相邻高度相似句、
    超 30 字不断句的长句、一人连续说 5 句以上、"哈哈"句号收尾。

用法: python3 check-script.py /tmp/hourly-script.txt
有问题打印清单并 exit 1；通过打印"文本质检通过。"并 exit 0。
"""
import difflib
import json
import os
import re
import sys

# 注意：不用 \s（写文件链路会转义反斜杠），空白用 split()/strip() 处理
PUNCT = '[，、。！？；：""''（）()～…—· ]'


def _load_speakers():
    # 说话人名单取自 bin/voices.json（与 assemble-dry.py 一致）；文件不存在时回退默认名单
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'voices.json')
    try:
        raw = json.load(open(p, encoding='utf-8'))
        names = [k for k in raw.keys() if not k.startswith('_')]
        if names:
            return names
    except Exception:
        pass
    return ['周周', '小夏', '阿飒', '悠悠', '买买提']


SPEAKERS = _load_speakers()


def norm(s):
    return ''.join(re.sub(PUNCT, '', s).split())


def main(path):
    raw = open(path, encoding='utf-8').read().splitlines()
    issues = []
    sents = []  # (lineno, text)
    prev_speaker, run = None, 0

    for i, line in enumerate(raw, 1):
        line = ' '.join(line.split())
        if not line:
            continue
        _names = '|'.join(re.escape(n) for n in sorted(SPEAKERS, key=len, reverse=True))
        m = re.match(r'^(' + _names + r') *([:：]) *(.*)$', line)
        if not m:
            issues.append(f'L{i}: 说话人标签格式不对: {line[:30]}')
            continue
        speaker, colon, body = m.group(1), m.group(2), m.group(3).strip()
        if colon == '：':
            issues.append(f'L{i}: 用了全角冒号，会导致合成失败，改半角冒号')
        if speaker == prev_speaker:
            run += 1
        else:
            prev_speaker, run = speaker, 1
        if run == 5:
            issues.append(f'L{i}: {speaker} 连续说 5 句以上，拆成对话')
        if not body or re.fullmatch(r'[，。！？；：、～…—· ]+', body):
            issues.append(f'L{i}: 空话（标签后无内容，会合成出空白段）')
            continue
        if re.search(r'哈哈[。.]', body):
            issues.append(f'L{i}: "哈哈"用了句号收尾，改成"哈哈哈！/～"')
        for s in re.split(r'(?<=[。！？；])', body):
            s = s.strip()
            if s:
                sents.append((i, s))

    for i, s in sents:  # 超长不断句
        if len(s) > 30 and '，' not in s and '、' not in s:
            issues.append(f'L{i}: 超过30字没断句: {s[:35]}…')

    seen = {}  # 完全重复句
    for i, s in sents:
        n = norm(s)
        if len(n) < 10:
            continue
        if n in seen:
            issues.append(f'L{i}: 与 L{seen[n]} 重复: {s[:35]}…')
        else:
            seen[n] = i

    for (i1, s1), (i2, s2) in zip(sents, sents[1:]):  # 相邻高度相似
        n1, n2 = norm(s1), norm(s2)
        if len(n1) > 15 and len(n2) > 15 and n1 != n2:
            if difflib.SequenceMatcher(None, n1, n2).ratio() > 0.8:
                issues.append(f'L{i2}: 与上一句高度相似（疑似重复段落）: {s2[:35]}…')

    if issues:
        print(f'发现 {len(issues)} 个问题：')
        for it in issues[:30]:
            print(' -', it)
        return 1
    print('文本质检通过。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
