import datetime
import stripe
import os
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, Response
from sqlalchemy.orm import Session
from typing import Optional

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.payment import Transaction
from app.models.meta import MetaSubscriptionPlan

# Configure Stripe key
stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/billing", tags=["billing"])

@router.post("/create-checkout-session", status_code=status.HTTP_200_OK)
async def create_checkout_session(
    plan_tier: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Checkout Session for subscription plans.
    Supports Card, Apple Pay, Google Pay, and PayPal automatically.
    """
    if not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY == "sk_test_placeholder_key":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured on this server."
        )

    if current_user.role == "candidate":
        candidate = current_user.candidate
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate profile not found"
            )
        
        if plan_tier not in ["pro", "premium"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid plan tier for candidate. Choose 'pro' or 'premium'."
            )
        
        price_id = settings.candidate_stripe_prices.get(plan_tier)
        if not price_id or "placeholder" in price_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stripe Price ID for plan '{plan_tier}' is not configured."
            )
        
        # Create/get customer
        customer_id = candidate.stripe_customer_id
        if not customer_id:
            try:
                customer = stripe.Customer.create(
                    email=current_user.email,
                    name=candidate.full_name,
                    metadata={"candidate_id": str(candidate.id), "user_id": str(current_user.id)}
                )
                customer_id = customer.id
                candidate.stripe_customer_id = customer_id
                db.commit()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create Stripe customer: {str(e)}"
                )
        
        # Create Checkout Session
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                line_items=[{
                    "price": price_id,
                    "quantity": 1
                }],
                mode="subscription",
                success_url=f"{settings.FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{settings.FRONTEND_URL}/billing/cancel",
                automatic_payment_methods={"enabled": True},
                metadata={
                    "role": "candidate",
                    "candidate_id": str(candidate.id),
                    "plan_tier": plan_tier,
                    "user_id": str(current_user.id)
                }
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create Stripe checkout session: {str(e)}"
            )
        
        # Find the plan details from MetaSubscriptionPlan if available
        plan = db.query(MetaSubscriptionPlan).filter(MetaSubscriptionPlan.name.ilike(plan_tier)).first()
        
        # Create pending transaction record
        transaction = Transaction(
            user_id=current_user.id,
            candidate_id=candidate.id,
            stripe_checkout_session_id=session.id,
            amount=plan.price if plan else 0.0,
            currency=plan.currency.code.lower() if (plan and plan.currency) else "usd",
            payment_status="pending",
            plan_tier=plan_tier,
            subscription_plan_id=plan.id if plan else None
        )
        db.add(transaction)
        db.commit()
        
        return {"checkout_url": session.url}

    elif current_user.role == "employer":
        employer = current_user.employer
        if not employer or not employer.company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company profile not found. Please complete company onboarding first."
            )
        company = employer.company
        
        if plan_tier not in ["startup", "msme", "enterprise"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid plan tier for company. Choose 'startup', 'msme', or 'enterprise'."
            )
        
        price_id = settings.company_stripe_prices.get(plan_tier)
        if not price_id or "placeholder" in price_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stripe Price ID for plan '{plan_tier}' is not configured."
            )
        
        # Create/get customer for the Company
        customer_id = company.stripe_customer_id
        if not customer_id:
            try:
                customer = stripe.Customer.create(
                    email=company.alternate_email or current_user.email,
                    name=company.name,
                    metadata={"company_id": str(company.id), "employer_user_id": str(current_user.id)}
                )
                customer_id = customer.id
                company.stripe_customer_id = customer_id
                db.commit()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create Stripe customer for company: {str(e)}"
                )
        
        # Create Checkout Session
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                line_items=[{
                    "price": price_id,
                    "quantity": 1
                }],
                mode="subscription",
                success_url=f"{settings.FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{settings.FRONTEND_URL}/billing/cancel",
                automatic_payment_methods={"enabled": True},
                metadata={
                    "role": "employer",
                    "company_id": str(company.id),
                    "plan_tier": plan_tier,
                    "user_id": str(current_user.id)
                }
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create Stripe checkout session: {str(e)}"
            )
        
        # Find the plan details from MetaSubscriptionPlan if available
        plan = db.query(MetaSubscriptionPlan).filter(MetaSubscriptionPlan.name.ilike(plan_tier)).first()
        
        # Create pending transaction record
        transaction = Transaction(
            user_id=current_user.id,
            company_id=company.id,
            stripe_checkout_session_id=session.id,
            amount=plan.price if plan else 0.0,
            currency=plan.currency.code.lower() if (plan and plan.currency) else "usd",
            payment_status="pending",
            plan_tier=plan_tier,
            subscription_plan_id=plan.id if plan else None
        )
        db.add(transaction)
        db.commit()
        
        return {"checkout_url": session.url}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role for subscription creation."
        )

@router.post("/create-portal-session", status_code=status.HTTP_200_OK)
async def create_portal_session(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Customer Portal Session for billing management.
    """
    if not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY == "sk_test_placeholder_key":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured on this server."
        )

    customer_id = None
    if current_user.role == "candidate":
        candidate = current_user.candidate
        if candidate:
            customer_id = candidate.stripe_customer_id
    elif current_user.role == "employer":
        employer = current_user.employer
        if employer and employer.company:
            customer_id = employer.company.stripe_customer_id

    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Stripe billing details found. You must check out first."
        )

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.FRONTEND_URL}/billing"
        )
        return {"portal_url": session.url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}"
        )

@router.get("/status")
async def get_billing_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's billing status, plan details, and transaction history.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if current_user.role == "candidate":
        candidate = current_user.candidate
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate profile not found")
        
        transactions = db.query(Transaction).filter(
            Transaction.candidate_id == candidate.id
        ).order_by(Transaction.created_at.desc()).all()
        
        has_active_sub = (
            candidate.plan_tier != "free" and 
            (candidate.subscription_ends_at is None or candidate.subscription_ends_at > now)
        )
        
        return {
            "role": "candidate",
            "plan_tier": candidate.plan_tier,
            "subscription_ends_at": candidate.subscription_ends_at,
            "has_active_subscription": has_active_sub,
            "transactions": [
                {
                    "id": str(tx.id),
                    "amount": float(tx.amount),
                    "currency": tx.currency,
                    "status": tx.payment_status,
                    "payment_method": tx.payment_method,
                    "plan_tier": tx.plan_tier,
                    "created_at": tx.created_at
                } for tx in transactions
            ]
        }
    elif current_user.role == "employer":
        employer = current_user.employer
        if not employer or not employer.company:
            raise HTTPException(status_code=404, detail="Company profile not found")
        
        company = employer.company
        transactions = db.query(Transaction).filter(
            Transaction.company_id == company.id
        ).order_by(Transaction.created_at.desc()).all()
        
        has_active_sub = (
            company.plan_tier != "free" and 
            (company.subscription_ends_at is None or company.subscription_ends_at > now)
        )
        
        return {
            "role": "employer",
            "company_id": str(company.id),
            "plan_tier": company.plan_tier,
            "subscription_ends_at": company.subscription_ends_at,
            "has_active_subscription": has_active_sub,
            "transactions": [
                {
                    "id": str(tx.id),
                    "amount": float(tx.amount),
                    "currency": tx.currency,
                    "status": tx.payment_status,
                    "payment_method": tx.payment_method,
                    "plan_tier": tx.plan_tier,
                    "created_at": tx.created_at
                } for tx in transactions
            ]
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid user role for billing")

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db)
):
    """
    Handle Stripe Webhooks to update database upon payment success/failure.
    """
    if not settings.STRIPE_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET == "whsec_placeholder_secret":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured."
        )

    payload = await request.body()
    
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type = event["type"]
    data_object = event["data"]["object"]

    import uuid

    if event_type == "checkout.session.completed":
        session_id = data_object["id"]
        metadata = data_object.get("metadata", {})
        role = metadata.get("role")
        plan_tier = metadata.get("plan_tier")
        
        user_id_str = metadata.get("user_id")
        user_id = uuid.UUID(user_id_str) if user_id_str else None
        
        subscription_id = data_object.get("subscription")
        customer_id = data_object.get("customer")
        
        # Find or create transaction
        transaction = db.query(Transaction).filter(
            Transaction.stripe_checkout_session_id == session_id
        ).first()
        
        if not transaction:
            transaction = Transaction(
                stripe_checkout_session_id=session_id,
                user_id=user_id,
                plan_tier=plan_tier
            )
            db.add(transaction)
        
        # Update transaction fields
        transaction.stripe_subscription_id = subscription_id
        transaction.stripe_payment_intent_id = data_object.get("payment_intent")
        transaction.amount = (data_object.get("amount_total") or 0) / 100.0
        transaction.currency = data_object.get("currency", "usd")
        
        pm_types = data_object.get("payment_method_types", [])
        transaction.payment_method = pm_types[0] if pm_types else "card"
        transaction.payment_status = "succeeded"
        
        # Set subscription end date to 30 days from now as a default
        ends_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
        
        # Process based on role
        if role == "candidate":
            candidate_id_str = metadata.get("candidate_id")
            candidate_id = uuid.UUID(candidate_id_str) if candidate_id_str else None
            candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            if candidate:
                candidate.plan_tier = plan_tier
                candidate.stripe_customer_id = customer_id
                candidate.stripe_subscription_id = subscription_id
                candidate.subscription_ends_at = ends_at
                transaction.candidate_id = candidate.id
                
                # Trigger plan upgrade email notification
                from app.tasks.notifications import send_email_task
                send_email_task.delay(
                    to_email=candidate.user.email,
                    template_name_or_id="emails/plan_upgrade.html",
                    template_data={"name": candidate.full_name, "plan_name": plan_tier.capitalize()},
                    subject="Your Plan Has Been Upgraded!"
                )
        elif role == "employer":
            company_id_str = metadata.get("company_id")
            company_id = uuid.UUID(company_id_str) if company_id_str else None
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                company.plan_tier = plan_tier
                company.stripe_customer_id = customer_id
                company.stripe_subscription_id = subscription_id
                company.subscription_ends_at = ends_at
                company.subscription_duration_months = 1
                transaction.company_id = company.id
                
                # Trigger plan upgrade email notification
                from app.tasks.notifications import send_email_task
                for emp in company.employers:
                    send_email_task.delay(
                        to_email=emp.user.email,
                        template_name_or_id="emails/plan_upgrade.html",
                        template_data={"name": emp.contact_person or emp.user.email, "plan_name": plan_tier.capitalize()},
                        subject="Your Company Plan Has Been Upgraded!"
                    )
                
        db.commit()

    elif event_type in ["customer.subscription.updated", "customer.subscription.deleted"]:
        subscription_id = data_object["id"]
        status_str = data_object["status"]
        current_period_end = data_object.get("current_period_end")
        
        ends_at = datetime.datetime.fromtimestamp(current_period_end, datetime.timezone.utc) if current_period_end else None
        
        candidate = db.query(Candidate).filter(Candidate.stripe_subscription_id == subscription_id).first()
        company = db.query(Company).filter(Company.stripe_subscription_id == subscription_id).first()
        
        if status_str in ["canceled", "unpaid"]:
            if candidate:
                candidate.plan_tier = "free"
                candidate.subscription_ends_at = None
                candidate.stripe_subscription_id = None
            if company:
                company.plan_tier = "free"
                company.subscription_ends_at = None
                company.stripe_subscription_id = None
                company.subscription_duration_months = 0
        else:
            if candidate:
                candidate.subscription_ends_at = ends_at
            if company:
                company.subscription_ends_at = ends_at
        
        # Log transaction renewal
        past_tx = db.query(Transaction).filter(Transaction.stripe_subscription_id == subscription_id).first()
        transaction = Transaction(
            stripe_subscription_id=subscription_id,
            user_id=past_tx.user_id if past_tx else None,
            candidate_id=candidate.id if candidate else None,
            company_id=company.id if company else None,
            amount=(data_object.get("plan", {}).get("amount") or 0) / 100.0,
            currency=data_object.get("plan", {}).get("currency", "usd"),
            payment_status="succeeded" if status_str in ["active", "trialing"] else "failed",
            plan_tier=candidate.plan_tier if candidate else (company.plan_tier if company else None)
        )
        db.add(transaction)
        db.commit()

    return {"status": "success"}

@router.get("/invoices", status_code=status.HTTP_200_OK)
async def list_invoices(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List Stripe invoices for the current candidate or company.
    """
    if not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY == "sk_test_placeholder_key":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured on this server."
        )

    customer_id = None
    if current_user.role == "candidate":
        candidate = current_user.candidate
        if candidate:
            customer_id = candidate.stripe_customer_id
    elif current_user.role == "employer":
        employer = current_user.employer
        if employer and employer.company:
            customer_id = employer.company.stripe_customer_id

    if not customer_id:
        return []

    try:
        invoices = stripe.Invoice.list(customer=customer_id, limit=24)
        return [
            {
                "id": inv.id,
                "number": inv.number,
                "amount_paid": inv.amount_paid / 100.0 if inv.amount_paid is not None else 0.0,
                "currency": inv.currency,
                "status": inv.status,
                "hosted_invoice_url": inv.hosted_invoice_url,
                "invoice_pdf": inv.invoice_pdf,
                "created": inv.created
            }
            for inv in invoices.data
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch invoices from Stripe: {str(e)}"
        )

@router.get("/.well-known/apple-developer-merchantid-domain-association")
def apple_pay_verification():
    """
    Serve the Apple Pay developer domain verification file dynamically.
    """
    file_path = "app/templates/apple-developer-merchantid-domain-association"
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return Response(content=f.read(), media_type="text/plain")
    # Return a default signature placeholder if the file hasn't been uploaded yet
    return Response(content="placeholder-stripe-apple-verification-data", media_type="text/plain")
