from shelfmate.flows.pipeline import email_html


def test_email_escapes_text_from_the_web():
    book = {
        "title": "<script>x</script>",
        "author": "A & B",
        "because": "Next in Dune",
        "offers": [
            {
                "price_inr": 1299.0,
                "url": 'https://amazon.in/"onmouseover',
                "store": "amazon.in",
                "condition": "new",
                "format": "paperback",
            },
            {
                "price_inr": 2000.0,
                "url": "https://flipkart.com/x",
                "store": "flipkart.com",
                "condition": "new",
                "format": "hardcover",
            },
        ],
    }
    html = email_html([book, {**book, "offers": []}])
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "A &amp; B" in html
    assert 'href="https://amazon.in/&quot;onmouseover"' in html
    assert "Rs 1,299 at" in html and "2,000" not in html  # only the cheapest
    assert "No price found yet." in html
