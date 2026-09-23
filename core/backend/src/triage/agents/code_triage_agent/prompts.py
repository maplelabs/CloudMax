"""
Prompts for Code Triage Agent
"""

REPOSITORY_EXTRACTION_PROMPT = """
You are a repository information extractor. Your task is to extract GitHub repository information from the conversation history.

The repository information may appear in various formats:
1. Metadata format: "repository: myorg/payment-service"
2. Content format: "This service is deployed from repository: myorg/payment-service"
3. URL format: "https://github.com/myorg/payment-service"
4. Inline format: "The myorg/payment-service repository contains..."

Extract the repository in the format: owner/repository

Conversation History:
{conversation}

Return ONLY the repository in the format "owner/repository" or "NOT_FOUND" if no repository is mentioned.

Repository:
"""

CODE_ANALYSIS_REJECTION_TEMPLATE = """ **CODE TRIAGE AGENT: ANALYSIS REJECTED - NOT A CODE ISSUE**

**Rejection Reason**: {reason}

**IMPORTANT - DO NOT PERFORM CODE-LEVEL ANALYSIS**:
This alert describes an OPERATIONAL/INFRASTRUCTURE issue, NOT an application code defect. \
The alert contains operational metrics (memory usage, container restarts, resource limits, \
service availability) rather than code-level errors (exceptions, stack traces, file:line references).

**What Code Triage Agent Requires**:
- Exception with stack trace (e.g., 'ImportError at file.py:42')
- Runtime errors with file paths and line numbers
- Application crashes with traceback
- Syntax errors, type errors with code references

**This Alert Has**:
- Memory/CPU metrics
- Container/resource events
- Service availability issues
- Infrastructure operational data

**STOP - Do Not Speculate About Code Issues**:
Do NOT attempt to infer or speculate about potential code-level causes (memory leaks, \
connection pooling, request queuing) without actual code inspection. Such speculation \
is not supported by code evidence and should not be included in your analysis.

**Correct Investigation Path**:
1. This is an OPERATIONAL incident - focus on infrastructure and runtime metrics
2. Use **Observability Agents** to gather metrics, logs, and runtime data
3. Use **Diagnostic Tests Agent** for real-time infrastructure validation
4. Consult **runbooks** for operational remediation procedures
5. Base your root cause analysis on observable operational data, not code speculation

**Your Next Action**: Proceed with operational investigation using the appropriate agents and tools listed above. \
Do not generate code-level root cause hypotheses."""
