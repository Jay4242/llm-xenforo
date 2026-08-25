from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from .classifier import DEFAULT_LLM_TIMEOUT, LocalClassifier
from .scraper import ForumAccessError, ForumScraper
from .storage import save_comment

DEFAULT_CHROME_PATH = "/usr/bin/google-chrome"
DEFAULT_BROWSER_PROFILE = os.path.expanduser("~/.cache/forum-classifier/chrome-profile")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify comments from a XenForo forum thread.")
    parser.add_argument("url", help="absolute URL of the thread")
    parser.add_argument("--output-dir", type=Path, default=Path("classified-comments"))
    parser.add_argument("--llm-url", default="http://127.0.0.1:9393/v1")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--llm-timeout", type=float, default=DEFAULT_LLM_TIMEOUT, help="LLM request timeout in seconds (default: 600)")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between page requests")
    images_group = parser.add_mutually_exclusive_group()
    images_group.add_argument("--images", dest="images", action="store_true", help="download comment images in memory and send them to the LLM (default)")
    images_group.add_argument("--no-images", dest="images", action="store_false", help="do not download or send comment images")
    parser.set_defaults(images=True)
    browser_group = parser.add_mutually_exclusive_group()
    browser_group.add_argument("--browser", dest="browser", action="store_true", help="use Playwright with Chrome (default)")
    browser_group.add_argument("--no-browser", dest="browser", action="store_false", help="use plain requests instead")
    parser.set_defaults(browser=True)
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH, help=f"Chrome executable path (default: {DEFAULT_CHROME_PATH})")
    parser.add_argument("--user-data-dir", help="persistent Chrome profile directory for --browser")
    headed_group = parser.add_mutually_exclusive_group()
    headed_group.add_argument("--headed", dest="headed", action="store_true", help="show the Chrome window (default)")
    headed_group.add_argument("--headless", dest="headed", action="store_false", help="run Chrome without a window")
    parser.set_defaults(headed=True)
    parser.add_argument("--verbose", action="store_true", help="show scraping, LLM, and file-writing progress")
    args = parser.parse_args()
    if args.user_data_dir is None:
        args.user_data_dir = DEFAULT_BROWSER_PROFILE

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Starting classification for %s", args.url)

    scraper = ForumScraper(
        delay=args.delay,
        browser=args.browser,
        chrome_path=args.chrome_path,
        headed=args.headed,
        user_data_dir=args.user_data_dir,
        include_images=args.images,
    )
    classifier = LocalClassifier(args.llm_url, args.model, timeout=args.llm_timeout)
    seen: set[str] = set()
    total = 0
    try:
        for comment in scraper.comments(args.url, max_pages=args.max_pages):
            if comment.comment_id in seen:
                logging.info("Skipping duplicate comment %s", comment.comment_id)
                continue
            seen.add(comment.comment_id)
            classification = classifier.classify(comment)
            path = save_comment(args.output_dir, comment, classification)
            total += 1
            print(f"{comment.comment_id}: {classification.category} -> {path}")
    except ForumAccessError as error:
        parser.error(str(error))
    print(f"Processed {total} comments")


if __name__ == "__main__":
    main()
