import sys
import keyring
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
SERVICE_NAME = "cachy-assistant-google"


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: assist-auth-google /caminho/para/credentials.json")
        sys.exit(1)

    creds_file = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
    creds = flow.run_local_server(port=0)
    keyring.set_password(SERVICE_NAME, "oauth_token", creds.to_json())
    print("✅ Token OAuth 2.0 salvo com segurança no Keyring do Linux (KWallet/GNOME Keyring).")
    print("Você já pode apagar o arquivo credentials.json se desejar.")


if __name__ == "__main__":
    main()
