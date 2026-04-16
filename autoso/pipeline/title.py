# autoso/pipeline/title.py
from llama_index.core import Settings
from autoso.scraping.models import Post


def infer_title(post: Post) -> str:
    """Use the configured LLM to infer a title from post content and sample comments."""
    sample_comments = " | ".join(
        c.text[:120] for c in post.comments[:5]
    )
    prompt = (
        f"Based on the following post content and sample comments from {post.platform}, "
        f"generate a concise title (3-8 words, Title Case). "
        f"Output ONLY the title, nothing else.\n\n"
        f"Post content: {post.content[:500]}\n"
        f"Sample comments: {sample_comments}\n\n"
        f"Title:"
    )
    response = Settings.llm.complete(prompt)
    return str(response).strip().strip("\"'")
