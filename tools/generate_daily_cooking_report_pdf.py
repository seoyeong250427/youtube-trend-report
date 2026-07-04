"""
매일 요리 트렌드 분석 결과를 받아 PDF 리포트로 조립하는 Tool.

이 Tool은 분석하지 않는다 — 이미 정리된 JSON(입력)을 받아서 PDF로 조립만 한다.
분석/추천/대본 작성은 워크플로를 실행하는 Agent(Claude)가 한다.

입력 JSON 스키마: tools/cooking_daily_trends.py 출력을 Agent가 읽고 직접 작성.
예시는 .tmp/cooking_daily_analysis.json 참고 (date_label, summary, data_caveats,
keyword_trend, watch_channels, recommendations, scripts, helpful_topics,
helpful_scripts, closing).

- recommendations/scripts: 트렌드·후킹 기반 추천 (알고리즘 편승용)
- helpful_topics/helpful_scripts: 트렌드와 무관하게, 시청자에게 실제로 도움되는
  요리 지식/노하우 기반 추천 (조리 원리, 보관법, 도구 관리, 낭비 줄이기 등).
  각각 recommendations/scripts와 동일한 스키마(title/reason, number/title/type/beats)

사용법:
    python tools/generate_daily_cooking_report_pdf.py --input .tmp/analysis.json --output .tmp/report.pdf
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
from reportlab.lib.styles import ParagraphStyle
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

ROOT_DIR = Path(__file__).resolve().parent.parent
FONT_REGULAR_PATH = ROOT_DIR / "assets" / "fonts" / "NanumGothic-Regular.ttf"
FONT_BOLD_PATH = ROOT_DIR / "assets" / "fonts" / "NanumGothic-Bold.ttf"

COLOR_SERIES_1_BLUE = "#2a78d6"
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


def make_keyword_chart(keyword_trend: list[dict], output_path: Path):
    keywords = [k["keyword"] for k in keyword_trend][:8][::-1]
    counts = [k["count"] for k in keyword_trend][:8][::-1]

    fig, ax = plt.subplots(figsize=(6.5, 3.2), dpi=200)
    bars = ax.barh(keywords, counts, color=COLOR_SERIES_1_BLUE, height=0.6)
    for bar, value in zip(bars, counts):
        ax.text(bar.get_width() + max(counts) * 0.02, bar.get_y() + bar.get_height() / 2, str(value),
                va="center", ha="left", fontsize=8, color=COLOR_TEXT_SECONDARY)
    ax.set_title("오늘의 인기 키워드 (상위 영상 내 등장 빈도)", fontsize=11, color=COLOR_TEXT_PRIMARY, loc="left")
    ax.tick_params(axis="y", labelsize=9, colors=COLOR_TEXT_PRIMARY)
    ax.set_xticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_BASELINE)
    fig.tight_layout()
    fig.savefig(output_path, facecolor="#fcfcfb")
    plt.close(fig)


def build_pdf(data: dict, output_path: Path, tmp_dir: Path):
    register_fonts()
    styles = {
        "title": ParagraphStyle("title", fontName="NanumGothic-Bold", fontSize=20, leading=28, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceAfter=6),
        "subtitle": ParagraphStyle("subtitle", fontName="NanumGothic", fontSize=11, leading=16, textColor=colors.HexColor(COLOR_TEXT_SECONDARY), spaceAfter=10),
        "caveat": ParagraphStyle("caveat", fontName="NanumGothic", fontSize=8, leading=12, textColor=colors.HexColor(COLOR_MUTED), spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName="NanumGothic-Bold", fontSize=14, leading=19, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceBefore=16, spaceAfter=8),
        "body": ParagraphStyle("body", fontName="NanumGothic", fontSize=10, leading=16, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceAfter=6),
        "muted": ParagraphStyle("muted", fontName="NanumGothic", fontSize=9, leading=14, textColor=colors.HexColor(COLOR_MUTED)),
        "rec_title": ParagraphStyle("rec_title", fontName="NanumGothic-Bold", fontSize=11, leading=16, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceAfter=2),
        "script_num": ParagraphStyle("script_num", fontName="NanumGothic-Bold", fontSize=20, leading=24, textColor=colors.HexColor(COLOR_GRIDLINE)),
        "script_title": ParagraphStyle("script_title", fontName="NanumGothic-Bold", fontSize=11.5, leading=15, textColor=colors.HexColor(COLOR_TEXT_PRIMARY)),
        "script_type": ParagraphStyle("script_type", fontName="NanumGothic", fontSize=9, leading=12, textColor=colors.HexColor(COLOR_SERIES_1_BLUE), spaceAfter=4),
        "beat_time": ParagraphStyle("beat_time", fontName="NanumGothic-Bold", fontSize=8.5, leading=12, textColor=colors.HexColor(COLOR_MUTED)),
        "beat_text": ParagraphStyle("beat_text", fontName="NanumGothic", fontSize=9.3, leading=13.5, textColor=colors.HexColor(COLOR_TEXT_PRIMARY), spaceAfter=4),
    }

    story = []
    story.append(Paragraph("일일 요리 쇼츠 트렌드 리포트", styles["title"]))
    story.append(Paragraph(data.get("date_label", ""), styles["subtitle"]))
    if data.get("summary"):
        story.append(Paragraph(data["summary"], styles["body"]))
    for caveat in data.get("data_caveats", []):
        story.append(Paragraph(f"※ {caveat}", styles["caveat"]))

    keyword_trend = data.get("keyword_trend", [])
    if keyword_trend:
        story.append(Paragraph("오늘의 인기 키워드", styles["h2"]))
        chart_path = tmp_dir / "_chart_keywords.png"
        make_keyword_chart(keyword_trend, chart_path)
        story.append(Image(str(chart_path), width=160 * mm, height=79 * mm))

    watch_channels = data.get("watch_channels", [])
    if watch_channels:
        story.append(Paragraph("오늘 주목할 채널", styles["h2"]))
        table_data = [["채널", "구독자", "신호", "영상 / 이유"]]
        for ch in watch_channels:
            cell = Paragraph(f"{ch['video_title']}<br/><font color='{COLOR_MUTED}'>{ch['why']}</font>", styles["muted"])
            table_data.append([
                Paragraph(ch["channel_title"], styles["muted"]),
                f"{ch['subscriber_count']:,}",
                Paragraph(ch["signal"], styles["muted"]),
                cell,
            ])
        table = Table(table_data, colWidths=[28 * mm, 20 * mm, 32 * mm, 84 * mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "NanumGothic-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor(COLOR_BASELINE)),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor(COLOR_GRIDLINE)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)

    recommendations = data.get("recommendations", [])
    if recommendations:
        story.append(Paragraph("오늘의 콘텐츠 주제 추천", styles["h2"]))
        for i, rec in enumerate(recommendations, 1):
            story.append(Paragraph(f"{i}. {rec.get('title', '')}", styles["rec_title"]))
            if rec.get("reason"):
                story.append(Paragraph(rec["reason"], styles["body"]))

    def render_scripts(scripts: list[dict]):
        for script in scripts:
            story.append(Spacer(1, 10))
            header = Table(
                [[Paragraph(script["number"], styles["script_num"]),
                  [Paragraph(script["title"], styles["script_title"]), Paragraph(script["type"], styles["script_type"])]]],
                colWidths=[16 * mm, 148 * mm],
            )
            header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(header)
            for beat in script["beats"]:
                row = Table(
                    [[Paragraph(beat["time"], styles["beat_time"]), Paragraph(beat["text"], styles["beat_text"])]],
                    colWidths=[18 * mm, 146 * mm],
                )
                row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
                story.append(row)

    scripts = data.get("scripts", [])
    if scripts:
        story.append(Paragraph("예시 대본 5개 (트렌드·후킹 기반)", styles["h2"]))
        render_scripts(scripts)

    helpful_topics = data.get("helpful_topics", [])
    if helpful_topics:
        story.append(Paragraph("시청자에게 실질적으로 도움되는 주제 5개", styles["h2"]))
        story.append(Paragraph(
            "트렌드/후킹이 아니라, 실제 요리 지식과 노하우로 시청자에게 도움이 되는 주제입니다.",
            styles["muted"],
        ))
        for i, topic in enumerate(helpful_topics, 1):
            story.append(Paragraph(f"{i}. {topic.get('title', '')}", styles["rec_title"]))
            if topic.get("reason"):
                story.append(Paragraph(topic["reason"], styles["body"]))

    helpful_scripts = data.get("helpful_scripts", [])
    if helpful_scripts:
        story.append(Paragraph("위 주제 대본 5개 (정보성)", styles["h2"]))
        render_scripts(helpful_scripts)

    if data.get("closing"):
        story.append(Spacer(1, 8))
        story.append(Paragraph(data["closing"], styles["body"]))

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        topMargin=20 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title="일일 요리 쇼츠 트렌드 리포트",
    )
    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description="일일 요리 트렌드 PDF 리포트 생성")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
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
