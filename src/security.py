import json
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

AUDIT_LOG = Path.home() / "Projetos/AssistentJarvis/audit.log"

# Classificação das ferramentas por nível de risco
TOOL_LEVELS: dict[str, int] = {
    # Nível 1: Somente leitura (automático, sem pop-up)
    "system_health": 1,
    "list_projects": 1,
    "list_project_files": 1,
    "read_project_file": 1,
    "list_upcoming_events": 1,
    "list_unread_emails": 1,
    "search_emails": 1,
    "read_email": 1,
    "web_search": 1,
    "search_place": 1,
    # Nível 2: Escrita segura em ~/Projetos / sandbox / agenda / rascunhos (automático)
    "create_project": 2,
    "write_project_file": 2,
    "run_in_sandbox": 2,
    "check_project": 2,
    "create_calendar_event": 2,
    "update_calendar_event": 2,
    "create_email_draft": 2,
    # Nível 3: Comandos administrativos/destrutivos no host ou exclusão irreversível
    "run_host_command": 3,
    "delete_calendar_event": 3,
}

SAFE_READONLY_BINS = {
    "ls", "ll", "la", "tree", "find", "fd", "cat", "head", "tail",
    "grep", "rg", "wc", "stat", "file", "pwd", "which", "echo",
    "du", "df", "free", "uname", "uptime", "ps", "nvidia-smi",
}

SAFE_DEV_PATTERNS = (
    r"^git\s+(status|log|diff|branch|show|rev-parse)\b",
    r"^(dotnet|cargo|rustc|node|npm|npx|python3?|uv)\s+(--version|-v|-V|--info|check|build|test)\b",
)

SHELL_META_RE = re.compile(r"[;&|`$<>]|\$\(")
DANGEROUS_RE = re.compile(
    r"\b(rm|rmdir|shred|dd|mkfs|fdisk|parted|sudo|su|pkexec|pacman|paru|yay|systemctl|reboot|shutdown|poweroff|chmod|chown|kill|killall|pkill)\b"
)
SENSITIVE_PATH_RE = re.compile(
    r"(\.ssh|\.gnupg|\.aws|id_rsa|id_ed25519|/etc/shadow|client_secret|credentials\.json)",
    re.IGNORECASE,
)


def _is_safe_host_command(command: str) -> bool:
    cmd = (command or "").strip()
    if not cmd:
        return False
    if SHELL_META_RE.search(cmd) or DANGEROUS_RE.search(cmd) or SENSITIVE_PATH_RE.search(cmd):
        return False
    if any(re.match(pat, cmd) for pat in SAFE_DEV_PATTERNS):
        return True
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return False
    if not tokens:
        return False
    binary = Path(tokens[0]).name
    return binary in SAFE_READONLY_BINS


def log_audit(tool_name: str, args: dict, level: int, approved: bool, reason: str = "") -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_name,
        "level": level,
        "approved": approved,
        "reason": reason,
        "args": args,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _ask_desktop_confirmation(title: str, message: str) -> bool:
    """Abre pop-up nativo (KDE kdialog ou GTK zenity) apenas para ações destrutivas/críticas."""
    if shutil.which("kdialog"):
        res = subprocess.run(
            ["kdialog", "--title", title, "--warningyesno", message],
            capture_output=True,
        )
        return res.returncode == 0
    if shutil.which("zenity"):
        res = subprocess.run(
            ["zenity", "--question", "--title", title, "--text", message, "--width=480"],
            capture_output=True,
        )
        return res.returncode == 0
    return False


def authorize_tool_call(tool_name: str, args: dict, untrusted_context: bool = False) -> tuple[bool, str]:
    """
    Valida permissão da ferramenta.
    - Níveis 1 e 2 rodam direto (sem pop-up).
    - run_host_command com comandos seguros/somente leitura também roda direto.
    - Apenas comandos destrutivos/administrativos ou exclusões irreversíveis pedem confirmação.
    """
    level = TOOL_LEVELS.get(tool_name, 3)

    if level == 1:
        log_audit(tool_name, args, level, True, "auto_level_1")
        return True, "Autorizado (Nível 1)."

    if tool_name == "run_host_command" and not untrusted_context:
        if _is_safe_host_command(str(args.get("command", ""))):
            log_audit(tool_name, args, 1, True, "auto_safe_host_cmd")
            return True, "Autorizado automaticamente (comando seguro de leitura)."

    needs_prompt = (level >= 3) or (level == 2 and untrusted_context)
    if not needs_prompt:
        log_audit(tool_name, args, level, True, "auto_level_2")
        return True, "Autorizado (Nível 2)."

    reason_tag = " [CONTEXTO EXTERNO DETECTADO]" if untrusted_context else ""
    msg = (
        f"O assistente solicitou permissão para executar uma ação crítica (Nível {level}){reason_tag}:\n\n"
        f"Ferramenta: {tool_name}\n"
        f"Argumentos:\n{json.dumps(args, indent=2, ensure_ascii=False)}\n\n"
        f"Deseja permitir esta execução?"
    )
    approved = _ask_desktop_confirmation("CachyOS Assistant - Aprovação de Segurança", msg)
    log_audit(tool_name, args, level, approved, "hitl_prompt")
    if approved:
        return True, "Autorizado pelo usuário."
    return False, "Ação recusada pelo usuário na janela de segurança."
