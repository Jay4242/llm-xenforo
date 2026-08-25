from dataclasses import dataclass


@dataclass(frozen=True)
class ImageAttachment:
    url: str
    media_type: str
    data: bytes


@dataclass(frozen=True)
class Comment:
    comment_id: str
    author: str
    posted_at: str
    url: str
    text: str
    images: tuple[ImageAttachment, ...] = ()


@dataclass(frozen=True)
class Classification:
    category: str
    summary: str
    subjects: tuple[str, ...] = ()
    confidence: str = "unknown"
