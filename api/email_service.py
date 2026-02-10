#!/usr/bin/env python3
"""
Email Service for sending verification and password reset emails
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending emails via Gmail SMTP"""
    
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.username = os.getenv("EMAIL_USERNAME")
        self.password = os.getenv("EMAIL_APP_PASSWORD")
        
        if not self.username or not self.password:
            logger.warning("Email credentials not configured. Email sending will fail.")
    
    def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """
        Send an email
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.username or not self.password:
            logger.error("Email credentials not configured")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.username
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def send_verification_email(self, to_email: str, verification_token: str, base_url: str) -> bool:
        """
        Send email verification link
        
        Args:
            to_email: User's email address
            verification_token: Verification token
            base_url: Base URL of the application (e.g., https://jobdetector.com)
            
        Returns:
            True if sent successfully
        """
        verification_link = f"{base_url}/api/auth/verify-email?token={verification_token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to JobDetector!</h1>
                </div>
                <div class="content">
                    <h2>Verify Your Email Address</h2>
                    <p>Thank you for registering with JobDetector. Please click the button below to verify your email address:</p>
                    <p style="text-align: center;">
                        <a href="{verification_link}" class="button">Verify Email</a>
                    </p>
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #667eea;">{verification_link}</p>
                    <p><strong>This link will expire in 24 hours.</strong></p>
                    <p>If you didn't create an account with JobDetector, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>© 2026 JobDetector. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(to_email, "Verify Your JobDetector Account", html_content)
    
    def send_password_reset_email(self, to_email: str, reset_token: str, base_url: str) -> bool:
        """
        Send password reset link
        
        Args:
            to_email: User's email address
            reset_token: Password reset token
            base_url: Base URL of the application
            
        Returns:
            True if sent successfully
        """
        reset_link = f"{base_url}/reset-password.html?token={reset_token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <h2>Reset Your Password</h2>
                    <p>We received a request to reset your password for your JobDetector account. Click the button below to create a new password:</p>
                    <p style="text-align: center;">
                        <a href="{reset_link}" class="button">Reset Password</a>
                    </p>
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #667eea;">{reset_link}</p>
                    <div class="warning">
                        <strong>⚠️ Security Notice:</strong>
                        <ul>
                            <li>This link will expire in 1 hour</li>
                            <li>If you didn't request this reset, please ignore this email</li>
                            <li>Your password will remain unchanged until you create a new one</li>
                        </ul>
                    </div>
                </div>
                <div class="footer">
                    <p>© 2026 JobDetector. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(to_email, "Reset Your JobDetector Password", html_content)


# Singleton instance
_email_service = None

def get_email_service() -> EmailService:
    """Get or create email service instance"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
