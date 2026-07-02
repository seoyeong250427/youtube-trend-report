"""
분석된 트렌드 데이터를 받아 브랜드 PDF 리포트를 생성하는 Tool.

이 Tool은 분석을 하지 않는다 — 이미 정리된 JSON(입력)을 받아서 PDF로 "조립"만 한다.
분석/추천 문구 작성은 Workflow를 실행하는 Agent(Claude)가 한다.

입력 JSON 스키마 (예시):
{
  "week_label": "2026-W27 (2026-06-29 ~ 2026-07-05)",
  "summary": "이번 주 전체 요약 2~3문장",
  "top_topics": [
    {"topic": "주제명", "total_views": 1234567, "video_count": 5, "example_titles": ["...", "..."]}
  ],
  "format_analysis": {
    "shorts_count": 12, "shorts_avg_views": 500000,
    "longform_count": 20, "longform_avg_views": 300000,
    "note": "짧은 설명 문장"
  },
  "recommendations": [
    {"title": "추천 주제", "reason": "추천 근거"}
  ],
  "top_videos": [
    {"title": "...", "channel_title": "...", "view_count": 123456, "url": "https://..."}
  ]
}

사용법:
    python tools/generate_report_pdf.py --input .tmp/analysis.json --output .tmp/report.pdf
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle

ROOT_DIR = Path(__file__).resolve().parent.parent
FONT_REGULAR_PATH = ROOT_DIR / "assets" / "fonts" / "NanumGothic-Regular.ttf"
FONT_BOLD_PATH = ROOT_DIR / "assets" / "fonts" / "NanumGothic-Bold.ttf"

# dataviz 스킬의 검증된 팔레트 (references/palette.md)
COLOR_SERIES_1_BLUE = "#2a78d6"
COLOR_SERIES_2_AQUA = "#1baf7a"
COLOR_TEXT_PRIMARY = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"
COLOR_MUTED = "#898781"
COLOR_GRIDLINE = "#e1e0d9"
COLOR_BASELINE = "#c3c2b7"


def register_fonts():
    pdfmetrics.registerFont(TTFont("NanumGothic", str(FONT_REGULAR_PATH)))
    pdfmetrics.registerFont(TTFont("NanumGothic-Bold", str(FONT_BOLD_PATH)))
    font_manager.fontManager.addfont(str(FONT_REGULAR_PATH))
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(FONT_REGULAR_PATH)).get_name()
    plt.rcParams["axes.unicode_minus"] = False


def make_topics_chart(top_topics: list[dict], output_path: Path):
    """상위 주제 총 조회수 랭킹 — 단일 시리즈이므로 한 가지 색(blue)만 사용."""
    topics = [t["topic"] for t in top_topics][:8][::-1]
    views = [t["total_views"] for t in top_topics][:8][::-1]

    fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=200)
    bars = ax.barh(topics, views, color=COLOR_SERIES_1_BLUE, height=0.6)

    for bar, value in zip(bars, views):
        ax.text(
            bar.get_width() + max(views) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:,}",
            va="center",
            ha="left",
            fontsize=8,
            color=COLOR_TEXT_SECONDARY,
        )

    ax.set_title("이번 주 인기 주제 Top 8 (총 조회수)", fontsize=11, color=COLOR_TEXT_PRIMARY, loc="left")
    ax.set_xlabel("총 조회수", fontsize=8, color=COLOR_MUTED)
    ax.tick_params(axis="y", labelsize=9, colors=COLOR_TEXT_PRIMARY)
    ax.tick_params(axis="x", labelsize=8, colors=COLOR_MUTED)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_BASELINE)
    ax.set_xticks([])
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(output_path, transparent=False, facecolor="#fcfcfb")
    plt.close(fig)


def make_format_chart(format_analysis: dict, output_path: Path):
    """Shorts vs 롱폼 평균 조회수 비교 — 두 카테고리이므로 고정 순서 2색(blue, aqua) 사용."""
    labels = ["Shorts", "롱폼"]
    values = [
        format_analysis.get("shorts_avg_views", 0),
        format_analysis.get("longform_avg_views", 0),
    ]
    counts = [
        format_analysis.get("shorts_count", 0),
        format_analysis.get("longform_count", 0),
    ]
    bar_colors = [COLOR_SERIES_1_BLUE, COLOR_SERIES_2_AQUA]

    fig, ax = plt.subplots(figsize=(4.2, 3.6), dpi=200)
    bars = ax.bar(labels, values, color=bar_colors, width=0.5)
    ax.set_ylim(0, max(values) * 1.35)

    for bar, value, count in zip(bars, values, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.04,
            f"{value:,}\n(영상 {count}개)",
            ha="center",
            va="bottom",
            fontsize=8,
            color=COLOR_TEXT_SECONDARY,
        )

    ax.set_title("포맷별 평균 조회수", fontsize=11, color=COLOR_TEXT_PRIMARY, loc="left", pad=14)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_BASELINE)
    ax.set_yticks([])
    ax.tick_params(axis="x", labelsize=10, colors=COLOR_TEXT_PRIMARY)
    fig.tight_layout()
    fig.savefig(output_path, transparent=False, facecolor="#fcfcfb")
    plt.close(fig)


def build_pdf(data: dict, output_path: Path, tmp_dir: Path):
    register_fonts()

    styles = {
        "title": ParagraphStyle("title", fontName="NanumGothic-Bold", fontSize=20, leading=28, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceAfter=6),
        "subtitle": ParagraphStyle("subtitle", fontName="NanumGothic", fontSize=11, leading=16, textColor=colors.HexColor(COLOR_TEXT_SECONDARY), spaceAfter=16),
        "h2": ParagraphStyle("h2", fontName="NanumGothic-Bold", fontSize=14, leading=19, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceBefore=18, spaceAfter=8),
        "body": ParagraphStyle("body", fontName="NanumGothic", fontSize=10, leading=16, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceAfter=6),
        "muted": ParagraphStyle("muted", fontName="NanumGothic", fontSize=9, leading=14, textColor=colors.HexColor(COLOR_MUTED)),
        "rec_title": ParagraphStyle("rec_title", fontName="NanumGothic-Bold", fontSize=11, leading=16, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceAfter=2),
    }

    story = []
    story.append(Paragraph("주간 유튜브 트렌드 리포트", styles["title"]))
    story.append(Paragraph(data.get("week_label", ""), styles["subtitle"]))

    if data.get("summary"):
        story.append(Paragraph(data["summary"], styles["body"]))

    top_topics = data.get("top_topics", [])
    if top_topics:
        story.append(Paragraph("인기 주제", styles["h2"]))
        chart_path = tmp_dir / "_chart_topics.png"
        make_topics_chart(top_topics, chart_path)
        story.append(Image(str(chart_path), width=160 * mm, height=88 * mm))

    format_analysis = data.get("format_analysis")
    if format_analysis:
        story.append(Paragraph("포맷 분석 (Shorts vs 롱폼)", styles["h2"]))
        chart_path = tmp_dir / "_chart_format.png"
        make_format_chart(format_analysis, chart_path)
        story.append(Image(str(chart_path), width=105 * mm, height=90 * mm))
        if format_analysis.get("note"):
            story.append(Paragraph(format_analysis["note"], styles["muted"]))

    recommendations = data.get("recommendations", [])
    if recommendations:
        story.append(Paragraph("이번 주 콘텐츠 주제 추천", styles["h2"]))
        for i, rec in enumerate(recommendations, 1):
            story.append(Paragraph(f"{i}. {rec.get('title', '')}", styles["rec_title"]))
            if rec.get("reason"):
                story.append(Paragraph(rec["reason"], styles["body"]))

    top_videos = data.get("top_videos", [])
    if top_videos:
        story.append(Paragraph("참고 영상 (상위 조회수)", styles["h2"]))
        table_data = [["제목", "채널", "조회수"]]
        for v in top_videos[:15]:
            table_data.append([
                Paragraph(v.get("title", ""), styles["muted"]),
                Paragraph(v.get("channel_title", ""), styles["muted"]),
                f"{v.get('view_count', 0):,}",
            ])
        table = Table(table_data, colWidths=[90 * mm, 45 * mm, 25 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "NanumGothic-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "NanumGothic"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(COLOR_TEXT_PRIMARY)),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor(COLOR_BASELINE)),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor(COLOR_GRIDLINE)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title="주간 유튜브 트렌드 리포트",
    )
    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description="주간 트렌드 분석 PDF 리포트 생성")
    parser.add_argument("--input", required=True, help="분석 결과 JSON 경로")
    parser.add_argument("--output", required=True, help="생성할 PDF 경로")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    build_pdf(data, output_path, tmp_dir=output_path.parent)
    print(f"완료: PDF 생성 -> {output_path}")


if __name__ == "__main__":
    main()
