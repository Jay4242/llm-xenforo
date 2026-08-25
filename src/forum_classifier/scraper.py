from __future__ import annotations

import logging
import mimetypes
import time
from collections.abc import Iterator
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .models import Comment, ImageAttachment

logger = logging.getLogger(__name__)


class ForumAccessError(RuntimeError):
    """The forum returned an interstitial instead of thread content."""


class ForumScraper:
    """Scrape XenForo-style thread pages without downloading the whole site."""

    def __init__(
        self,
        *,
        delay: float = 1.0,
        timeout: float = 30.0,
        user_agent: str | None = None,
        browser: bool = False,
        chrome_path: str | None = None,
        headed: bool = False,
        user_data_dir: str | None = None,
        include_images: bool = False,
        max_image_bytes: int = 10 * 1024 * 1024,
    ):
        self.browser = browser
        self.chrome_path = chrome_path
        self.headed = headed
        self.user_data_dir = user_data_dir
        self.include_images = include_images
        self.max_image_bytes = max_image_bytes
        if browser:
            self.session = None
            self.delay = max(0.0, delay)
            self.timeout = timeout
            self.user_agent = user_agent
            return
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent or "forum-comment-classifier/0.1"})
        self.delay = max(0.0, delay)
        self.timeout = timeout

    def pages(self, start_url: str, *, max_pages: int | None = None) -> Iterator[tuple[str, str]]:
        if self.browser:
            yield from self._browser_pages(start_url, max_pages=max_pages)
            return
        current = self._canonical_url(start_url)
        seen: set[str] = set()
        count = 0
        while current and current not in seen and (max_pages is None or count < max_pages):
            logger.info("Fetching forum page %d: %s", count + 1, current)
            response = self.session.get(current, timeout=self.timeout)
            response.raise_for_status()
            logger.info("Received forum page %d (%d bytes)", count + 1, len(response.text))
            if self.is_browser_challenge(response.text):
                raise ForumAccessError(
                    "The forum returned a browser-validation page instead of thread content. "
                    "This site requires JavaScript bot-guard verification; plain requests "
                    "cannot complete it. Open the thread in a normal browser first, or use an "
                    "authorized browser/session export or saved HTML."
                )
            yield current, response.text
            seen.add(current)
            count += 1
            next_url = self.next_page_url(response.text, current)
            if next_url and next_url not in seen:
                logger.info("Next forum page: %s", next_url)
                time.sleep(self.delay)
            current = next_url

    def _browser_pages(self, start_url: str, *, max_pages: int | None = None) -> Iterator[tuple[str, str]]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise ForumAccessError("Browser mode requires Playwright. Install with: pip install -e '.[browser]'") from error

        current = self._canonical_url(start_url)
        seen: set[str] = set()
        count = 0
        with sync_playwright() as playwright:
            launch_options = {
                "headless": not self.headed,
                "args": ["--disable-blink-features=AutomationControlled"],
                "ignore_default_args": ["--enable-automation"],
            }
            if self.chrome_path:
                launch_options["executable_path"] = self.chrome_path
            if self.user_data_dir:
                context = playwright.chromium.launch_persistent_context(self.user_data_dir, **launch_options)
                browser = None
            else:
                browser = playwright.chromium.launch(**launch_options)
                context = browser.new_context(user_agent=self.user_agent)
            page = context.new_page()
            page.set_default_timeout(self.timeout * 1000)
            try:
                while current and current not in seen and (max_pages is None or count < max_pages):
                    logger.info("Opening forum page %d in browser: %s", count + 1, current)
                    page.goto(current, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                    try:
                        page.wait_for_selector("article.message, li.message", timeout=self.timeout * 1000)
                    except PlaywrightTimeoutError:
                        html = page.content()
                        if self.is_browser_challenge(html):
                            raise ForumAccessError(
                                "The browser did not complete the forum's bot-guard validation. "
                                "Try --headed so the validation can be observed, or increase the timeout."
                            )
                        raise
                    html = page.content()
                    logger.info("Browser loaded forum page %d (%d bytes)", count + 1, len(html))
                    yield current, html
                    seen.add(current)
                    count += 1
                    next_url = self.next_page_url(html, current)
                    if next_url and next_url not in seen:
                        logger.info("Next forum page: %s", next_url)
                        time.sleep(self.delay)
                    current = next_url
            finally:
                context.close()
                if browser:
                    browser.close()

    def comments(self, start_url: str, *, max_pages: int | None = None) -> Iterator[Comment]:
        for page_url, html in self.pages(start_url, max_pages=max_pages):
            comments = self.parse_comments(html, page_url)
            if self.include_images:
                comments = [self._with_images(comment) for comment in comments]
            logger.info("Extracted %d comments from %s", len(comments), page_url)
            yield from comments

    @staticmethod
    def parse_comments(html: str, page_url: str) -> list[Comment]:
        soup = BeautifulSoup(html, "html.parser")
        result: list[Comment] = []
        for node in soup.select("article.message, li.message"):
            message = node.select_one(".message-body .bbWrapper, .message-body")
            if not message:
                continue
            text = message.get_text("\n", strip=True)
            if not text:
                continue
            comment_id = node.get("data-content", "") or node.get("id", "")
            comment_id = str(comment_id).removeprefix("post-") or f"{page_url}#comment-{len(result) + 1}"
            author_node = node.select_one(".message-name, .username, h4 a")
            time_node = node.select_one("time")
            image_urls = tuple(
                urljoin(page_url, image.get(attribute))
                for image in message.select("img")
                for attribute in ("src", "data-src", "data-url")
                if image.get(attribute) and not str(image.get(attribute)).startswith("data:")
            )
            result.append(Comment(
                comment_id=comment_id,
                author=author_node.get_text(" ", strip=True) if author_node else "unknown",
                posted_at=(time_node.get("datetime") or time_node.get_text(" ", strip=True)) if time_node else "unknown",
                url=urljoin(page_url, f"#{node.get('id')}") if node.get("id") else page_url,
                text=text,
                images=tuple(ImageAttachment(url, "", b"") for url in dict.fromkeys(image_urls)),
            ))
        return result

    def _with_images(self, comment: Comment) -> Comment:
        images: list[ImageAttachment] = []
        for image in comment.images:
            try:
                response = (self.session or requests.Session()).get(image.url, timeout=self.timeout, stream=True)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
                if not content_type.startswith("image/"):
                    logger.warning("Skipping non-image attachment %s (%s)", image.url, content_type or "unknown type")
                    continue
                data = response.content
                if len(data) > self.max_image_bytes:
                    logger.warning("Skipping oversized image %s (%d bytes)", image.url, len(data))
                    continue
                images.append(ImageAttachment(image.url, content_type or mimetypes.guess_type(image.url)[0] or "image/jpeg", data))
                logger.info("Downloaded image for comment %s: %s (%d bytes)", comment.comment_id, image.url, len(data))
            except requests.RequestException as error:
                logger.warning("Could not download image %s: %s", image.url, error)
        return Comment(comment.comment_id, comment.author, comment.posted_at, comment.url, comment.text, tuple(images))

    @staticmethod
    def next_page_url(html: str, page_url: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        link = soup.select_one('a[rel="next"], a.pageNav-jump--next')
        return urljoin(page_url, link.get("href")) if link and link.get("href") else None

    @staticmethod
    def is_browser_challenge(html: str) -> bool:
        lowered = html.lower()
        return "validating browser" in lowered or "zeebotguard" in lowered

    @staticmethod
    def _canonical_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("thread URL must be an absolute http(s) URL")
        return urlunparse(parsed._replace(fragment=""))
