"""
자동화를 실행하기 전에, 필요한 키/토큰이 다 준비됐는지 미리 확인하는 Tool.

이걸 먼저 돌리면 "PDF가 안 생겼다" 같은 뭔지 모를 실패 대신,
정확히 뭐가 비어있는지 바로 알 수 있다. workflows/weekly_youtube_trend_report.md의
0번 단계로 항상 이걸 먼저 실행한다.

사용법:
    python tools/check_setup.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

REQUIRED_VARS = {
    "YOUTUBE_API_KEY": "유튜브 데이터 수집 (Google Cloud Console에서 발급)",
    "EMAIL_ADDRESS": "이메일 발송/수신용 Gmail 주소",
    "GOOGLE_OAUTH_CLIENT_ID": "Gmail API OAuth 클라이언트 ID",
    "GOOGLE_OAUTH_CLIENT_SECRET": "Gmail API OAuth 클라이언트 보안 비밀",
    "GOOGLE_OAUTH_REFRESH_TOKEN": "Gmail API 리프레시 토큰 (tools/_oauth_setup_gmail.py로 최초 1회 발급)",
    "GOOGLE_SHEET_ID": "기록할 구글 시트 ID (시트 URL의 /d/ 다음 부분)",
}
OPTIONAL_VARS = {
    "REPORT_RECIPIENT_EMAIL": "리포트 받을 이메일 (비워두면 EMAIL_ADDRESS 자기 자신)",
}
REQUIRED_FILES = {
    ROOT_DIR / "credentials.json": "구글 서비스 계정 키 (Google Cloud Console > IAM 및 관리자 > 서비스 계정 > 키)",
}


def main():
    load_dotenv(ROOT_DIR / ".env")

    missing = []
    print("=== 자동화 실행 전 점검 ===")
    for name, description in REQUIRED_VARS.items():
        value = os.environ.get(name)
        if value:
            print(f"[OK]      {name}")
        else:
            print(f"[누락]    {name}  <- {description}")
            missing.append(name)

    for path, description in REQUIRED_FILES.items():
        if path.exists():
            print(f"[OK]      {path.name}")
        else:
            print(f"[누락]    {path.name}  <- {description}")
            missing.append(path.name)

    for name, description in OPTIONAL_VARS.items():
        value = os.environ.get(name)
        status = "OK" if value else "비어있음(선택)"
        print(f"[{status:8}] {name}  <- {description}")

    print()
    if missing:
        print(f"{len(missing)}개 항목이 비어있습니다: {', '.join(missing)}")
        print("claude.ai Routine 프롬프트(클라우드 실행) 또는 로컬 .env/credentials.json(로컬 테스트)에 값을 채워주세요.")
        sys.exit(1)

    print("모든 필수 항목이 준비됐습니다. 다음 단계로 진행하세요.")
    sys.exit(0)


if __name__ == "__main__":
    main()
