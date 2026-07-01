import os
import requests

API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-f7ab6ca7fb8148b6a34b102b14660da0")
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

AGENT_PROMPTS = {
    "note": "你是大学笔记整理专家，只输出【重点】【考点】【总结】三部分。",
    "plan": "你是大学复习规划师，生成简洁可执行的每日计划。",
    "qa": "你是大学答疑老师，直接精准回答，不要废话。"
}

MOCK_RESPONSES = {
    "note": "【重点】这是笔记的核心内容摘要。\n\n【考点】考试重点包括：概念理解、公式应用、案例分析。\n\n【总结】本章节主要讲述了基础知识和应用方法。",
    "plan": "## 复习计划\n\n### 第1天：基础概念\n- 复习第一章知识点\n- 完成课后习题\n\n### 第2天：核心公式\n- 推导重要公式\n- 练习公式应用\n\n### 第3天：综合练习\n- 模拟测试\n- 错题回顾",
    "qa": "我是大学答疑老师，专门解答大学课程相关问题。"
}

def run_agent(agent_type: str, user_input: str):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = AGENT_PROMPTS.get(agent_type, "")
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_input})
    
    data = {
        "model": "qwen3.6-plus",
        "messages": messages,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        print(f"AI调用失败: {e}")
        return MOCK_RESPONSES.get(agent_type, "服务暂时不可用")
    except (KeyError, IndexError) as e:
        print(f"解析响应失败: {e}")
        return MOCK_RESPONSES.get(agent_type, "服务暂时不可用")