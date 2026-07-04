"""
매일 요리 트렌드 데이터를 수집하는 Tool.

tools/config/cooking_keywords.json 의 키워드로 최근 인기 요리 영상을 검색하고,
영상 원본 데이터 + 채널별 집계를 만든다. 분석/추천 문구는 만들지 않는다
(그건 워크플로를 실행하는 Agent가 한다).

주의 — 데이터 한계 (있는 척 하지 않음):
- "검색 수요"는 실제 검색량이 아니라 유튜브 조회수를 대신 쓰는 추정치다 (구글 트렌드
  공식 API가 없어서). generate_daily_report_pdf.py에서도 이걸 "추정치"라고 명시해야 한다.
- 사운드/음악 트렌드는 유튜브 공식 API가 제공하지 않아 이 Tool은 수집하지 않는다.
- "급성장 채널"의 정확한 성장률은 channel_growth_tracker.py가 며칠간 데이터를 쌓아야
  계산 가능하다. 데이터가 없는 초기에는 "이번 기간 조회수 급증 채널"로 대체한다.

사용법:
    python tools/cooking_daily_trends.py --output .tmp/cooking_daily_trends.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
KEYWORDS_CONFIG_PATH = ROOT_DIR / "tools" / "config" / "cooking_keywords.json"
DEFAULT_OUTPUT_PATH = ROOT_DIR / ".tmp" / "cooking_daily_trends.json"

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


def load_config() -> dict:
    with open(KEYWORDS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_iso8601_duration(duration: str) -> int:
    match = re.match(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def search_video_ids(api_key: str, keyword: str, published_after: str, max_results: int) -> list[str]:
    params = {
        "key": api_key,
        "q": keyword,
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": max_results,
        "relevanceLanguage": "ko",
        "regionCode": "KR",
    }
    resp = requests.get(SEARCH_URL, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"  [경고] '{keyword}' 검색 실패 ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        return []
    data = resp.json()
    return [item["id"]["videoId"] for item in data.get("items", []) if item.get("id", {}).get("videoId")]


def fetch_video_details(api_key: str, video_ids: list[str]) -> list[dict]:
    details = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        params = {"key": api_key, "id": ",".join(batch), "part": "snippet,statistics,contentDetails"}
        resp = requests.get(VIDEOS_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  [경고] videos.list 실패 ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
            continue
        details.extend(resp.json().get("items", []))
    return details


def fetch_channel_stats(api_key: str, channel_ids: list[str]) -> dict:
    stats = {}
    unique_ids = list(set(channel_ids))
    for i in range(0, len(unique_ids), 50):
        batch = unique_ids[i : i + 50]
        params = {"key": api_key, "id": ",".join(batch), "part": "statistics,snippet"}
        resp = requests.get(CHANNELS_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  [경고] channels.list 실패 ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
            continue
        for item in resp.json().get("items", []):
            s = item.get("statistics", {})
            stats[item["id"]] = {
                "title": item["snippet"]["title"],
                "subscriber_count": int(s.get("subscriberCount", 0)),
                "view_count": int(s.get("viewCount", 0)),
                "video_count": int(s.get("videoCount", 0)),
            }
    return stats


def collect(api_key: str, config: dict) -> dict:
    lookback_days = config.get("lookback_days", 3)
    max_per_keyword = config.get("max_videos_per_keyword", 15)
    max_total = config.get("max_total_videos", 80)
    keywords = config["keywords"]

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    video_id_to_keywords: dict[str, list[str]] = {}
    for keyword in keywords:
        print(f"검색 중: {keyword}")
        ids = search_video_ids(api_key, keyword, published_after, max_per_keyword)
        for vid in ids:
            video_id_to_keywords.setdefault(vid, []).append(keyword)

    print(f"영상 {len(video_id_to_keywords)}개 상세정보 조회 중...")
    details = fetch_video_details(api_key, list(video_id_to_keywords.keys()))

    records = []
    for item in details:
        video_id = item["id"]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})
        duration_seconds = parse_iso8601_duration(content.get("duration", "PT0S"))

        records.append(
            {
                "video_id": video_id,
                "title": snippet.get("title"),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "published_at": snippet.get("publishedAt"),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "duration_seconds": duration_seconds,
                "is_short": duration_seconds > 0 and duration_seconds <= 180,
                "matched_keywords": video_id_to_keywords.get(video_id, []),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    records.sort(key=lambda r: r["view_count"], reverse=True)
    records = records[:max_total]

    channel_ids = [r["channel_id"] for r in records if r["channel_id"]]
    print(f"채널 {len(set(channel_ids))}개 통계 조회 중...")
    channel_stats = fetch_channel_stats(api_key, channel_ids)

    channel_agg: dict[str, dict] = {}
    for r in records:
        cid = r["channel_id"]
        if not cid:
            continue
        agg = channel_agg.setdefault(
            cid,
            {
                "channel_id": cid,
                "channel_title": r["channel_title"],
                "videos_in_window": [],
                "total_views_in_window": 0,
                "subscriber_count": channel_stats.get(cid, {}).get("subscriber_count", 0),
                "total_channel_views": channel_stats.get(cid, {}).get("view_count", 0),
                "total_channel_videos": channel_stats.get(cid, {}).get("video_count", 0),
            },
        )
        agg["videos_in_window"].append({"title": r["title"], "view_count": r["view_count"], "url": r["url"]})
        agg["total_views_in_window"] += r["view_count"]

    channels_ranked = sorted(channel_agg.values(), key=lambda c: c["total_views_in_window"], reverse=True)

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "keywords": keywords,
        "video_count": len(records),
        "videos": records,
        "channels_ranked_by_window_views": channels_ranked[:20],
        "data_caveats": [
            "조회수는 실제 검색 수요가 아니라 대신 쓰는 추정치입니다.",
            "사운드/음악 트렌드는 유튜브 공식 API가 제공하지 않아 이 데이터에는 없습니다.",
            "채널 성장률(구독자 증가 %)은 이 파일에 없습니다 — tools/channel_growth_tracker.py가 며칠치 기록이 쌓여야 계산합니다. 그전까지 channels_ranked_by_window_views는 '성장률'이 아니라 '이번 기간 조회수 총합' 랭킹입니다.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="일일 요리 트렌드 데이터 수집")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("에러: YOUTUBE_API_KEY 환경변수가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    payload = collect(api_key, config)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"완료: 영상 {payload['video_count']}개, 채널 {len(payload['channels_ranked_by_window_views'])}개 -> {output_path}")


if __name__ == "__main__":
    main()
