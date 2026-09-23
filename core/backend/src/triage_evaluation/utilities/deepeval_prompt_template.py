"""
Custom MCP evaluation templates for SRE-specific scoring.
Monkey patches DeepEval templates with domain-specific prompts.
"""
import logging
from typing import List

from deepeval.metrics.mcp.schema import Task
from deepeval.metrics.mcp.template import MCPTaskCompletionTemplate
from deepeval.test_case import MCPServer

logger = logging.getLogger(__name__)


def patch_mcp_templates():
    """Apply SRE-specific template patches to DeepEval."""

    def sre_args_correctness_score(task: Task, mcp_servers: List[MCPServer]):
        available_tools = [data.available_tools for data in mcp_servers]
        steps_taken = "\n".join(task.steps_taken)
        return f"""Evaluate whether the arguments (inputs) provided by the agent to the tools, resources, and prompts were correct and aligned with their respective input schemas. Your job is to determine if the agent supplied appropriate, complete, and well-formatted arguments for each invocation.

Output a JSON object with exactly two fields: 'score' and 'reason'.

Scoring:
- 'score' is a float between 0 and 1 inclusive.
- Treat argument correctness as outcome-oriented: if the final conclusion is correct and evidence-backed, assume arguments were sufficiently correct unless a schema violation directly caused an incorrect conclusion.
- Do not infer argument incorrectness from investigation ordering, sequencing, or diagnostic completeness.
- 'reason' must briefly justify the score (1-3 sentences), emphasizing what the agent did well and referencing any incorrect, missing, or misformatted arguments compared to the required schema.
- Completely ignore steps that used unknown/unavailable tools or returned empty results due to environment limits; they must not reduce the score nor be cited negatively in 'reason'.
- Do NOT penalize for any failed tool call, malformed query, unknown tool invocation, or empty tool result, as long as the agent ultimately reached a correct and well-supported conclusion.
- Unknown tool invocations that are promptly abandoned in favor of valid tools should not reduce the score.
-  Penalize only if Unknown tool invocations misleads the outcome; otherwise ignore the tool call entierly. 
- Treat empty-argument calls as valid when the schema is empty/permissive (e.g., delegate tools); do not penalize such usage.
- Do not penalize environment-driven empty results or unavailable datasources when arguments fit the schema.
- Prefer the final, corrected arguments over early attempts; minor malformed/missing fields later corrected should not reduce the score.
- Always prioritize the final, correct argument set that contributed to the successful outcome. Ignore any earlier failed or incomplete attempts, including attempts on unknown or unavailable tools.

CHAIN OF THOUGHT:
1. Review each step where a tool, resource, or prompt was called.
2. Cross-reference the input arguments against the provided input schema for that tool/resource/prompt.
3. Highlight correct, well-structured, and complete arguments.
4. Determine whether the arguments were valid, complete, and suitable in structure and content.
5. Note only major missing fields or clearly incorrect types that affect functionality.
6. Score based on the correctness and suitability of the arguments passed and overall correctness of the arguments.
7. Recognize any attempt to provide structured, relevant arguments as a positive contribution, even if the tool call failed or was ultimately unused.
8. Recognize delegation patterns as valid tool usage (empty schemas are often correct)
9. If the tool calls with empty arguments and results eventually led to a correct answer, do not penalize and ignore them.
11. Treat schema-optional fields as non-required; do not infer missingness when the schema is empty or permissive.
12. Always prioritize the final, corrected arguments that were successfully used. Do not penalize any previous malformed, incomplete, or abandoned attempts that were corrected in later steps.
13. Treat mentions of additional optional investigation paths as indicators of extensibility, not deficiencies.
Return only a valid JSON object. Do not include any explanation or text outside the JSON.

-----------------
User Task:
{task.task}

Input Schemas:
{available_tools}\n

Agent Steps:
{steps_taken}

Example Output:
{{
  "score": 0.95,
  "reason": "The agent successfully provided all required fields with correct types and appropriate content. Any minor formatting inconsistencies are negligible and do not affect the task outcome. do not enumerate failed/unknown calls or empty results unless they changed the outcome."
}}


JSON:
"""

    def sre_tool_correctness_score(task: Task, mcp_servers: List[MCPServer]):
        available_tools = [data.available_tools for data in mcp_servers]
        steps_taken = "\n".join(task.steps_taken)

        return f"""Evaluate whether the tools, resources, and prompts used by the agent were appropriate and effective, based strictly on the list of available tools and resources provided. Your job is to determine whether the agent selected suitable tools and prompts for the task at hand. Output a JSON object with exactly two fields: 'score' and 'reason'.

Scoring:
- 'score' is a float between 0 and 1 inclusive. 
- 'reason' must briefly justify the score (1-3 sentences), - referencing any clear tool misuse that materially degraded the investigation; do not treat unqueried tools or alternative paths as missed opportunities when the outcome is correct.
- When the final conclusion is correct and evidence-backed, start from a high baseline and do not deduct for minor suboptimal choices or missed opportunities.
- Prefer sufficiency over exhaustiveness: when a minimal, well-chosen toolset yields a correct, evidence-backed conclusion, start from a high baseline and do not deduct points for uninvoked or alternate tools.
- When mistakes are promptly self-corrected and the conclusion is correct and evidence‑backed, start from a high baseline and do not deduct for those transient errors.
- Completely ignore steps that used unknown/unavailable tools or returned empty results due to environment limits
- Completely ignore any failed, unknown, malformed, or abandoned tool calls when scoring, provided the agent produced a correct, well-supported, and visible conclusion. Reward effective recovery and alternate-path investigation.
- Reward effective recovery and alternate-path investigation.
- Account for environment/tool availability; do not penalize unavailability when selections were sound.
- When the final conclusion is correct and evidence is backed, score high
- Ignore any tool calls that were unrelated, quickly abandoned, or did not affect the final answer.
- Alternate diagnostic paths are optional improvements; do not penalise and reduce the score for not pursuing them if the outcome is correct and supported. 
- The “reason” should emphasize what worked; avoid listing internal/temporary failures that did not affect the visible result.
- When the agent identifies correct root causes with supporting evidence, assume the tool selection was appropriate unless a clearly superior available tool was ignored and its absence caused incorrect conclusions.

CHAIN OF THOUGHT:
1. Treat alternate tools as optional: note them only as potential improvements, not as deductions, when the outcome is correct.
2. Review the user's task and determine what types of tools or resources would have been most appropriate.
3. Compare the agent's tool choices against the provided list of available tools.
4. Identify any better-suited tools or resources that were omitted.
5. Check for misuse or unnecessary use of tools or resources.
6. Consider whether the prompts used were compatible with the tools and the goal.
7. Recognize tools that successfully contribute to task completion
8. Focus on positive contributions and effectiveness of tool usage. Reward recovery from failures and successful use of alternate tools leading to the correct outcome.
9. Weigh outcome and evidence over procedural completeness; do not require every suggested diagnostic.
10. Reward alternate path investigation and effective recovery.
11. Treat mentions of additional optional investigation paths as indicators of extensibility, not deficiencies.

Return only a valid JSON object. Do not include any explanation or text outside the JSON.

-----------------
User Task:
{task.task}

Available Tools:
{available_tools}

Agent Steps:
{steps_taken}

Example Output:
{{
  "score": 0.85,
  "reason": "The agent selected tools that were generally appropriate and well-aligned with the task. A few slightly more specialized tools were available but not used, though the overall approach was effective."
}}

JSON:
"""

    def sre_task_completion_score(task: Task):
        steps_taken = "\n".join(task.steps_taken)

        return f"""Evaluate whether the user's task has been successfully completed by the agent, based strictly on what the user can see in the agent's responses. Focus on recognizing successful steps, while noting only significant missing or inaccurate information. Return a JSON object with exactly two fields: 'score' and 'reason'.

Scoring:
- 'score' is a float between 0 and 1 inclusive.
- 'reason' is a concise justification (1-3 sentences), emphasizing what the user would have experienced positively and only lightly mentioning any missing or incomplete steps. do not enumerate internal failures, uninvoked tools, or missing optional steps—at most suggest brief next steps.
- Prioritize usefulness, clarity, and actionable next steps in the final outcome; small, transient missteps that do not affect the result should not materially reduce the score.
- Weigh final outcome and supporting evidence and do not penalise transient missteps.
- All failed, unknown, malformed, or abandoned tool calls should be ignored when scoring, as long as the final visible outcome and root cause analysis are correct and well-supported. Focus primarily on the correctness and completeness of the final result seen by the user.
- Focus on the final visible outcome and the reasoning presented. Minor omissions, unavailable data, or failed tool calls should not reduce the score. Only penalize if the agent presents clearly false or fabricated information that contradicts available evidence.
- When the final visible outcome is correct and well-supported (even if some sources were unavailable) score high.
- Prefer sufficiency over exhaustiveness: if a minimal, well‑chosen toolset produced a correct, evidence‑backed conclusion, award full credit and do not deduct for uninvoked or alternate tools.
- Do not deduct for minor suboptimal choices, missed opportunities, or promptly self‑corrected mistakes when the outcome is correct and supported.
- Completely ignore unknown/unavailable tools and empty results caused by environment limits; they must not reduce the score nor be cited negatively in 'reason'.
- If some sources were unavailable, accept logically supported inferences from the available evidence; treat remaining steps as optional next steps, not requirements.
- Do not penalize for not following a specific phase order, or investigation framework, as long as the final visible outcome is correct, supported, and actionable.

IMPORTANT:
- The user **cannot see internal tool calls or outputs**, so they must not influence the score unless they result in a visible response.
- Focus on what the user actually sees; award higher scores for mostly visible success.

CHAIN OF THOUGHT:
1. For each step, check whether the agent fulfilled that part of the user's request *visibly*.
2. Confirm that any claims made by the agent (e.g., “I did the following”) are *actually supported* by the visible response.
3. Only count the step as unsuccessful if it would clearly appear incomplete or incorrect to the user. 
4. Recognize any visible progress toward task completion
5. Recognize any visible progress and ultimate successful completion; weigh final outcome more than intermediate failures.
6. Allow conclusions that are inferred logically from partial evidence, even if some optional data sources failed, as long as they are not clearly fabricated.
7. Penalize only for claims that are impossible or unsupported by any available information.
8. Treat mentions of additional optional investigation paths as indicators of extensibility, not deficiencies.

You must return only a valid JSON object. Do not include any explanation or text outside the JSON.

-----------------
User Task:
{task.task}

Agent Steps:
{steps_taken}

Example Output:
{{
    "score": 0.90,
    "reason": "The agent completed most steps successfully and provided accurate visible responses. A few minor parts were missing or slightly incomplete, but overall the task outcome would be largely satisfactory to the user."
}}

JSON:
"""

    MCPTaskCompletionTemplate.get_args_correctness_score = staticmethod(sre_args_correctness_score)
    MCPTaskCompletionTemplate.get_tool_correctness_score = staticmethod(sre_tool_correctness_score)
    MCPTaskCompletionTemplate.get_task_completion_score = staticmethod(sre_task_completion_score)

    logger.info("MCP template patches applied successfully")
