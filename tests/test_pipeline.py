from shelfmate.flows.pipeline import email_html


def test_email_escapes_text_from_the_web():
    book = {
        "title": "<script>x</script>",
        "author": "A & B",
        "because": "Next in Dune",
        "shops": [
            {"store": "amazon.in", "url": 'https://amazon.in/"onmouseover'},
            {"store": "<b>flipkart</b>", "url": "https://flipkart.com/x"},
        ],
    }
    html = email_html([book])
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "A &amp; B" in html
    assert 'href="https://amazon.in/&quot;onmouseover"' in html
    assert "&lt;b&gt;flipkart&lt;/b&gt;" in html
