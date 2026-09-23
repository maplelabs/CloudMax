#!/usr/bin/env python3
"""Entry point for running the MCP server."""
import sys
import os

# Add parent directory to path so we can import src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import main

if __name__ == "__main__":
    main()

