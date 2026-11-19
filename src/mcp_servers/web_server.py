import httpx
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("web-and-places")


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """[Nível 1] Pesquisa informações atualizadas na internet (gratuita, sem chave de API)."""
    try:
        results = DDGS().text(query, region="br-pt", max_results=max_results)
    except Exception as e:
        return f"Erro ao pesquisar na web: {e}"

    if not results:
        return f"Nenhum resultado encontrado para: {query}"

    lines = []
    for r in results:
        title = r.get("title", "")
        href = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"- **{title}**\n  URL: {href}\n  Resumo: {body}")
    return "\n\n".join(lines)


@mcp.tool()
def search_place(place_name: str, city: str = "") -> str:
    """[Nível 1] Busca endereço completo, telefone, WhatsApp e horário de um estabelecimento ou clínica."""
    query_str = f"{place_name} {city}".strip()
    sections = []

    # 1. Busca na web focada em endereço e telefone
    try:
        web_results = DDGS().text(
            f"{query_str} endereço telefone",
            region="br-pt",
            max_results=6,
        )
        if web_results:
            web_lines = [
                f"- {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})"
                for r in web_results
            ]
            sections.append("### Resultados da Web (Endereço / Telefone):\n" + "\n".join(web_lines))
    except Exception as e:
        sections.append(f"### Web Search indisponível: {e}")

    # 2. Busca estruturada no OpenStreetMap Nominatim (endereço oficial)
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": f"{query_str} Brasil",
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 3,
            },
            headers={"User-Agent": "cachy-assistant/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        places = resp.json()
        if places:
            osm_lines = [
                f"- {p.get('display_name', '')} (Lat: {p.get('lat')}, Lon: {p.get('lon')})"
                for p in places
            ]
            sections.append("### OpenStreetMap (Localização):\n" + "\n".join(osm_lines))
    except Exception as e:
        sections.append(f"### OpenStreetMap indisponível: {e}")

    return "\n\n".join(sections) if sections else f"Não foram encontrados detalhes para '{query_str}'."


if __name__ == "__main__":
    mcp.run()
