from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from ddgs import DDGS


class WebSearchParams(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(
        10,
        ge=1,
        le=20,
        description="Maximum results to return (default: 10)",
    )


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information. Returns search results with titles, URLs and snippets"
    kind = ToolKind.NETWORK
    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebSearchParams(**invocation.params)

        try:
            results = DDGS().text(
                params.query,
                region="us-en",
                safesearch="off",
                timelimit="y",
                page=1,
                backend="auto",
            )
        except Exception as e:
            return ToolResult.error_result(
                f"Search failed: {e}",
                summary="Web search failed",
                recovery_hint="Check network connectivity, then retry. Simplify the query if needed.",
            )

        if not results:
            return ToolResult.success_result(
                f"No results found for: {params.query}",
                summary=f"No search results for '{params.query}'",
                metadata={
                    "results": 0,
                },
            )

        output_lines = [f"Search results for: {params.query}"]
        result_urls = []

        limited_results = list(results)[: params.max_results]

        for i, result in enumerate(limited_results, start=1):
            output_lines.append(f"{i}. Title: {result['title']}")
            output_lines.append(f"   URL: {result['href']}")
            result_urls.append(result['href'])
            if result.get("body"):
                output_lines.append(f"   Snippet: {result['body']}")

            output_lines.append("")

        return ToolResult.success_result(
            "\n".join(output_lines),
            summary=f"Found {len(limited_results)} result(s) for '{params.query}'",
            artifacts=result_urls[:10],
            next_actions=["Use web_fetch to read content from a specific result URL."],
            metadata={
                "results": len(limited_results),
            },
        )
