"""
주간 트렌드 분석 데이터를 노션 데이터베이스에 누적 기록하는 Tool.

Notion 공식 API를 직접 호출한다 (Integration 토큰 방식) — MCP 커넥터가 아니라
requests로 직접 호출하는 이유는 무인 스케줄 자동화에서 더 안정적이기 때문.

사용법:
    python tools/notion_logger.py --input .tmp/analysis.json

analysis.json 스키마는 generate_report_pdf.py 상단 docstring 참고.

필요 환경변수:
    NOTION_TOKEN         Notion Integration 토큰 (secret_...)
    NOTION_DATABASE_ID   기록할 데이터베이스 ID

사전 준비:
    1. notion.so/my-integrations 에서 Integration 생성, 토큰 복사
    2. 기록할 데이터베이스 페이지에서 "···" -> Connections -> 해당 Integration 연결
       (연결 안 하면 API가 "object not found" 에러를 낸다)

이 데이터베이스에는 다음 속성(컬럼)이 있어야 한다 (Notion에서 미리 만들어둘 것):
    - 주차 (Title)
    - 인기 주제 (Rich text)
    - 인기 포맷 (Rich text)
    - 추천 주제 (Rich text)
    - 분석 영상 수 (Number)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


def build_page_payload(database_id: str, data: dict) -> dict:
    top_topics = data.get("top_topics", [])
    topics_text = ", ".join(t["topic"] for t in top_topics[:5]) or "-"

    format_analysis = data.get("format_analysis", {})
    format_text = (
        f"Shorts 평균 {format_analysis.get('shorts_avg_views', 0):,}회 "
        f"(영상 {format_analysis.get('shorts_count', 0)}개) / "
        f"롱폼 평균 {format_analysis.get('longform_avg_views', 0):,}회 "
        f"(영상 {format_analysis.get('longform_count', 0)}개)"
    ) if format_analysis else "-"

    recommendations = data.get("recommendations", [])
    recommendations_text = "; ".join(r.get("title", "") for r in recommendations) or "-"

    video_count = len(data.get("top_videos", [])) or data.get("video_count", 0)

    return {
        "parent": {"database_id": database_id},
        "properties": {
            "주차": {"title": [{"text": {"content": data.get("week_label", "")}}]},
            "인기 주제": {"rich_text": [{"text": {"content": topics_text[:2000]}}]},
            "인기 포맷": {"rich_text": [{"text": {"content": format_text[:2000]}}]},
            "추천 주제": {"rich_text": [{"text": {"content": recommendations_text[:2000]}}]},
            "분석 영상 수": {"number": video_count},
        },
    }


def create_page(token: str, database_id: str, data: dict):
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    payload = build_page_payload(database_id, data)
    resp = requests.post(NOTION_API_URL, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 300:
        print(f"에러: Notion 페이지 생성 실패 ({resp.status_code}): {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="주간 분석 데이터를 노션에 기록")
    parser.add_argument("--input", required=True, help="분석 결과 JSON 경로")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")
    token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not token or not database_id:
        print("에러: NOTION_TOKEN / NOTION_DATABASE_ID 환경변수가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = create_page(token, database_id, data)
    print(f"완료: 노션 페이지 생성됨 -> {result.get('url', result.get('id'))}")


if __name__ == "__main__":
    main()
