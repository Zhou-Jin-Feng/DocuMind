"""
RAG系统 - 向量化与嵌入模块
支持多个API提供商的统一嵌入接口（含本地Ollama）
"""

import json
import time
from copy import deepcopy
from math import isfinite
from typing import List, Optional
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener
from httpx import Timeout
from openai import OpenAI
from app.config import settings
from app.utils.logger import get_logger
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

# 尝试导入 Ollama（如果可用）
try:
    from langchain_ollama import OllamaEmbeddings

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

logger = get_logger(__name__)


class UniversalEmbeddingClient:
    """
    统一嵌入客户端
    支持OpenAI、DeepSeek、智谱GLM的嵌入API，以及本地Ollama
    """

    _HEALTH_CACHE_SECONDS = 30.0

    # 模型配置
    MODELS = {
        "openai": {
            "model": "text-embedding-3-small",
            "dimensions": 1536,
            "max_batch_size": 100,
            "type": "api",  # 标记类型
        },
        "openai-large": {
            "model": "text-embedding-3-large",
            "dimensions": 3072,
            "max_batch_size": 100,
            "type": "api",
        },
        "deepseek": {
            "model": "deepseek-embedding",
            "dimensions": 1536,
            "max_batch_size": 100,
            "type": "api",
        },
        "glm": {
            "model": "embedding-2",
            "dimensions": 1024,
            "max_batch_size": 100,
            "type": "api",
        },
        # ===== 新增 Ollama 支持 =====
        "ollama": {
            "model": "qwen3-embedding",
            # qwen3-embedding 的默认向量维度为 4096。运行时仍会优先使用探测值。
            "dimensions": 4096,
            "max_batch_size": 50,  # Ollama 批处理能力有限
            "type": "local",
        },
        "ollama-nomic": {
            "model": "nomic-embed-text",
            "dimensions": 768,
            "max_batch_size": 50,
            "type": "local",
        },
        "ollama-qwen": {
            "model": "qwen3-embedding",
            "dimensions": 4096,
            "max_batch_size": 50,
            "type": "local",
        },
    }

    @classmethod
    def configuration_for(cls, provider: str) -> dict:
        """Return configured model metadata without initializing a provider."""
        if provider not in cls.MODELS:
            raise ValueError(
                f"Unsupported embedding provider: {provider}. "
                f"Supported providers: {', '.join(cls.MODELS.keys())}"
            )
        config = deepcopy(cls.MODELS[provider])
        if provider == "ollama":
            config["model"] = settings.ollama_embedding_model
            if settings.ollama_embedding_dimensions is not None:
                config["dimensions"] = settings.ollama_embedding_dimensions
        return config

    def __init__(
        self,
        provider: str = "ollama",
        *,
        connection_timeout_seconds: float | None = None,
        request_timeout_seconds: float | None = None,
    ):
        """
        初始化嵌入客户端

        Args:
            provider: API提供商 (openai/openai-large/deepseek/glm/ollama)
        """
        self.provider = provider
        self._ollama_health_expires_at = 0.0
        self.connection_timeout_seconds = self._optional_timeout(
            connection_timeout_seconds,
            name="connection_timeout_seconds",
        )
        self.request_timeout_seconds = self._optional_timeout(
            request_timeout_seconds,
            name="request_timeout_seconds",
        )

        self.config = self.configuration_for(provider)
        self.type = self.config.get("type", "api")

        # 根据类型初始化客户端
        if self.type == "local":
            self._initialize_ollama()
        else:
            self._initialize_api_client()

        logger.info(f"已初始化嵌入客户端: {provider}")
        logger.info(f"  类型: {'本地Ollama' if self.type == 'local' else '云端API'}")
        logger.info(f"  模型: {self.config['model']}")
        logger.info(f"  向量维度: {self.config['dimensions']}")

    @staticmethod
    def _optional_timeout(value: float | None, *, name: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{name} 必须是正有限数字")
        return float(value)

    def _http_timeout(self) -> Timeout | None:
        request_timeout = getattr(self, "request_timeout_seconds", None)
        if request_timeout is None:
            return None
        connection_timeout = (
            getattr(self, "connection_timeout_seconds", None) or request_timeout
        )
        return Timeout(request_timeout, connect=connection_timeout)

    def _embed_ollama_query(
        self,
        text: str,
        *,
        max_retries: int = 3,
    ) -> List[float]:
        """Embed one text with bounded retries for transient Ollama failures."""
        if max_retries <= 0:
            raise ValueError("max_retries 必须大于 0")

        for attempt in range(max_retries):
            try:
                return self.ollama_client.embed_query(text)
            except Exception as exc:
                if attempt == max_retries - 1:
                    raise
                wait_time = 0.5 * (2**attempt)
                logger.warning(
                    "Ollama 向量化暂时失败，将重试",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    wait_seconds=wait_time,
                    error_type=type(exc).__name__,
                )
                time.sleep(wait_time)

        raise RuntimeError("Ollama embedding retry loop exited unexpectedly")

    def _initialize_ollama(self):
        """初始化 Ollama 本地客户端"""
        if not OLLAMA_AVAILABLE:
            raise ImportError(
                "需要安装 langchain-ollama 来使用 Ollama\n"
                "运行: pip install langchain-ollama"
            )

        base_url = settings.ollama_base_url
        model_name = self.config["model"]
        self.base_url = base_url

        try:
            parsed_host = urlparse(base_url).hostname
            client_kwargs = (
                {"trust_env": False}
                if parsed_host in {"localhost", "127.0.0.1", "::1"}
                else {}
            )
            http_timeout = self._http_timeout()
            if http_timeout is not None:
                client_kwargs["timeout"] = http_timeout
            self.ollama_client = OllamaEmbeddings(
                model=model_name,
                base_url=base_url,
                client_kwargs=client_kwargs,
            )

            # 尝试获取实际维度
            try:
                test_vector = self._embed_ollama_query("test")
                self.config["dimensions"] = len(test_vector)
                self._ollama_health_expires_at = (
                    time.monotonic() + self._HEALTH_CACHE_SECONDS
                )
                logger.info(f"  实际向量维度: {len(test_vector)}")
            except Exception as exc:
                # Ollama 首次加载模型时可能短暂返回 502；保留与模型匹配的
                # fallback，避免把 qwen3-embedding 错记为 1024 维并污染索引。
                logger.warning(
                    "无法探测 Ollama 向量维度，将使用配置中的 fallback",
                    model=model_name,
                    fallback_dimension=self.config["dimensions"],
                    error_type=type(exc).__name__,
                )

        except Exception as e:
            raise ConnectionError(
                f"无法连接到 Ollama 服务: {str(e)}\n"
                f"请确保 Ollama 正在运行 (ollama serve)\n"
                f"并已下载模型: ollama pull {model_name}"
            )

    @staticmethod
    def _ollama_model_available(
        configured_model: str,
        installed_models: List[str],
    ) -> bool:
        """判断 Ollama 模型列表是否包含配置模型。"""
        configured = configured_model.strip()
        if not configured:
            return False
        if ":" in configured:
            return configured in installed_models
        return (
            configured in installed_models or f"{configured}:latest" in installed_models
        )

    @staticmethod
    def _ollama_opener(base_url: str):
        parsed_host = urlparse(base_url).hostname
        return (
            build_opener(ProxyHandler({}))
            if parsed_host in {"localhost", "127.0.0.1", "::1"}
            else build_opener()
        )

    @staticmethod
    def _read_ollama_json(opener, request: Request, timeout_seconds: float) -> dict:
        with opener.open(request, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", None)
            if status_code is None:
                status_code = response.getcode()
            if status_code != 200:
                raise ConnectionError(
                    f"Ollama health probe returned HTTP {status_code}"
                )
            try:
                payload = json.load(response)
            except (UnicodeDecodeError, ValueError) as exc:
                raise ConnectionError(
                    "Ollama health probe returned invalid JSON"
                ) from exc
        if not isinstance(payload, dict):
            raise ConnectionError("Ollama health probe returned an invalid payload")
        return payload

    def health_check(self, *, timeout_seconds: float = 2.0) -> bool:
        """检查 Embedding 提供商是否可用于当前配置。"""
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds 必须是正数")

        # 云端 Embedding 不主动发送 API 请求；客户端成功创建即表示配置完整。
        if self.type != "local":
            return getattr(self, "client", None) is not None

        if time.monotonic() < getattr(self, "_ollama_health_expires_at", 0.0):
            return True

        base_url = str(getattr(self, "base_url", settings.ollama_base_url)).rstrip("/")
        opener = self._ollama_opener(base_url)
        tags_request = Request(
            f"{base_url}/api/tags",
            headers={"Accept": "application/json"},
        )
        payload = self._read_ollama_json(
            opener,
            tags_request,
            float(timeout_seconds),
        )
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise ConnectionError("Ollama health probe returned an invalid model list")
        installed_models = [
            str(item.get("name") or item.get("model") or "")
            for item in models
            if isinstance(item, dict)
        ]
        configured_model = str(self.config.get("model") or "")
        if not self._ollama_model_available(configured_model, installed_models):
            raise ConnectionError(
                f"Ollama embedding model is not installed: {configured_model}"
            )

        embed_request = Request(
            f"{base_url}/api/embed",
            data=json.dumps(
                {"model": configured_model, "input": "readiness"},
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        embed_payload = self._read_ollama_json(
            opener,
            embed_request,
            float(timeout_seconds),
        )
        embeddings = embed_payload.get("embeddings")
        if (
            not isinstance(embeddings, list)
            or not embeddings
            or not isinstance(embeddings[0], list)
            or not embeddings[0]
        ):
            raise ConnectionError("Ollama embedding probe returned no vector")
        expected_dimension = int(self.config.get("dimensions") or 0)
        actual_dimension = len(embeddings[0])
        if expected_dimension > 0 and actual_dimension != expected_dimension:
            raise ConnectionError(
                "Ollama embedding probe dimension mismatch: "
                f"{actual_dimension} != {expected_dimension}"
            )
        self._ollama_health_expires_at = time.monotonic() + self._HEALTH_CACHE_SECONDS
        return True

    def _initialize_api_client(self) -> OpenAI:
        """初始化云端API客户端"""
        client_options = {"max_retries": 0}
        http_timeout = self._http_timeout()
        if http_timeout is not None:
            client_options["timeout"] = http_timeout
        if self.provider.startswith("openai"):
            api_key = settings.openai_api_key
            base_url = settings.openai_base_url

            if not api_key:
                raise ValueError("未配置OPENAI_API_KEY，请检查.env文件")

            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                **client_options,
            )

        elif self.provider == "deepseek":
            api_key = settings.deepseek_api_key
            base_url = settings.deepseek_base_url

            if not api_key:
                raise ValueError("未配置DEEPSEEK_API_KEY，请检查.env文件")

            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                **client_options,
            )

        elif self.provider == "glm":
            api_key = settings.glm_api_key
            base_url = settings.glm_base_url

            if not api_key:
                raise ValueError("未配置GLM_API_KEY，请检查.env文件")

            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                **client_options,
            )

    def embed_text(
        self,
        text: str,
        *,
        timeout_seconds: float | None = None,
        max_attempts: int = 3,
    ) -> List[float]:
        """
        对单个文本进行向量化

        Args:
            text: 待向量化的文本

        Returns:
            向量列表（浮点数）
        """
        if not text.strip():
            raise ValueError("输入文本不能为空")
        timeout_seconds = self._optional_timeout(
            timeout_seconds,
            name="timeout_seconds",
        )
        if max_attempts <= 0:
            raise ValueError("max_attempts 必须大于 0")

        # 本地 Ollama
        if self.type == "local":
            try:
                return self._embed_ollama_query(text, max_retries=max_attempts)
            except Exception:
                logger.exception("Ollama 单文本向量化失败")
                raise

        # 云端 API
        try:
            client = (
                self.client.with_options(timeout=timeout_seconds, max_retries=0)
                if timeout_seconds is not None
                else self.client
            )
            response = client.embeddings.create(model=self.config["model"], input=text)
            return response.data[0].embedding
        except Exception:
            logger.exception("API 单文本向量化失败")
            raise

    def embed_texts_batch(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        show_progress: bool = True,
        max_retries: int = 3,
    ) -> List[List[float]]:
        """
        批量向量化文本（推荐使用）
        自动分批、带进度条、支持错误重试

        Args:
            texts: 文本列表
            batch_size: 每批处理的数量（默认使用模型最大值）
            show_progress: 是否显示进度条
            max_retries: 失败时最大重试次数

        Returns:
            向量列表的列表
        """
        if not texts:
            return []
        if max_retries <= 0:
            raise ValueError("max_retries 必须大于 0")

        empty_indexes = [
            index
            for index, text in enumerate(texts)
            if not isinstance(text, str) or not text.strip()
        ]
        if empty_indexes:
            raise ValueError(f"存在空文本，索引位置: {empty_indexes[:10]}")
        texts = [text.strip() for text in texts]

        # 设置批处理大小
        if batch_size is None:
            batch_size = self.config["max_batch_size"]
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")

        total_batches = (len(texts) + batch_size - 1) // batch_size
        all_embeddings = []

        # 显示开始信息
        logger.info(f"\n开始批量向量化...")
        logger.info(f"  总文本数: {len(texts)}")
        logger.info(f"  批次大小: {batch_size}")
        logger.info(f"  总批次数: {total_batches}")
        logger.info(f"  模式: {'本地' if self.type == 'local' else '云端'}\n")

        # 创建进度条
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        ) as progress:

            task = progress.add_task(
                "向量化进度...", total=len(texts), visible=show_progress
            )

            # 分批处理
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i : i + batch_size]
                batch_num = i // batch_size + 1

                # 本地 Ollama 处理
                if self.type == "local":
                    try:
                        batch_embeddings = []
                        for text in batch_texts:
                            embedding = self._embed_ollama_query(
                                text,
                                max_retries=max_retries,
                            )
                            batch_embeddings.append(embedding)

                        all_embeddings.extend(batch_embeddings)
                        progress.update(task, advance=len(batch_texts))

                    except Exception:
                        logger.exception(f"Ollama 批次 {batch_num} 向量化失败")
                        raise

                else:
                    # 云端 API 处理（带重试）
                    for attempt in range(max_retries):
                        try:
                            response = self.client.embeddings.create(
                                model=self.config["model"], input=batch_texts
                            )

                            # 提取向量
                            batch_embeddings = [
                                item.embedding for item in response.data
                            ]
                            all_embeddings.extend(batch_embeddings)

                            # 更新进度
                            progress.update(task, advance=len(batch_texts))

                            break  # 成功则跳出重试循环

                        except Exception as e:
                            if attempt < max_retries - 1:
                                wait_time = 2**attempt  # 指数退避
                                logger.info(
                                    f"批次 {batch_num} 失败，{wait_time}秒后重试... "
                                    f"({attempt + 1}/{max_retries})"
                                )
                                time.sleep(wait_time)
                            else:
                                logger.exception(
                                    f"API 批次 {batch_num} 失败，已达最大重试次数"
                                )
                                raise

                # 限流保护
                if i + batch_size < len(texts):
                    time.sleep(0.1 if self.type == "api" else 0.05)

        logger.info(f"\n批量向量化完成！总共 {len(all_embeddings)} 个向量")

        return all_embeddings

    def get_embedding_dimension(self) -> int:
        """获取当前模型的向量维度"""
        return self.config["dimensions"]

    def test_embedding(self):
        """
        测试嵌入功能
        """
        logger.info("=" * 60)

        test_texts = [
            "人工智能是计算机科学的一个分支",
            "机器学习是AI的核心技术",
            "今天天气真好",
        ]

        logger.info("\n测试文本:")
        for i, text in enumerate(test_texts, 1):
            logger.info(f"  {i}. {text}")

        logger.info("\n正在向量化...")

        # 批量向量化
        embeddings = self.embed_texts_batch(test_texts, show_progress=True)

        # 分析结果
        logger.info("\n向量信息:")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("文本", width=30)
        table.add_column("向量维度", width=10)
        table.add_column("前5个值", width=40)

        for text, embedding in zip(test_texts, embeddings):
            preview = ", ".join([f"{v:.4f}" for v in embedding[:5]])
            table.add_row(
                text[:25] + "..." if len(text) > 25 else text,
                str(len(embedding)),
                preview,
            )

        logger.info(table)

        # 计算相似度
        logger.info("\n语义相似度分析:")
        sim_1_2 = self._cosine_similarity(embeddings[0], embeddings[1])
        sim_1_3 = self._cosine_similarity(embeddings[0], embeddings[2])

        logger.info(f"  「AI」 vs 「机器学习」: {sim_1_2:.4f} (应该较高)")
        logger.info(f"  「AI」 vs 「天气」:     {sim_1_3:.4f} (应该较低)")

        if sim_1_2 > sim_1_3:
            logger.info("\n嵌入模型工作正常！语义相似的文本向量距离更近。")
        else:
            logger.info("\n结果异常，请检查API配置")

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            vec1: 向量1
            vec2: 向量2

        Returns:
            相似度值（-1到1之间，越接近1越相似）
        """
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)


def demo_compare_providers():
    """
    演示：对比不同提供商的嵌入效果
    """
    logger.info("=" * 60)

    test_text = "检索增强生成技术结合了信息检索和文本生成"

    logger.info(f"\n测试文本: {test_text}\n")

    # 检测可用的提供商
    available_providers = []

    providers_to_test = ["ollama", "openai", "deepseek", "glm"]

    for provider in providers_to_test:
        try:
            client = UniversalEmbeddingClient(provider)
            available_providers.append((provider, client))
            logger.info(f"{provider} 可用")
        except Exception as e:
            logger.info(f"{provider} 不可用: {str(e)[:50]}")

    if not available_providers:
        logger.info("\n没有可用的提供商，请检查配置")
        return

    logger.info("\n" + "=" * 60)

    # 对比测试
    results = []

    for provider, client in available_providers:
        logger.info(f"\n测试 {provider}...")

        start_time = time.time()
        try:
            embedding = client.embed_text(test_text)
            elapsed_time = time.time() - start_time

            results.append(
                {
                    "provider": provider,
                    "type": "本地" if client.type == "local" else "云端",
                    "dimensions": len(embedding),
                    "time": elapsed_time,
                    "preview": embedding[:5],
                }
            )
        except Exception as e:
            logger.error(f"测试失败: {str(e)}")

    # 展示对比表格
    logger.info("\n" + "=" * 60)
    logger.info("\n性能对比:\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("提供商", width=15)
    table.add_column("类型", width=10)
    table.add_column("向量维度", width=10)
    table.add_column("耗时(秒)", width=10)
    table.add_column("向量预览(前5值)", width=40)

    for result in results:
        preview = ", ".join([f"{v:.3f}" for v in result["preview"]])
        table.add_row(
            result["provider"],
            result["type"],
            str(result["dimensions"]),
            f"{result['time']:.3f}",
            preview,
        )

    logger.info(table)


if __name__ == "__main__":
    logger.info("\nRAG系统 - 向量化与嵌入模块测试\n")

    logger.info("选择测试模式:")
    logger.info("1. 测试单个API提供商")
    logger.info("2. 对比所有可用提供商")

    choice = input("\n请输入选项 (1/2): ").strip()

    if choice == "1":
        logger.info("\n选择提供商:")
        logger.info("1. Ollama (本地免费 - 推荐)")
        logger.info("2. OpenAI (云端)")
        logger.info("3. DeepSeek (云端)")
        logger.info("4. 智谱GLM (云端)")

        provider_choice = input("\n请输入选项 (1/2/3/4): ").strip()

        provider_map = {"1": "ollama", "2": "openai", "3": "deepseek", "4": "glm"}

        provider = provider_map.get(provider_choice, "ollama")

        try:
            client = UniversalEmbeddingClient(provider)
            client.test_embedding()
        except Exception as e:
            logger.exception("测试失败")
            if provider == "ollama":
                logger.info("提示: 请确保 Ollama 正在运行并已下载模型")
                logger.info("  1. 启动: ollama serve")
                logger.info("  2. 下载模型: ollama pull qwen3-embedding")
            else:
                logger.info("请检查.env文件中的API配置")

    else:
        demo_compare_providers()
