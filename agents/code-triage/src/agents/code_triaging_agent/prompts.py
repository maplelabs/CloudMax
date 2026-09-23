"""Prompts for Orchestrator - LLM-based routing decisions"""

ORCHESTRATOR_SYSTEM_PROMPT = """You are an expert Orchestrator Agent that coordinates the code triaging workflow.

Your role is to make intelligent routing decisions based on the current state of the analysis:
1. Decide if code retrieval is necessary
2. Evaluate if retrieved code is sufficient
3. Determine if analysis needs to be retried or refined

Always return valid JSON matching the requested schema.
Be decisive but conservative - when in doubt, gather more information."""


# Decision 1: Should we retrieve code?
SHOULD_RETRIEVE_CODE_PROMPT = """Based on the error analysis, decide if we need to retrieve code from the repository.

Error Analysis:
- Error Type: {error_type}
- Language: {language}
- Severity: {severity}
- Needs Code Flag: {needs_code}
- File Hints: {file_hints}
- Search Strategy: {search_strategy}

Decision Criteria:
- Some errors are self-explanatory (e.g., "ModuleNotFoundError: No module named 'requests'" → just needs pip install)
- Some errors require code context (e.g., "AttributeError: 'NoneType' object has no attribute 'get'" → need to see the code)
- If file_hints are available and valid, retrieval is likely useful
- If needs_code is False, we can skip retrieval

Provide your decision in JSON format:
{{
  "should_retrieve": true/false,
  "reasoning": "brief explanation of your decision"
}}

Return ONLY valid JSON."""


# Decision 2: Evaluate retrieval success
EVALUATE_RETRIEVAL_PROMPT = """Evaluate if the code retrieval was successful and decide next action.

Retrieval Results:
- Snippets Retrieved: {snippet_count}
- Total Code Length: {code_length} characters
- File Hints Attempted: {file_hints_attempted}
- Search Strategy Used: {search_strategy_used}
- Repository: {repository}

Original Error Context:
- Error Type: {error_type}
- Severity: {severity}

Decision Options:
1. "proceed" - We have enough code context to analyze
2. "retry_search" - Try different search queries (if we used search)
3. "retry_files" - Try alternative file paths (if we used file hints)
4. "proceed_without_code" - Analysis can proceed without code (better than failing)

Provide your decision in JSON format:
{{
  "action": "proceed" | "retry_search" | "retry_files" | "proceed_without_code",
  "reasoning": "brief explanation",
  "retry_strategy": "optional: specific guidance for retry (if action is retry_*)"
}}

Return ONLY valid JSON."""


# Decision 3: Should we refine analysis?
SHOULD_REFINE_ANALYSIS_PROMPT = """Evaluate the analysis results and decide if we should refine or accept them.

Analysis Results:
- Root Cause: {root_cause}
- Confidence: {confidence}
- Severity: {severity}
- Recommendations Count: {recommendations_count}
- Analyzer needs more code: {analysis_needs_more_code}
- Analyzer additional file hints: {analysis_additional_file_hints}

Quality Criteria:
- Confidence >= 0.75: Good - accept immediately (this overrides needs_more_code flag)
- Confidence >= 0.7: Generally acceptable
- Confidence < 0.5: Consider refining
- Root cause should be specific, not generic
- Recommendations should be actionable

IMPORTANT: High confidence (>= 0.75) indicates a solid diagnosis even if the analyzer
suggests more code could help. In such cases, accept the analysis rather than
fetching more code unnecessarily.

Decision Options:
1. "accept" - Analysis is good enough, generate final report
2. "refine_with_more_context" - Need more code context (only if confidence < 0.75)
3. "refine_analysis" - Re-analyze with different approach
4. "accept_low_confidence" - Accept despite low confidence (no better option)

Provide your decision in JSON format:
{{
  "action": "accept" | "refine_with_more_context" | "refine_analysis" | "accept_low_confidence",
  "reasoning": "brief explanation"
}}

Return ONLY valid JSON."""

