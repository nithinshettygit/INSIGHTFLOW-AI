"""Prompt templates for RAG answer synthesis."""

RAG_SYSTEM_PROMPT = """You are InsightFlow AI's document analyst.
Answer the user's question using ONLY the provided context excerpts from a PDF.
If the context is insufficient, say what is missing instead of inventing facts.
Be concise and cite page numbers when available.
Do not discuss columns, charts, or tabular analytics unless they appear in the context.
"""


def build_rag_user_prompt(question: str, passages: list[dict]) -> str:
    blocks: list[str] = []
    for i, item in enumerate(passages, start=1):
        page = item.get("page_number")
        page_label = f"page {page}" if page is not None else "unknown page"
        score = item.get("score")
        score_label = f", score={score:.3f}" if isinstance(score, (int, float)) else ""
        blocks.append(
            f"[{i}] ({page_label}{score_label})\n{item.get('text', '').strip()}"
        )
    context = "\n\n".join(blocks) if blocks else "(no passages retrieved)"
    return (
        f"Question:\n{question.strip()}\n\n"
        f"Context excerpts:\n{context}\n\n"
        "Answer:"
    )
