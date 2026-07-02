"""
주간 트렌드 분석 데이터를 구글 시트에 누적 기록하는 Tool.

노션 대신 구글 시트를 쓰는 이유: 클라우드 Routine 실행 환경의 네트워크 정책이
googleapis.com 계열 주소는 허용하지만 notion.com은 막아서, 노션 API 호출이
클라우드에서 실패했다. 구글 시트는 같은 googleapis.com 계열이라 클라우드에서도 동작한다.

서비스 계정(사람이 아니라 프로그램 전용 구글 계정) 방식을 쓴다 — OAuth 로그인 절차 없이
JSON 키 파일 하나로 인증한다.

사용법:
    python tools/sheets_logger.py --input .tmp/analysis.json

필요한 것:
    - credentials.json: 서비스 계정 키 파일 (프로젝트 루트, .gitignore 처리됨)
    - GOOGLE_SHEET_ID 환경변수: 기록할 구글 시트의 ID (시트 URL의 /d/ 다음, /edit 이전 부분)
    - 그 시트를 credentials.json 안의 client_email 주소와 "편집자"로 공유해뒀을 것

시트에는 헤더 행(1행)에 "주차, 인기 주제, 인기 포맷, 추천 주제, 분석 영상 수"를
미리 넣어두면 보기 좋다 (없어도 데이터는 그대로 쌓인다).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIALS_PATH = ROOT_DIR / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_access_token(credentials_path: Path) -> str:
    creds = Credentials.from_service_account_file(str(credentials_path), scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def get_first_sheet_title(sheet_id: str, access_token: str) -> str:
    """탭 이름이 언어 설정에 따라 'Sheet1'이 아니라 '시트1' 등일 수 있어, 실제 이름을 조회한다."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers, params={"fields": "sheets.properties.title"}, timeout=30)
    if resp.status_code >= 300:
        print(f"에러: 구글 시트 정보 조회 실패 ({resp.status_code}): {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)
    sheets = resp.json().get("sheets", [])
    if not sheets:
        print("에러: 시트에 탭이 하나도 없습니다.", file=sys.stderr)
        sys.exit(1)
    return sheets[0]["properties"]["title"]


def build_row(data: dict) -> list:
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

    return [data.get("week_label", ""), topics_text, format_text, recommendations_text, video_count]


def append_row(sheet_id: str, access_token: str, sheet_title: str, row: list):
    sheet_range = f"'{sheet_title}'!A:E"
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{sheet_range}:append"
    params = {"valueInputOption": "USER_ENTERED"}
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"values": [row]}
    resp = requests.post(url, params=params, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 300:
        print(f"에러: 구글 시트 기록 실패 ({resp.status_code}): {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="주간 분석 데이터를 구글 시트에 기록")
    parser.add_argument("--input", required=True, help="분석 결과 JSON 경로")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("에러: GOOGLE_SHEET_ID 환경변수가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    if not DEFAULT_CREDENTIALS_PATH.exists():
        print(f"에러: {DEFAULT_CREDENTIALS_PATH} 파일을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    access_token = get_access_token(DEFAULT_CREDENTIALS_PATH)
    sheet_title = get_first_sheet_title(sheet_id, access_token)
    row = build_row(data)
    result = append_row(sheet_id, access_token, sheet_title, row)
    updated_range = result.get("updates", {}).get("updatedRange", "")
    print(f"완료: 구글 시트에 기록됨 -> {updated_range}")


if __name__ == "__main__":
    main()
