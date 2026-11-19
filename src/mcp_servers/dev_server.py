import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cachyos-dev")
WORKSPACE = (Path.home() / "Projetos").resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _normalize_project_name(project_name: str) -> str:
    p = project_name.strip().rstrip("/")
    ws = str(WORKSPACE)
    if p.startswith(ws):
        p = p[len(ws):].lstrip("/")
    elif p.startswith("~/Projetos"):
        p = p[len("~/Projetos"):].lstrip("/")
    return p.lstrip("/")


def _to_pascal(name: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", name)
    pascal = "".join(p.capitalize() for p in parts if p)
    if not pascal or pascal[0].isdigit():
        pascal = "App" + pascal
    return pascal


def _safe_path(project_name: str, rel_path: str = "") -> Path:
    proj_clean = _normalize_project_name(project_name)
    if not proj_clean:
        raise ValueError("Nome do projeto inválido.")

    proj_dir = (WORKSPACE / proj_clean).resolve()
    if not str(proj_dir).startswith(str(WORKSPACE)):
        raise ValueError("Acesso negado: projeto fora de ~/Projetos.")

    if not rel_path:
        return proj_dir

    rel_clean = rel_path.strip()
    if rel_clean.startswith(str(proj_dir)):
        rel_clean = rel_clean[len(str(proj_dir)):].lstrip("/")
    elif rel_clean.startswith(str(WORKSPACE)):
        rel_clean = rel_clean[len(str(WORKSPACE)):].lstrip("/")
        if rel_clean.startswith(proj_clean + "/"):
            rel_clean = rel_clean[len(proj_clean) + 1:]
    else:
        rel_clean = rel_clean.lstrip("/")
        if rel_clean.startswith(proj_clean + "/"):
            rel_clean = rel_clean[len(proj_clean) + 1:]

    target = (proj_dir / rel_clean).resolve()
    if not str(target).startswith(str(proj_dir)):
        raise ValueError("Acesso negado: caminho fora do diretório do projeto.")
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


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _ensure_project_gitignore(proj: Path) -> None:
    _write_if_missing(
        proj / ".gitignore",
        """# Dependências e builds
node_modules/
dist/
bin/
obj/
target/
.venv/
__pycache__/
*.py[cod]

# Segredos e variáveis locais
.env
.env.*
!.env.example
*.pfx
*.pem
*.key

# IDEs e SO
.vscode/
.idea/
.DS_Store
""",
    )


def _scaffold_dotnet_ddd(proj: Path) -> str:
    ns = _to_pascal(proj.name)
    src = proj / "src"

    dom_dir = src / f"{ns}.Domain"
    app_dir = src / f"{ns}.Application"
    inf_dir = src / f"{ns}.Infrastructure"
    api_dir = src / f"{ns}.Api"

    # 1. Solution .slnx (XML oficial do .NET 9/10 SDK)
    slnx_content = f"""<Solution>
  <Project Path="src/{ns}.Domain/{ns}.Domain.csproj" />
  <Project Path="src/{ns}.Application/{ns}.Application.csproj" />
  <Project Path="src/{ns}.Infrastructure/{ns}.Infrastructure.csproj" />
  <Project Path="src/{ns}.Api/{ns}.Api.csproj" />
</Solution>
"""
    _write_if_missing(proj / f"{ns}.slnx", slnx_content)

    # 2. Domain (.NET 10)
    _write_if_missing(
        dom_dir / f"{ns}.Domain.csproj",
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <AllowMissingPrunePackageData>true</AllowMissingPrunePackageData>
  </PropertyGroup>
</Project>
""",
    )
    _write_if_missing(
        dom_dir / "Exceptions/DomainException.cs",
        f"""namespace {ns}.Domain.Exceptions;

public class DomainException : Exception
{{
    public DomainException(string message) : base(message) {{ }}
}}
""",
    )
    (dom_dir / "Entities").mkdir(parents=True, exist_ok=True)
    (dom_dir / "ValueObjects").mkdir(parents=True, exist_ok=True)
    (dom_dir / "Interfaces").mkdir(parents=True, exist_ok=True)

    # 3. Application (.NET 10)
    _write_if_missing(
        app_dir / f"{ns}.Application.csproj",
        f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <AllowMissingPrunePackageData>true</AllowMissingPrunePackageData>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\{ns}.Domain\\{ns}.Domain.csproj" />
  </ItemGroup>
</Project>
""",
    )
    (app_dir / "DTOs").mkdir(parents=True, exist_ok=True)
    (app_dir / "UseCases").mkdir(parents=True, exist_ok=True)
    (app_dir / "Interfaces").mkdir(parents=True, exist_ok=True)

    # 4. Infrastructure (.NET 10)
    _write_if_missing(
        inf_dir / f"{ns}.Infrastructure.csproj",
        f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <AllowMissingPrunePackageData>true</AllowMissingPrunePackageData>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\{ns}.Domain\\{ns}.Domain.csproj" />
    <ProjectReference Include="..\\{ns}.Application\\{ns}.Application.csproj" />
  </ItemGroup>
</Project>
""",
    )
    (inf_dir / "Repositories").mkdir(parents=True, exist_ok=True)

    # 5. API (.NET 10 Web SDK + Security Headers + Global Exception Filter + CORS restrito)
    _write_if_missing(
        api_dir / f"{ns}.Api.csproj",
        f"""<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <AllowMissingPrunePackageData>true</AllowMissingPrunePackageData>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\{ns}.Application\\{ns}.Application.csproj" />
    <ProjectReference Include="..\\{ns}.Infrastructure\\{ns}.Infrastructure.csproj" />
  </ItemGroup>
</Project>
""",
    )
    _write_if_missing(
        api_dir / "Properties/launchSettings.json",
        """{
  "profiles": {
    "http": {
      "commandName": "Project",
      "dotnetRunMessages": true,
      "launchBrowser": false,
      "applicationUrl": "http://localhost:5000",
      "environmentVariables": {
        "ASPNETCORE_ENVIRONMENT": "Development"
      }
    }
  }
}
""",
    )
    _write_if_missing(
        api_dir / "Program.cs",
        f"""using {ns}.Domain.Exceptions;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddCors(options =>
{{
    options.AddDefaultPolicy(policy =>
    {{
        policy.WithOrigins("http://localhost:3000", "http://127.0.0.1:3000")
              .AllowAnyHeader()
              .AllowAnyMethod();
    }});
}});

// Registre aqui os UseCases, Services e Repositories (DI)

var app = builder.Build();

// Headers HTTP de segurança (AppSec)
app.Use(async (context, next) =>
{{
    context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    context.Response.Headers["X-Frame-Options"] = "DENY";
    context.Response.Headers["Referrer-Policy"] = "strict-origin-when-cross-origin";
    context.Response.Headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()";
    await next();
}});

// Tratamento seguro de exceções (não vaza stack trace ao cliente)
app.Use(async (context, next) =>
{{
    try
    {{
        await next();
    }}
    catch (DomainException ex)
    {{
        context.Response.StatusCode = StatusCodes.Status400BadRequest;
        await context.Response.WriteAsJsonAsync(new {{ error = ex.Message }});
    }}
    catch (Exception)
    {{
        context.Response.StatusCode = StatusCodes.Status500InternalServerError;
        await context.Response.WriteAsJsonAsync(new {{ error = "Erro interno inesperado ao processar a solicitação." }});
    }}
}});

app.UseCors();
app.MapControllers();

app.Run();
""",
    )
    (api_dir / "Controllers").mkdir(parents=True, exist_ok=True)
    return ns


def _scaffold_react_vite(fe_dir: Path, title: str) -> None:
    fe_dir.mkdir(parents=True, exist_ok=True)
    (fe_dir / "src/components").mkdir(parents=True, exist_ok=True)
    (fe_dir / "src/hooks").mkdir(parents=True, exist_ok=True)

    pkg = {
        "name": re.sub(r"[^a-z0-9-]", "-", title.lower()).strip("-") or "frontend",
        "private": True,
        "version": "1.0.0",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "start": "vite",
            "build": "vite build",
            "preview": "vite preview --port 4173",
        },
        "dependencies": {
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
        },
        "devDependencies": {
            "@vitejs/plugin-react": "^4.3.4",
            "vite": "^6.1.0",
        },
    }
    _write_if_missing(fe_dir / "package.json", json.dumps(pkg, indent=2) + "\n")

    _write_if_missing(
        fe_dir / "vite.config.js",
        """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
  },
});
""",
    )

    _write_if_missing(
        fe_dir / "index.html",
        f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="X-Content-Type-Options" content="nosniff" />
    <meta name="referrer" content="strict-origin-when-cross-origin" />
    <title>{title}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
""",
    )

    _write_if_missing(
        fe_dir / "src/main.jsx",
        """import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles/design-system.css';
import App from './App.jsx';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
""",
    )

    _write_if_missing(
        fe_dir / "src/services/api.js",
        """const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

export async function apiRequest(path, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      signal: controller.signal,
      ...options,
    });

    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { message: text };
    }

    if (!response.ok) {
      throw new Error(data?.error || data?.message || `Erro HTTP ${response.status}`);
    }
    return data;
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Tempo limite excedido ao comunicar com a API.');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
""",
    )

    _write_if_missing(
        fe_dir / "src/styles/design-system.css",
        """:root {
  --bg-canvas: #090d16;
  --bg-surface: rgba(17, 24, 39, 0.86);
  --bg-elevated: rgba(30, 41, 59, 0.85);
  --border-subtle: rgba(148, 163, 184, 0.18);
  --border-accent: rgba(56, 189, 248, 0.5);
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --accent: #38bdf8;
  --accent-strong: #0284c7;
  --accent-glow: rgba(56, 189, 248, 0.25);
  --operator: #f59e0b;
  --operator-hover: #fbbf24;
  --utility: #334155;
  --success: #34d399;
  --danger: #fb7185;
  --radius-sm: 12px;
  --radius-md: 16px;
  --radius-lg: 24px;
  --shadow-lg: 0 24px 60px rgba(0, 0, 0, 0.58);
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
}

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  min-height: 100vh;
  font-family: var(--font-sans);
  color: var(--text-primary);
  background:
    radial-gradient(circle at 18% 20%, rgba(56, 189, 248, 0.14), transparent 42%),
    radial-gradient(circle at 82% 80%, rgba(99, 102, 241, 0.14), transparent 45%),
    var(--bg-canvas);
  -webkit-font-smoothing: antialiased;
}

.app-shell {
  min-height: 100vh;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem 1.25rem;
}

.glass-card {
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(16px);
  padding: 1.75rem;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--accent);
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.25);
}

/* Primitivas de Grid Blindadas contra overflow */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

.calc-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.65rem;
  width: 100%;
}

.calc-display {
  width: 100%;
  min-width: 0;
  background: rgba(9, 13, 22, 0.85);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
  text-align: right;
  overflow: hidden;
}

.calc-expression {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text-secondary);
  min-height: 1.25rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.calc-value {
  font-family: var(--font-mono);
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.btn {
  appearance: none;
  min-width: 0;
  min-height: 46px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 1rem;
  font-weight: 600;
  border-radius: var(--radius-sm);
  padding: 0.75rem 1rem;
  cursor: pointer;
  user-select: none;
  transition: transform 0.1s ease, background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.btn:hover:not(:disabled) {
  border-color: var(--border-accent);
  background: rgba(51, 65, 85, 0.95);
  transform: translateY(-1px);
}

.btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
}

.btn:focus-visible,
.input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  border-color: transparent;
  color: #03111d;
  box-shadow: 0 8px 24px var(--accent-glow);
}

.btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #7dd3fc, var(--accent));
}

.btn-op {
  background: var(--operator);
  border-color: transparent;
  color: #090d16;
  font-weight: 700;
}

.btn-op:hover:not(:disabled) {
  background: var(--operator-hover);
}

.btn-util {
  background: var(--utility);
  color: var(--text-primary);
}

.span-2 {
  grid-column: span 2;
}

.input {
  width: 100%;
  min-width: 0;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  padding: 0.75rem 1rem;
  font-size: 0.95rem;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.alert-error {
  padding: 0.75rem 1rem;
  border-radius: var(--radius-sm);
  background: rgba(251, 113, 133, 0.12);
  border: 1px solid rgba(251, 113, 133, 0.35);
  color: #fecdd3;
  font-size: 0.875rem;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

@media (max-width: 720px) {
  .grid-2, .grid-3 {
    grid-template-columns: 1fr;
  }
  .glass-card {
    padding: 1.25rem;
  }
}
""",
    )

    _write_if_missing(
        fe_dir / "src/App.jsx",
        f"""import React from 'react';
import './App.css';

export default function App() {{
  return (
    <main className="app-shell">
      <section className="glass-card" style={{{{ maxWidth: '460px' }}}} aria-label="{title}">
        <span className="badge">{title}</span>
        <h1 style={{{{ marginTop: '0.75rem' }}}}>{title}</h1>
        <p style={{{{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}}}>
          Substitua este componente pela interface completa da aplicação.
        </p>
      </section>
    </main>
  );
}}
""",
    )
    _write_if_missing(fe_dir / "src/App.css", "/* Estilos específicos da aplicação */\n")


def _run_bwrap(
    proj_dir: Path,
    command: str,
    timeout: int = 120,
    allow_net: bool = False,
) -> subprocess.CompletedProcess:
    home = Path.home()
    cmd = ["bwrap"]
    for ro in (
        "/usr", "/lib", "/lib64", "/bin",
        "/etc/ssl", "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ld.so.conf.d",
        "/etc/dotnet", "/opt/dotnet", "/etc/localtime",
    ):
        if os.path.exists(ro):
            cmd.extend(["--ro-bind", ro, ro])

    if allow_net:
        for net_file in ("/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf"):
            if os.path.exists(net_file):
                cmd.extend(["--ro-bind", net_file, net_file])

    extra_paths = []
    for p in (home / ".rustup", home / ".cargo/bin", home / ".local/bin", home / ".dotnet"):
        if p.exists():
            cmd.extend(["--ro-bind", str(p), str(p)])
            if p.name in ("bin", ".dotnet"):
                extra_paths.append(str(p))

    nuget_cache = home / ".nuget/packages"
    if nuget_cache.exists():
        cmd.extend(["--ro-bind", str(nuget_cache), "/opt/nuget-cache"])

    npm_cache = home / ".npm"
    if npm_cache.exists():
        cmd.extend(["--bind", str(npm_cache), "/tmp/npm-cache"])

    full_path = ":".join(extra_paths + ["/usr/local/bin", "/usr/bin", "/bin"])

    cmd.extend([
        "--tmpfs", "/tmp",
        "--tmpfs", "/dev/shm",
        "--proc", "/proc",
        "--dev", "/dev",
        "--bind", str(proj_dir), "/workspace",
    ])
    if not allow_net:
        cmd.append("--unshare-net")

    cmd.extend([
        "--die-with-parent",
        "--chdir", "/workspace",
        "--setenv", "PATH", full_path,
        "--setenv", "HOME", "/tmp",
        "--setenv", "XDG_RUNTIME_DIR", "/tmp",
        "--setenv", "XDG_CONFIG_HOME", "/tmp/.config",
        "--setenv", "XDG_CACHE_HOME", "/tmp/.cache",
        "--setenv", "CARGO_HOME", "/tmp/cargo_home",
        "--setenv", "DOTNET_CLI_HOME", "/tmp/dotnet_home",
        "--setenv", "NUGET_PACKAGES", "/tmp/nuget_packages",
        "--setenv", "NUGET_HTTP_CACHE_PATH", "/tmp/nuget_http",
        "--setenv", "NUGET_PLUGINS_CACHE_PATH", "/tmp/nuget_plugins",
        "--setenv", "NPM_CONFIG_CACHE", "/tmp/npm-cache",
        "--setenv", "DOTNET_NOLOGO", "1",
        "--setenv", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE", "1",
        "--setenv", "DOTNET_CLI_TELEMETRY_OPTOUT", "1",
        "--setenv", "DOTNET_EnableWriteXorExecute", "0",
        "--setenv", "MSBUILDDISABLENODEREUSE", "1",
    ])
    if (home / ".rustup").exists():
        cmd.extend(["--setenv", "RUSTUP_HOME", str(home / ".rustup")])
    if nuget_cache.exists():
        cmd.extend(["--setenv", "NUGET_FALLBACK_PACKAGES", "/opt/nuget-cache"])

    cmd.extend(["/usr/bin/bash", "-c", command])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _audit_security_and_ux(proj: Path, fe_dir: Path | None) -> list[str]:
    """Audita boas práticas de segurança e UX/acessibilidade no código gerado."""
    issues: list[str] = []
    ignored = {".git", "bin", "obj", "target", "node_modules", ".venv", "__pycache__", "dist"}

    if not (proj / ".gitignore").exists():
        _ensure_project_gitignore(proj)

    secret_re = re.compile(
        r"""(?i)\b(password|passwd|secret|api_key|apikey|token|connectionstring)\b\s*[:=]\s*["'][^"']{8,}["']"""
    )

    for f in proj.rglob("*"):
        if not f.is_file() or any(part in ignored for part in f.relative_to(proj).parts):
            continue
        if f.suffix.lower() not in {".cs", ".py", ".js", ".jsx", ".ts", ".tsx", ".rs"}:
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        rel = f.relative_to(proj)

        if "dangerouslySetInnerHTML" in txt:
            issues.append(f"[Segurança] Uso de dangerouslySetInnerHTML detectado em {rel}. Use renderização React segura.")
        if re.search(r"\beval\s*\(", txt) and f.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".py"}:
            issues.append(f"[Segurança] Uso de eval() detectado em {rel}. Substitua por parser seguro.")
        if "AllowAnyOrigin()" in txt:
            issues.append(f"[Segurança] Política CORS insegura AllowAnyOrigin() em {rel}. Restrinja com WithOrigins(...).")
        if secret_re.search(txt) and "example" not in f.name.lower():
            issues.append(f"[Segurança] Possível segredo/credencial fixo no código em {rel}. Use variáveis de ambiente.")

    if fe_dir is not None and (fe_dir / "src").is_dir():
        jsx_files = list((fe_dir / "src").rglob("*.jsx")) + list((fe_dir / "src").rglob("*.tsx"))
        combined_jsx = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in jsx_files)
        if combined_jsx and not re.search(r"\b(aria-label|aria-live|role=|htmlFor=)", combined_jsx):
            issues.append(
                "[UX/Acessibilidade] Nenhum atributo ARIA/semântico encontrado no React (adicione aria-label nos botões/inputs e aria-live='polite' nos resultados)."
            )

    return issues


@mcp.tool()
def list_projects() -> str:
    """[Nível 1] Lista todos os projetos existentes em ~/Projetos."""
    items = sorted([p.name for p in WORKSPACE.iterdir() if p.is_dir()])
    return "\n".join(items) if items else "Nenhum projeto encontrado em ~/Projetos."


@mcp.tool()
def list_project_files(project_name: str) -> str:
    """[Nível 1] Lista a árvore de arquivos de um projeto em ~/Projetos/<project_name> (ignorando bin/obj/target/node_modules/.git)."""
    proj = _safe_path(project_name)
    if not proj.is_dir():
        return f"Projeto não encontrado: {proj}"
    ignored = {".git", "bin", "obj", "target", "node_modules", ".venv", "__pycache__"}
    files = []
    for p in sorted(proj.rglob("*")):
        if any(part in ignored for part in p.relative_to(proj).parts):
            continue
        if p.is_file():
            files.append(str(p.relative_to(proj)))
    return "\n".join(files) if files else "Projeto vazio."


@mcp.tool()
def create_project(project_name: str, stack: str = "python") -> str:
    """[Nível 2] Cria a estrutura DDD completa de um projeto em ~/Projetos.
    Stacks suportadas:
    - 'dotnet-react' ou 'fullstack': Backend .NET 10 DDD 4 camadas com .slnx + Frontend React/Vite com Design System em frontend/
    - 'dotnet' ou 'dotnet-ddd': Backend .NET 10 DDD 4 camadas com .slnx (Domain, Application, Infrastructure, Api)
    - 'react': Frontend React + Vite + Design System
    - 'rust': Projeto Rust modularizado em camadas DDD (domain, application, presentation)
    - 'python': Projeto Python modularizado em camadas DDD (domain, application, infrastructure, presentation)
    - 'node' ou 'generic'
    """
    proj = _safe_path(project_name)
    proj.mkdir(parents=True, exist_ok=True)
    _ensure_project_gitignore(proj)
    stack_low = stack.strip().lower()
    crate_name = re.sub(r"[^a-z0-9_]", "_", proj.name.lower()).strip("_") or "app"
    next_steps = ""

    if stack_low in ("dotnet-react", "fullstack", "dotnet-fullstack", "dotnet+react"):
        ns = _scaffold_dotnet_ddd(proj)
        _scaffold_react_vite(proj / "frontend", ns)
        next_steps = (
            f"Backend DDD .NET 10 criado com '{ns}.slnx' (src/{ns}.Domain, src/{ns}.Application, "
            f"src/{ns}.Infrastructure, src/{ns}.Api) e Frontend React+Vite criado em 'frontend/' com Design System.\n"
            f"PRÓXIMOS PASSOS OBRIGATÓRIOS com write_project_file:\n"
            f"1) Implemente Entidades/ValueObjects/Regras em src/{ns}.Domain/\n"
            f"2) Implemente UseCases e DTOs em src/{ns}.Application/\n"
            f"3) Implemente Repositório/Serviço em src/{ns}.Infrastructure/ (se aplicável)\n"
            f"4) Registre DI em src/{ns}.Api/Program.cs e crie Controller com [Route(\"api/[controller]\")] em src/{ns}.Api/Controllers/\n"
            f"5) Implemente UI/UX moderna, acessível e responsiva em frontend/src/App.jsx e frontend/src/App.css usando as classes do design-system.css."
        )
    elif stack_low in ("dotnet", "dotnet-ddd", "dotnet-webapi", "csharp", "c#"):
        ns = _scaffold_dotnet_ddd(proj)
        next_steps = (
            f"Solução DDD .NET 10 criada com '{ns}.slnx' (src/{ns}.Domain, src/{ns}.Application, "
            f"src/{ns}.Infrastructure, src/{ns}.Api).\n"
            f"Implemente agora as camadas Domain, Application, Infrastructure e Controllers usando write_project_file."
        )
    elif stack_low in ("react", "reactjs", "vite"):
        _scaffold_react_vite(proj, _to_pascal(proj.name))
        next_steps = (
            "Frontend React + Vite + Design System criado. Implemente agora a UI/UX completa em src/App.jsx e src/App.css."
        )
    elif stack_low in ("rust", "rust-ddd"):
        if shutil.which("cargo") and not (proj / "Cargo.toml").exists():
            subprocess.run(["cargo", "init", "--name", crate_name], cwd=proj, capture_output=True)
        elif not (proj / "Cargo.toml").exists():
            (proj / "src").mkdir(exist_ok=True)
            _write_if_missing(
                proj / "Cargo.toml",
                f'[package]\nname = "{crate_name}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n',
            )
        for mod in ("domain", "application", "presentation"):
            (proj / "src" / mod).mkdir(parents=True, exist_ok=True)
            _write_if_missing(proj / "src" / mod / "mod.rs", f"// Camada DDD: {mod}\n")
        next_steps = (
            "Estrutura DDD Rust criada (src/domain, src/application, src/presentation, src/main.rs). "
            "Implemente agora o domínio, os casos de uso e a interface CLI rica usando write_project_file."
        )
    elif stack_low in ("python", "python-ddd"):
        subprocess.run(["uv", "init", "--no-readme"], cwd=proj, capture_output=True)
        for mod in ("domain", "application", "infrastructure", "presentation"):
            (proj / "src" / mod).mkdir(parents=True, exist_ok=True)
            _write_if_missing(proj / "src" / mod / "__init__.py", "")
        next_steps = (
            "Estrutura DDD Python criada em src/{domain,application,infrastructure,presentation}. "
            "Implemente agora o código completo usando write_project_file."
        )
    elif stack_low == "node":
        subprocess.run(["npm", "init", "-y"], cwd=proj, capture_output=True)
        next_steps = "Projeto Node criado. Implemente o código agora usando write_project_file."
    else:
        next_steps = "Pasta do projeto criada. Implemente os arquivos agora usando write_project_file."

    _write_if_missing(proj / "README.md", f"# {proj.name}\n\nProjeto DDD gerado pelo J.A.R.V.I.S. (CachyOS).\n")
    _git_snapshot(proj, "chore: initial DDD project scaffolding")
    return f"Estrutura criada em {proj} (stack: {stack_low}).\n{next_steps}"


@mcp.tool()
def read_project_file(project_name: str, rel_path: str) -> str:
    """[Nível 1] Lê o conteúdo de um arquivo dentro de ~/Projetos/<project_name>."""
    target = _safe_path(project_name, rel_path)
    if not target.is_file():
        return f"Arquivo não encontrado: {rel_path}"
    return target.read_text(encoding="utf-8")[:24000]


@mcp.tool()
def write_project_file(project_name: str, rel_path: str, content: str) -> str:
    """[Nível 2] Cria ou sobrescreve um arquivo em ~/Projetos/<project_name>/<rel_path>, salvando backup automático no Git."""
    proj = _safe_path(project_name)
    target = _safe_path(project_name, rel_path)
    proj.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        _git_snapshot(proj, f"backup: before editing {rel_path}")

    target.write_text(content, encoding="utf-8")
    _git_snapshot(proj, f"feat: update {rel_path} via assistant")
    return f"Arquivo gravado com sucesso ({len(content)} caracteres) e versionado no Git: {target}"


@mcp.tool()
def check_project(project_name: str) -> str:
    """[Nível 2] Compila/valida Backend (.NET .slnx/csproj, Rust, Python), audita Segurança/UX e executa 'npm run build' no Frontend React+Vite garantindo a geração da pasta dist/."""
    proj = _safe_path(project_name)
    if not proj.is_dir():
        return f"Projeto não encontrado: {proj}"

    reports: list[str] = []
    has_errors = False

    # 1. Backend .NET (.slnx / .sln / .csproj recursivo)
    slnx_files = sorted(proj.glob("*.slnx"))
    sln_files = sorted(proj.glob("*.sln"))
    csprojs = [
        p for p in sorted(proj.rglob("*.csproj"))
        if not any(part in {"bin", "obj", "node_modules"} for part in p.parts)
    ]
    if slnx_files or sln_files or csprojs:
        target_rel = (
            slnx_files[0].relative_to(proj)
            if slnx_files
            else (sln_files[0].relative_to(proj) if sln_files else csprojs[0].relative_to(proj))
        )
        if slnx_files:
            slnx_txt = slnx_files[0].read_text(encoding="utf-8", errors="ignore")
            if "<Solution" not in slnx_txt:
                has_errors = True
                reports.append(
                    f"ERRO DE COMPILAÇÃO/SINTAXE (.slnx): {slnx_files[0].name} não contém a tag raiz <Solution>."
                )
        try:
            res = _run_bwrap(proj, f"dotnet build '{target_rel}' --nologo", timeout=120)
            if res.returncode == 0:
                reports.append(f"COMPILAÇÃO/VERIFICAÇÃO OK (dotnet build {target_rel}, exit 0).")
            else:
                has_errors = True
                reports.append(
                    f"ERRO DE COMPILAÇÃO/SINTAXE (dotnet build {target_rel}, exit {res.returncode}):\n"
                    f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
                )
        except subprocess.TimeoutExpired:
            has_errors = True
            reports.append("ERRO DE COMPILAÇÃO/SINTAXE (dotnet build): Tempo limite excedido (120s).")

    # 2. Rust
    if (proj / "Cargo.toml").exists():
        try:
            res = _run_bwrap(proj, "cargo check --color never", timeout=90)
            if res.returncode == 0:
                reports.append("COMPILAÇÃO/VERIFICAÇÃO OK (cargo check, exit 0).")
            else:
                has_errors = True
                reports.append(
                    f"ERRO DE COMPILAÇÃO/SINTAXE (cargo check, exit {res.returncode}):\n"
                    f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
                )
        except subprocess.TimeoutExpired:
            has_errors = True
            reports.append("ERRO DE COMPILAÇÃO/SINTAXE (cargo check): Tempo limite excedido (90s).")

    # 3. Python
    py_files = [
        p for p in proj.rglob("*.py")
        if not any(part in {".venv", "__pycache__", "node_modules"} for part in p.parts)
    ]
    if py_files:
        res = _run_bwrap(
            proj,
            "find . -maxdepth 4 -name '*.py' ! -path './.venv/*' -exec python3 -m py_compile {} +",
            timeout=60,
        )
        if res.returncode == 0:
            reports.append("COMPILAÇÃO/VERIFICAÇÃO OK (python3 py_compile, exit 0).")
        else:
            has_errors = True
            reports.append(f"ERRO DE COMPILAÇÃO/SINTAXE (Python):\n{res.stderr}")

    # 4. Frontend React + Vite (garante npm install + npm run build -> dist/)
    fe_dir = (
        proj / "frontend"
        if (proj / "frontend/package.json").exists()
        else (proj if (proj / "package.json").exists() and (proj / "vite.config.js").exists() else None)
    )
    if fe_dir is not None:
        fe_issues = []
        for req in ("package.json", "index.html", "vite.config.js", "src/main.jsx", "src/App.jsx"):
            if not (fe_dir / req).exists():
                fe_issues.append(f"Arquivo obrigatório ausente no frontend: {req}")

        src_fe = fe_dir / "src"
        if src_fe.is_dir():
            for js_file in src_fe.rglob("*.js"):
                txt = js_file.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"return\s*\(\s*<[A-Za-z]", txt):
                    fe_issues.append(
                        f"Arquivo {js_file.relative_to(proj)} contém JSX com extensão .js — salve como .jsx para o Vite."
                    )
            for css_file in src_fe.rglob("*.css"):
                css_txt = css_file.read_text(encoding="utf-8", errors="ignore")
                if css_txt.count("{") != css_txt.count("}"):
                    fe_issues.append(
                        f"CSS inválido em {css_file.relative_to(proj)}: chaves '{{' e '}}' desbalanceadas "
                        f"({css_txt.count('{')} aberturas vs {css_txt.count('}')} fechamentos)."
                    )

        if not fe_issues:
            fe_rel = fe_dir.relative_to(proj)
            cd_prefix = "" if str(fe_rel) == "." else f"cd '{fe_rel}' && "

            # Instala dependências se node_modules ainda não existir
            if not (fe_dir / "node_modules").is_dir():
                try:
                    inst = _run_bwrap(
                        proj,
                        f"{cd_prefix}npm install --prefer-offline --no-audit --no-fund",
                        timeout=180,
                        allow_net=True,
                    )
                    if inst.returncode != 0:
                        fe_issues.append(
                            f"Falha ao instalar dependências (npm install):\n{inst.stdout}\n{inst.stderr}"
                        )
                except subprocess.TimeoutExpired:
                    fe_issues.append("Tempo limite excedido ao executar npm install (180s).")

            # Executa npm run build sempre para gerar e validar dist/
            if not fe_issues:
                try:
                    bld = _run_bwrap(proj, f"{cd_prefix}npm run build", timeout=90, allow_net=False)
                    dist_index = fe_dir / "dist/index.html"
                    if bld.returncode != 0 or not dist_index.is_file():
                        fe_issues.append(
                            f"Falha ao gerar build de produção (npm run build -> dist/):\n{bld.stdout}\n{bld.stderr}"
                        )
                    else:
                        _git_snapshot(proj, "build: verify production dist bundle")
                except subprocess.TimeoutExpired:
                    fe_issues.append("Tempo limite excedido ao executar npm run build (90s).")

        if fe_issues:
            has_errors = True
            reports.append("ERRO DE COMPILAÇÃO/SINTAXE (Frontend React+Vite):\n- " + "\n- ".join(fe_issues))
        else:
            dist_rel = (fe_dir / "dist").relative_to(proj)
            reports.append(
                f"COMPILAÇÃO/VERIFICAÇÃO OK (Frontend React+Vite: npm run build concluído e '{dist_rel}/' gerado)."
            )

    # 5. Auditoria de Segurança e Acessibilidade/UX
    sec_ux_issues = _audit_security_and_ux(proj, fe_dir)
    if sec_ux_issues:
        has_errors = True
        reports.append("ERRO DE COMPILAÇÃO/SINTAXE (Auditoria de Segurança & UX):\n- " + "\n- ".join(sec_ux_issues))
    else:
        reports.append("AUDITORIA SEGURANÇA & UX OK (sem vulnerabilidades ou falhas de acessibilidade).")

    if not reports:
        return "COMPILAÇÃO/VERIFICAÇÃO OK (nenhum compilador específico detectado)."

    prefix = "ERRO DE COMPILAÇÃO/SINTAXE DETECTADO:\n" if has_errors else ""
    return prefix + "\n\n".join(reports)


if __name__ == "__main__":
    mcp.run()
