from pydantic import BaseModel
from typing import Any, Optional

class APIBaseRequest(BaseModel):
    """Base class for all API request bodies."""
    pass

class APIBaseResponse(BaseModel):
    """Base class for all API response bodies."""
    message: Optional[str] = None
    data: Optional[Any] = None

    class Config:
        arbitrary_types_allowed = True
