from pydantic import BaseModel


class APIBaseRequest(BaseModel):
    """Base class for all API request bodies."""

    pass


class APIBaseResponse(BaseModel):
    """Base class for all API response bodies."""

    message: str | None = None

    class Config:
        arbitrary_types_allowed = True
