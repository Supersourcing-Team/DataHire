import logging
import httpx
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelnyxService:
    @staticmethod
    async def send_sms(to_phone: str, text: str) -> bool:
        """
        Sends an SMS message using Telnyx API.
        If Telnyx is not fully configured (missing API Key or From Phone),
        it falls back to logging the SMS in the console (Mock/Stub mode).
        
        Args:
            to_phone: Recipient phone number in E.164 format (e.g. +14155552671).
            text: Body text of the SMS message.
            
        Returns:
            bool: True if the SMS was sent or logged successfully, False otherwise.
        """
        if not settings.TELNYX_API_KEY or not settings.TELNYX_FROM_PHONE:
            logger.warning("----- TELNYX SMS STUB -----")
            logger.warning(f"To: {to_phone}")
            logger.warning(f"Text: {text}")
            logger.warning("---------------------------")
            return True

        url = "https://api.telnyx.com/v2/messages"
        headers = {
            "Authorization": f"Bearer {settings.TELNYX_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": settings.TELNYX_FROM_PHONE,
            "to": to_phone,
            "text": text
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in (200, 201, 202):
                    resp_data = response.json()
                    message_id = resp_data.get("data", {}).get("id")
                    logger.info(f"SMS successfully sent to {to_phone} via Telnyx (Message ID: {message_id})")
                    return True
                else:
                    logger.error(
                        f"Telnyx API returned error status {response.status_code}: {response.text} "
                        f"(Recipient: {to_phone})"
                    )
                    return False
        except httpx.HTTPError as e:
            logger.error(f"HTTP error occurred while calling Telnyx API: {str(e)} (Recipient: {to_phone})")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending SMS via Telnyx: {str(e)} (Recipient: {to_phone})")
            return False
