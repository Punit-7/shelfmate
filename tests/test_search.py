from shelfmate.agent.search import on_store, selling_price


def test_selling_price_skips_mrp_and_discounts():
    assert selling_price("M.R.P.: ₹599 ₹349 (42% off)") == "349"
    assert selling_price("Save ₹250, now ₹349") == "349"
    assert selling_price("₹250 off today, Rs. 1,299.00") == "1,299.00"
    assert selling_price("Paperback. ₹495.00 with 38 percent savings") == "495.00"
    assert selling_price("no price here") is None


def test_on_store_checks_the_host():
    assert on_store("https://www.amazon.in/dp/1", "amazon.in")
    assert on_store("https://amazon.in/x", "amazon.in")
    assert not on_store("https://notamazon.in/x", "amazon.in")
    assert not on_store("https://blog.com/amazon.in", "amazon.in")
