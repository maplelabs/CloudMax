import os

from langfuse import Langfuse


def setup_langfuse():
    """
    Setup Langfuse for tracing
    """
    Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"]
    )
