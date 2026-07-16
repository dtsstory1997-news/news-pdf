from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"필수 환경변수 {name}이 없습니다.")
    return value


def authorization(api_key: str, api_secret: str) -> str:
    date = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    salt = uuid.uuid4().hex
    signature = hmac.new(api_secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    return f"HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}"


def main() -> None:
    api_key, api_secret = required("SOLAPI_API_KEY"), required("SOLAPI_API_SECRET")
    recipients = [x.strip() for x in required("SOLAPI_RECIPIENTS").split(",") if x.strip()]
    report_url = required("REPORT_URL")
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")
    variables = {"#{날짜}": today, "#{링크}": report_url}
    messages = []
    for recipient in recipients:
        messages.append({
            "to": recipient,
            "from": required("SOLAPI_SENDER"),
            "kakaoOptions": {
                "pfId": required("SOLAPI_PF_ID"),
                "templateId": required("SOLAPI_TEMPLATE_ID"),
                "variables": variables
            }
        })
    payload = json.dumps({"messages": messages}, ensure_ascii=False).encode()
    req = urllib.request.Request("https://api.solapi.com/messages/v4/send-many/detail", data=payload, method="POST", headers={"Authorization": authorization(api_key, api_secret), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        print(response.read().decode())


if __name__ == "__main__":
    main()

