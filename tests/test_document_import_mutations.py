"""Boundary and failure-path checks for local statement import."""

import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parent.parent / "services" / "document_import.py"
SPEC = importlib.util.spec_from_file_location("document_import_under_test", SOURCE)
document_import = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = document_import
SPEC.loader.exec_module(document_import)


def test_validate_document_rejects_empty_and_wrong_image_signatures():
    for filename, content, message in [
        ("Harbor-Kite.txt", b"detail", "Supported"),
        ("Harbor-Kite.png", b"", "empty"),
        ("Harbor-Kite.pdf", b"wrong", "valid PDF"),
        ("Harbor-Kite.png", b"wrong", "valid PNG"),
        ("Harbor-Kite.jpg", b"wrong", "valid JPEG"),
    ]:
        with pytest.raises(ValueError, match=message):
            document_import._validate_document(filename, content)


def test_validate_document_accepts_exact_size_limit_and_returns_extension():
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (document_import.MAX_DOCUMENT_BYTES - 8)
    assert document_import._validate_document("Harbor-Kite.PNG", content) == ".png"


def _vision_mocks(monkeypatch, *, source=True, image=True, performed=True,
                  width=100, height=100, observations=()):
    class Request:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

        def setRecognitionLevel_(self, value):
            pass

        def setUsesLanguageCorrection_(self, value):
            pass

        def results(self):
            return observations

    class Handler:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithCGImage_options_(self, image_value, options):
            return self

        def performRequests_error_(self, requests, options):
            return performed

    objc = SimpleNamespace(
        loadBundle=lambda *args, **kwargs: None,
        lookUpClass=lambda name: Request if name == "VNRecognizeTextRequest" else Handler,
    )
    quartz = SimpleNamespace(
        kCGImagePropertyPixelWidth="width",
        kCGImagePropertyPixelHeight="height",
        CGImageSourceCreateWithData=lambda data, options: object() if source else None,
        CGImageSourceCopyPropertiesAtIndex=lambda value, index, options:
            {"width": width, "height": height},
        CGImageSourceCreateImageAtIndex=lambda value, index, options:
            object() if image else None,
    )
    monkeypatch.setitem(sys.modules, "objc", objc)
    monkeypatch.setitem(sys.modules, "Quartz", quartz)


def _observation(y, x, text):
    candidates = [] if text is None else [SimpleNamespace(string=lambda: text)]
    return SimpleNamespace(
        topCandidates_=lambda count: candidates,
        boundingBox=lambda: SimpleNamespace(origin=SimpleNamespace(y=y, x=x)),
    )


def test_vision_ocr_reports_decode_render_and_request_errors(monkeypatch):
    for options, message in [
        ({"source": False}, "decode"),
        ({"image": False}, "render"),
        ({"performed": False}, "recognize"),
    ]:
        _vision_mocks(monkeypatch, **options)
        with pytest.raises((ValueError, RuntimeError), match=message):
            document_import._vision_ocr(b"invented image")


def test_vision_ocr_allows_exact_pixel_limit(monkeypatch):
    _vision_mocks(monkeypatch, width=document_import.MAX_IMAGE_PIXELS, height=1)
    assert document_import._vision_ocr(b"invented image") == ""


def test_vision_ocr_groups_nearby_words_and_skips_empty_candidates(monkeypatch):
    observations = [
        _observation(0.8, 0.7, "Kite"),
        _observation(0.795, 0.1, "Harbor"),
        _observation(0.6, 0.2, "42.00"),
        _observation(0.5, 0.2, None),
    ]
    _vision_mocks(monkeypatch, observations=observations)
    assert document_import._vision_ocr(b"invented image") == "Harbor Kite\n42.00"


def _pdf_mocks(monkeypatch, page_texts):
    class TextPage:
        def __init__(self, text):
            self.text = text

        def get_text_range(self):
            return self.text

        def close(self):
            pass

    class Bitmap:
        def to_pil(self):
            return SimpleNamespace(save=lambda stream, format: stream.write(b"PNG"))

        def close(self):
            pass

    class Page:
        def __init__(self, text):
            self.text = text

        def get_textpage(self):
            return TextPage(self.text)

        def get_size(self):
            return 600, 800

        def render(self, scale):
            return Bitmap()

        def close(self):
            pass

    class PDF:
        def __len__(self):
            return len(page_texts)

        def __getitem__(self, index):
            return Page(page_texts[index])

        def close(self):
            pass

    pdfium = SimpleNamespace(PdfDocument=lambda content: PDF())
    monkeypatch.setitem(sys.modules, "pypdfium2", pdfium)


def test_extract_document_rejects_blank_image_and_reads_valid_image(monkeypatch):
    content = b"\x89PNG\r\n\x1a\nplaceholder"
    monkeypatch.setattr(document_import, "_vision_ocr", lambda value: "   ")
    with pytest.raises(ValueError, match="No readable text"):
        document_import.extract_document("Harbor-Kite.png", content)
    monkeypatch.setattr(document_import, "_vision_ocr", lambda value: "Harbor Kite 42.00")
    result = document_import.extract_document("Harbor-Kite.png", content)
    assert result.text == "Harbor Kite 42.00"
    assert (result.page_count, result.ocr_pages) == (1, 1)


def test_extract_document_accepts_exact_page_limit(monkeypatch):
    _pdf_mocks(monkeypatch, ["Harbor Kite entry 42.00 posted today"] * 50)
    result = document_import.extract_document("Harbor-Kite.pdf", b"%PDFlocal")
    assert result.page_count == 50
    assert result.native_text_pages == 50


def test_extract_document_uses_native_text_at_exact_threshold(monkeypatch):
    _pdf_mocks(monkeypatch, ["A" * 30])
    monkeypatch.setattr(document_import, "_vision_ocr", lambda value:
                        (_ for _ in ()).throw(AssertionError("unexpected OCR")))
    result = document_import.extract_document("Harbor-Kite.pdf", b"%PDFlocal")
    assert (result.native_text_pages, result.ocr_pages) == (1, 0)


def test_extract_document_warns_for_empty_ocr_page(monkeypatch):
    _pdf_mocks(monkeypatch, [""])
    monkeypatch.setattr(document_import, "_vision_ocr", lambda value: "")
    result = document_import.extract_document("Harbor-Kite.pdf", b"%PDFlocal")
    assert result.warnings == ["Page 1: no readable text found."]
    assert result.ocr_pages == 1


def test_parse_date_returns_none_for_invalid_value():
    assert document_import._parse_date("02/30/2026", 2026) is None


def test_parse_statement_text_preserves_source_limit():
    line = "01/05 Harbor Kite 42.00 " + "Z" * 500
    transactions, skipped = document_import.parse_statement_text(line, 2026)
    assert skipped == []
    assert transactions[0]["source_text"] == line[:500]


def test_parse_statement_text_limits_description():
    description = "Harbor Kite " + "X" * 205
    transactions, skipped = document_import.parse_statement_text(
        f"01/05 {description} 42.00", 2026
    )
    assert skipped == []
    assert transactions[0]["description"] == description[:200]


def _fake_ai(monkeypatch, rows):
    class Messages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"transactions": rows})])

    class Anthropic:
        def __init__(self, api_key):
            self.messages = Messages()

    monkeypatch.setattr("anthropic.Anthropic", Anthropic)


def test_parse_statement_with_ai_accepts_exact_text_limit(monkeypatch):
    _fake_ai(monkeypatch, [{"date": "2026-04-03", "description": "Harbor Kite",
                            "amount": 42.0}])
    result = document_import.parse_statement_with_ai(
        "x" * document_import.MAX_AI_TEXT_CHARS, "Asset", "offline-key", "fake-model"
    )
    assert result[0]["date"] == date(2026, 4, 3)


def test_parse_statement_with_ai_skips_invalid_rows(monkeypatch):
    _fake_ai(monkeypatch, [
        {"date": "invalid", "description": "Harbor Kite", "amount": 1},
        {"date": "2026-04-03", "description": "Bay Lantern", "amount": -18.5},
    ])
    result = document_import.parse_statement_with_ai(
        "invented statement", "Asset", "offline-key", "fake-model"
    )
    assert [(row["description"], row["amount"]) for row in result] == [
        ("Bay Lantern", -18.5)
    ]
