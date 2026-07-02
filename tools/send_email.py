"""
PDF 리포트를 Gmail(SMTP)로 발송하는 Tool.

OAuth 대신 앱 비밀번호 방식을 쓴다 — 토큰 만료/갱신 걱정이 없어서
사장님이 직접 유지보수하기 쉽다.

사용법:
    python tools/send_email.py --pdf .tmp/report.pdf --subject "이번 주 트렌드 리포트" --body "..."

필요 환경변수:
    EMAIL_ADDRESS        보내는 Gmail 주소
    EMAIL_APP_PASSWORD   Google 계정 2단계 인증 후 발급받은 16자리 앱 비밀번호
    REPORT_RECIPIENT_EMAIL  받는 사람 이메일 (기본값: EMAIL_ADDRESS 자기 자신)
"""

import argparse
import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(sender: str, app_password: str, recipient: str, subject: str, body: str, pdf_path: Path):
    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        message.attach(attachment)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(sender, app_password)
        server.send_message(message)


def main():
    parser = argparse.ArgumentParser(description="PDF 리포트를 Gmail로 발송")
    parser.add_argument("--pdf", required=True, help="첨부할 PDF 경로")
    parser.add_argument("--subject", default="주간 유튜브 트렌드 리포트")
    parser.add_argument("--body", default="이번 주 트렌드 리포트를 첨부합니다.")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env")
    sender = os.environ.get("EMAIL_ADDRESS")
    app_password = os.environ.get("EMAIL_APP_PASSWORD")
    recipient = os.environ.get("REPORT_RECIPIENT_EMAIL") or sender

    if not sender or not app_password:
        print("에러: EMAIL_ADDRESS / EMAIL_APP_PASSWORD 환경변수가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"에러: PDF 파일을 찾을 수 없습니다: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    send_email(sender, app_password, recipient, args.subject, args.body, pdf_path)
    print(f"완료: {recipient} 로 이메일 발송됨 ({pdf_path.name} 첨부)")


if __name__ == "__main__":
    main()
