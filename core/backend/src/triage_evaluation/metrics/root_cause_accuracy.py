"""
Root Cause Accuracy metric using DeepEval G-Eval.
Compares expected RCA from chaos system vs actual RCA from AI triager.
"""
import logging
from typing import Dict, Any, List, Union

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from src.server.models.api.alert_traige import TriageAIMessage, TriageToolMessage
from ..utilities import LangGraphLLMWrapper

logger = logging.getLogger(__name__)


class RootCauseAccuracyMetric:
    """
    Evaluates the accuracy of root cause analysis by comparing expected vs actual RCA.
    Uses G-Eval with custom criteria for RCA comparison.
    """

    def __init__(self, llm_wrapper: LangGraphLLMWrapper, alert_name: str, alert_payload: Any):
        """
        Initialize the RCA accuracy metric.
        No thresholds as per requirements.
        """
        self.llm_wrapper = llm_wrapper

        # Create G-Eval metric for RCA comparison (no threshold)
        self.metric = GEval(
            name="Root Cause Analysis Accuracy",
            criteria="""
            Evaluate ONLY whether the expected RCA and actual RCA identify the SAME PRIMARY TECHNICAL FAILURE.
            Focus EXCLUSIVELY on semantic similarity of the core technical root cause.
            
            Definition of "primary technical failure":
                - The direct technical mechanism that caused the alert 

            CRITICAL INSTRUCTIONS - IGNORE EVERYTHING ELSE:
                - DO NOT evaluate causal chains, downstream impacts, or triggering workflows
                - DO NOT penalize for missing context, speculation
                - DO NOT evaluate narrative quality, detail level, structure,
                - DO NOT penalize if one RCA has more/less detail than the other
                - ONLY compare the core technical failure mechanism
            """,
            evaluation_steps=[
                "Extract ONLY the primary technical failure mechanism from expected RCA ",
                "Extract ONLY the primary technical failure mechanism from actual RCA",
                "Compare if both identify the same core technical failure",
                "Ignore ALL other aspects: workflows, impacts, chains, detail level",
            ],
            evaluation_params=[
                LLMTestCaseParams.EXPECTED_OUTPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.INPUT
            ],
            model=self.llm_wrapper,
            async_mode=True
        )

        self.alert_context = f"Triage the following:\n\nAlert Name: {alert_name}, Details: {alert_payload}"

    async def evaluate(
            self,
            messages: List[Union[TriageAIMessage, TriageToolMessage]],
            expected_rca: str
    ) -> Dict[str, Any]:
        """
        Evaluate RCA accuracy using the last orchestrator message as actual RCA.

        Args:
            messages: List of triage messages
            expected_rca: Expected RCA from chaos system

        Returns:
            Dictionary containing score and reason (no threshold)
        """
        logger.info("Evaluating root cause accuracy")

        # Find the last orchestrator AI message as actual RCA
        # Assume that last message is orchestrator and will most likely have content field filled up
        actual_rca = messages[-1].content.strip()

        if not actual_rca:
            logger.warning("No final orchestrator RCA found in messages")
            return {
                'score': 0.0,
                'reason': "No final orchestrator RCA found in messages"
            }

        # Create test case for evaluation
        test_case = LLMTestCase(
            input=self.alert_context,
            expected_output=expected_rca,
            actual_output=actual_rca
        )

        # Run async evaluation
        await self.metric.a_measure(test_case)

        score = {
            'score': round(self.metric.score * 100.0, 0),
            'reason': self.metric.reason
        }

        logger.info(f"Root cause accuracy evaluation completed with score: {score}")

        return score
