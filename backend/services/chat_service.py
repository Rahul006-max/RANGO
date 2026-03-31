"""
Chat service - handles conversational chat mode with streaming responses.
"""
import os
import time
import json
import asyncio
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate

from dependencies import (
    get_supabase_user_client,
    PIPELINE_DB_PATHS,
    COLLECTION_FULLTEXT,
    PREFERRED_PIPELINE_CACHE,
    get_embeddings,
    get_llm,
    get_vectorstore,
    supabase_vector_search,
)
from core.pipelines import SYSTEM_PIPELINES
from core.retrieval import dedupe_docs
from utils.text_utils import clean_text, enrich_answer_if_duration, smart_extract_answer
from models import ChatRequest


def get_chat_history(collection_id: str, user_id: str, access_token: str):
    """Get chat history for a collection."""
    sb = get_supabase_user_client(access_token)
    
    res = sb.table("rag_chat_messages") \
        .select("role,message") \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=False) \
        .limit(20) \
        .execute()
    
    return {"messages": res.data or []}


def clear_chat_history(collection_id: str, user_id: str, access_token: str):
    """Clear chat history for a collection."""
    sb = get_supabase_user_client(access_token)
    
    sb.table("rag_chat_messages") \
        .delete() \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .execute()
    
    return {"status": "cleared [OK]"}


async def chat_stream_generator(
    data: ChatRequest,
    user_id: str,
    access_token: str,
    model_name: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
):
    """
    Generate streaming chat responses.
    
    Args:
        data: ChatRequest with question and collection_id
        user_id: User ID
        access_token: User's access token
        model_name: Optional model name override (None = system default).
        api_key: Optional API key for custom models.
        temperature: Optional temperature override.
    
    Yields:
        str: Character-by-character response stream
    """
    embeddings = get_embeddings()
    llm = get_llm(model_name=model_name, api_key=api_key, temperature=temperature)
    sb = get_supabase_user_client(access_token)
    final_response = None
    t_start = time.time()
    docs_retrieved = 0
    is_smart_extract = False
    
    # Store user message
    sb.table("rag_chat_messages").insert({
        "user_id": user_id,
        "collection_id": data.collection_id,
        "role": "user",
        "message": data.question
    }).execute()

    # Validate collection and route tree-indexed collections before vector-only logic.
    collection_res = (
        sb.table("rag_collections")
        .select("id,index_type")
        .eq("id", data.collection_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not collection_res.data:
        yield "[ERROR] Collection not found. Please upload documents first."
        return

    col_index_type = (collection_res.data.get("index_type") or "vector").lower()
    if col_index_type == "tree":
        from services.page_index_service import answer_with_tree

        tree_result = answer_with_tree(
            question=data.question,
            collection_id=data.collection_id,
            user_id=user_id,
            sb=sb,
            fast=True,
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
        )
        if "error" in tree_result:
            yield f"[ERROR] {tree_result['error']}"
            return

        final_response = tree_result.get("final_answer") or ""
        for token in final_response:
            yield token

        sb.table("rag_chat_messages").insert({
            "user_id": user_id,
            "collection_id": data.collection_id,
            "role": "assistant",
            "message": final_response,
        }).execute()

        latency_ms = round((time.time() - t_start) * 1000)
        meta = {
            "pipeline": "PageIndex Tree",
            "latency_ms": latency_ms,
            "docs_retrieved": 0,
            "smart_extract": False,
        }
        yield f"\n\n__META__{json.dumps(meta)}"
        return
    
    try:
        cache_key = f"{user_id}:{data.collection_id}"
        if cache_key in PREFERRED_PIPELINE_CACHE:
            preferred_pipeline = PREFERRED_PIPELINE_CACHE[cache_key]
            # Pipeline already cached — only fetch chat history
            history_res = sb.table("rag_chat_messages") \
                .select("role,message") \
                .eq("collection_id", data.collection_id) \
                .eq("user_id", user_id) \
                .order("created_at", desc=False) \
                .limit(10) \
                .execute()
            chat_history = history_res.data or []
        else:
            # Run history fetch and preferred-pipeline fetch concurrently
            from concurrent.futures import ThreadPoolExecutor as _TPE

            def _fetch_history():
                return sb.table("rag_chat_messages") \
                    .select("role,message") \
                    .eq("collection_id", data.collection_id) \
                    .eq("user_id", user_id) \
                    .order("created_at", desc=False) \
                    .limit(10) \
                    .execute()

            def _fetch_preferred():
                return sb.table("rag_chat_history") \
                    .select("best_pipeline") \
                    .eq("collection_id", data.collection_id) \
                    .eq("user_id", user_id) \
                    .not_.is_("best_pipeline", "null") \
                    .neq("best_pipeline", "FULLTEXT_EXTRACT") \
                    .order("created_at", desc=True) \
                    .limit(5) \
                    .execute()

            with _TPE(max_workers=2) as ex:
                f_hist = ex.submit(_fetch_history)
                f_pref = ex.submit(_fetch_preferred)
                history_res = f_hist.result()
                best_pipeline_res = f_pref.result()

            chat_history = history_res.data or []
            records = best_pipeline_res.data or []
            if records:
                from collections import Counter
                counts = Counter(r["best_pipeline"] for r in records if r.get("best_pipeline"))
                preferred_pipeline = counts.most_common(1)[0][0] if counts else "Pipeline A"
            else:
                preferred_pipeline = "Pipeline A"
            PREFERRED_PIPELINE_CACHE[cache_key] = preferred_pipeline
        
        # Build conversation context from chat history
        context_messages = []
        for msg in chat_history[-4:]:  # Last 4 messages for context (faster prompt)
            context_messages.append(f"{msg['role'].capitalize()}: {msg['message']}")
        conversation_context = "\n".join(context_messages)

        # Vector collections require local vector index map
        if data.collection_id not in PIPELINE_DB_PATHS:
            yield "[ERROR] Collection not found. Please upload documents first."
            return
        
        collection_paths = PIPELINE_DB_PATHS[data.collection_id]
        
        # Try smart extraction first
        full_text = COLLECTION_FULLTEXT.get(data.collection_id, "")
        extracted = smart_extract_answer(data.question, full_text)
        
        if extracted:
            response = f"📋 Direct Answer: {extracted}"
            final_response = response
            is_smart_extract = True
            yield response
        
        else:
            # Use the preferred/best performing pipeline
            pipeline_info = next((p for p in SYSTEM_PIPELINES if p["name"] == preferred_pipeline), SYSTEM_PIPELINES[0])
            
            if data.collection_id not in PIPELINE_DB_PATHS:
                yield f"Collection not available. Please upload documents first."
                return
            
            # Build enhanced query with conversation context
            if len(chat_history) > 1:
                enhanced_query = f"""
Previous conversation context:
{conversation_context}

Current question: {data.question}

Please answer the current question considering the conversation context.
"""
            else:
                enhanced_query = data.question
            
            # Retrieve relevant documents via Supabase pgvector.
            # Use a larger k when the question mentions multiple docs or "both".
            question_lower = data.question.lower()
            is_multidoc_q = any(w in question_lower for w in ["both", "two doc", "all doc", "each doc", "every doc", "compare", "difference between", "documents say", "docs say"])
            effective_k = pipeline_info["k"] * 3 if is_multidoc_q else pipeline_info["k"] * 2

            docs = dedupe_docs(supabase_vector_search(
                collection_id=data.collection_id,
                pipeline_name=pipeline_info["name"],
                query_text=enhanced_query,
                k=effective_k,
                search_type=pipeline_info["search_type"],
                access_token=access_token,
            ))
            docs_retrieved = len(docs)

            # Build context with source labels so the LLM knows which file
            # each chunk came from — critical for multi-document collections.
            def _chunk_label(doc):
                src = doc.metadata.get("source") or ""
                fname = os.path.basename(src) if src else ""
                page = doc.metadata.get("page")
                label = f"[{fname}" + (f", p.{page + 1}" if page is not None else "") + "]"
                return f"{label}\n{doc.page_content}"

            context = clean_text("\n\n".join(_chunk_label(d) for d in docs))
            # Collect distinct filenames present in the retrieved chunks
            source_files = sorted(set(
                os.path.basename(d.metadata.get("source") or "")
                for d in docs if d.metadata.get("source")
            ))
            
            # Create conversational prompt
            conv_prompt = ChatPromptTemplate.from_template("""
You are a helpful assistant having a conversation with a user about their documents.

Documents available in this collection: {source_files}

Previous conversation context:
{conversation_context}

Relevant document context (each chunk is labelled with [filename, page]):
{document_context}

Current question: {current_question}

Instructions:
- Answer using ONLY the document context above.
- If multiple documents are present, treat each [filename] block as a separate source and compare/contrast them when relevant.
- When the user asks "what do both/all documents say", summarise each document's contribution separately.
- Consider the conversation history to provide a coherent response.
- Keep responses conversational but informative.
- If you can't answer from the documents, say so.

Answer:
""")
            
            # Generate response
            chain = conv_prompt | llm
            
            # Stream tokens directly — no duplicate invoke() call
            accumulated = ""
            async for chunk in chain.astream({
                "source_files": ", ".join(source_files) if source_files else "(unknown)",
                "conversation_context": conversation_context if len(chat_history) > 1 else "This is the start of our conversation.",
                "document_context": context,
                "current_question": data.question
            }):
                # Guard against non-text LangChain chunk types (usage-metadata,
                # tool-call chunks) that produce raw object repr via str().
                if hasattr(chunk, "content"):
                    if not isinstance(chunk.content, str):
                        continue
                    token = chunk.content
                elif isinstance(chunk, str):
                    token = chunk
                else:
                    continue
                if not token:
                    continue
                accumulated += token
                yield token
            
            response = enrich_answer_if_duration(data.question, context, accumulated)
            final_response = response
            # If enrich changed the response, send the delta
            if response != accumulated:
                yield response[len(accumulated):]
        
        # Store assistant response
        sb.table("rag_chat_messages").insert({
            "user_id": user_id,
            "collection_id": data.collection_id,
            "role": "assistant",
            "message": final_response or ""
        }).execute()

        # Emit analytics metadata trailer
        latency_ms = round((time.time() - t_start) * 1000)
        meta = {
            "pipeline": preferred_pipeline if not is_smart_extract else "FULLTEXT_EXTRACT",
            "latency_ms": latency_ms,
            "docs_retrieved": docs_retrieved,
            "smart_extract": is_smart_extract,
        }
        yield f"\n\n__META__{json.dumps(meta)}"
    
    except Exception as e:
        error_msg = f"[ERROR] Chat error: {str(e)}"
        yield error_msg
        
        # Store error as assistant message
        sb.table("rag_chat_messages").insert({
            "user_id": user_id,
            "collection_id": data.collection_id,
            "role": "assistant",
            "message": error_msg
        }).execute()
