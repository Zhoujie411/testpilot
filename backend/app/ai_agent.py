import json
import re
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.url_fetch import read_url_text


SYSTEM_PROMPT = """你是资深软件测试分析师，负责根据需求文档生成高质量测试用例。
你必须主动分析功能流程、业务规则、异常、边界、安全、兼容性和数据一致性。
你可以使用工具检索附件、抓取用户给出的需求链接、记录需要跨轮次保留的项目事实，这就是 ReAct 工作方式的一部分。
当用户消息中包含 http/https 链接时，优先调用 fetch_requirement_url 获取真实内容，绝不要凭空猜测链接内容。

最终回答必须先给出一句简短中文说明，然后输出一个 ```json 代码块，JSON 格式严格如下：
{
  "suite_name": "测试集名称",
  "summary": "覆盖范围说明",
  "cases": [
    {
      "module": "模块",
      "title": "用例标题",
      "priority": "P0/P1/P2/P3",
      "type": "功能/异常/边界/安全/兼容性/性能",
      "preconditions": "前置条件",
      "steps": ["步骤1", "步骤2"],
      "expected_result": "预期结果"
    }
  ]
}
不要省略字段，不要在 JSON 中使用 Markdown。若用户只是补充信息或讨论，也要基于当前会话返回更新后的完整用例集。
"""


def build_model(config: dict, api_key: str) -> ChatOpenAI:
    kwargs = {
        "model": config["model_name"],
        "api_key": api_key,
        "max_retries": 2,
        "timeout": 120,
    }
    if config.get("base_url"):
        kwargs["base_url"] = config["base_url"].rstrip("/")
    if config.get("api_style") == "responses":
        kwargs["use_responses_api"] = True
    return ChatOpenAI(**kwargs)


def run_test_case_agent(
    config: dict,
    api_key: str,
    history: list[dict],
    attachment_context: str,
    memory_summary: str,
    save_memory: Callable[[str], None],
) -> tuple[str, dict | None]:
    @tool
    def search_attachments(keyword: str) -> str:
        """Search uploaded requirement attachments for a keyword and return matching context."""
        if not attachment_context:
            return "当前会话没有附件。"
        lines = attachment_context.splitlines()
        matches = [line for line in lines if keyword.lower() in line.lower()]
        return "\n".join(matches[:40]) or "附件中没有找到该关键词。"

    @tool
    def remember_project_fact(fact: str) -> str:
        """Persist an important project rule, term, constraint, or user preference for later turns."""
        save_memory(fact)
        return "已写入会话长期记忆。"

    @tool
    def fetch_requirement_url(url: str) -> str:
        """Fetch an http/https requirement document URL and return its extracted plain text. Use this when the user message contains a link."""
        try:
            text, final_url, size = read_url_text(url)
        except ValueError as error:
            return f"抓取链接失败：{error}"
        if f"附件：{final_url}" in attachment_context or f"附件：{url}" in attachment_context:
            return f"链接 {final_url} 的内容已在会话附件中，可直接用 search_attachments 检索关键词。"
        if not text.strip():
            return (
                f"链接 {final_url} 已尝试浏览器渲染但正文仍为空，页面可能是纯图片/画布原型或需要登录。"
                "请告知用户导出需求文档（PDF/Word）后上传附件。"
            )
        return f"===== 链接：{final_url}（{size} 字节）=====\n{text[:8000]}"

    model = build_model(config, api_key)
    agent = create_react_agent(
        model, [search_attachments, remember_project_fact, fetch_requirement_url], prompt=SYSTEM_PROMPT
    )
    messages = []
    if memory_summary:
        messages.append(SystemMessage(content=f"会话长期记忆：\n{memory_summary}"))
    if attachment_context:
        messages.append(SystemMessage(content=f"以下是用户上传的需求附件内容：{attachment_context}"))
    for item in history[-20:]:
        message_cls = HumanMessage if item["role"] == "user" else AIMessage
        messages.append(message_cls(content=item["content"]))
    result = agent.invoke({"messages": messages}, config={"recursion_limit": 30})
    content = _message_text(result["messages"][-1].content)
    return content, parse_case_payload(content)


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


def parse_case_payload(content: str) -> dict | None:
    code_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL | re.IGNORECASE)
    candidates = [code_match.group(1)] if code_match else []
    first = content.find("{")
    last = content.rfind("}")
    if first >= 0 and last > first:
        candidates.append(content[first:last + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload.get("cases"), list):
                return payload
        except (json.JSONDecodeError, AttributeError):
            continue
    return None
