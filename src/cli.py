import json
import os
import socket
import sys
import tomllib
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

APP_DIR = Path.home() / "Projetos/AssistentJarvis"
CONFIG = tomllib.loads((APP_DIR / "config.toml").read_text(encoding="utf-8"))
SOCKET_PATH = os.path.expanduser(CONFIG["paths"]["socket_path"])
console = Console()


def send_prompt(prompt: str) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(SOCKET_PATH)
        s.sendall(json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while data := s.recv(65536):
            chunks.append(data)
    return json.loads(b"".join(chunks).decode("utf-8"))


def interactive_loop() -> None:
    console.print(Panel("[bold cyan]CachyOS Assistant[/bold cyan] • Digite sua ordem (ou 'sair' / '/clear')", expand=False))
    while True:
        try:
            prompt = console.input("\n[bold green]Você > [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not prompt or prompt.lower() in {"sair", "exit", "quit"}:
            break
        with console.status("[cyan]Processando na RTX 5080...[/cyan]"):
            resp = send_prompt(prompt)
        console.print(f"\n[dim]Modelo: {resp['model']}[/dim]")
        console.print(Markdown(resp["reply"]))


def main() -> None:
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        with console.status("[cyan]Processando...[/cyan]"):
            resp = send_prompt(prompt)
        console.print(f"[dim]Modelo: {resp['model']}[/dim]")
        console.print(Markdown(resp["reply"]))
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
