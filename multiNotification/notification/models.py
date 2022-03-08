from typing import Optional
from pydantic import BaseModel
from typing import Protocol


class FormatFunction(Protocol):
    def __call__(self, service, *args, **kwargs) -> str:
        ...


class NotificationSettings(BaseModel):
    message: Optional[bool] = True

    error: Optional[bool] = True
    warning: Optional[bool] = False
    info: Optional[bool] = False
    debug: Optional[bool] = False


class NotificationAuth(BaseModel):
    endpoint: Optional[str] = None
    chat_id: Optional[int] = None


class NotificationModel(BaseModel):
    service: str
    enabled: bool
    settings: Optional[NotificationSettings] = None
    auth: Optional[NotificationAuth] = None
