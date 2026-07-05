"""
SmartNotes MCP Server - 学习辅助服务
基于 FastMCP 提供闪卡制作、测验生成、文本摘要等学习辅助工具
这些工具调用 LLM 进行内容生成，为 SmartNotes Agent 扩展学习辅助能力
"""
import json
import logging
import os

from mcp.server.fastmcp import FastMCP
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

mcp = FastMCP("SmartNotesLearning", json_response=True)


def _get_llm() -> ChatOpenAI:
    """获取 LLM 实例"""
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "qwen3.7-plus"),
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        temperature=0.7,
        max_tokens=4096,
    )


@mcp.tool()
async def create_flashcard(content: str, count: int = 5) -> str:
    """根据给定内容生成学习闪卡（Flashcard）。
    将学习内容转化为问答形式的闪卡，方便用户进行间隔重复记忆。
    每张闪卡正面是问题，背面是答案。
    
    参数:
        content: 要制作闪卡的学习内容文本
        count: 生成闪卡数量（默认5张，最多10张）
    
    返回:
        JSON 格式的闪卡列表，每张包含 question 和 answer 字段
    """
    count = min(max(count, 1), 10)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的学习工具助手，擅长从学习内容中提取关键知识点并制作闪卡。"),
        ("human", """请根据以下学习内容生成 {count} 张闪卡。

要求：
1. 每张闪卡包含一个问题和对应答案
2. 问题应该简洁明了，答案应该完整准确
3. 覆盖内容中的核心知识点
4. 以 JSON 数组格式返回，每个元素包含 "question" 和 "answer" 字段
5. 只返回 JSON，不要其他解释

学习内容:
{content}"""),
    ])

    try:
        chain = prompt | _get_llm() | StrOutputParser()
        result = await chain.ainvoke({"content": content[:2000], "count": count})

        # 尝试提取 JSON
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1] if "\n" in result else result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        # 验证是否为有效 JSON
        json.loads(result)
        return result

    except json.JSONDecodeError:
        return json.dumps([
            {"question": f"闪卡生成失败，请尝试提供更详细的学习内容（{i+1}）",
             "answer": "无法解析生成结果"}
            for i in range(count)
        ], ensure_ascii=False)
    except Exception as e:
        logger.error(f"Create flashcard failed: {e}")
        return json.dumps([{"question": f"闪卡生成出错: {str(e)}", "answer": ""}], ensure_ascii=False)


@mcp.tool()
async def generate_quiz(content: str, question_type: str = "mixed", count: int = 5) -> str:
    """根据学习内容生成测验题目。
    支持多种题型：选择题、判断题、填空题等，用于自我检测学习效果。
    
    参数:
        content: 学习内容文本
        question_type: 题目类型，可选 "choice"(选择题)、"true_false"(判断题)、
                       "fill_blank"(填空题)、"mixed"(混合，默认)
        count: 生成题目数量（默认5题，最多10题）
    
    返回:
        JSON 格式的测验题目列表，每题包含 type、question、options（选择题）、answer 字段
    """
    count = min(max(count, 1), 10)
    type_desc = {
        "choice": "单选题（4个选项）",
        "true_false": "判断题（正确/错误）",
        "fill_blank": "填空题",
        "mixed": "混合题型（包含选择题、判断题和填空题）",
    }
    type_instruction = type_desc.get(question_type, type_desc["mixed"])

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的教育测评工具，擅长根据学习内容生成高质量的测验题目。"),
        ("human", """请根据以下学习内容生成 {count} 道测验题。

要求：
1. 题型: {type_desc}
2. 题目应覆盖内容中的核心知识点
3. 以 JSON 数组格式返回
4. 选择题格式: {{"type": "choice", "question": "...", "options": ["A...", "B...", "C...", "D..."], "answer": "A"}}
5. 判断题格式: {{"type": "true_false", "question": "...", "answer": true}}
6. 填空题格式: {{"type": "fill_blank", "question": "___是...", "answer": "答案"}}
7. 只返回 JSON，不要其他解释

学习内容:
{content}"""),
    ])

    try:
        chain = prompt | _get_llm() | StrOutputParser()
        result = await chain.ainvoke({
            "content": content[:2000],
            "count": count,
            "type_desc": type_instruction,
        })

        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1] if "\n" in result else result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        json.loads(result)
        return result

    except json.JSONDecodeError:
        return json.dumps([
            {"type": "choice", "question": "测验生成失败，请尝试提供更详细的学习内容",
             "options": ["重试", "重试", "重试", "重试"], "answer": "A"}
            for _ in range(count)
        ], ensure_ascii=False)
    except Exception as e:
        logger.error(f"Generate quiz failed: {e}")
        return json.dumps([{"type": "choice", "question": f"测验生成出错: {str(e)}",
                            "options": ["A", "B", "C", "D"], "answer": "A"}], ensure_ascii=False)


@mcp.tool()
async def summarize_text(content: str, style: str = "concise", max_length: int = 500) -> str:
    """对文本进行智能摘要。
    支持多种摘要风格，帮助用户快速掌握长文本的核心内容。
    
    参数:
        content: 需要摘要的文本内容
        style: 摘要风格，可选 "concise"(简洁摘要，默认)、"detailed"(详细摘要)、
               "bullet"(要点列表)、"study"(学习笔记风格)
        max_length: 摘要最大长度（默认500字）
    
    返回:
        摘要文本
    """
    style_desc = {
        "concise": "简洁摘要：用1-3段话概括核心内容",
        "detailed": "详细摘要：保留重要细节的完整摘要",
        "bullet": "要点列表：用编号列表列出核心要点",
        "study": "学习笔记风格：包含核心概念、关键论点和个人理解建议",
    }
    instruction = style_desc.get(style, style_desc["concise"])

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的文本摘要助手。"),
        ("human", """请对以下文本进行摘要。

要求：
1. 风格: {instruction}
2. 最大长度: {max_length} 字
3. 不要遗漏关键信息
4. 保持客观准确

原文:
{content}"""),
    ])

    try:
        chain = prompt | _get_llm() | StrOutputParser()
        result = await chain.ainvoke({
            "content": content[:4000],
            "instruction": instruction,
            "max_length": max_length,
        })
        return result.strip()

    except Exception as e:
        logger.error(f"Summarize text failed: {e}")
        return f"摘要生成失败: {str(e)}"


@mcp.tool()
async def explain_concept(concept: str, context: str = "") -> str:
    """用通俗易懂的方式解释一个概念或术语。
    类似费曼学习法，用简单的语言解释复杂概念，帮助深入理解。
    
    参数:
        concept: 要解释的概念或术语名称
        context: 可选的上下文信息，帮助更精准地解释（如学科、应用场景等）
    
    返回:
        概念的解释文本，包含定义、简单类比、实际应用示例
    """
    context_part = f"\n\n上下文信息: {context}" if context else ""

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个优秀的老师，擅长用通俗易懂的语言解释复杂概念（费曼学习法）。"),
        ("human", """请解释以下概念：

概念: {concept}{context_part}

请按以下结构回答：
1. 一句话定义：用最简单的一句话定义这个概念
2. 通俗类比：用一个日常生活中的类比来帮助理解
3. 核心要点：列出3-5个核心要点
4. 实际应用：举1-2个实际应用场景
5. 常见误区：指出1-2个关于这个概念的常见误解

保持语言简洁清晰，适合学习者理解。"""),
    ])

    try:
        chain = prompt | _get_llm() | StrOutputParser()
        result = await chain.ainvoke({"concept": concept, "context_part": context_part})
        return result.strip()

    except Exception as e:
        logger.error(f"Explain concept failed: {e}")
        return f"概念解释失败: {str(e)}"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.mcp.smartnotes_server:app", host="0.0.0.0", port=8011)

# 模块级 app 供 uvicorn 直接导入（docker compose 使用）
_mcp_app = mcp.streamable_http_app()


class HostRewriteMiddleware:
    """ASGI 中间件：将 Host 头重写为 localhost，绕过 FastMCP 的 Host 校验"""
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            new_headers = []
            for key, value in scope.get("headers", []):
                if key == b"host":
                    value = b"localhost:8011"
                new_headers.append((key, value))
            scope["headers"] = new_headers
        await _mcp_app(scope, receive, send)


app = HostRewriteMiddleware()
