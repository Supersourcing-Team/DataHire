import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, DECIMAL, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    
    stripe_checkout_session_id = Column(String(255), nullable=True, unique=True, index=True)
    stripe_payment_intent_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    stripe_invoice_id = Column(String(255), nullable=True, index=True)
    
    amount = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="usd")
    payment_method = Column(String(50), nullable=True)  # 'card', 'paypal', 'apple_pay', 'google_pay', etc.
    payment_status = Column(String(50), nullable=False, default="pending")  # 'pending', 'succeeded', 'failed', 'refunded'
    
    plan_tier = Column(String(50), nullable=True)  # 'pro', 'premium', 'startup', etc.
    subscription_plan_id = Column(Integer, ForeignKey("meta_subscription_plans.id", ondelete="SET NULL"), nullable=True)
    
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User")
    candidate = relationship("Candidate")
    company = relationship("Company")
    subscription_plan = relationship("MetaSubscriptionPlan")

    def __repr__(self):
        return f"<Transaction(id={self.id}, amount={self.amount}, status={self.payment_status})>"
