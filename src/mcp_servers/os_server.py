import subprocess
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cachyos-system")
ALLOWED_WORKSPACE = (Path.home() / "Projetos").resolve()


@mcp.tool()
def system_health() -> str:
    """[Nível 1] Retorna uso da GPU RTX 5080, memória RAM DDR5, disco e carga da CPU."""
    try:
        gpu = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip()
    except Exception as e:
        gpu = f"Indisponível ({e})"

    mem = subprocess.check_output(["free", "-h"], text=True)
    disk = subprocess.check_output(["df", "-h", str(Path.home())], text=True)
    return f"GPU: {gpu}\n\nRAM:\n{mem}\nDisco:\n{disk}"


@mcp.tool()
def run_in_sandbox(project_name: str, command: str) -> str:
    """[Nível 2] Executa comandos de build, scripts ou testes isolados via bubblewrap sem rede."""
    target = (ALLOWED_WORKSPACE / project_name).resolve()
    if not str(target).startswith(str(ALLOWED_WORKSPACE)):
        return "ERRO DE SEGURANÇA: Acesso negado fora de ~/Projetos."
    target.mkdir(parents=True, exist_ok=True)

    bwrap_cmd = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--tmpfs", "/tmp",
        "--proc", "/proc",
        "--dev", "/dev",
        "--bind", str(target), "/workspace",
        "--unshare-net",
        "--die-with-parent",
        "--chdir", "/workspace",
        "/usr/bin/bash", "-c", command,
    ]
    try:
        res = subprocess.run(bwrap_cmd, capture_output=True, text=True, timeout=90)
        return f"Exit Code: {res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    except subprocess.TimeoutExpired:
        return "ERRO: Execução excedeu o limite de 90 segundos na sandbox."


@mcp.tool()
def run_host_command(command: str) -> str:
    """[Nível 3] Executa comando administrativo/sistema diretamente no host (requer aprovação)."""
    try:
        res = subprocess.run(
            ["/usr/bin/bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return f"Exit Code: {res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    except subprocess.TimeoutExpired:
        return "ERRO: Comando excedeu o limite de 120 segundos."


if __name__ == "__main__":
    mcp.run()
