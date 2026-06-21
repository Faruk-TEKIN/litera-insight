from backend.app.services.telegram_bot_service import TelegramBotService


def test_send_document_supports_pdf_bytes():
    service = TelegramBotService.__new__(TelegramBotService)
    captured = {}

    def fake_post_multipart(method, data, files):
        captured["method"] = method
        captured["data"] = data
        captured["files"] = files
        return {"message_id": 123}

    service._post_multipart = fake_post_multipart

    result = service.send_document(
        "42",
        "weeks_best.pdf",
        b"%PDF-1.4",
        mime_type="application/pdf",
        caption="Full PDF",
    )

    assert result == {"message_id": 123}
    assert captured["method"] == "sendDocument"
    assert captured["data"] == {"chat_id": "42", "caption": "Full PDF"}
    filename, file_obj, mime_type = captured["files"]["document"]
    assert filename == "weeks_best.pdf"
    assert file_obj.getvalue() == b"%PDF-1.4"
    assert mime_type == "application/pdf"
