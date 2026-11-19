import subprocess
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cachyos-dev")
WORKSPACE = (Path.home() / "Projetos").resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe_path(project_name: str, rel_path: str = "") -> Path:
    target = (WORKSPACE / project_name / rel_path).resolve()
    if not str(target).startswith(str(WORKSPACE)):
        raise ValueError("Acesso negado: caminho fora de ~/Projetos.")
    return target


def _git_snapshot(project_dir: Path, message: str) -> None:
    if not (project_dir / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=project_dir, check=False)
    subprocess.run(["git", "add", "-A"], cwd=project_dir, check=False)
    subprocess.run(
        ["git", "commit", "-q", "-m", message, "--allow-empty"],
        cwd=project_dir,
        capture_output=True,
        check=False,
    )


@mcp.tool()
def list_projects() -> str:
    """[Nível 1] Lista todos os projetos existentes em ~/Projetos."""
    items = sorted([p.name for p in WORKSPACE.iterdir() if p.is_dir()])
    return "\n".join(items) if items else "Nenhum projeto encontrado em ~/Projetos."


@mcp.tool()
def create_project(project_name: str, stack: str = "python") -> str:
    """[Nível 2] Cria um novo projeto em ~/Projetos com Git inicializado (stacks: python, dotnet, node, generic)."""
    proj = _safe_path(project_name)
    proj.mkdir(parents=True, exist_ok=True)

    if stack == "python":
        subprocess.run(["uv", "init", "--no-readme"], cwd=proj, capture_output=True)
    elif stack == "dotnet":
        subprocess.run(["dotnet", "new", "console"], cwd=proj, capture_output=True)
    elif stack == "node":
        subprocess.run(["npm", "init", "-y"], cwd=proj, capture_output=True)

    (proj / "README.md").write_text(f"# {project_name}\n\nCriado via CachyOS Assistant.\n", encoding="utf-8")
    _git_snapshot(proj, "chore: initial project scaffolding")
    return f"Projeto '{project_name}' criado em {proj} (stack: {stack}) com repositório Git inicial."


@mcp.tool()
def read_project_file(project_name: str, rel_path: str) -> str:
    """[Nível 1] Lê o conteúdo de um arquivo dentro de ~/Projetos/<project_name>."""
    target = _safe_path(project_name, rel_path)
    if not target.is_file():
        return f"Arquivo não encontrado: {rel_path}"
    return target.read_text(encoding="utf-8")[:24000]


@mcp.tool()
def write_project_file(project_name: str, rel_path: str, content: str) -> str:
    """[Nível 2] Cria ou edita um arquivo em ~/Projetos/<project_name>, salvando snapshot Git antes."""
    proj = _safe_path(project_name)
    target = _safe_path(project_name, rel_path)
    proj.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        _git_snapshot(proj, f"backup: before editing {rel_path}")

    target.write_text(content, encoding="utf-8")
    _git_snapshot(proj, f"feat: update {rel_path} via assistant")
    return f"Arquivo salvo com sucesso e versionado no Git: {target}"


if __name__ == "__main__":
    mcp.run()
