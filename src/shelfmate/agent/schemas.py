from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class PriceOffer(BaseModel):
    title: str
    store: str
    format: Literal["hardcover", "paperback", "audiobook"]
    condition: Literal["new", "used"]
    price_inr: float = Field(gt=0, lt=20000)
    url: HttpUrl
    checked_at: datetime
