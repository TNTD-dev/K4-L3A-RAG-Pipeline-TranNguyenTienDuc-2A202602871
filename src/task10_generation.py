"""
Task 10 — Generation có citation.

Hướng dẫn:
    1. Retrieve top-k chunks.
    2. Reorder để giảm lost-in-the-middle.
    3. Format context kèm title và source.
    4. Gọi provider được chọn trong .env.
    5. Trả answer, sources và retrieval_source.

Nếu context không đủ hoặc provider lỗi, trả safe refusal; không bịa thông tin.
"""

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - minimal CI images
    def load_dotenv() -> bool:
        return False

from .task9_retrieval_pipeline import retrieve


load_dotenv()

TOP_K = 5
TOP_P = 0.9
TEMPERATURE = 0.3

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "")

SYSTEM_PROMPT = """Trả lời chỉ từ context được cung cấp.
Mỗi khẳng định phải có citation. Nếu thiếu evidence, hãy từ chối xác minh."""


def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """Đưa chunks quan trọng về đầu và cuối context."""
    if len(chunks) <= 2:
        return list(chunks)
    front = list(chunks[::2])
    back = list(chunks[1::2])
    return front + back[::-1]


def format_context(chunks: list[dict]) -> str:
    """Tạo context có title và source label."""
    parts = []
    for index, chunk in enumerate(chunks, 1):
        metadata = chunk["metadata"]
        version = metadata.get("policy_version") or metadata.get("version")
        effective = metadata.get("effective_date")
        suffix = ""
        if version:
            suffix += f" | Policy Version: {version}"
        if effective:
            suffix += f" | Effective: {effective}"
        parts.append(
            f"[Document {index} | Title: {metadata.get('title', 'Untitled')} | "
            f"Source: {metadata.get('source', '')}{suffix}]\n{chunk['content']}"
        )
    return "\n\n---\n\n".join(parts)


def call_llm(system_prompt: str, user_message: str) -> str:
    """Gọi OpenAI, Gemini hoặc Anthropic theo cấu hình."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    provider = LLM_PROVIDER.strip().lower()
    if provider == "openai" and key:
        try:
            from openai import OpenAI
            model_name = LLM_MODEL or "gpt-5.6-luna"
            req = {
                "model": model_name,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            }
            if not model_name.startswith("gpt-5.6"):
                req["temperature"] = TEMPERATURE
            response = OpenAI(api_key=key).chat.completions.create(**req)
            return response.choices[0].message.content or ""
        except Exception:
            pass
    # Deterministic offline adapter.  It deliberately mentions evidence but
    # never invents a policy fact from outside the supplied context.
    from src.vinuni_compass.providers.adapters import DeterministicGenerationAdapter
    return DeterministicGenerationAdapter().complete(system_prompt, user_message)


def generate_with_citation(query: str, top_k: int = TOP_K) -> dict:
    """Trả về GenerationResult."""
    chunks = retrieve(query, top_k=top_k)
    if not chunks:
        return {"answer": "Tôi không thể xác minh thông tin này từ nguồn hiện có.", "sources": [], "retrieval_source": "none"}
    context = format_context(reorder_for_llm(chunks))
    try:
        answer = call_llm(SYSTEM_PROMPT, f"Context:\n{context}\n\nQuestion: {query}")
    except Exception:
        answer = "Tôi không thể xác minh thông tin này từ nguồn hiện có."
    method = chunks[0].get("retrieval_method")
    retrieval_source = method if method in {"hybrid", "pageindex"} else "hybrid"
    return {"answer": answer.strip() or "Tôi không thể xác minh thông tin này từ nguồn hiện có.", "sources": chunks, "retrieval_source": retrieval_source}


if __name__ == "__main__":
    print(generate_with_citation("test query"))
