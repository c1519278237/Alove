from __future__ import annotations

import re
from collections import Counter


def analyze_style_samples(texts: list[str]) -> dict[str, object]:
    cleaned = [re.sub(r"\s+", " ", text).strip() for text in texts if text.strip()]
    combined = "\n".join(cleaned)
    sentences = [
        item.strip()
        for item in re.split(r"[。！？!?\n]+", combined)
        if 2 <= len(item.strip()) <= 120
    ]
    average_length = sum(map(len, sentences)) / max(1, len(sentences))
    if average_length <= 12:
        sentence_style = "以短句为主，直接、自然、少用复杂表达"
    elif average_length <= 24:
        sentence_style = "中短句为主，自然亲切，先回应再给建议"
    else:
        sentence_style = "表达较完整，会补充原因，但每次只推进一件事"

    greetings = []
    greeting_markers = ("早", "晚", "妈", "爸", "吃饭", "在干嘛", "最近", "今天")
    for sentence in sentences:
        if any(marker in sentence[:18] for marker in greeting_markers):
            greetings.append(sentence[:40])

    phrases = Counter(
        token
        for sentence in sentences
        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", sentence)
        if token not in {"这个", "那个", "什么", "怎么", "我们", "你们", "他们"}
    )
    common = list(dict.fromkeys(greetings + [item for item, _ in phrases.most_common(8)]))[:12]
    comfort_style = (
        "先表示理解和陪伴，再用温和短句建议联系真实家人"
        if any(term in combined for term in ("别担心", "没事", "我在", "慢慢", "放心"))
        else "先听完并复述感受，再提供一个简单可执行的建议"
    )
    reminder_style = (
        "像日常聊天一样温和提醒，说明原因，不责备、不命令"
        if any(term in combined for term in ("记得", "别忘", "要按时", "早点"))
        else "使用温和、不命令的提醒方式"
    )
    return {
        "common_greetings": common,
        "sentence_style": sentence_style,
        "comfort_style": comfort_style,
        "reminder_style": reminder_style,
        "sample_count": len(cleaned),
        "sentence_count": len(sentences),
        "average_sentence_length": round(average_length, 1),
    }
