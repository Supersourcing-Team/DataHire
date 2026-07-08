import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, Text, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    notification_type = Column(String(50), nullable=False) # e.g. 'welcome_email', 'auto_apply_success'
    action_url = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, title={self.title}, is_read={self.is_read})>"


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = Column(String(50), nullable=False)
    
    email_enabled = Column(Boolean, default=True, nullable=False)
    in_app_enabled = Column(Boolean, default=True, nullable=False)
    sms_enabled = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="notification_preferences")

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "notification_type", name="pk_user_notification_pref"),
    )

    def __repr__(self):
        return f"<NotificationPreference(user_id={self.user_id}, type={self.notification_type}, email={self.email_enabled})>"
