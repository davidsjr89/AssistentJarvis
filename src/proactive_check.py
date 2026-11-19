import json
import subprocess
from datetime import datetime, timedelta, timezone
import keyring
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SERVICE_NAME = "cachy-assistant-google"


def main() -> None:
    raw = keyring.get_password(SERVICE_NAME, "oauth_token")
    if not raw:
        return  # Ainda não autenticado

    creds = Credentials.from_authorized_user_info(json.loads(raw))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        keyring.set_password(SERVICE_NAME, "oauth_token", creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    now = datetime.now(timezone.utc)
    soon = now + timedelta(minutes=20)
    events = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=soon.isoformat(),
            singleEvents=True,
        )
        .execute()
        .get("items", [])
    )
    for e in events:
        summary = e.get("summary", "Compromisso")
        subprocess.run(
            ["notify-send", "-u", "normal", "📅 Compromisso em breve", summary],
            check=False,
        )


if __name__ == "__main__":
    main()
