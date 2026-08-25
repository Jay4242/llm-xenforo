# Forum Comment Classifier

Scrapes comments from a XenForo thread and sends each comment separately to an OpenAI-compatible local LLM endpoint. Results are appended to one UTF-8 text file per classification, with author, date, source URL, summary, subjects, and original text.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test,browser]'
```

The `browser` extra installs Playwright; it uses the system Chrome executable when `--chrome-path` is supplied. The non-browser fallback uses plain `requests`.

## Run

Start the backend at `http://127.0.0.1:8080/v1`, then run:

```bash
forum-classify 'https://www.diyaudio.com/community/threads/finally-an-affordable-cd-transport-the-shigaclone-story.120229/'
```

This forum currently presents a JavaScript bot guard to HTTP clients. Browser mode, installed Chrome, headed mode, and a persistent profile are the defaults for this project, so the short command is sufficient:

```bash
forum-classify \
  'https://www.diyaudio.com/community/threads/finally-an-affordable-cd-transport-the-shigaclone-story.120229/'
```

The default profile is `~/.cache/forum-classifier/chrome-profile`. Browser mode waits for the message elements to appear before handing the rendered HTML to the same parser used by the requests mode. Use `--headless` for unattended operation, or `--no-browser` to force the plain `requests` path.

Useful options:

```text
--output-dir classified-comments   destination directory
--llm-url URL                      OpenAI-compatible /v1 base URL
--model NAME                       model name expected by the backend
--llm-timeout SECONDS              LLM request timeout (default: 600)
--max-pages N                      limit pagination while testing
--delay SECONDS                    delay between forum page requests (default: 1)
--images                           send comment images to the multimodal LLM (default)
--no-images                        do not download or send comment images
--verbose                          show scraping, LLM, and file-writing progress
--browser                          use Playwright with Chrome (default)
--no-browser                       use plain requests instead
--chrome-path PATH                 Chrome executable (default: /usr/bin/google-chrome)
--user-data-dir PATH               persistent Chrome profile
--headed                           show the browser window (default)
--headless                         run Chrome without a window
```

The classifier calls `POST /chat/completions` and expects a JSON response in the normal `choices[0].message.content` shape. It requests JSON containing `category`, `summary`, `subjects`, and `confidence`.

Images attached inside comments are downloaded into memory and sent as base64 image inputs by default. Images are never written to disk. Use `--no-images` to disable this behavior. The local model must support OpenAI-compatible multimodal chat content when images are enabled.

## Development

```bash
pytest
```

Be mindful of the forum's terms, robots policy, rate limits, and any applicable copyright or privacy requirements before running a large crawl.
