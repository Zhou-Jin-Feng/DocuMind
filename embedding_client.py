"""
RAG系统 - 向量化与嵌入模块
支持多个API提供商的统一嵌入接口（含本地Ollama）
"""

import os
import time
from typing import List, Optional, Union
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.table import Table

# 尝试导入 Ollama（如果可用）
try:
    from langchain_community.embeddings import OllamaEmbeddings
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("⚠️ langchain-community 未安装，Ollama支持将不可用")
    print("   安装: pip install langchain-community")

# 加载环境变量
load_dotenv()
console = Console()


class UniversalEmbeddingClient:
    """
    统一嵌入客户端
    支持OpenAI、DeepSeek、智谱GLM的嵌入API，以及本地Ollama
    """

    # 模型配置
    MODELS = {
        'openai': {
            'model': 'text-embedding-3-small',
            'dimensions': 1536,
            'max_batch_size': 100,
            'type': 'api'  # 标记类型
        },
        'openai-large': {
            'model': 'text-embedding-3-large',
            'dimensions': 3072,
            'max_batch_size': 100,
            'type': 'api'
        },
        'deepseek': {
            'model': 'deepseek-embedding',
            'dimensions': 1536,
            'max_batch_size': 100,
            'type': 'api'
        },
        'glm': {
            'model': 'embedding-2',
            'dimensions': 1024,
            'max_batch_size': 100,
            'type': 'api'
        },
        # ===== 新增 Ollama 支持 =====
        'ollama': {
            'model': os.getenv('OLLAMA_EMBEDDING_MODEL', 'qwen3-embedding'),
            'dimensions': 1024,  # 实际维度由模型决定，这里给默认值
            'max_batch_size': 50,  # Ollama 批处理能力有限
            'type': 'local'
        },
        'ollama-nomic': {
            'model': 'nomic-embed-text',
            'dimensions': 768,
            'max_batch_size': 50,
            'type': 'local'
        },
        'ollama-qwen': {
            'model': 'qwen3-embedding',
            'dimensions': 1024,
            'max_batch_size': 50,
            'type': 'local'
        }
    }

    def __init__(self, provider: str = 'ollama'):
        """
        初始化嵌入客户端

        Args:
            provider: API提供商 (openai/openai-large/deepseek/glm/ollama)
        """
        self.provider = provider

        if provider not in self.MODELS:
            raise ValueError(
                f"不支持的提供商: {provider}\n"
                f"支持的选项: {', '.join(self.MODELS.keys())}"
            )

        self.config = self.MODELS[provider]
        self.type = self.config.get('type', 'api')

        # 根据类型初始化客户端
        if self.type == 'local':
            self._initialize_ollama()
        else:
            self._initialize_api_client()

        console.print(f"[green]✓ 已初始化嵌入客户端: {provider}[/green]")
        console.print(f"  类型: {'本地Ollama' if self.type == 'local' else '云端API'}")
        console.print(f"  模型: {self.config['model']}")
        console.print(f"  向量维度: {self.config['dimensions']}")

    def _initialize_ollama(self):
        """初始化 Ollama 本地客户端"""
        if not OLLAMA_AVAILABLE:
            raise ImportError(
                "需要安装 langchain-community 来使用 Ollama\n"
                "运行: pip install langchain-community"
            )

        base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        model_name = self.config['model']

        try:
            self.ollama_client = OllamaEmbeddings(
                model=model_name,
                base_url=base_url
            )

            # 尝试获取实际维度
            try:
                test_vector = self.ollama_client.embed_query("test")
                self.config['dimensions'] = len(test_vector)
                console.print(f"[dim]  实际向量维度: {len(test_vector)}[/dim]")
            except:
                pass  # 使用默认维度

        except Exception as e:
            raise ConnectionError(
                f"无法连接到 Ollama 服务: {str(e)}\n"
                f"请确保 Ollama 正在运行 (ollama serve)\n"
                f"并已下载模型: ollama pull {model_name}"
            )

    def _initialize_api_client(self) -> OpenAI:
        """初始化云端API客户端"""
        if self.provider.startswith('openai'):
            api_key = os.getenv('OPENAI_API_KEY')
            base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')

            if not api_key:
                raise ValueError("未配置OPENAI_API_KEY，请检查.env文件")

            self.client = OpenAI(api_key=api_key, base_url=base_url)

        elif self.provider == 'deepseek':
            api_key = os.getenv('DEEPSEEK_API_KEY')
            base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')

            if not api_key:
                raise ValueError("未配置DEEPSEEK_API_KEY，请检查.env文件")

            self.client = OpenAI(api_key=api_key, base_url=base_url)

        elif self.provider == 'glm':
            api_key = os.getenv('GLM_API_KEY')
            base_url = os.getenv('GLM_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4')

            if not api_key:
                raise ValueError("未配置GLM_API_KEY，请检查.env文件")

            self.client = OpenAI(api_key=api_key, base_url=base_url)

    def embed_text(self, text: str) -> List[float]:
        """
        对单个文本进行向量化

        Args:
            text: 待向量化的文本

        Returns:
            向量列表（浮点数）
        """
        if not text.strip():
            raise ValueError("输入文本不能为空")

        # 本地 Ollama
        if self.type == 'local':
            try:
                return self.ollama_client.embed_query(text)
            except Exception as e:
                console.print(f"[red]✗ 向量化失败: {str(e)}[/red]")
                raise

        # 云端 API
        try:
            response = self.client.embeddings.create(
                model=self.config['model'],
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            console.print(f"[red]✗ 向量化失败: {str(e)}[/red]")
            raise

    def embed_texts_batch(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        show_progress: bool = True,
        max_retries: int = 3
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

        # 过滤空文本
        texts = [t.strip() for t in texts if t.strip()]

        if not texts:
            console.print("[yellow]⚠ 所有文本为空，跳过向量化[/yellow]")
            return []

        # 设置批处理大小
        if batch_size is None:
            batch_size = self.config['max_batch_size']

        total_batches = (len(texts) + batch_size - 1) // batch_size
        all_embeddings = []

        # 显示开始信息
        console.print(f"\n[cyan]开始批量向量化...[/cyan]")
        console.print(f"  总文本数: {len(texts)}")
        console.print(f"  批次大小: {batch_size}")
        console.print(f"  总批次数: {total_batches}")
        console.print(f"  模式: {'本地' if self.type == 'local' else '云端'}\n")

        # 创建进度条
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:

            task = progress.add_task(
                "[cyan]向量化进度...",
                total=len(texts),
                visible=show_progress
            )

            # 分批处理
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_num = i // batch_size + 1

                # 本地 Ollama 处理
                if self.type == 'local':
                    try:
                        batch_embeddings = []
                        for text in batch_texts:
                            embedding = self.ollama_client.embed_query(text)
                            batch_embeddings.append(embedding)

                        all_embeddings.extend(batch_embeddings)
                        progress.update(task, advance=len(batch_texts))

                    except Exception as e:
                        console.print(f"[red]✗ 批次 {batch_num} 失败: {str(e)}[/red]")
                        raise

                else:
                    # 云端 API 处理（带重试）
                    for attempt in range(max_retries):
                        try:
                            response = self.client.embeddings.create(
                                model=self.config['model'],
                                input=batch_texts
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
                                wait_time = 2 ** attempt  # 指数退避
                                console.print(
                                    f"[yellow]批次 {batch_num} 失败，{wait_time}秒后重试... "
                                    f"({attempt + 1}/{max_retries})[/yellow]"
                                )
                                time.sleep(wait_time)
                            else:
                                console.print(
                                    f"[red]✗ 批次 {batch_num} 失败，已达最大重试次数[/red]"
                                )
                                raise

                # 限流保护
                if i + batch_size < len(texts):
                    time.sleep(0.1 if self.type == 'api' else 0.05)

        console.print(f"\n[green]✓ 批量向量化完成！总共 {len(all_embeddings)} 个向量[/green]")

        return all_embeddings

    def get_embedding_dimension(self) -> int:
        """获取当前模型的向量维度"""
        return self.config['dimensions']

    def test_embedding(self):
        """
        测试嵌入功能
        """
        console.print(Panel.fit(
            f"[bold cyan]测试 {self.provider} 嵌入模型[/bold cyan]",
            border_style="cyan"
        ))

        test_texts = [
            "人工智能是计算机科学的一个分支",
            "机器学习是AI的核心技术",
            "今天天气真好",
        ]

        console.print("\n[bold]测试文本:[/bold]")
        for i, text in enumerate(test_texts, 1):
            console.print(f"  {i}. {text}")

        console.print("\n[cyan]正在向量化...[/cyan]")

        # 批量向量化
        embeddings = self.embed_texts_batch(test_texts, show_progress=True)

        # 分析结果
        console.print("\n[bold]向量信息:[/bold]")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("文本", width=30)
        table.add_column("向量维度", width=10)
        table.add_column("前5个值", width=40)

        for text, embedding in zip(test_texts, embeddings):
            preview = ', '.join([f"{v:.4f}" for v in embedding[:5]])
            table.add_row(
                text[:25] + "..." if len(text) > 25 else text,
                str(len(embedding)),
                preview
            )

        console.print(table)

        # 计算相似度
        console.print("\n[bold]语义相似度分析:[/bold]")
        sim_1_2 = self._cosine_similarity(embeddings[0], embeddings[1])
        sim_1_3 = self._cosine_similarity(embeddings[0], embeddings[2])

        console.print(f"  「AI」 vs 「机器学习」: {sim_1_2:.4f} (应该较高)")
        console.print(f"  「AI」 vs 「天气」:     {sim_1_3:.4f} (应该较低)")

        if sim_1_2 > sim_1_3:
            console.print("\n[green]✓ 嵌入模型工作正常！语义相似的文本向量距离更近。[/green]")
        else:
            console.print("\n[yellow]⚠ 结果异常，请检查API配置[/yellow]")

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
    console.print(Panel.fit(
        "[bold cyan]对比不同API提供商的嵌入模型[/bold cyan]",
        border_style="cyan"
    ))

    test_text = "检索增强生成技术结合了信息检索和文本生成"

    console.print(f"\n[bold]测试文本:[/bold] {test_text}\n")

    # 检测可用的提供商
    available_providers = []

    providers_to_test = ['ollama', 'openai', 'deepseek', 'glm']

    for provider in providers_to_test:
        try:
            client = UniversalEmbeddingClient(provider)
            available_providers.append((provider, client))
            console.print(f"[green]✓ {provider} 可用[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ {provider} 不可用: {str(e)[:50]}[/yellow]")

    if not available_providers:
        console.print("\n[red]✗ 没有可用的提供商，请检查配置[/red]")
        return

    console.print("\n" + "="*60)

    # 对比测试
    results = []

    for provider, client in available_providers:
        console.print(f"\n[bold cyan]测试 {provider}...[/bold cyan]")

        start_time = time.time()
        try:
            embedding = client.embed_text(test_text)
            elapsed_time = time.time() - start_time

            results.append({
                'provider': provider,
                'type': '本地' if client.type == 'local' else '云端',
                'dimensions': len(embedding),
                'time': elapsed_time,
                'preview': embedding[:5]
            })
        except Exception as e:
            console.print(f"[red]✗ 测试失败: {str(e)}[/red]")

    # 展示对比表格
    console.print("\n" + "="*60)
    console.print("\n[bold]性能对比:[/bold]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("提供商", width=15)
    table.add_column("类型", width=10)
    table.add_column("向量维度", width=10)
    table.add_column("耗时(秒)", width=10)
    table.add_column("向量预览(前5值)", width=40)

    for result in results:
        preview = ', '.join([f"{v:.3f}" for v in result['preview']])
        table.add_row(
            result['provider'],
            result['type'],
            str(result['dimensions']),
            f"{result['time']:.3f}",
            preview
        )

    console.print(table)


if __name__ == "__main__":
    console.print("\n[bold cyan]RAG系统 - 向量化与嵌入模块测试[/bold cyan]\n")

    console.print("选择测试模式:")
    console.print("1. 测试单个API提供商")
    console.print("2. 对比所有可用提供商")

    choice = input("\n请输入选项 (1/2): ").strip()

    if choice == "1":
        console.print("\n选择提供商:")
        console.print("1. Ollama (本地免费 - 推荐)")
        console.print("2. OpenAI (云端)")
        console.print("3. DeepSeek (云端)")
        console.print("4. 智谱GLM (云端)")

        provider_choice = input("\n请输入选项 (1/2/3/4): ").strip()

        provider_map = {
            '1': 'ollama',
            '2': 'openai',
            '3': 'deepseek',
            '4': 'glm'
        }

        provider = provider_map.get(provider_choice, 'ollama')

        try:
            client = UniversalEmbeddingClient(provider)
            client.test_embedding()
        except Exception as e:
            console.print(f"\n[red]✗ 测试失败: {str(e)}[/red]")
            if provider == 'ollama':
                console.print("[yellow]提示: 请确保 Ollama 正在运行并已下载模型[/yellow]")
                console.print("  1. 启动: ollama serve")
                console.print("  2. 下载模型: ollama pull qwen3-embedding")
            else:
                console.print("[yellow]请检查.env文件中的API配置[/yellow]")

    else:
        demo_compare_providers()