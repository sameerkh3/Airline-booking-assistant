"""
Custom MCP server for the Airline Booking Assistant — Phase 2.

Exposes one tool:
  send_email(to, subject, body_html) — sends a formatted HTML email via Gmail SMTP.

Transport: streamable-HTTP (default FastMCP transport), listening on
  http://localhost:8001/mcp

Environment variables (loaded from repo-root .env):
  GMAIL_EMAIL         — sender Gmail address
  GMAIL_APP_PASSWORD  — Gmail App Password (not your account password)
  MCP_PORT            — optional override for the listening port (default 8001)

Run:
  python mcp-server/server.py
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env from the repo root (one directory above mcp-server/)
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
_port = int(os.environ.get("MCP_PORT", "8001"))
mcp = FastMCP("airline-booking-email-server", port=_port)

# ---------------------------------------------------------------------------
# HTML email template
# ---------------------------------------------------------------------------

def _build_email_html(subject: str, body_html: str) -> str:
    """
    Wrap body_html in the branded ABA HTML email template.
    Inline CSS ensures broad email client compatibility.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f6f8;font-family:Arial,Helvetica,sans-serif;">

  <!-- Wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f6f8;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background-color:#1a1a2e;padding:24px 32px;">
              <p style="margin:0;font-size:20px;font-weight:bold;color:#ffffff;letter-spacing:0.5px;">
                ✈ Kāishǐ — Airline Booking Assistant
              </p>
              <p style="margin:6px 0 0;font-size:13px;color:#a0aec0;">
                Your flight options, delivered
              </p>
            </td>
          </tr>

          <!-- Greeting -->
          <tr>
            <td style="padding:28px 32px 8px;">
              <p style="margin:0;font-size:16px;color:#2d3748;">Hi there,</p>
              <p style="margin:8px 0 0;font-size:15px;color:#4a5568;line-height:1.6;">
                Here are your flight options as requested. Review the details below and book directly with the airline.
              </p>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:16px 32px;">
              <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;">
            </td>
          </tr>

          <!-- Flight content (agent-generated) -->
          <tr>
            <td style="padding:0 32px 24px;">
              <div style="font-size:14px;color:#2d3748;line-height:1.7;">
                {body_html}
              </div>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:0 32px;">
              <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;">
            </td>
          </tr>

          <!-- Disclaimer footer -->
          <tr>
            <td style="padding:20px 32px 28px;">
              <p style="margin:0;font-size:12px;color:#a0aec0;line-height:1.6;">
                <strong>Disclaimer:</strong> This is a proof-of-concept application.
                Flight prices, availability, and schedules shown are <strong>not real</strong>
                and are for demonstration purposes only. Do not use this information for
                actual travel bookings.
              </p>
              <p style="margin:10px 0 0;font-size:12px;color:#cbd5e0;">
                Sent by Airline Booking Assistant POC &mdash; powered by Claude AI
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Tool: send_email
# ---------------------------------------------------------------------------

@mcp.tool()
def send_email(to: str, subject: str, body_html: str) -> str:
    """
    Send a formatted HTML flight-details email via Gmail SMTP.

    Reads GMAIL_EMAIL and GMAIL_APP_PASSWORD from environment variables.
    Wraps body_html in the branded ABA email template before sending.

    Args:
        to:        Recipient email address.
        subject:   Email subject line.
        body_html: HTML content block (flight table + route summary) generated
                   by the agent. Will be embedded inside the full template.

    Returns:
        A success message string, or a descriptive error string on failure.
    """
    gmail_address = os.environ.get("GMAIL_EMAIL")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_password:
        logger.error("GMAIL_EMAIL or GMAIL_APP_PASSWORD not configured")
        return "Email could not be sent: Gmail credentials are not configured."

    # Build the complete HTML email
    full_html = _build_email_html(subject, body_html)

    # Construct MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(full_html, "html", "utf-8"))

    # Send via Gmail SMTP with STARTTLS
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(gmail_address, gmail_password)
            smtp.sendmail(gmail_address, to, msg.as_string())

        logger.info("Email sent | to=%s | subject=%s", to, subject)
        return f"Email successfully sent to **{to}** with subject: \"{subject}\"."

    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail SMTP authentication failed for %s", gmail_address)
        return "Email could not be sent: Gmail authentication failed. Check GMAIL_APP_PASSWORD."
    except smtplib.SMTPRecipientsRefused:
        logger.error("Recipient refused: %s", to)
        return f"Email could not be sent: the address '{to}' was rejected by the server."
    except TimeoutError:
        logger.error("Gmail SMTP connection timed out")
        return "Email could not be sent: connection to Gmail timed out."
    except Exception as exc:
        logger.error("Unexpected SMTP error: %s", exc)
        return f"Email could not be sent: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting ABA MCP server on port %d", _port)
    # transport="streamable-http" makes this server connectable via HTTP,
    # matching the streamablehttp_client used in the backend.
    mcp.run(transport="streamable-http")
