"""
RAG系统 - 生成模块。

支持多个 LLM API 的统一调用、流式输出和引用溯源。
"""

import os
from dataclasses import dataclass
from typing import Dict, Generator, List, Optional, Tuple

from anthropic import Anthropic
from openai import OpenAI
from rich.panel import Panel

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GenerationConfig:
    """生成配置。"""

    temperature: float = 0.7
    max_tokens: int = 1000
    stream: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature 必须在 0 到 2 之间")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens 必须大于 0")


class UniversalLLMClient:
    """OpenAI、Claude、DeepSeek 和 GLM 的统一客户端。"""

    MODELS = {
        "openai": {
            "default_model": "gpt-3.5-turbo",
            "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
        },
        "claude": {
            "default_model": "claude-3-haiku-20240307",
            "models": [
                "claude-3-haiku-20240307",
                "claude-3-sonnet-20240229",
                "claude-3-opus-20240229",
            ],
        },
        "deepseek": {
            "default_model": "deepseek-chat",
            "models": ["deepseek-chat"],
        },
        "glm": {
            "default_model": "glm-4-flash",
            "models": ["glm-4-flash", "glm-4"],
        },
    }

    def __init__(self, provider: str = "openai", model: Optional[str] = None):
        self.provider = provider.strip().lower()
        if self.provider not in self.MODELS:
            raise ValueError(
                f"不支持的提供商: {provider}\n"
                f"支持的选项: {', '.join(self.MODELS.keys())}"
            )

        self.model = model or self.MODELS[self.provider]["default_model"]
        self.client = self._initialize_client()
        logger.info(f"已初始化LLM客户端: {self.provider}")
        logger.info(f"  模型: {self.model}")

    def _initialize_client(self):
        """根据提供商初始化 API 客户端。"""
        if self.provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("未配置OPENAI_API_KEY")
            return OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )

        if self.provider == "claude":
            if not settings.anthropic_api_key:
                raise ValueError("未配置ANTHROPIC_API_KEY")
            return Anthropic(api_key=settings.anthropic_api_key)

        if self.provider == "deepseek":
            if not settings.deepseek_api_key:
                raise ValueError("未配置DEEPSEEK_API_KEY")
            return OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )

        if self.provider == "glm":
            if not settings.glm_api_key:
                raise ValueError("未配置GLM_API_KEY")
            return OpenAI(
                api_key=settings.glm_api_key,
                base_url=settings.glm_base_url,
            )

        raise RuntimeError(f"未实现的LLM提供商: {self.provider}")

    @staticmethod
    def _validate_messages(messages: List[Dict[str, str]]) -> None:
        if not messages:
            raise ValueError("messages 不能为空")
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ValueError(f"第 {index} 条消息必须是字典")
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                raise ValueError(f"第 {index} 条消息的 role 不受支持: {role}")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"第 {index} 条消息内容不能为空")

    @classmethod
    def _prepare_claude_messages(
        cls,
        messages: List[Dict[str, str]],
    ) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """将 system 消息拆分为 Anthropic API 的独立 system 参数。"""
        cls._validate_messages(messages)
        system_parts: List[str] = []
        claude_messages: List[Dict[str, str]] = []
        for message in messages:
            if message["role"] == "system":
                system_parts.append(message["content"].strip())
            else:
                claude_messages.append(
                    {
                        "role": message["role"],
                        "content": message["content"],
                    }
                )
        if not claude_messages:
            raise ValueError("Claude 请求至少需要一条 user 或 assistant 消息")
        system_prompt = "\n\n".join(system_parts) or None
        return system_prompt, claude_messages

    def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[GenerationConfig] = None,
    ) -> str:
        """生成回答（一次性输出）。"""
        config = config or GenerationConfig(stream=False)
        self._validate_messages(messages)

        try:
            if self.provider == "claude":
                system_prompt, claude_messages = self._prepare_claude_messages(messages)
                request = {
                    "model": self.model,
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "messages": claude_messages,
                }
                if system_prompt:
                    request["system"] = system_prompt
                response = self.client.messages.create(**request)
                if not response.content:
                    raise RuntimeError("Claude 未返回文本内容")
                answer = response.content[0].text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
                answer = response.choices[0].message.content

            if not answer:
                raise RuntimeError("模型未返回文本内容")
            return answer
        except Exception:
            logger.exception(f"LLM 生成失败: provider={self.provider}")
            raise

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        config: Optional[GenerationConfig] = None,
    ) -> Generator[str, None, None]:
        """生成回答（流式输出）。"""
        config = config or GenerationConfig(stream=True)
        self._validate_messages(messages)

        try:
            if self.provider == "claude":
                system_prompt, claude_messages = self._prepare_claude_messages(messages)
                request = {
                    "model": self.model,
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "messages": claude_messages,
                }
                if system_prompt:
                    request["system"] = system_prompt
                with self.client.messages.stream(**request) as stream:
                    for text in stream.text_stream:
                        if text:
                            yield text
                return

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True,
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as exc:
            logger.warning(
                "LLM 流式生成中断",
                event="llm_stream_failed",
                operation="llm.generate",
                status="error",
                error_type=type(exc).__name__,
                provider=self.provider,
            )
            raise


class RAGGenerator:
    """结合检索结果和 LLM 生成答案。"""

    SYSTEM_PROMPT = """你是一个专业的AI知识助手。你的任务是基于提供的文档内容回答用户问题。

重要规则：
1. **严格基于文档内容**：只使用提供的文档信息回答，不要添加文档中没有的内容
2. **引用来源**：在回答中注明信息来源（如"根据文档1"或"来源：xxx.pdf"）
3. **承认局限**：如果文档中没有答案，明确说"根据提供的文档，未找到相关信息"
4. **保持客观**：如实陈述文档内容，不要过度推断
5. **结构清晰**：用分点、分段的方式组织答案，便于阅读

你的回答应该：
- 准确：忠于文档内容
- 完整：综合多个文档片段
- 可追溯：标注信息来源
"""

    def __init__(self, llm_client: UniversalLLMClient):
        self.llm_client = llm_client
        logger.info("RAG生成器初始化完成")

    def _build_context_from_retrieval(self, retrieval_results) -> str:
        """从检索结果构建上下文。"""
        if not retrieval_results:
            return "未找到相关文档。"

        context_parts = ["以下是相关文档内容：\n"]
        for index, result in enumerate(retrieval_results, 1):
            source_info = result.source or "未知来源"
            if result.page_number:
                source_info += f" 第{result.page_number}页"
            context_parts.append(
                f"[文档{index}] 来源: {source_info}\n"
                f"{result.content}\n"
            )
        return "\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> List[Dict[str, str]]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("query 不能为空")
        user_message = f"{context}\n\n用户问题：{normalized_query}\n\n请基于上述文档回答："
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

    def generate_answer(
        self,
        query: str,
        retrieval_results,
        config: Optional[GenerationConfig] = None,
        show_prompt: bool = False,
    ) -> str:
        """生成答案（一次性输出）；失败时向上抛出异常。"""
        logger.info("正在生成答案...")
        context = self._build_context_from_retrieval(retrieval_results)
        messages = self._build_prompt(query, context)
        if show_prompt:
            logger.debug(f"构造的Prompt预览: {messages[1]['content'][:500]}")
        answer = self.llm_client.generate(messages, config)
        logger.info("答案生成完成")
        return answer

    def generate_answer_stream(
        self,
        query: str,
        retrieval_results,
        config: Optional[GenerationConfig] = None,
    ) -> Generator[str, None, None]:
        """生成答案（流式输出）；失败时向上抛出异常。"""
        context = self._build_context_from_retrieval(retrieval_results)
        messages = self._build_prompt(query, context)
        yield from self.llm_client.generate_stream(messages, config)

def demo_rag_generation():
    """
    演示：完整的RAG问答流程
    """
    logger.info("="*60)

    # 导入依赖模块
    try:
        from app.core.retriever import Retriever
        from app.core.vector_store import VectorStore
        from app.core.embedding_client import UniversalEmbeddingClient
    except ImportError as e:
        logger.error(f"导入失败: {str(e)}")
        logger.info("请确保前面课程的脚本都在同一目录")
        return

    import os

    # 步骤1：检查是否有已存在的知识库
    logger.info("\n步骤1: 加载知识库")

    kb_exists = os.path.exists("./retrieval_chroma_db")

    if kb_exists:
        logger.info("发现已有知识库，直接加载")

        # 初始化embedding和vector store
        provider = settings.default_embedding_provider
        embedding_client = UniversalEmbeddingClient(provider)

        vector_store = VectorStore(
            collection_name="retrieval_demo",
            persist_directory="./retrieval_chroma_db"
        )

    else:
        logger.info("未找到知识库，正在创建...")

        # 创建知识库（复用第6课的代码）
        logger.info("请先运行 retriever.py 创建知识库")
        return

    # 步骤2：初始化检索器
    logger.info("\n步骤2: 初始化检索器")
    retriever = Retriever(vector_store, embedding_client)

    # 步骤3：初始化LLM生成器
    logger.info("\n步骤3: 初始化LLM生成器")

    llm_provider = settings.default_llm_provider
    logger.info(f"使用LLM: {llm_provider}")

    try:
        llm_client = UniversalLLMClient(provider=llm_provider)
        rag_generator = RAGGenerator(llm_client)
    except Exception as e:
        logger.exception("LLM初始化失败")
        logger.info("请检查.env中的LLM API配置")
        return

    # 步骤4：测试问答
    logger.info("\n" + "="*70)
    logger.info("\n步骤4: 测试RAG问答")

    test_queries = [
        "监督学习有哪些常见算法？请列举并简单说明。",
        "RAG系统包含哪些核心组件？",
    ]

    for i, query in enumerate(test_queries, 1):
        logger.info("\n" + "="*70)
        logger.info(f"\n问题 {i}: {query}")

        # 执行检索
        logger.info("\n1️⃣ 检索相关文档...")
        retrieval_results = retriever.retrieve_semantic(query, top_k=3)

        logger.info(f"检索到 {len(retrieval_results)} 个相关片段")
        for j, result in enumerate(retrieval_results, 1):
            preview = result.content[:80].replace('\n', ' ')
            logger.info(f"  [{j}] {preview}...")

        # 生成答案
        logger.info("\n2️⃣ 生成答案...\n")

        if i == 1:
            # 第一个问题：流式输出
            logger.info("答案（流式输出）:\n")

            answer_parts = []
            for chunk in rag_generator.generate_answer_stream(
                query,
                retrieval_results,
                config=GenerationConfig(temperature=0.3, stream=True)
            ):
                logger.info(chunk, end='')
                answer_parts.append(chunk)

            full_answer = ''.join(answer_parts)
            logger.info("\n")

        else:
            # 第二个问题：一次性输出
            answer = rag_generator.generate_answer(
                query,
                retrieval_results,
                config=GenerationConfig(temperature=0.3, stream=False),
                show_prompt=False
            )

            logger.info("\n答案:")
            logger.info(Panel(answer, border_style="green"))

    # 步骤5：对比测试（有/无RAG）
    logger.info("\n" + "="*70)
    logger.info("\n步骤5: 对比测试（RAG vs 直接问）")

    comparison_query = "K-means聚类的具体步骤是什么？"

    logger.info(f"\n测试问题: {comparison_query}")

    # 5.1 不使用RAG（直接问）
    logger.info("\n方式1: 不使用RAG（直接问LLM）")

    direct_messages = [
        {"role": "user", "content": comparison_query}
    ]

    direct_answer = llm_client.generate(
        direct_messages,
        config=GenerationConfig(temperature=0.3, stream=False)
    )

    logger.info("\n直接回答（可能不准确或编造）:")
    logger.info(Panel(direct_answer, border_style="yellow", title="无RAG"))

    # 5.2 使用RAG
    logger.info("\n方式2: 使用RAG（检索+生成）")

    retrieval_results = retriever.retrieve_semantic(comparison_query, top_k=2)

    rag_answer = rag_generator.generate_answer(
        comparison_query,
        retrieval_results,
        config=GenerationConfig(temperature=0.3, stream=False)
    )

    logger.info("\nRAG回答（基于文档）:")
    logger.info(Panel(rag_answer, border_style="green", title="使用RAG"))

    # 完成
    logger.info("\n" + "="*70)
    logger.info("="*60)


if __name__ == "__main__":
    demo_rag_generation()
