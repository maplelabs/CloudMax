"""
DeepEval LLM wrapper for integrating with our existing LangGraph LLM utilities.
This wrapper allows DeepEval metrics to use the same LLM configuration as the triage system.
"""
import asyncio
import os
from typing import Union

from deepeval.models import DeepEvalBaseLLM
from langchain_aws import ChatBedrockConverse
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.server.utilities.rate_limiter import TokenRateLimiter
from ...server.utilities.llm_manager import get_secondary_llm_async
from ...server.utilities.llm_metrics_tracker import LLMMetricsTracker


class LangGraphLLMWrapper(DeepEvalBaseLLM):

    def __init__(self, *args, **kwargs):
        self.model: Union[ChatOpenAI, ChatBedrockConverse] = None
        self.usage_callback = UsageMetadataCallbackHandler()
        self.llm_metrics_tracker = LLMMetricsTracker()
        self.token_rate_limiter = TokenRateLimiter(usage_callback=self.usage_callback)
        self.callbacks = [self.usage_callback, self.llm_metrics_tracker]

    async def _initialize_model(self):
        """Initialize the model asynchronously using secondary LLM for evaluation"""
        if self.model is None:
            self.model = await get_secondary_llm_async()

    def load_model(self) -> Union[ChatOpenAI, ChatBedrockConverse]:
        if self.model is None:
            raise ValueError("Model not initialized. Call _initialize_model() first.")
        return self.model

    def generate(self, prompt: str) -> str:
        """
        Synchronous generate method.
        Note: This should not be called from within an async context.
        Use a_generate() instead when in async context.
        """
        # Check if we're in an async context
        try:
            asyncio.get_running_loop()
            # We're in an async context - we need to run the async code in the existing loop
            if self.model is None:
                # Create a task in the existing event loop and wait for it
                import nest_asyncio
                nest_asyncio.apply()
                asyncio.run(self._initialize_model())
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            asyncio.run(self._initialize_model())

        model = self.load_model()

        if os.getenv("ENABLE_TOKEN_RATE_LIMITING", "true").lower() == "true":
            if self.token_rate_limiter not in self.callbacks:
                self.callbacks.append(self.token_rate_limiter)

        config: RunnableConfig = {
            "callbacks": self.callbacks
        }

        response = model.invoke(
            input=prompt,
            config=config
        )

        return response.content

    async def a_generate(self, prompt: str) -> str:

        await self._initialize_model()

        model = self.load_model()

        if os.getenv("ENABLE_TOKEN_RATE_LIMITING", "true").lower() == "true":
            if self.token_rate_limiter not in self.callbacks:
                self.callbacks.append(self.token_rate_limiter)

        config: RunnableConfig = {
            "callbacks": self.callbacks
        }

        response = await model.ainvoke(
            input=prompt,
            config=config
        )

        return response.content

    def get_model_name(self):

        model = self.load_model()

        if isinstance(model, ChatOpenAI):
            return f"Azure-OpenAI"
        elif isinstance(model, ChatBedrockConverse):
            return f"AWS-Bedrock"
        else:
            return f"Custom"
