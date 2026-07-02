"""
Gmail API를 쓰기 위한 최초 1회 인증 스크립트.

이 스크립트를 로컬에서 한 번 실행하면 브라우저가 열리고, 로그인 후 "허용"을 누르면
refresh_token이 발급된다. 이 토큰은 만료 걱정 없이(Production 게시 시) 계속 쓸 수 있어서,
클라우드 Routine에서는 이 스크립트를 다시 실행할 필요가 없다 — 발급받은 토큰 값만
환경변수로 넘겨주면 된다.

사용법:
    python tools/_oauth_setup_gmail.py

다 끝나면 이 파일은 삭제해도 된다 (한 번만 쓰고 버리는 스크립트).
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main():
    if len(sys.argv) != 3:
        print("사용법: python tools/_oauth_setup_gmail.py <CLIENT_ID> <CLIENT_SECRET>")
        sys.exit(1)

    client_id, client_secret = sys.argv[1], sys.argv[2]

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=== 인증 완료 ===")
    print(f"REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
