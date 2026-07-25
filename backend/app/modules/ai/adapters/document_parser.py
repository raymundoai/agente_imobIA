from pathlib import Path

from app.modules.ai.domain.ports import DocumentParserPort


class PlainTextDocumentParser(DocumentParserPort):
    SUPPORTED = {".txt", ".md", ".markdown", ".pdf", ".docx"}

    def parse(self, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            return content.decode("utf-8", errors="ignore")
        if suffix == ".pdf":
            return self._parse_pdf(content)
        if suffix == ".docx":
            return self._parse_docx(content)
        raise ValueError("Unsupported knowledge document type")

    @staticmethod
    def _parse_pdf(content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ModuleNotFoundError as exc:
            raise RuntimeError("PDF parsing requires pypdf") from exc
        from io import BytesIO

        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def _parse_docx(content: bytes) -> str:
        try:
            import docx
        except ModuleNotFoundError as exc:
            raise RuntimeError("DOCX parsing requires python-docx") from exc
        from io import BytesIO

        document = docx.Document(BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
