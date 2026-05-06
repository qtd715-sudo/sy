import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

RECIPIENTS = ["ssarang615@naver.com", "qtd715@gmail.com"]

PROVIDERS = {
    "gmail": ("smtp.gmail.com", 465),
    "naver": ("smtp.naver.com", 465),
}


def send(subject: str, body: str, to: list[str] | None = None) -> None:
    sender = os.environ.get("MAIL_SENDER")
    password = os.environ.get("MAIL_PASSWORD")
    provider = os.environ.get("MAIL_PROVIDER", "gmail").lower()

    if not sender or not password:
        sys.exit("MAIL_SENDER, MAIL_PASSWORD 환경변수를 설정하세요. (Gmail은 앱 비밀번호 필요)")
    if provider not in PROVIDERS:
        sys.exit(f"MAIL_PROVIDER must be one of {list(PROVIDERS)}")

    host, port = PROVIDERS[provider]
    recipients = to or RECIPIENTS

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

    print(f"보낸사람: {sender}")
    print(f"받는사람: {', '.join(recipients)}")
    print(f"제목: {subject}")
    print("발송 완료")


if __name__ == "__main__":
    subject = sys.argv[1] if len(sys.argv) > 1 else "테스트 메일"
    body = sys.argv[2] if len(sys.argv) > 2 else "SY 프로젝트에서 보낸 테스트 메일입니다."
    send(subject, body)
