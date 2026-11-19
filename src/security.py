import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

AUDIT_LOG = Path.home() / "Projetos/AssistentJarvis/audit.log"

# Classificação das ferramentas por nível de risco
TOOL_LEVELS: dict[str, int] = {
    # Nível 1: Somente leitura (automático)
    "system_health": 1,
    "list_projects": 1,
    "read_project_file": 1,
    "list_upcoming_events": 1,
    "list_unread_emails": 1,
    "search_emails": 1,
    "read_email": 1,
    "web_search": 1,
    "search_place": 1,
    # Nível 2: Escrita segura em sandbox / rascunhos / novos eventos
    "create_project": 2,
    "write_project_file": 2,
    "run_in_sandbox": 2,
    "create_calendar_event": 2,
    "update_calendar_event": 2,
    "create_email_draft": 2,
    # Nível 3: Crítico / Irreversível / Fora da sandbox (sempre exige aprovação)
    "run_host_command": 3,
    "delete_calendar_event": 3,
}


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
    """Abre pop-up nativo (KDE kdialog ou GTK zenity) para aprovação humana."""
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
    Se untrusted_context=True (ex: após ler um e-mail externo), eleva Nível 2 para exigir
    confirmação humana como defesa contra Prompt Injection indireto.
    """
    level = TOOL_LEVELS.get(tool_name, 3)

    if level == 1:
        log_audit(tool_name, args, level, True, "auto_level_1")
        return True, "Autorizado (Nível 1)."

    needs_prompt = (level >= 3) or (level == 2 and untrusted_context)
    if not needs_prompt:
        log_audit(tool_name, args, level, True, "auto_level_2")
        return True, "Autorizado (Nível 2)."

    reason_tag = " [CONTEXTO EXTERNO DETECTADO]" if untrusted_context else ""
    msg = (
        f"O assistente solicitou permissão para executar uma ação Nível {level}{reason_tag}:\n\n"
        f"Ferramenta: {tool_name}\n"
        f"Argumentos:\n{json.dumps(args, indent=2, ensure_ascii=False)}\n\n"
        f"Deseja permitir esta execução?"
    )
    approved = _ask_desktop_confirmation("CachyOS Assistant - Aprovação de Segurança", msg)
    log_audit(tool_name, args, level, approved, "hitl_prompt")
    if approved:
        return True, "Autorizado pelo usuário."
    return False, "Ação recusada pelo usuário na janela de segurança."
