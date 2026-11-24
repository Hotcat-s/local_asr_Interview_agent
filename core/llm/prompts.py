"""Prompt templates for interview evaluation."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "你是一位资深的面试官与技术面试教练，擅长评估候选人的回答质量并给出改进建议。"
    "你的输出必须是可被程序解析的严格 JSON，不要包含 JSON 之外的任何文字。"
)

QA_ANALYSIS_PROMPT = """\
请评估下面这道面试题的回答。

【问题】
{question}

【候选人回答】
{answer}

请以 JSON 返回，字段如下：
- "score": 0-100 的整数，表示回答质量
- "strengths": 字符串数组，回答的亮点
- "weaknesses": 字符串数组，回答的不足
- "reference_answer": 字符串，这道题理想的参考答案
- "suggestion": 字符串，针对该候选人的改进建议
只返回 JSON。"""

BATCH_ANALYSIS_PROMPT = """\
以下是一次面试中的 {count} 道问答，已按时间顺序给出（JSON 数组，index 为题目序号）：
{items}

请结合整段对话的上下文，逐题评估候选人的回答质量。以 JSON 数组返回，数组元素与输入题目一一对应，且必须原样保留每题的 index：
[
  {{
    "index": <与输入题目的 index 完全一致>,
    "score": <0-100 的整数，表示回答质量>,
    "strengths": [<回答的亮点，字符串数组>],
    "weaknesses": [<回答的不足，字符串数组>],
    "reference_answer": "<这道题理想的参考答案>",
    "suggestion": "<针对该候选人的改进建议>"
  }}
]

只返回 JSON 数组，不要包含 JSON 之外的任何文字，不要遗漏任何一题。"""


SUMMARY_PROMPT = """\
以下是一次面试中每道题的评估结果（JSON 数组）：
{items}

请综合这些结果给出整体复盘，以 JSON 返回：
- "overall_score": 0-100 的整数，整体表现
- "summary": 字符串，整体评价
- "improvements": 字符串数组，需要重点改进的地方（3-6 条）
只返回 JSON。"""
