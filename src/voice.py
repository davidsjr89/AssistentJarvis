import os
import subprocess
import tempfile
import tomllib
from pathlib import Path
from cli import send_prompt

APP_DIR = Path.home() / "Projetos/AssistentJarvis"
CONFIG = tomllib.loads((APP_DIR / "config.toml").read_text(encoding="utf-8"))

WHISPER_BIN = os.path.expanduser(CONFIG["voice"]["whisper_bin"])
WHISPER_MODEL = os.path.expanduser(CONFIG["voice"]["whisper_model"])
PIPER_BIN = os.path.expanduser(CONFIG["voice"]["piper_bin"])
PIPER_VOICE = os.path.expanduser(CONFIG["voice"]["piper_voice"])


def speak(text: str) -> None:
    clean = text.replace("*", "").replace("#", "").replace("`", "")
    piper = subprocess.Popen(
        [PIPER_BIN, "--model", PIPER_VOICE, "--output_raw"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    play = subprocess.Popen(
        ["pw-play", "--raw", "--rate=22050", "--channels=1", "--format=s16", "-"],
        stdin=piper.stdout,
    )
    piper.stdin.write(clean.encode("utf-8"))
    piper.stdin.close()
    play.wait()


def main() -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    try:
        subprocess.run(["notify-send", "CachyOS Assistant", "🎙️ Ouvindo... (5 segundos)"], check=False)
        subprocess.run(
            ["timeout", "5", "pw-record", "--format=s16", "--rate=16000", "--channels=1", wav_path],
            check=False,
        )
        res = subprocess.run(
            [WHISPER_BIN, "-m", WHISPER_MODEL, "-l", "pt", "-nt", "-f", wav_path],
            capture_output=True,
            text=True,
        )
        transcript = res.stdout.strip()
        if not transcript:
            subprocess.run(["notify-send", "CachyOS Assistant", "Nenhuma fala detectada."], check=False)
            return

        subprocess.run(["notify-send", "Você disse:", transcript], check=False)
        resp = send_prompt(transcript)
        speak(resp["reply"])
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


if __name__ == "__main__":
    main()
