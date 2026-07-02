"""
PDF 리포트를 Gmail API로 발송하는 Tool.

원래는 SMTP(smtplib) + 앱 비밀번호 방식이었으나, 클라우드 Routine 실행 환경의
네트워크 프록시가 raw TCP 소켓 연결(SMTP가 쓰는 방식) 자체를 지원하지 않아서
실패했다 (OSError: Address family not supported by protocol). Gmail API는
HTTPS REST 호출이라 googleapis.com 계열 주소로 나가는 게 이미 허용되어 있어
클라우드에서도 동작한다.

OAuth 인증을 쓰지만, 사람이 매번 로그인할 필요는 없다 — tools/_oauth_setup_gmail.py를
최초 1회만 로컬에서 실행해서 refresh_token을 발급받아두면, 그 뒤로는 이 토큰으로
계속 새 access_token을 발급받아 쓴다 (Google Cloud Console에서 OAuth 동의 화면을
"프로덕션"으로 게시해야 refresh_token이 만료되지 않는다).

사용법:
    python tools/send_email.py --pdf .tmp/report.pdf --subject "..." --body "..."

필요 환경변수:
    EMAIL_ADDRESS                 보내는/받는 기본 Gmail 주소
    GOOGLE_OAUTH_CLIENT_ID
    GOOGLE_OAUTH_CLIENT_SECRET
    GOOGLE_OAUTH_REFRESH_TOKEN
    REPORT_RECIPIENT_EMAIL        받는 사람 이메일 (기본값: EMAIL_ADDRESS 자기 자신)
"""

import argparse
import base64
import os
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"에러: Gmail 액세스 토큰 발급 실패 ({resp.status_code}): {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["access_token"]


def build_raw_message(sender: str, recipient: str, subject: str, body: str, pdf_path: Path) -> str:
    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        message.attach(attachment)

    raw_bytes = message.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")


def send_email(access_token: str, raw_message: str):
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = requests.post(SEND_URL, headers=headers, json={"raw": raw_message}, timeout=30)
    if resp.status_code >= 300:
        print(f"에러: Gmail 발송 실패 ({resp.status_code}): {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="PDF 리포트를 Gmail API로 발송")
    parser.add_argument("--pdf", required=True, help="첨부할 PDF 경로")
    parser.add_argument("--subject", default="주간 유튜브 트렌드 리포트")
    parser.add_argument("--body", default="이번 주 트렌드 리포트를 첨부합니다.")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")
    sender = os.environ.get("EMAIL_ADDRESS")
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")
    recipient = os.environ.get("REPORT_RECIPIENT_EMAIL") or sender

    if not all([sender, client_id, client_secret, refresh_token]):
        print(
            "에러: EMAIL_ADDRESS / GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / "
            "GOOGLE_OAUTH_REFRESH_TOKEN 환경변수가 설정되어 있지 않습니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"에러: PDF 파일을 찾을 수 없습니다: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    access_token = get_access_token(client_id, client_secret, refresh_token)
    raw_message = build_raw_message(sender, recipient, args.subject, args.body, pdf_path)
    send_email(access_token, raw_message)
    print(f"완료: {recipient} 로 이메일 발송됨 ({pdf_path.name} 첨부)")


if __name__ == "__main__":
    main()
