from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any


class JsonScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.documents: list[Any] = []
        self._capture = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        values = dict(attrs)
        self._capture = values.get("type") in {"application/ld+json", "application/json"}
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._capture:
            return
        try:
            self.documents.append(json.loads("".join(self._parts)))
        except (json.JSONDecodeError, TypeError):
            pass
        self._capture = False
        self._parts = []


def json_documents(html: str) -> list[Any]:
    parser = JsonScriptParser()
    parser.feed(html)
    return parser.documents


def walk_json(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)
