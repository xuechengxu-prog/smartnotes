"""
SmartNotes MCP Server - 联网搜索服务
基于 FastMCP 提供 web_search 和 get_web_content 工具
使用 DuckDuckGo 搜索（无需 API Key）
"""
import logging
import re

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("WebSearch", json_response=True)

# 搜索结果缓存
_search_cache: dict = {}


def _clean_html(text: str) -> str:
    """简单清理 HTML 标签"""
    text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网获取最新信息。
    使用 DuckDuckGo 搜索引擎搜索指定查询关键词，返回搜索结果摘要列表。
    当用户询问需要最新信息的知识库中可能没有的内容时使用此工具。
    
    参数:
        query: 搜索关键词或问题
        max_results: 返回结果数量（默认5条）
    
    返回:
        搜索结果列表，每条包含标题、摘要和链接
    """
    try:
        # 使用 DuckDuckGo Lite（HTML 版本，无需 JS）
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            response = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query, "kl": "wt-wt"},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            response.raise_for_status()

            html = response.text
            # 解析搜索结果（DuckDuckGo Lite 格式）
            results = []
            # 提取结果块
            result_blocks = re.findall(
                r'<tr class="result-link">.*?<td class="result-snippet">(.*?)</td>',
                html, re.DOTALL
            )

            # 提取链接和标题
            links = re.findall(
                r'<a rel="nofollow" class="result-link" href="([^"]*)"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )

            for i in range(min(len(links), max_results)):
                link_url = links[i][0]
                title = _clean_html(links[i][1])
                snippet = ""
                if i < len(result_blocks):
                    snippet = _clean_html(result_blocks[i])
                results.append(f"[{i+1}] {title}\n    摘要: {snippet}\n    链接: {link_url}")

            if not results:
                return f"未找到与 '{query}' 相关的搜索结果。"

            return "\n\n".join(results)

    except httpx.TimeoutException:
        return f"搜索超时，请稍后重试。"
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"搜索时出错: {str(e)}"


@mcp.tool()
async def get_web_content(url: str, max_length: int = 3000) -> str:
    """获取指定网页的文本内容。
    访问指定 URL 并提取网页中的主要文本内容（去除 HTML 标签）。
    当 web_search 返回的搜索结果摘要不够详细，需要获取完整页面内容时使用此工具。
    
    参数:
        url: 要访问的网页 URL
        max_length: 返回文本的最大长度（默认3000字符）
    
    返回:
        网页的纯文本内容
    """
    try:
        async with httpx.AsyncClient(timeout=20, verify=False, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return f"不支持的网页类型: {content_type}"

            text = _clean_html(response.text)

            # 提取有意义的内容（过滤太短的行）
            lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 20]
            meaningful_text = '\n'.join(lines)

            if not meaningful_text:
                return f"无法从该网页提取有效文本内容。"

            if len(meaningful_text) > max_length:
                meaningful_text = meaningful_text[:max_length] + "\n\n[...内容已截断]"

            return meaningful_text

    except httpx.TimeoutException:
        return f"访问网页超时，请稍后重试。"
    except Exception as e:
        logger.error(f"Get web content failed: {e}")
        return f"获取网页内容时出错: {str(e)}"


@mcp.tool()
async def search_and_summarize(query: str) -> str:
    """搜索并总结。
    自动搜索指定查询，并尝试获取排名最高的结果页面内容进行总结。
    适合需要快速了解某个话题的全貌时使用。
    
    参数:
        query: 要搜索和总结的话题或问题
    
    返回:
        搜索结果和内容的综合总结
    """
    # 先搜索
    search_result = await web_search(query, max_results=3)

    if "未找到" in search_result or "出错" in search_result:
        return search_result

    # 提取第一个链接
    links = re.findall(r'链接: (https?://[^\s]+)', search_result)
    if not links:
        return search_result

    # 获取第一个链接的内容
    content = await get_web_content(links[0], max_length=2000)

    return f"=== 搜索结果 ===\n{search_result}\n\n=== 详细内容 ===\n{content}"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.mcp.web_search_server:app", host="0.0.0.0", port=8010)

# 模块级 app 供 uvicorn 直接导入（docker compose 使用）
_mcp_app = mcp.streamable_http_app()


class HostRewriteMiddleware:
    """ASGI 中间件：将 Host 头重写为 localhost，绕过 FastMCP 的 Host 校验"""
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            new_headers = []
            for key, value in scope.get("headers", []):
                if key == b"host":
                    value = b"localhost:8010"
                new_headers.append((key, value))
            scope["headers"] = new_headers
        await _mcp_app(scope, receive, send)


app = HostRewriteMiddleware()
