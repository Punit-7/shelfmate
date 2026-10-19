from shelfmate import notify


def test_recommendations_go_to_the_recipient_not_the_sender(monkeypatch):
    monkeypatch.setattr(notify.settings, "email_address", "sender@example.com")
    msg = notify.build_message("Subject", "<p>hi</p>", to="reader@example.com")
    assert msg["From"] == "sender@example.com"
    assert msg["To"] == "reader@example.com"
