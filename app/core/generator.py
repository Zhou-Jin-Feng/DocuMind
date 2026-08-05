"""
RAG系统 - 生成模块
支持多个LLM API的统一调用，流式输出，引用溯源
"""

import os
from typing import List, Dict, Optional, Generator
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic
from app.utils.logger import get_logger
from rich.panel import Panel
from rich.markdown import Markdown

# 加载环境变量
load_dotenv()
logger = get_logger(__name__)


@dataclass
class GenerationConfig:
    """生成配置"""
    temperature: float = 0.7      # 创造性（0=确定性，1=随机性）
    max_tokens: int = 1000        # 最大生成长度
    stream: bool = True           # 是否流式输出


class UniversalLLMClient:
    """
    统一LLM客户端
    支持OpenAI、Claude、DeepSeek、GLM的统一调用
    """

    # 模型配置
    MODELS = {
        'openai': {
            'default_model': 'gpt-3.5-turbo',
            'models': ['gpt-3.5-turbo', 'gpt-4', 'gpt-4-turbo']
        },
        'claude': {
            'default_model': 'claude-3-haiku-20240307',
            'models': ['claude-3-haiku-20240307', 'claude-3-sonnet-20240229', 'claude-3-opus-20240229']
        },
        'deepseek': {
            'default_model': 'deepseek-chat',
            'models': ['deepseek-chat']
        },
        'glm': {
            'default_model': 'glm-4-flash',
            'models': ['glm-4-flash', 'glm-4']
        }
    }

    def __init__(self, provider: str = 'openai', model: Optional[str] = None):
        """
        初始化LLM客户端

        Args:
            provider: API提供商 (openai/claude/deepseek/glm)
            model: 模型名称（可选，默认使用推荐模型）
        """
        self.provider = provider

        if provider not in self.MODELS:
            raise ValueError(
                f"不支持的提供商: {provider}\n"
                f"支持的选项: {', '.join(self.MODELS.keys())}"
            )

        self.model = model or self.MODELS[provider]['default_model']
        self.client = self._initialize_client()

        logger.info(f"已初始化LLM客户端: {provider}")
        logger.info(f"  模型: {self.model}")

    def _initialize_client(self):
        """根据提供商初始化API客户端"""
        if self.provider == 'openai':
            api_key = os.getenv('OPENAI_API_KEY')
            base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')

            if not api_key:
                raise ValueError("未配置OPENAI_API_KEY")

            return OpenAI(api_key=api_key, base_url=base_url)

        elif self.provider == 'claude':
            api_key = os.getenv('ANTHROPIC_API_KEY')

            if not api_key:
                raise ValueError("未配置ANTHROPIC_API_KEY")

            return Anthropic(api_key=api_key)

        elif self.provider == 'deepseek':
            api_key = os.getenv('DEEPSEEK_API_KEY')
            base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')

            if not api_key:
                raise ValueError("未配置DEEPSEEK_API_KEY")

            return OpenAI(api_key=api_key, base_url=base_url)

        elif self.provider == 'glm':
            api_key = os.getenv('GLM_API_KEY')
            base_url = os.getenv('GLM_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4')

            if not api_key:
                raise ValueError("未配置GLM_API_KEY")

            return OpenAI(api_key=api_key, base_url=base_url)

    def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[GenerationConfig] = None
    ) -> str:
        """
        生成回答（一次性输出）

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            config: 生成配置

        Returns:
            生成的文本
        """
        if config is None:
            config = GenerationConfig(stream=False)

        try:
            if self.provider == 'claude':
                # Claude使用不同的API格式
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    messages=messages
                )
                return response.content[0].text

            else:
                # OpenAI兼容格式（OpenAI/DeepSeek/GLM）
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens
                )
                return response.choices[0].message.content

        except Exception as e:
            logger.info(f"生成失败: {str(e)}")
            raise

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        config: Optional[GenerationConfig] = None
    ) -> Generator[str, None, None]:
        """
        生成回答（流式输出）

        Args:
            messages: 消息列表
            config: 生成配置

        Yields:
            文本片段
        """
        if config is None:
            config = GenerationConfig(stream=True)

        try:
            if self.provider == 'claude':
                # Claude流式输出
                with self.client.messages.stream(
                    model=self.model,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    messages=messages
                ) as stream:
                    for text in stream.text_stream:
                        yield text

            else:
                # OpenAI兼容格式流式输出
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    stream=True
                )

                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

        except Exception as e:
            logger.info(f"流式生成失败: {str(e)}")
            raise


class RAGGenerator:
    """
    RAG生成器
    结合检索结果和LLM生成答案
    """

    # RAG系统提示词模板
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
        """
        初始化RAG生成器

        Args:
            llm_client: UniversalLLMClient实例
        """
        self.llm_client = llm_client
        logger.info("RAG生成器初始化完成")

    def _build_context_from_retrieval(self, retrieval_results) -> str:
        """
        从检索结果构建上下文

        Args:
            retrieval_results: 检索结果列表（RetrievalResult对象）

        Returns:
            格式化的上下文字符串
        """
        if not retrieval_results:
            return "未找到相关文档。"

        context_parts = ["以下是相关文档内容：\n"]

        for i, result in enumerate(retrieval_results, 1):
            source_info = f"{result.source}" if result.source else "未知来源"
            if result.page:
                source_info += f" 第{result.page}页"

            context_parts.append(
                f"[文档{i}] 来源: {source_info}\n"
                f"{result.content}\n"
            )

        return "\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> List[Dict[str, str]]:
        """
        构建完整的对话消息

        Args:
            query: 用户问题
            context: 文档上下文

        Returns:
            消息列表
        """
        user_message = f"{context}\n\n用户问题：{query}\n\n请基于上述文档回答："

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        return messages

    def generate_answer(
        self,
        query: str,
        retrieval_results,
        config: Optional[GenerationConfig] = None,
        show_prompt: bool = False
    ) -> str:
        """
        生成答案（一次性输出）

        Args:
            query: 用户问题
            retrieval_results: 检索结果列表
            config: 生成配置
            show_prompt: 是否显示构造的prompt（调试用）

        Returns:
            生成的答案
        """
        logger.info(f"\n正在生成答案...")

        # 1. 构建上下文
        context = self._build_context_from_retrieval(retrieval_results)

        # 2. 构建prompt
        messages = self._build_prompt(query, context)

        if show_prompt:
            logger.info("\n--- 构造的Prompt ---")
            logger.info(messages[1]['content'][:500] + "...")
            logger.info("--- End ---\n")

        # 3. 调用LLM生成
        try:
            answer = self.llm_client.generate(messages, config)
            logger.info(f"答案生成完成")
            return answer

        except Exception as e:
            logger.info(f"生成失败: {str(e)}")
            return "抱歉，生成答案时发生错误。"

    def generate_answer_stream(
        self,
        query: str,
        retrieval_results,
        config: Optional[GenerationConfig] = None
    ) -> Generator[str, None, None]:
        """
        生成答案（流式输出）

        Args:
            query: 用户问题
            retrieval_results: 检索结果列表
            config: 生成配置

        Yields:
            答案文本片段
        """
        # 构建上下文和prompt
        context = self._build_context_from_retrieval(retrieval_results)
        messages = self._build_prompt(query, context)

        # 流式生成
        try:
            for chunk in self.llm_client.generate_stream(messages, config):
                yield chunk

        except Exception as e:
            logger.info(f"流式生成失败: {str(e)}")
            yield "抱歉，生成答案时发生错误。"


def demo_rag_generation():
    """
    演示：完整的RAG问答流程
    """
    logger.info("="*60)

    # 导入依赖模块
    try:
        from retriever import Retriever
        from vector_store import VectorStore
        from embedding_client import UniversalEmbeddingClient
        from document_loader import UniversalDocumentLoader
        from document_chunker import DocumentChunker
    except ImportError as e:
        logger.info(f"导入失败: {str(e)}")
        logger.info("请确保前面课程的脚本都在同一目录")
        return

    import os

    # 步骤1：检查是否有已存在的知识库
    logger.info("\n步骤1: 加载知识库")

    kb_exists = os.path.exists("./retrieval_chroma_db")

    if kb_exists:
        logger.info("发现已有知识库，直接加载")

        # 初始化embedding和vector store
        provider = os.getenv('DEFAULT_EMBEDDING_PROVIDER', 'openai')
        embedding_client = UniversalEmbeddingClient(provider)

        vector_store = VectorStore(
            collection_name="retrieval_demo",
            persist_directory="./retrieval_chroma_db"
        )

    else:
        logger.info("未找到知识库，正在创建...")

        # 创建知识库（复用第6课的代码）
        from retriever import demo_retrieval
        logger.info("请先运行 retriever.py 创建知识库")
        return

    # 步骤2：初始化检索器
    logger.info("\n步骤2: 初始化检索器")
    retriever = Retriever(vector_store, embedding_client)

    # 步骤3：初始化LLM生成器
    logger.info("\n步骤3: 初始化LLM生成器")

    llm_provider = os.getenv('DEFAULT_LLM_PROVIDER', 'openai')
    logger.info(f"使用LLM: {llm_provider}")

    try:
        llm_client = UniversalLLMClient(provider=llm_provider)
        rag_generator = RAGGenerator(llm_client)
    except Exception as e:
        logger.info(f"LLM初始化失败: {str(e)}")
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


