import logging
import json
import re
from pathlib import Path

from .models import Classification, Comment

logger = logging.getLogger(__name__)

STATE_FILENAME = ".state.json"


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


def load_comment_ids(output_dir: Path) -> set[str]:
    """Read IDs from existing category files without contacting the forum."""
    ids: set[str] = set()
    if not output_dir.exists():
        return ids
    for path in output_dir.glob("*.txt"):
        ids.update(re.findall(r"^Comment ID: (.+)$", path.read_text(encoding="utf-8"), flags=re.MULTILINE))
    return ids


def load_state(output_dir: Path) -> dict[str, object] | None:
    path = output_dir / STATE_FILENAME
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read {path}: {error}") from error
    if not isinstance(state, dict) or not isinstance(state.get("thread_url"), str) or not isinstance(state.get("page"), int):
        raise ValueError(f"invalid state file: {path}")
    return state


def save_state(output_dir: Path, thread_url: str, page: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / STATE_FILENAME
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"thread_url": thread_url, "page": page}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
