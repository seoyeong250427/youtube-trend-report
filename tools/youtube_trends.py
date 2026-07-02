"""
매주 유튜브에서 트렌드 데이터를 수집하는 Tool.

tools/config/youtube_keywords.json 에 있는 키워드로 최근 인기 영상을 검색하고,
조회수/좋아요/영상길이/자막 텍스트를 모아 원본 JSON으로 저장한다.
분석이나 추천 문구는 만들지 않는다 (그건 Workflow를 실행하는 Agent가 한다).

사용법:
    python tools/youtube_trends.py [--output .tmp/youtube_trends.json]

필요 환경변수:
    YOUTUBE_API_KEY
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
KEYWORDS_CONFIG_PATH = ROOT_DIR / "tools" / "config" / "youtube_keywords.json"
DEFAULT_OUTPUT_PATH = ROOT_DIR / ".tmp" / "youtube_trends.json"

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
TRANSCRIPT_CHAR_LIMIT = 800


def load_config() -> dict:
    with open(KEYWORDS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_iso8601_duration(duration: str) -> int:
    """PT1H2M10S 같은 형식을 초 단위 정수로 변환."""
    import re

    match = re.match(
        r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration
    )
    if not match:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def fetch_transcript_text(video_id: str) -> str | None:
    """가능하면 자막 텍스트를 가져온다. 없으면 None (에러로 취급하지 않음)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None

    try:
        # 신버전(1.x) 인터페이스
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["ko", "en"])
        text = " ".join(snippet.text for snippet in transcript)
    except AttributeError:
        try:
            # 구버전 인터페이스
            raw = YouTubeTranscriptApi.get_transcript(video_id, languages=["ko", "en"])
            text = " ".join(item["text"] for item in raw)
        except Exception:
            return None
    except Exception:
        return None

    text = text.strip()
    if not text:
        return None
    return text[:TRANSCRIPT_CHAR_LIMIT]


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
    }
    resp = requests.get(SEARCH_URL, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"  [경고] '{keyword}' 검색 실패 ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
        return []
    data = resp.json()
    return [item["id"]["videoId"] for item in data.get("items", []) if item.get("id", {}).get("videoId")]


def fetch_video_details(api_key: str, video_ids: list[str]) -> list[dict]:
    """videos.list는 한 번에 최대 50개 ID까지 받는다."""
    details = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        params = {
            "key": api_key,
            "id": ",".join(batch),
            "part": "snippet,statistics,contentDetails",
        }
        resp = requests.get(VIDEOS_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  [경고] videos.list 실패 ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
            continue
        details.extend(resp.json().get("items", []))
    return details


def collect(api_key: str, config: dict) -> list[dict]:
    lookback_days = config.get("lookback_days", 10)
    max_per_keyword = config.get("max_videos_per_keyword", 15)
    max_total = config.get("max_total_videos", 60)
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
                "is_short": duration_seconds > 0 and duration_seconds <= 60,
                "matched_keywords": video_id_to_keywords.get(video_id, []),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "transcript_snippet": None,
            }
        )

    records.sort(key=lambda r: r["view_count"], reverse=True)
    records = records[:max_total]

    print(f"자막 수집 중 (상위 {len(records)}개)...")
    for record in records:
        record["transcript_snippet"] = fetch_transcript_text(record["video_id"])

    return records


def main():
    parser = argparse.ArgumentParser(description="유튜브 트렌드 데이터 수집")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("에러: YOUTUBE_API_KEY 환경변수가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    records = collect(api_key, config)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "keywords": config["keywords"],
        "video_count": len(records),
        "videos": records,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"완료: 영상 {len(records)}개 -> {output_path}")


if __name__ == "__main__":
    main()
