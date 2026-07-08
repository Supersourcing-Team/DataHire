from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    content: str
    notification_type: str
    action_url: Optional[str] = None
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationPreferenceResponse(BaseModel):
    notification_type: str
    email_enabled: bool
    in_app_enabled: bool
    sms_enabled: bool

    class Config:
        from_attributes = True


class NotificationPreferenceUpdate(BaseModel):
    notification_type: str
    email_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
