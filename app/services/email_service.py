import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def send_otp_email(
        to_email: str,
        otp_code: str,
        purpose: str = "Verification"
    ) -> bool:
        """
        Sends an OTP email.

        Returns:
            bool: True if email sent successfully, otherwise False.
        """

        # Fallback for development environments
        if not all([
            settings.SMTP_HOST,
            settings.SMTP_USER,
            settings.SMTP_PASSWORD
        ]):
            logger.warning("SMTP settings not configured.")
            logger.warning("----- OTP EMAIL -----")
            logger.warning(f"To: {to_email}")
            logger.warning(f"Purpose: {purpose}")
            logger.warning(f"OTP: {otp_code}")
            logger.warning("---------------------")
            return True

        try:
            msg = MIMEMultipart("alternative")

            msg["From"] = settings.SMTP_FROM_EMAIL
            msg["To"] = to_email
            msg["Subject"] = f"Your {purpose} Code - DataHire"

            # Plain-text fallback
            plain_text = f"""
                            Hello,

                            Your One-Time Password (OTP) for {purpose} is:

                            {otp_code}

                            This code will expire in 10 minutes.

                            If you did not request this code, please ignore this email.

                            Best regards,
                            DataHire Team
                            """

            # HTML Email Template
            html_body = f"""
                        <!DOCTYPE html>
                            <html lang="en">
                            <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <title>OTP Verification</title>
                            </head>

                            <body style="
                                margin:0;
                                padding:0;
                                background-color:#f4f6f9;
                                font-family:Arial, Helvetica, sans-serif;
                            ">

                            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                                style="background-color:#f4f6f9;padding:40px 0;">
                                <tr>
                                    <td align="center">

                                        <table width="600" cellpadding="0" cellspacing="0" border="0"
                                            style="
                                            background:#ffffff;
                                            border-radius:12px;
                                            overflow:hidden;
                                            box-shadow:0 4px 12px rgba(0,0,0,0.08);
                                            ">

                                            <!-- Header -->
                                            <tr>
                                                <td align="center"
                                                    style="
                                                    background:#f2b11c;
                                                    padding:30px;
                                                    ">
                                                    <h1 style="
                                                        margin:0;
                                                        color:#ffffff;
                                                        font-size:28px;
                                                        ">
                                                        DataHire
                                                    </h1>
                                                </td>
                                            </tr>

                                            <!-- Body -->
                                            <tr>
                                                <td style="padding:40px;">

                                                    <h2 style="
                                                        margin-top:0;
                                                        color:#111827;
                                                        ">
                                                        {purpose} OTP
                                                    </h2>

                                                    <p style="
                                                        font-size:16px;
                                                        color:#4b5563;
                                                        line-height:1.6;
                                                        ">
                                                        Hello,
                                                    </p>

                                                    <p style="
                                                        font-size:16px;
                                                        color:#4b5563;
                                                        line-height:1.6;
                                                        ">
                                                        Use the One-Time Password (OTP) below to complete your verification process.
                                                    </p>

                                                    <!-- OTP Box -->
                                                    <div style="
                                                        text-align:center;
                                                        margin:35px 0;
                                                    ">
                                                        <div style="
                                                            display:inline-block;
                                                            background:#eff6ff;
                                                            border:2px dashed #2563eb;
                                                            border-radius:12px;
                                                            padding:18px 40px;
                                                        ">
                                                            <span style="
                                                                font-size:36px;
                                                                font-weight:bold;
                                                                color:#f2b11c;
                                                                letter-spacing:8px;
                                                            ">
                                                                {otp_code}
                                                            </span>
                                                        </div>
                                                    </div>

                                                    <p style="
                                                        font-size:15px;
                                                        color:#6b7280;
                                                        line-height:1.6;
                                                    ">
                                                        This OTP will expire in
                                                        <strong>10 minutes</strong>.
                                                    </p>

                                                    <p style="
                                                        font-size:15px;
                                                        color:#6b7280;
                                                        line-height:1.6;
                                                    ">
                                                        For your security, never share this code with anyone.
                                                    </p>

                                                    <p style="
                                                        font-size:15px;
                                                        color:#6b7280;
                                                        line-height:1.6;
                                                    ">
                                                        If you did not request this OTP,
                                                        please ignore this email.
                                                    </p>

                                                </td>
                                            </tr>

                                            <!-- Footer -->
                                            <tr>
                                                <td style="
                                                    background:#f9fafb;
                                                    text-align:center;
                                                    padding:20px;
                                                    border-top:1px solid #e5e7eb;
                                                ">
                                                    <p style="
                                                        margin:0;
                                                        color:#9ca3af;
                                                        font-size:12px;
                                                    ">
                                                        © 2025 DataHire. All rights reserved.
                                                    </p>
                                                </td>
                                            </tr>

                                        </table>

                                    </td>
                                </tr>
                            </table>

                            </body>
                            </html>

                        """

            # Attach both versions
            msg.attach(MIMEText(plain_text, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT
            ) as server:
                server.starttls()
                server.login(
                    settings.SMTP_USER,
                    settings.SMTP_PASSWORD
                )
                server.send_message(msg)

            logger.info(f"OTP email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to send OTP email to {to_email}: {str(e)}"
            )
            return False



