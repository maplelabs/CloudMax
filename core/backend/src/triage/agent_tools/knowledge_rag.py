"""
Knowledge Base RAG Tool for SRE Operations.

This module provides a RAG (Retrieval-Augmented Generation) tool that combines
vector search with LLM generation to answer SRE-related questions using the
knowledge base.
"""

import logging

from langchain_core.documents import Document
from langchain_core.tools import tool
from sqlalchemy import select

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db import RunbookDBModel
from src.server.utilities.embedding_manager import get_embedding_manager_async
from src.server.utilities.llm_manager import get_secondary_llm_async

logger = logging.getLogger(__name__)


def parse_llm_response(response_text: str) -> list:
    """Extract runbook IDs from LLM response"""
    import json
    try:
        # Try to parse as JSON array
        logger.info(f"Respone after pasring is {json.loads(response_text)}")
        return json.loads(response_text)
    except (json.JSONDecodeError, ValueError, TypeError):
        # If JSON parsing fails, try to extract IDs manually
        import re
        ids = re.findall(r'runbook:\d+', response_text)
        logger.info(f"Respose from regular exp as the documents were not able to get converted to json {ids}")
        return ids

def format_selected_runbooks(selected_documents) -> str:
    """Format raw content of LLM-selected runbooks"""
    if not selected_documents:
        return "No relevant runbooks were selected for this query."
    
    parts = []
    for i, doc in enumerate(selected_documents, 1):
        title = doc.metadata.get("title", "Unknown")
        source = doc.metadata.get("source", "")
        # similarity_score is available in metadata but not currently displayed

        parts.append(
            f"[Runbook {i}] {source} - {title} \n"
            f"{doc.page_content}"
        )
    
    return "\n\n" + "="*80 + "\n\n".join(parts)

async def search_in_knowledge_base_async(query: str) -> str:
    """
    Search the SRE knowledge base and generate an answer using RAG pipeline.

    Args:
        query: Search query for the knowledge base

    Returns:
        LLM-generated answer based on relevant knowledge base content
    """
    try:
        # Step 1: Generate embedding for the search query
        embedding_manager = await get_embedding_manager_async()
        embedding_model = embedding_manager.get_embedding_model()
        query_embedding = await embedding_model.aembed_query(query)

        # Ensure proper vector format for pgvector
        if isinstance(query_embedding, str):
            # If embedding is a string, try to parse it as JSON
            import json
            try:
                query_embedding_list = json.loads(query_embedding)
            except (json.JSONDecodeError, TypeError):
                raise ValueError(
                    f"Invalid embedding format: expected list or array, got string: {type(query_embedding)}")
        elif hasattr(query_embedding, '__iter__') and not isinstance(query_embedding, str):
            query_embedding_list = list(query_embedding)
        else:
            query_embedding_list = query_embedding

        # Validate that we have a proper numeric list
        if not isinstance(query_embedding_list, (list, tuple)) or not query_embedding_list:
            raise ValueError(
                f"Invalid embedding format: expected non-empty list, got {type(query_embedding_list)}")

        # Ensure all elements are numeric
        try:
            query_embedding_list = [float(x) for x in query_embedding_list]
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Invalid embedding values: all elements must be numeric, got error: {e}")

        # Step 2: Search database using pgvector
        from src.alert_grouping.services import KNOWLEDGE_BASE_MAX_DOCUMENTS, KNOWLEDGE_BASE_MIN_SIMILARITY

        sql_query = select(
            RunbookDBModel.id,
            RunbookDBModel.title,
            RunbookDBModel.content,
            RunbookDBModel.embedding.cosine_distance(query_embedding_list).label('distance')
        ).where(
            RunbookDBModel.embedding.is_not(None),
            RunbookDBModel.embedding.cosine_distance(query_embedding_list) <= (1.0 - KNOWLEDGE_BASE_MIN_SIMILARITY)
        ).order_by(
            RunbookDBModel.embedding.cosine_distance(query_embedding_list)
        ).limit(
            KNOWLEDGE_BASE_MAX_DOCUMENTS
        )

        async with async_db_session() as db:
            result = await db.execute(sql_query)
            rows = result.fetchall()

            # Convert to LangChain Document format
            documents = []
            for row in rows:
                distance = float(row.distance)
                similarity_score = max(0.0, 1.0 - distance) if distance is not None else 0.0

                doc = Document(
                    page_content=row.content,
                    metadata={
                        "source": f"runbook:{row.id}",
                        "title": row.title,
                        "runbook_id": str(row.id),
                        "distance": distance,
                        "similarity_score": similarity_score,
                        "relevance": "high" if similarity_score > 0.8 else "medium" if similarity_score > 0.6 else "low"
                    }
                )

                documents.append(doc)

        logger.info(
            f"Retrieved {len(documents)} documents from vector search "
            f"(max: {KNOWLEDGE_BASE_MAX_DOCUMENTS}, min_similarity: {KNOWLEDGE_BASE_MIN_SIMILARITY}, "
            f"avg_similarity: {sum(d.metadata.get('similarity_score', 0) for d in documents) / len(documents) if documents else 0:.2f})"
        )

        if not documents:
            return "I don't have relevant information in the knowledge base to answer this question."

        # Step 2: Prepare context from retrieved documents
        context_parts = []
        for i, doc in enumerate(documents, 1):
            # Include metadata if available for better context
            metadata_info = ""
            if hasattr(doc, "metadata") and doc.metadata:
                source = doc.metadata.get("source", "")
                if source:
                    metadata_info = f" (Source: {source})"

            context_parts.append(
                f"[Reference {i}]{metadata_info}: {doc.page_content}")

        context = "\n\n".join(context_parts)

        # Log context size for monitoring
        logger.info(f"Knowledge base context size: {len(context)} characters, {len(documents)} documents retrieved")

        # Step 3: Generate answer using Secondary LLM (RAG)
        llm = await get_secondary_llm_async()

        prompt = f"""You are an expert SRE (Site Reliability Engineering) Knowledge Base Assistant. Your role is to help users find information from the knowledge base to answer questions about Kubernetes, services, infrastructure, and DevOps operations. Given these runbooks, identify which ones are NECESSARY for triaging this alert.

INSTRUCTIONS:
1. Analyze each runbook carefully to determine if it's relevant for triaging this specific alert
2. Return ONLY the runbook IDs that are directly relevant and necessary for investigation
3. If NONE of the runbooks are relevant to this alert, return an empty array: []
4. Format your response as a JSON array of runbook IDs: ["runbook:5", "runbook:8"]

User Question: {query}

Available Runbooks: {context}

<Response Format>
Return ONLY the runbook IDs that are necessary for triage. Format as JSON array: ["runbook:5", "runbook:8"]
</Response Format>

Answer:"""

        try:
            response = llm.invoke(prompt)
            runbook_ids = parse_llm_response(response.content)
            if not runbook_ids:
                return "I don't have relevant information in the knowledge base to answer this question."
            else:
                selected_docs = [doc for doc in documents if doc.metadata.get("source") in runbook_ids]

            # LAYER 1: Filter by similarity threshold
            from src.alert_grouping.services import KNOWLEDGE_BASE_MAX_DOCUMENTS, KNOWLEDGE_BASE_MIN_SIMILARITY

            pre_filter_count = len(selected_docs)
            selected_docs = [
                doc for doc in selected_docs
                if doc.metadata.get("similarity_score", 0.0) >= KNOWLEDGE_BASE_MIN_SIMILARITY
            ]

            if pre_filter_count > len(selected_docs):
                logger.info(
                    f"Filtered out {pre_filter_count - len(selected_docs)} runbooks below {KNOWLEDGE_BASE_MIN_SIMILARITY} "
                    f"({pre_filter_count} → {len(selected_docs)})"
                )

            # LAYER 2: Enforce hard limit - NEVER return more than MAX_DOCS_TO_RETRIEVE (5)
            # This prevents LLM from selecting all documents when filtering fails
            if len(selected_docs) > KNOWLEDGE_BASE_MAX_DOCUMENTS:
                logger.warning(
                    f"LLM selected {len(selected_docs)} runbooks, but max is {KNOWLEDGE_BASE_MAX_DOCUMENTS}. "
                    f"Truncating to top {KNOWLEDGE_BASE_MAX_DOCUMENTS} by similarity score."
                )
                # Sort by similarity score (descending) and take top N
                selected_docs = sorted(
                    selected_docs,
                    key=lambda doc: doc.metadata.get("similarity_score", 0.0),
                    reverse=True
                )[:KNOWLEDGE_BASE_MAX_DOCUMENTS]

            # LAYER 3: Check if any docs remain after filtering
            if not selected_docs:
                logger.warning(
                    f"All LLM-selected runbooks were below similarity threshold {KNOWLEDGE_BASE_MIN_SIMILARITY}"
                )
                return f"I found some runbooks, but none were relevant enough (similarity < {KNOWLEDGE_BASE_MIN_SIMILARITY}) for this alert."

            # Log final selection with similarity scores
            doc_info = [
                f"{doc.metadata.get('source')} (sim: {doc.metadata.get('similarity_score', 0):.2f})"
                for doc in selected_docs
            ]
            logger.info(
                f"Final selection: {len(selected_docs)} runbooks selected by LLM: {doc_info}"
            )

            return format_selected_runbooks(selected_docs)
        except Exception:
            logger.exception(f"LLM Error with prompt length {len(prompt)}")
            return (f"I encountered an error while generating the response. Please try rephrasing your question or "
                    f"contact support if the issue persists.")

    except Exception:

        logger.exception(f"Knowledge RAG Error")
        return "I encountered an error while searching the knowledge base"


@tool
async def search_in_knowledge_base(query: str) -> str:
    """
    Search the SRE knowledge base and generate an answer using Retrieval-Augmented Generation (RAG) pipeline.

    Use this tool when you need information about:
    - Kubernetes operations, troubleshooting, and best practices
    - Service dependencies, configurations, and monitoring
    - Alert investigation, diagnosis, and mitigation procedures
    - Infrastructure troubleshooting and incident response
    - DevOps tools, processes, and runbooks

    Args:
        query: Search query for the knowledge base

    Returns:
        LLM-generated answer based on relevant knowledge base content
    """
    try:
        return await search_in_knowledge_base_async(query)
    except Exception:
        logger.exception(f"Knowledge RAG Error for query: {query}")
        return "I encountered an error while searching the knowledge base"

