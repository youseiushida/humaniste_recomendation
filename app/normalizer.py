from __future__ import annotations

import re
from bs4 import BeautifulSoup
from typing import Tuple
from openai import OpenAI
from .config import settings


SYSTEM_PROMPT = (
    "あなたは歴史・人文学分野に精通した編集者かつ学術ライターです。"
    "与えられた記事テキストを、体裁の違い（対談/学会評/書評/展覧会評/研究/随筆など）を吸収して、"
    "内容を正確に維持したまま日本語で一貫性ある標準形に整えます。"
    "事実の追加・憶測は禁止。UIや広告などノイズは削除。見出しは簡潔。"
    "出力は章立ての自然言語で、特に『11) 正規化本文』を明確に示してください。"
)


USER_TEMPLATE = (
    "入力情報:\n"
    "- タイトル: {title}\n"
    "- 投稿日時: {published_at}\n"
    "- 著者/参加者: {authors}\n"
    "- 種別ヒント: {type_hint}\n\n"
    "本文:\n" + "```\n{article_text}\n```\n\n"
    "タスク:\n1) 指示どおりに章立てで自然言語の標準形へ整形\n"
    "2) 曖昧・不明は『不明』と記載\n"
    "3) 最後に『11) 正規化本文』を必ず含める\n"
)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # Remove scripts/styles/nav/footer/header likely noise
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    # Drop common share/UI phrases quickly
    text = re.sub(r"(シェア|共有|COPY|著作権|All rights reserved).*$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    return text


def extract_normalized_body(full_output: str) -> Tuple[str, str]:
    """Return (normalized_body, summary_section_or_empty)."""
    # Capture from line starting with '11) 正規化本文' to next numbered heading or end
    body_match = re.search(r"^\s*11\)\s*正規化本文\s*\n([\s\S]*)", full_output, re.MULTILINE)
    normalized_body = ""
    if body_match:
        body = body_match.group(1)
        next_heading = re.search(r"^\s*1[2-9]\)\s*", body, re.MULTILINE)
        normalized_body = body[: next_heading.start()] if next_heading else body
    normalized_body = normalized_body.strip()
    # Optional: capture short summary
    summary_match = re.search(r"^\s*3\)\s*要約\s*\n([\s\S]*?)(?:^\s*4\)|\Z)", full_output, re.MULTILINE)
    summary = (summary_match.group(1).strip() if summary_match else "")
    return normalized_body, summary


async def normalize_article(
    title: str,
    raw_html_or_text: str,
    published_at: str | None = None,
    authors: str | None = None,
    type_hint: str | None = None,
) -> tuple[str, str, str]:
    """Return (normalized_text, summary, full_output)."""
    article_text = html_to_text(raw_html_or_text)

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    user_prompt = USER_TEMPLATE.format(
        title=title or "",
        published_at=published_at or "",
        authors=authors or "",
        type_hint=type_hint or "",
        article_text=article_text,
    )

    resp = client.responses.create(
        model=settings.OPENAI_NORMALIZE_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    full_out: str = resp.output_text  # type: ignore[attr-defined]
    normalized, summary = extract_normalized_body(full_out)
    # Fallback: if no explicit normalized body, use the whole cleaned article
    if not normalized:
        normalized = article_text
    return normalized, summary, full_out


