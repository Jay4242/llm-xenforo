import logging
from pathlib import Path

from .models import Classification, Comment

logger = logging.getLogger(__name__)


def save_comment(output_dir: Path, comment: Comment, classification: Classification) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{classification.category}.txt"
    subjects = ", ".join(classification.subjects) or "none"
    entry = (
        f"\n{'=' * 72}\n"
        f"Comment ID: {comment.comment_id}\nAuthor: {comment.author}\n"
        f"Posted: {comment.posted_at}\nSource: {comment.url}\n"
        f"Summary: {classification.summary}\nSubjects: {subjects}\n"
        f"Confidence: {classification.confidence}\n\n{comment.text}\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    logger.info("Saved comment %s to %s", comment.comment_id, path)
    return path
