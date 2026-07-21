from fastapi import APIRouter, Depends, HTTPException, status, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timezone
from typing import List, Optional

from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.core.security import verify_token
from app.core.websocket_manager import manager
from app.models.user import User
from app.models.notification import Notification, NotificationPreference
from app.schemas.notification import (
    NotificationResponse,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate
)

router = APIRouter(prefix="/notifications", tags=["notifications"])
singular_router = APIRouter(prefix="/notification", tags=["notifications"])

@router.get("", response_model=List[NotificationResponse])
@router.get("/", response_model=List[NotificationResponse])
@singular_router.get("", response_model=List[NotificationResponse])
@singular_router.get("/", response_model=List[NotificationResponse])
def get_notifications(
    is_read: Optional[bool] = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get paginated notifications for the current user.
    """
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)
    
    notifications = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset).all()
    return notifications


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
@router.patch("/{notification_id}/read/", response_model=NotificationResponse)
@singular_router.patch("/{notification_id}/read", response_model=NotificationResponse)
@singular_router.patch("/{notification_id}/read/", response_model=NotificationResponse)
def mark_notification_as_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Mark a notification as read.
    """
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
        
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
        
    return notification


@router.patch("/read-all", status_code=status.HTTP_200_OK)
@router.patch("/read-all/", status_code=status.HTTP_200_OK)
@singular_router.patch("/read-all", status_code=status.HTTP_200_OK)
@singular_router.patch("/read-all/", status_code=status.HTTP_200_OK)
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Mark all unread notifications of the current user as read.
    """
    unread_notifications = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).all()
    
    now = datetime.now(timezone.utc)
    for notification in unread_notifications:
        notification.is_read = True
        notification.read_at = now
        
    db.commit()
    return {"message": "All notifications marked as read"}


@router.delete("/{notification_id}", status_code=status.HTTP_200_OK)
@router.delete("/{notification_id}/", status_code=status.HTTP_200_OK)
@singular_router.delete("/{notification_id}", status_code=status.HTTP_200_OK)
@singular_router.delete("/{notification_id}/", status_code=status.HTTP_200_OK)
def delete_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a specific notification.
    """
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
        
    db.delete(notification)
    db.commit()
    return {"message": "Notification deleted successfully"}


@router.get("/preferences", response_model=List[NotificationPreferenceResponse])
@router.get("/preferences/", response_model=List[NotificationPreferenceResponse])
@singular_router.get("/preferences", response_model=List[NotificationPreferenceResponse])
@singular_router.get("/preferences/", response_model=List[NotificationPreferenceResponse])
def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get user notification preferences.
    """
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == current_user.id
    ).all()
    return prefs


@router.patch("/preferences", response_model=NotificationPreferenceResponse)
@router.patch("/preferences/", response_model=NotificationPreferenceResponse)
@singular_router.patch("/preferences", response_model=NotificationPreferenceResponse)
@singular_router.patch("/preferences/", response_model=NotificationPreferenceResponse)
def update_notification_preferences(
    pref_in: NotificationPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create or update a user's preference for a specific notification type.
    """
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == current_user.id,
        NotificationPreference.notification_type == pref_in.notification_type
    ).first()
    
    if not pref:
        pref = NotificationPreference(
            user_id=current_user.id,
            notification_type=pref_in.notification_type
        )
        db.add(pref)
        
    if pref_in.email_enabled is not None:
        pref.email_enabled = pref_in.email_enabled
    if pref_in.in_app_enabled is not None:
        pref.in_app_enabled = pref_in.in_app_enabled
    if pref_in.sms_enabled is not None:
        pref.sms_enabled = pref_in.sms_enabled
        
    db.commit()
    db.refresh(pref)
    return pref


@router.websocket("/ws")
@router.websocket("/ws/")
@singular_router.websocket("/ws")
@singular_router.websocket("/ws/")
async def websocket_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None)
):
    """
    WebSocket endpoint for real-time notifications.
    Expects token query parameter: `/api/v1/notifications/ws?token=<JWT_TOKEN>` or `/api/v1/notification/ws?token=<JWT_TOKEN>`
    """
    if not token:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    payload = verify_token(token)
    if not payload:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    user_id = payload.get("sub") or payload.get("id") or payload.get("user_id")
    if not user_id:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(str(user_id), websocket)
    try:
        # Keep connection open. WebSockets need an active listen loop.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(str(user_id), websocket)
    except Exception:
        manager.disconnect(str(user_id), websocket)
