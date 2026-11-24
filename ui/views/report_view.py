"""复盘报告视图：以现代卡片式 HTML 渲染 ``core.schemas.InterviewReport``。"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from ui import theme

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.schemas import InterviewReport, QAAnalysis

_ACCENT = "#4f8cff"
_SUCCESS = "#3fb950"
_WARNING = "#d29922"
_DANGER = "#f85149"
_MUTED = "#8b98a9"


def _score_color(score: float) -> str:
    if score >= 80:
        return _SUCCESS
    if score >= 60:
        return _ACCENT
    if score >= 40:
        return _WARNING
    return _DANGER


def _list_block(title: str, items: list[str], color: str) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<li style='margin:2px 0;'>{html.escape(item)}</li>" for item in items
    )
    return (
        f"<div style='margin-top:8px;'>"
        f"<span style='color:{color};font-weight:600;'>{html.escape(title)}</span>"
        f"<ul style='margin:4px 0 0 18px;padding:0;'>{rows}</ul></div>"
    )


class ReportView(QWidget):
    """展示整体评分、逐题分析与改进建议。"""

    def __init__(self, parent: QWidget | None = None, theme_name: str = "dark") -> None:
        super().__init__(parent)
        self._font = theme.build_font("", theme.DEFAULT_FONT_SIZE)
        self._browser = QTextBrowser(self)
        self._browser.setOpenExternalLinks(False)
        self.set_theme_name(theme_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._browser)

        self.clear()

    def set_theme_name(self, theme_name: str) -> None:
        # 局部样式：让原生 QTextBrowser 随主题取色，避免深色下不可见。
        self._browser.setStyleSheet(
            theme.build_qss(theme_name) + "\nQTextBrowser { border: none; padding: 8px 16px; }"
        )

    def set_font(self, family: str = "", size: int = theme.DEFAULT_FONT_SIZE) -> None:
        """设置报告正文字体（HTML 无显式字号的文本会继承文档默认字体）。"""

        self._font = theme.build_font(family, size)
        self._browser.setFont(self._font)
        self._apply_document_font()

    def _apply_document_font(self) -> None:
        # setHtml 会重建文档，因此每次渲染后都要重新套用默认字体。
        self._browser.document().setDefaultFont(self._font)

    def set_report(self, report: "InterviewReport | None") -> None:
        self._browser.setHtml(self._render(report))
        self._apply_document_font()

    def clear(self) -> None:
        self._browser.setHtml(
            "<div style='color:#8b98a9;text-align:center;margin-top:60px;'>"
            "暂无复盘报告，点击「开始分析」生成。</div>"
        )
        self._apply_document_font()

    # ---- 渲染 ----
    def _render(self, report: "InterviewReport | None") -> str:
        if report is None:
            return (
                "<div style='color:#8b98a9;text-align:center;margin-top:60px;'>"
                "暂无复盘报告，点击「开始分析」生成。</div>"
            )

        score = float(report.overall_score)
        color = _score_color(score)
        parts: list[str] = []
        parts.append("<div style='margin-bottom:12px;'>")
        parts.append(
            "<div style='display:inline-block;width:84px;height:84px;border-radius:42px;"
            f"border:4px solid {color};color:{color};text-align:center;"
            "font-size:26px;font-weight:700;line-height:84px;'>"
            f"{score:.0f}</div>"
            "<span style='color:#8b98a9;margin-left:10px;'>/ 100 综合评分</span>"
        )
        parts.append("</div>")

        if report.summary:
            parts.append(
                "<div style='background:rgba(127,127,127,0.08);border-radius:8px;"
                "padding:12px 14px;margin-bottom:14px;'>"
                f"<b>总体评价</b><br>{html.escape(report.summary)}</div>"
            )

        if report.improvements:
            parts.append("<h3 style='margin:10px 0 6px 0;'>改进建议</h3><ul style='margin:0 0 0 18px;'>")
            for item in report.improvements:
                parts.append(f"<li style='margin:3px 0;'>{html.escape(item)}</li>")
            parts.append("</ul>")

        if report.items:
            parts.append("<h3 style='margin:16px 0 6px 0;'>逐题分析</h3>")
            for analysis in report.items:
                parts.append(self._render_item(analysis))

        if report.created_at:
            parts.append(
                f"<p style='color:{_MUTED};margin-top:16px;'>生成时间：{html.escape(report.created_at)}</p>"
            )
        return "".join(parts)

    def _render_item(self, analysis: "QAAnalysis") -> str:
        color = _score_color(float(analysis.score))
        blocks: list[str] = []
        blocks.append(
            "<div style='border:1px solid rgba(127,127,127,0.25);border-radius:8px;"
            "padding:12px 14px;margin-bottom:12px;'>"
        )
        blocks.append(
            f"<span style='font-weight:700;'>第 {analysis.index + 1} 题</span>"
            f"<span style='color:{color};font-weight:700;float:right;'>{analysis.score:.0f} 分</span>"
            "<div style='clear:both;'></div>"
        )
        blocks.append(
            f"<p style='margin:8px 0 4px 0;'><b>问题：</b>{html.escape(analysis.question)}</p>"
        )
        blocks.append(
            f"<p style='margin:0 0 4px 0;'><b>回答：</b>{html.escape(analysis.answer)}</p>"
        )
        blocks.append(_list_block("优点", analysis.strengths, _SUCCESS))
        blocks.append(_list_block("不足", analysis.weaknesses, _DANGER))
        if analysis.reference_answer:
            blocks.append(
                "<div style='margin-top:8px;'><span style='color:"
                f"{_ACCENT};font-weight:600;'>参考答案</span><br>"
                f"{html.escape(analysis.reference_answer)}</div>"
            )
        if analysis.suggestion:
            blocks.append(
                f"<div style='margin-top:6px;'><b>建议：</b>{html.escape(analysis.suggestion)}</div>"
            )
        blocks.append("</div>")
        return "".join(blocks)
