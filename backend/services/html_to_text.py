# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Convert simple HTML to plain text / lightweight markdown.

Uses only stdlib html.parser — no external dependencies.
Handles the common tags found in task descriptions: headings,
paragraphs, bold/italic, lists, links, line breaks.
"""

from html.parser import HTMLParser


class _HTMLToMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self._parts.append("\n" + "#" * level + " ")
        elif tag == "p" or tag == "br":
            self._parts.append("\n")
        elif tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
            self._parts.append("*")
        elif tag == "li":
            self._parts.append("\n- ")
        elif tag in ("ul", "ol"):
            self._parts.append("\n")
        elif tag == "a":
            href = dict(attrs).get("href", "")
            self._parts.append("[")
            self._tag_stack[-1] = f"a:{href}"
        elif tag == "code":
            self._parts.append("`")
        elif tag == "pre":
            self._parts.append("\n```\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") or tag == "p":
            self._parts.append("\n")
        elif tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
            self._parts.append("*")
        elif tag in ("ul", "ol"):
            self._parts.append("\n")
        elif tag == "code":
            self._parts.append("`")
        elif tag == "pre":
            self._parts.append("\n```\n")
        elif tag == "a":
            href = ""
            if self._tag_stack and self._tag_stack[-1].startswith("a:"):
                href = self._tag_stack[-1][2:]
            self._parts.append(f"]({href})" if href else "]")

        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse excessive blank lines
        lines = raw.split("\n")
        result: list[str] = []
        blank_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_count += 1
                if blank_count <= 2:
                    result.append("")
            else:
                blank_count = 0
                result.append(stripped)
        return "\n".join(result).strip()


def html_to_text(html: str | None) -> str:
    """Convert HTML string to markdown-flavoured plain text.

    Returns the original string unchanged if it contains no HTML tags.
    """
    if not html:
        return html or ""
    # Quick check: if no HTML tags at all, return as-is
    if "<" not in html:
        return html
    parser = _HTMLToMarkdown()
    parser.feed(html)
    return parser.get_text()