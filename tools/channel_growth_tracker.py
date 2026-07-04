"""
요리 채널의 구독자/조회수를 매일 기록해서, 며칠 후부터 실제 성장률을 계산하는 Tool.

같은 구글 시트(GOOGLE_SHEET_ID)에 "채널성장추적"이라는 탭을 따로 만들어서 쓴다.
탭이 없으면 자동으로 만든다.

두 가지 동작:
    python tools/channel_growth_tracker.py --log --input .tmp/cooking_daily_trends.json
        오늘 수집된 채널들의 구독자/조회수를 오늘 날짜로 기록

    python tools/channel_growth_tracker.py --report --input .tmp/cooking_daily_trends.json --output .tmp/channel_growth.json
        기록된 과거 데이터와 비교해서 성장률을 계산 (과거 기록이 없는 채널은 제외)

필요한 것: credentials.json, GOOGLE_SHEET_ID (기존 자동화와 동일)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIALS_PATH = ROOT_DIR / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TAB_NAME = "채널성장추적"
GROWTH_THRESHOLD_PCT = 5.0  # 이 이상 늘어난 채널만 "급성장"으로 취급


def get_access_token(credentials_path: Path) -> str:
    creds = Credentials.from_service_account_file(str(credentials_path), scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def ensure_tab_exists(sheet_id: str, access_token: str):
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
        headers=headers,
        params={"fields": "sheets.properties.title"},
        timeout=30,
    )
    titles = [s["properties"]["title"] for s in resp.json().get("sheets", [])]
    if TAB_NAME in titles:
        return
    requests.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}:batchUpdate",
        headers={**headers, "Content-Type": "application/json"},
        json={"requests": [{"addSheet": {"properties": {"title": TAB_NAME}}}]},
        timeout=30,
    )
    # 헤더 행 추가
    requests.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/'{TAB_NAME}'!A:E:append",
        headers={**headers, "Content-Type": "application/json"},
        params={"valueInputOption": "USER_ENTERED"},
        json={"values": [["날짜", "채널ID", "채널명", "구독자수", "총조회수"]]},
        timeout=30,
    )


def log_today(sheet_id: str, access_token: str, data: dict):
    ensure_tab_exists(sheet_id, access_token)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = []
    for ch in data.get("channels_ranked_by_window_views", []):
        rows.append([today, ch["channel_id"], ch["channel_title"], ch["subscriber_count"], ch["total_channel_views"]])
    if not rows:
        print("기록할 채널이 없습니다.")
        return
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = requests.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/'{TAB_NAME}'!A:E:append",
        headers=headers,
        params={"valueInputOption": "USER_ENTERED"},
        json={"values": rows},
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"에러: 기록 실패 ({resp.status_code}): {resp.text[:400]}", file=sys.stderr)
        sys.exit(1)
    print(f"완료: 채널 {len(rows)}개 오늘({today}) 기록됨")


def read_history(sheet_id: str, access_token: str) -> list[list[str]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/'{TAB_NAME}'!A2:E100000",
        headers=headers,
        timeout=30,
    )
    if resp.status_code >= 300:
        return []
    return resp.json().get("values", [])


def compute_growth(sheet_id: str, access_token: str, data: dict) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = read_history(sheet_id, access_token)

    earliest_by_channel: dict[str, tuple] = {}
    for row in history:
        if len(row) < 5:
            continue
        date, channel_id, channel_title, sub_count, total_views = row[:5]
        if date == today:
            continue
        try:
            sub_count = int(sub_count)
        except (ValueError, TypeError):
            continue
        existing = earliest_by_channel.get(channel_id)
        if existing is None or date < existing[0]:
            earliest_by_channel[channel_id] = (date, channel_title, sub_count)

    growers = []
    for ch in data.get("channels_ranked_by_window_views", []):
        cid = ch["channel_id"]
        prior = earliest_by_channel.get(cid)
        if not prior:
            continue
        prior_date, _, prior_subs = prior
        current_subs = ch["subscriber_count"]
        if prior_subs <= 0:
            continue
        pct_change = (current_subs - prior_subs) / prior_subs * 100
        if pct_change >= GROWTH_THRESHOLD_PCT:
            growers.append(
                {
                    "channel_id": cid,
                    "channel_title": ch["channel_title"],
                    "subscriber_count": current_subs,
                    "prior_subscriber_count": prior_subs,
                    "prior_date": prior_date,
                    "growth_pct": round(pct_change, 1),
                    "recent_videos": ch["videos_in_window"][:5],
                }
            )

    growers.sort(key=lambda g: g["growth_pct"], reverse=True)
    return {
        "has_historical_data": len(earliest_by_channel) > 0,
        "growers": growers,
    }


def main():
    parser = argparse.ArgumentParser(description="채널 성장 기록/계산")
    parser.add_argument("--log", action="store_true", help="오늘 데이터를 기록")
    parser.add_argument("--report", action="store_true", help="과거 데이터와 비교해서 성장률 계산")
    parser.add_argument("--input", required=True, help="cooking_daily_trends.json 경로")
    parser.add_argument("--output", help="--report 결과를 저장할 경로")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id or not DEFAULT_CREDENTIALS_PATH.exists():
        print("에러: GOOGLE_SHEET_ID 또는 credentials.json이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    access_token = get_access_token(DEFAULT_CREDENTIALS_PATH)

    if args.log:
        log_today(sheet_id, access_token, data)

    if args.report:
        result = compute_growth(sheet_id, access_token, data)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"완료: 급성장 채널 {len(result['growers'])}개 발견 (과거 데이터 있음: {result['has_historical_data']})")


if __name__ == "__main__":
    main()
