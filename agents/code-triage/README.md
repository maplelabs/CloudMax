# Code Triage Agent

An intelligent AI agent that automatically triages code errors by analyzing error messages, retrieving relevant code from GitHub, and providing root cause analysis with actionable recommendations.

---

## Overview

The Code Triage Agent is an autonomous LangGraph-based workflow that helps developers quickly understand and fix code errors. Given an error message and a GitHub repository, it:

- **Parses** error messages and stack traces to extract metadata (error type, language, severity, file hints)
- **Validates** repository accessibility and format
- **Retrieves** relevant code from GitHub using the Model Context Protocol (MCP)
- **Analyzes** the code to identify root causes with confidence scoring
- **Suggests** actionable fixes and recommendations
- **Tracks** token usage across all LLM calls for cost monitoring

### Key Capabilities

- ✅ Multi-language support (Python, Go, JavaScript, etc.)
- ✅ Intelligent iterative code retrieval and analysis
- ✅ Repository validation before processing
- ✅ Comprehensive token usage tracking
- ✅ Confidence-based analysis with refinement loops
- ✅ A2A protocol for agent-to-agent communication
- ✅ Structured JSON responses with detailed diagnostics

---

## Architecture

### High-Level Workflow

```
START
  ↓
parse_error (Error Parser + Repository Validation)
  ↓
decide_retrieval (LLM routing decision)
  ↓
retrieve_code (GitHub MCP) ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
  ↓                                              │
evaluate_retrieval (LLM routing decision)        │
  ↓                                              │
analyze_code (Code Analyzer)                     │
  ↓                                              │
evaluate_analysis (LLM routing decision) ─ ─ ─ ─ ┘
  ↓                                    (iterative refinement)
generate_report (with token usage)
  ↓
END
```

### Core Components

#### 1. **Error Parser Subagent** (`src/agents/error_parser_agent/`)
- Extracts error type, language, severity, and file hints from error messages
- Validates repository format and GitHub accessibility
- Uses structured Pydantic output for consistency

#### 2. **Code Retrieval Planner Subagent** (`src/agents/code_retrieval_agent/`)
- Plans retrieval strategy (file paths, search queries)
- Guides the orchestrator on what code to fetch from GitHub
- Supports both file-based and search-based retrieval

#### 3. **Code Analyzer Subagent** (`src/agents/code_analyzer_agent/`)
- Analyzes retrieved code to identify root cause
- Provides actionable recommendations with confidence scores
- Can request additional code context if needed (`needs_more_code`, `additional_file_hints`)

#### 4. **Orchestrator** (`src/agents/code_triaging_agent/`)
- LangGraph workflow with LLM-based routing decisions
- Coordinates all subagents and manages state transitions
- Implements iterative refinement loops for better analysis
- Tracks token usage across all components

#### 5. **GitHub MCP Integration** (`src/mcp_tools.py`)
- Fetches file contents from GitHub repositories
- Validates repository accessibility via GitHub API
- Uses Model Context Protocol for standardized tool invocation

#### 6. **Token Tracking** (`src/agents/middlewares/token_counter.py`)
- Tracks token usage per agent (error_parser, code_retrieval, code_analyzer, orchestrator)
- Provides detailed breakdown of prompt vs completion tokens
- Aggregates totals for cost monitoring

#### 7. **A2A Server** (`src/a2a_app.py`)
- FastAPI-based HTTP server implementing A2A protocol
- Exposes `/a2a/tasks` endpoint for agent communication
- Handles request/response serialization

---

## Prerequisites

### Required Services
- **AWS Account** with Bedrock access (Claude models)
- **GitHub Personal Access Token** with repo read permissions
- **Docker** and Docker Compose

### Environment Variables

Create a `.env` file or set these in your environment:

```bash
# GitHub Configuration
GITHUB_TOKEN=ghp_your_github_token_here
GITHUB_MCP_URL=https://api.githubcopilot.com/mcp/x/repos/readonly

# AWS Bedrock Configuration
BEDROCK_API_KEY=your_bedrock_api_key_here
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0

# Server Configuration
ORCHESTRATOR_PORT=8002
LOG_LEVEL=INFO
```

---

## Setup & Running

### Using Docker Compose

1. **Clone the repository**
   ```bash
   cd ai-sre-ops/agents/code-triage
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Start the agent**
   ```bash
   docker-compose up --build
   ```

4. **Verify it's running**
   ```bash
   curl http://localhost:8002/health
   ```

The agent will be available at `http://localhost:8002/a2a/tasks`.

---

## API Usage

### Request Format

Send a POST request to `/a2a/tasks` with the A2A protocol format:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "messageId": "msg-1",
      "parts": [
        {
          "kind": "data",
          "data": {
            "error": "Traceback (most recent call last):\n  File \"main.py\", line 1, in <module>\n    from service import AlertCorrelator\nImportError: cannot import name AlertCorrelator from service",
            "repository": "owner/repo"
          }
        }
      ]
    }
  }
}
```

### Example cURL Command

```bash
curl -X POST http://localhost:8002/a2a/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "messageId": "msg-1",
        "parts": [
          {
            "kind": "data",
            "data": {
              "error": "Traceback (most recent call last):\n  File \"python-import-error/main.py\", line 1, in <module>\n    from service import AlertCorrelator\nImportError: cannot import name AlertCorrelator from service",
              "repository": "jathin-s-ML/test-code-triager"
            }
          }
        ]
      }
    }
  }'
```

---

## Response Schema

### Successful Response

```json
{
  "id": 1,
  "jsonrpc": "2.0",
  "result": {
    "artifacts": [
      {
        "artifactId": "triage-result",
        "description": "Code triage report",
        "name": "triage_result",
        "parts": [
          {
            "kind": "data",
            "data": {
              "status": "success",
              "error_summary": {
                "error_type": "ImportError",
                "language": "python",
                "severity": "high",
                "file_hints": ["python-import-error/main.py", "service.py"]
              },
              "root_cause": "The AlertCorrelator class is not defined or exported in the service.py module...",
              "responsible_code": {
                "file_path": "python-import-error/main.py",
                "content": "from service import AlertCorrelator\n...",
                "language": "python"
              },
              "suggested_fix": [
                "Verify that AlertCorrelator class is defined in service.py",
                "Check if AlertCorrelator is defined with the correct class name (case-sensitive)",
                "Ensure AlertCorrelator is not inside a conditional block...",
                "..."
              ],
              "confidence": 0.75,
              "error_message": "ImportError: cannot import name AlertCorrelator from service",
              "workflow_stats": {
                "retrieval_attempts": 2,
                "analysis_attempts": 2
              },
              "token_usage": {
                "by_agent": {
                  "error_parser": {
                    "prompt_tokens": 1536,
                    "completion_tokens": 228,
                    "total_tokens": 1764,
                    "call_count": 1
                  },
                  "code_retrieval": {
                    "prompt_tokens": 2294,
                    "completion_tokens": 502,
                    "total_tokens": 2796,
                    "call_count": 2
                  },
                  "code_analyzer": {
                    "prompt_tokens": 3040,
                    "completion_tokens": 889,
                    "total_tokens": 3929,
                    "call_count": 2
                  },
                  "orchestrator_routing": {
                    "prompt_tokens": 1288,
                    "completion_tokens": 383,
                    "total_tokens": 1671,
                    "call_count": 3
                  }
                },
                "total": {
                  "prompt_tokens": 8158,
                  "completion_tokens": 2002,
                  "total_tokens": 10160,
                  "call_count": 8
                }
              }
            }
          }
        ]
      }
    ],
    "contextId": "...",
    "history": [],
    "id": "...",
    "kind": "task",
    "status": {
      "state": "completed"
    }
  }
}
```

### Key Response Fields

| Field | Description |
|-------|-------------|
| `status` | `"success"` or `"error"` |
| `error_summary` | Parsed error metadata (type, language, severity, file hints) |
| `root_cause` | Detailed explanation of what caused the error |
| `responsible_code` | The code snippet most relevant to the error |
| `suggested_fix` | List of actionable recommendations to fix the issue |
| `confidence` | Confidence score (0.0 - 1.0) indicating analysis certainty |
| `workflow_stats` | Number of retrieval and analysis attempts |
| `token_usage.by_agent` | Token breakdown per agent (error_parser, code_retrieval, code_analyzer, orchestrator_routing) |
| `token_usage.total` | Aggregated token usage across all LLM calls |

### Error Response

If repository validation fails or an error occurs:

```json
{
  "id": 1,
  "jsonrpc": "2.0",
  "result": {
    "artifacts": [
      {
        "parts": [
          {
            "data": {
              "status": "error",
              "error_summary": {
                "error_type": "RepositoryValidationError",
                "error_message": "Repository owner/invalid-repo not found or not accessible with provided token"
              }
            }
          }
        ]
      }
    ]
  }
}
```

---

## Example Terminal Output

Here's what you'll see when the agent processes a triage request:

```
code-triage-agent  | 2026-03-12 09:52:34,975 - src.bedrock_client - INFO - Initialized ChatBedrock: us.anthropic.claude-haiku-4-5-20251001-v1:0 (temp=0.1, max_tokens=2000)
code-triage-agent  | 2026-03-12 09:52:39,037 - src.bedrock_client - INFO - Initialized ChatBedrock: us.anthropic.claude-haiku-4-5-20251001-v1:0 (temp=0.1, max_tokens=500)
code-triage-agent  | 2026-03-12 09:52:43,058 - src.bedrock_client - INFO - Initialized ChatBedrock: us.anthropic.claude-haiku-4-5-20251001-v1:0 (temp=0.1, max_tokens=2000)
code-triage-agent  | 2026-03-12 09:52:47,079 - src.bedrock_client - INFO - Initialized ChatBedrock: us.anthropic.claude-haiku-4-5-20251001-v1:0 (temp=0.1, max_tokens=500)
code-triage-agent  | 2026-03-12 09:52:47,089 - src.agents.code_triaging_agent.agent - INFO - Initialized CodeTriagingAgent with LLM-based routing
code-triage-agent  | 2026-03-12 09:52:47,092 - src.a2a_app - INFO - Initialized A2A FastAPI application for code-triage-agent on /a2a/tasks
code-triage-agent  | INFO:     Started server process [1]
code-triage-agent  | INFO:     Waiting for application startup.
code-triage-agent  | INFO:     Application startup complete.
code-triage-agent  | INFO:     Uvicorn running on http://0.0.0.0:8002 (Press CTRL+C to quit)
code-triage-agent  | 2026-03-12 09:52:58,250 - src.agents.code_triaging_agent.a2a_executor - INFO - Executing triage via A2A executor for repo=jathin-s-ML/test-code-triager, task_id=a5c579ef-8fb9-4fa3-9fa9-efb4ac7915b4
code-triage-agent  | 2026-03-12 09:52:58,250 - src.agents.code_triaging_agent.agent - INFO - Starting intelligent triage for jathin-s-ML/test-code-triager
code-triage-agent  | 2026-03-12 09:52:58,254 - src.agents.code_triaging_agent.agent - INFO - Error Parser: Parsing error via subagent...
code-triage-agent  | 2026-03-12 09:53:00,976 - src.mcp_tools - INFO - Repository validation successful: jathin-s-ML/test-code-triager
code-triage-agent  | 2026-03-12 09:53:08,112 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] error_parser: prompt=1536, completion=228, total=1764 | Cumulative: 1764 tokens across 1 calls
code-triage-agent  | 2026-03-12 09:53:08,114 - src.agents.code_triaging_agent.agent - INFO - Parsed error type: ImportError
code-triage-agent  | 2026-03-12 09:53:08,114 - src.agents.code_triaging_agent.agent - INFO - Parsed language=python, severity=high, needs_code=True
code-triage-agent  | 2026-03-12 09:53:08,114 - src.agents.code_triaging_agent.agent - INFO - Using file hints from LLM: ['python-import-error/main.py', 'service.py']
code-triage-agent  | 2026-03-12 09:53:08,115 - src.agents.code_triaging_agent.agent - INFO - LLM Decision: Should we retrieve code?
code-triage-agent  | 2026-03-12 09:53:13,640 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] orchestrator_routing: prompt=385, completion=126, total=511 | Cumulative: 511 tokens across 1 calls
code-triage-agent  | 2026-03-12 09:53:13,640 - src.agents.code_triaging_agent.agent - INFO - Decision: True - ImportError with needs_code flag set to True and specific file hints provided...
code-triage-agent  | 2026-03-12 09:53:13,642 - src.agents.code_triaging_agent.agent - INFO - Code Retrieval: Fetching code (attempt=1) for repo=jathin-s-ML/test-code-triager
code-triage-agent  | 2026-03-12 09:53:13,642 - src.mcp_tools - INFO - Initialized MultiServerMCPClient for GitHub MCP server: https://api.githubcopilot.com/mcp/x/repos/readonly
code-triage-agent  | 2026-03-12 09:53:19,612 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] code_retrieval: prompt=1147, completion=250, total=1397 | Cumulative: 1397 tokens across 1 calls
code-triage-agent  | 2026-03-12 09:53:19,612 - src.agents.code_triaging_agent.agent - INFO - Retrieval plan: strategy=both, file_hints=['python-import-error/main.py', 'service.py'], queries=[...]
code-triage-agent  | 2026-03-12 09:53:19,612 - src.agents.code_triaging_agent.agent - INFO - Fetching 2 file hints
code-triage-agent  | 2026-03-12 09:53:40,011 - src.mcp_tools - INFO - Loaded GitHub MCP tool: get_file_contents=get_file_contents
code-triage-agent  | 2026-03-12 09:54:06,405 - src.agents.code_triaging_agent.agent - INFO - Fetched python-import-error/main.py
code-triage-agent  | 2026-03-12 09:54:31,466 - src.agents.code_triaging_agent.agent - INFO - Fetched service.py
code-triage-agent  | 2026-03-12 09:54:31,466 - src.agents.code_triaging_agent.agent - INFO - Retrieved 2 code snippets (277 chars)
code-triage-agent  | 2026-03-12 09:54:31,467 - src.agents.code_triaging_agent.agent - INFO - LLM Evaluation: Was code retrieval successful?
code-triage-agent  | 2026-03-12 09:54:31,467 - src.agents.code_triaging_agent.agent - INFO - All hinted files were retrieved (2 snippets); skipping LLM retrieval evaluation and proceeding.
code-triage-agent  | 2026-03-12 09:54:31,469 - src.agents.code_triaging_agent.agent - INFO - Code Analyzer: Analyzing code via subagent...
code-triage-agent  | 2026-03-12 09:54:40,265 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] code_analyzer: prompt=1503, completion=443, total=1946 | Cumulative: 1946 tokens across 1 calls
code-triage-agent  | 2026-03-12 09:54:40,265 - src.agents.code_triaging_agent.agent - INFO - Analysis confidence: 0.75, root_cause_preview=The AlertCorrelator class is not defined or exported in the service module...
code-triage-agent  | 2026-03-12 09:54:40,266 - src.agents.code_triaging_agent.agent - INFO - LLM Evaluation: Is analysis good enough?
code-triage-agent  | 2026-03-12 09:54:44,331 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] orchestrator_routing: prompt=450, completion=123, total=573 | Cumulative: 1084 tokens across 2 calls
code-triage-agent  | 2026-03-12 09:54:44,332 - src.agents.code_triaging_agent.agent - INFO - Analysis evaluation: refine_with_more_context - The analyzer explicitly indicates it needs more code...
code-triage-agent  | 2026-03-12 09:54:44,333 - src.agents.code_triaging_agent.agent - INFO - Code Retrieval: Fetching code (attempt=2) for repo=jathin-s-ML/test-code-triager
code-triage-agent  | 2026-03-12 09:54:48,784 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] code_retrieval: prompt=1147, completion=252, total=1399 | Cumulative: 2796 tokens across 2 calls
code-triage-agent  | 2026-03-12 09:54:48,785 - src.agents.code_triaging_agent.agent - INFO - Retrieval plan: strategy=both, file_hints=['python-import-error/main.py', 'service.py'], queries=[...]
code-triage-agent  | 2026-03-12 09:54:48,785 - src.agents.code_triaging_agent.agent - INFO - Fetching 3 file hints
code-triage-agent  | 2026-03-12 09:55:14,041 - src.agents.code_triaging_agent.agent - INFO - Fetched python-import-error/main.py
code-triage-agent  | 2026-03-12 09:55:39,096 - src.agents.code_triaging_agent.agent - INFO - Fetched service.py
code-triage-agent  | 2026-03-12 09:56:06,246 - src.agents.code_triaging_agent.agent - INFO - Fetched python-import-error/service.py
code-triage-agent  | 2026-03-12 09:56:06,246 - src.agents.code_triaging_agent.agent - INFO - Retrieved 3 code snippets (360 chars)
code-triage-agent  | 2026-03-12 09:56:06,246 - src.agents.code_triaging_agent.agent - INFO - LLM Evaluation: Was code retrieval successful?
code-triage-agent  | 2026-03-12 09:56:06,247 - src.agents.code_triaging_agent.agent - INFO - All hinted files were retrieved (3 snippets); skipping LLM retrieval evaluation and proceeding.
code-triage-agent  | 2026-03-12 09:56:06,248 - src.agents.code_triaging_agent.agent - INFO - Code Analyzer: Analyzing code via subagent...
code-triage-agent  | 2026-03-12 09:56:12,001 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] code_analyzer: prompt=1537, completion=446, total=1983 | Cumulative: 3929 tokens across 2 calls
code-triage-agent  | 2026-03-12 09:56:12,002 - src.agents.code_triaging_agent.agent - INFO - Analysis confidence: 0.75, root_cause_preview=The ImportError occurs because the AlertCorrelator class is not defined or exported...
code-triage-agent  | 2026-03-12 09:56:12,003 - src.agents.code_triaging_agent.agent - INFO - LLM Evaluation: Is analysis good enough?
code-triage-agent  | 2026-03-12 09:56:16,337 - src.agents.middlewares.token_counter - INFO - [TOKEN_COUNT] orchestrator_routing: prompt=453, completion=134, total=587 | Cumulative: 1671 tokens across 3 calls
code-triage-agent  | 2026-03-12 09:56:16,338 - src.agents.code_triaging_agent.agent - INFO - Analysis evaluation: refine_with_more_context - The analyzer explicitly indicates it needs more code...
code-triage-agent  | 2026-03-12 09:56:16,338 - src.agents.code_triaging_agent.agent - WARNING - Max analysis attempts reached, accepting result
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - Generating final report...
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - Triage summary: repo=jathin-s-ML/test-code-triager, error_type=ImportError, severity=high, code_snippets=3, confidence=0.75
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - [TOKEN_SUMMARY] ========== Token Usage Summary ==========
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - [TOKEN_SUMMARY] code_analyzer: 3929 tokens (2 calls) - prompt=3040, completion=889
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - [TOKEN_SUMMARY] code_retrieval: 2796 tokens (2 calls) - prompt=2294, completion=502
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - [TOKEN_SUMMARY] error_parser: 1764 tokens (1 calls) - prompt=1536, completion=228
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - [TOKEN_SUMMARY] orchestrator_routing: 1671 tokens (3 calls) - prompt=1288, completion=383
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - [TOKEN_SUMMARY] GRAND TOTAL: 10160 tokens across 8 LLM calls (prompt=8158, completion=2002)
code-triage-agent  | 2026-03-12 09:56:16,340 - src.agents.code_triaging_agent.agent - INFO - [TOKEN_SUMMARY] ==========================================
code-triage-agent  | 2026-03-12 09:56:16,341 - src.agents.code_triaging_agent.agent - INFO - Intelligent triage completed successfully
code-triage-agent  | INFO:     172.20.0.1:43892 - "POST /a2a/tasks HTTP/1.1" 200 OK
```

### Key Log Highlights

- **Repository Validation**: `Repository validation successful: jathin-s-ML/test-code-triager`
- **Token Tracking**: Real-time token counts per agent (`[TOKEN_COUNT] error_parser: prompt=1536, completion=228, total=1764`)
- **Workflow Progress**: Clear step-by-step execution (Error Parser → Retrieval → Analysis → Evaluation)
- **Iterative Refinement**: Multiple retrieval/analysis attempts when needed (`attempt=1`, `attempt=2`)
- **Final Summary**: Comprehensive token breakdown by agent and grand total

---

## Technology Stack

- **LangGraph** - Workflow orchestration with state management
- **LangChain** - Agent framework and LLM abstractions
- **AWS Bedrock** - Claude Haiku 4.5 for LLM reasoning
- **GitHub MCP** - Model Context Protocol for code retrieval
- **A2A Protocol** - Agent-to-Agent communication standard
- **FastAPI** - HTTP server for A2A endpoint
- **Pydantic** - Structured output validation
- **Docker** - Containerization and deployment

---

