"""
LangChain 复习计划链
使用 LLM 根据笔记内容生成个性化的复习计划
"""
import logging
from typing import AsyncIterator, Optional
from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.services.llm_service import llm_service

logger = logging.getLogger(__name__)


# 复习计划系统提示词
PLAN_SYSTEM_PROMPT = """你是一位专业的学习规划师。你的任务是根据用户的学习笔记内容，制定科学、高效的复习计划。

复习计划要求：
1. 基于艾宾浩斯遗忘曲线设计复习间隔
2. 将复习内容合理分配到不同时间段
3. 每次复习明确标注重点内容和复习目标
4. 提供具体的复习方法和建议
5. 计划应具有可操作性，时间分配合理
6. 使用 Markdown 格式输出

输出格式：
- 总体复习策略概述
- 按时间线排列的复习计划表
- 每次复习的具体内容和方法
- 复习效果自测建议
"""

PLAN_HUMAN_TEMPLATE = """请根据以下笔记内容帮我制定复习计划：

笔记内容：
{content}

{preferences}
"""


class PlanChain:
    """复习计划 LangChain 链"""

    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", PLAN_SYSTEM_PROMPT),
            ("human", PLAN_HUMAN_TEMPLATE),
        ])
        self.output_parser = StrOutputParser()
        # 构建链: prompt -> llm -> parser
        self.chain = self.prompt | llm_service.llm | self.output_parser

    async def generate_plan(
        self,
        content: str,
        days: int = 30,
        sessions_per_day: int = 2,
        focus_areas: Optional[str] = None,
    ) -> str:
        """
        生成复习计划（非流式）
        :param content: 笔记内容
        :param days: 计划总天数
        :param sessions_per_day: 每天复习次数
        :param focus_areas: 重点复习领域（可选）
        :return: 复习计划文本
        """
        preferences = f"""复习偏好：
- 计划总时长：{days} 天
- 每天复习次数：{sessions_per_day} 次
{f'- 重点复习领域：{focus_areas}' if focus_areas else ''}"""

        logger.info(f"Generating plan for {days} days, {sessions_per_day} sessions/day")

        result = await self.chain.ainvoke({
            "content": content,
            "preferences": preferences,
        })
        return result

    async def generate_plan_stream(
        self,
        content: str,
        days: int = 30,
        sessions_per_day: int = 2,
        focus_areas: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        生成复习计划（流式输出）
        :param content: 笔记内容
        :param days: 计划总天数
        :param sessions_per_day: 每天复习次数
        :param focus_areas: 重点复习领域（可选）
        :yield: 流式文本片段
        """
        preferences = f"""复习偏好：
- 计划总时长：{days} 天
- 每天复习次数：{sessions_per_day} 次
{f'- 重点复习领域：{focus_areas}' if focus_areas else ''}"""

        logger.info(f"Generating plan (stream) for {days} days")

        async for chunk in self.chain.astream({
            "content": content,
            "preferences": preferences,
        }):
            yield chunk

    def get_review_schedule(
        self,
        start_date: Optional[datetime] = None,
        days: int = 30,
    ) -> list:
        """
        生成基于艾宾浩斯遗忘曲线的复习时间表
        :param start_date: 开始日期，默认为今天
        :param days: 计划天数
        :return: 复习日期列表
        """
        if start_date is None:
            start_date = datetime.now()

        # 艾宾浩斯复习间隔（天）：1, 2, 4, 7, 15, 30
        intervals = [1, 2, 4, 7, 15, 30]
        schedule = []

        for day in range(days):
            current_date = start_date + timedelta(days=day)
            reviews = []

            for interval in intervals:
                if day % interval == 0 and day > 0:
                    reviews.append(f"第 {interval} 天间隔复习")

            if reviews:
                schedule.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "day": day + 1,
                    "reviews": reviews,
                })

        return schedule


# 全局链实例
plan_chain = PlanChain()
