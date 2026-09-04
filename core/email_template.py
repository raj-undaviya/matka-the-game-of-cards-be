"""
email_templates.py
==================
Centralized HTML Email Templates Library

Usage:
    from email_templates import EmailTemplates

    subject, html_body = EmailTemplates.user_registration(
        user_name="Rahul Sharma",
        email="rahul@example.com"
    )

    # Then send using your preferred email library:
    # send_email(to=email, subject=subject, html=html_body)
"""

# ─────────────────────────────────────────────
#  Base Layout
# ─────────────────────────────────────────────

def _base_template(content: str, title: str = "") -> str:
    """Wraps content in a styled base HTML email layout."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    body {{
      margin: 0; padding: 0;
      background-color: #f0f4f8;
      font-family: 'Inter', Arial, sans-serif;
      color: #1a202c;
    }}
    .email-wrapper {{
      max-width: 600px;
      margin: 40px auto;
      background: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }}
    .email-header {{
      background: linear-gradient(135deg, #1a56db 0%, #0e3fa3 100%);
      padding: 32px 40px;
      text-align: center;
    }}
    .email-header .logo {{
      font-size: 24px;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: -0.5px;
    }}
    .email-header .logo span {{
      color: #93c5fd;
    }}
    .email-body {{
      padding: 40px;
    }}
    .email-title {{
      font-size: 22px;
      font-weight: 700;
      color: #1a202c;
      margin: 0 0 8px 0;
    }}
    .email-subtitle {{
      font-size: 15px;
      color: #64748b;
      margin: 0 0 28px 0;
    }}
    .info-card {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 20px 24px;
      margin: 20px 0;
    }}
    .info-row {{
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px solid #e2e8f0;
      font-size: 14px;
    }}
    .info-row:last-child {{ border-bottom: none; }}
    .info-label {{ color: #64748b; font-weight: 500; }}
    .info-value {{ color: #1a202c; font-weight: 600; text-align: right; }}
    .otp-box {{
      background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
      border: 2px dashed #3b82f6;
      border-radius: 12px;
      text-align: center;
      padding: 28px;
      margin: 24px 0;
    }}
    .otp-label {{
      font-size: 13px;
      font-weight: 600;
      color: #3b82f6;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      margin-bottom: 10px;
    }}
    .otp-code {{
      font-size: 42px;
      font-weight: 700;
      color: #1a56db;
      letter-spacing: 10px;
      line-height: 1;
    }}
    .otp-expiry {{
      font-size: 13px;
      color: #64748b;
      margin-top: 10px;
    }}
    .status-badge {{
      display: inline-block;
      padding: 6px 16px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
    }}
    .badge-success {{ background: #dcfce7; color: #166534; }}
    .badge-failed  {{ background: #fee2e2; color: #991b1b; }}
    .badge-pending {{ background: #fef9c3; color: #854d0e; }}
    .amount-display {{
      text-align: center;
      padding: 24px;
      background: #f0fdf4;
      border-radius: 10px;
      margin: 20px 0;
      border: 1px solid #bbf7d0;
    }}
    .amount-display.failed {{
      background: #fff1f2;
      border-color: #fecdd3;
    }}
    .amount-label {{ font-size: 13px; color: #64748b; margin-bottom: 6px; }}
    .amount-value {{ font-size: 36px; font-weight: 700; color: #15803d; }}
    .amount-value.failed {{ color: #dc2626; }}
    .alert-box {{
      border-left: 4px solid #f59e0b;
      background: #fffbeb;
      padding: 14px 18px;
      border-radius: 0 8px 8px 0;
      margin: 20px 0;
      font-size: 14px;
      color: #78350f;
    }}
    .alert-box.danger {{
      border-left-color: #ef4444;
      background: #fff1f2;
      color: #991b1b;
    }}
    .btn {{
      display: inline-block;
      padding: 13px 32px;
      border-radius: 8px;
      font-size: 15px;
      font-weight: 600;
      text-decoration: none;
      margin: 16px 0 8px;
      cursor: pointer;
    }}
    .btn-primary {{ background: #1a56db; color: #ffffff; }}
    .btn-danger  {{ background: #dc2626; color: #ffffff; }}
    .divider {{
      border: none;
      border-top: 1px solid #e2e8f0;
      margin: 28px 0;
    }}
    .email-footer {{
      background: #f8fafc;
      padding: 24px 40px;
      text-align: center;
      font-size: 12px;
      color: #94a3b8;
      border-top: 1px solid #e2e8f0;
    }}
    .email-footer a {{ color: #3b82f6; text-decoration: none; }}
    p {{ font-size: 15px; line-height: 1.7; color: #374151; margin: 0 0 14px; }}
    h3 {{ margin: 0 0 4px; font-size: 16px; color: #1a202c; }}
  </style>
</head>
<body>
  <div class="email-wrapper">
    <div class="email-header">
      <div class="logo">My<span>App</span></div>
    </div>
    <div class="email-body">
      {content}
    </div>
    <div class="email-footer">
      <p style="margin:0 0 6px; font-size:12px;">
        © 2025 MyApp. All rights reserved.<br/>
        <a href="#">Privacy Policy</a> &nbsp;|&nbsp; <a href="#">Terms of Service</a> &nbsp;|&nbsp; <a href="#">Support</a>
      </p>
      <p style="margin:0; font-size:11px; color:#cbd5e1;">
        This is an automated email. Please do not reply directly to this message.
      </p>
    </div>
  </div>
</body>
</html>"""


def _footer_note(note: str) -> str:
    return f'<p style="font-size:13px; color:#94a3b8; margin-top:24px;">{note}</p>'


# ─────────────────────────────────────────────
#  Email Templates Class
# ─────────────────────────────────────────────

class EmailTemplates:

    APP_NAME = "MyApp"   # ← Change to your app name
    SUPPORT_EMAIL = "support@myapp.com"  # ← Change to your support email

    # ── 1. User Registration ────────────────────────────────────────────────
    @classmethod
    def user_registration(cls, user_name: str, email: str, login_url: str = "#") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"🎉 Welcome to {cls.APP_NAME} – Your Account is Ready!"
        content = f"""
        <h2 class="email-title">Welcome aboard, {user_name}! 🎉</h2>
        <p class="email-subtitle">We're thrilled to have you with us.</p>
        <p>Your account has been successfully created. Here are your account details:</p>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Full Name</span>
            <span class="info-value">{user_name}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Email Address</span>
            <span class="info-value">{email}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Account Status</span>
            <span class="info-value"><span class="status-badge badge-success">Active</span></span>
          </div>
        </div>
        <p>You can now log in and start exploring all features {cls.APP_NAME} has to offer.</p>
        <a href="{login_url}" class="btn btn-primary">Log In to Your Account</a>
        <hr class="divider"/>
        {_footer_note(f'If you did not create this account, please contact us at <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a> immediately.')}
        """
        return subject, _base_template(content, subject)

    # ── 2. Forgot Password ──────────────────────────────────────────────────
    @classmethod
    def forgot_password(cls, user_name: str, reset_url: str, expires_in: str = "30 minutes") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"🔑 Password Reset Request – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Password Reset Request</h2>
        <p class="email-subtitle">We received a request to reset your password.</p>
        <p>Hi <strong>{user_name}</strong>,</p>
        <p>Click the button below to reset your password. This link will expire in <strong>{expires_in}</strong>.</p>
        <a href="{reset_url}" class="btn btn-primary">Reset My Password</a>
        <div class="alert-box">
          ⚠️ <strong>This link expires in {expires_in}.</strong> If you didn't request a password reset, you can safely ignore this email.
        </div>
        <hr class="divider"/>
        <p style="font-size:13px; color:#64748b;">
          If the button above doesn't work, copy and paste this URL into your browser:<br/>
          <a href="{reset_url}" style="color:#1a56db; word-break:break-all;">{reset_url}</a>
        </p>
        {_footer_note(f'For security concerns, contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 3. Registration OTP ─────────────────────────────────────────────────
    @classmethod
    def registration_otp(cls, user_name: str, otp: str, expires_in: str = "10 minutes") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"✅ Verify Your Email – OTP for {cls.APP_NAME} Registration"
        content = f"""
        <h2 class="email-title">Verify Your Email Address</h2>
        <p class="email-subtitle">One last step to complete your registration.</p>
        <p>Hi <strong>{user_name}</strong>, use the OTP below to verify your email address:</p>
        <div class="otp-box">
          <div class="otp-label">Your One-Time Password</div>
          <div class="otp-code">{otp}</div>
          <div class="otp-expiry">⏱ This OTP is valid for <strong>{expires_in}</strong></div>
        </div>
        <div class="alert-box">
          🔒 Never share this OTP with anyone. {cls.APP_NAME} staff will never ask for your OTP.
        </div>
        {_footer_note("If you didn't request this, please ignore this email.")}
        """
        return subject, _base_template(content, subject)

    # ── 4. Forgot Password OTP ──────────────────────────────────────────────
    @classmethod
    def forgot_password_otp(cls, user_name: str, otp: str, expires_in: str = "10 minutes") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"🔐 Password Reset OTP – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Password Reset OTP</h2>
        <p class="email-subtitle">Use the OTP below to reset your password.</p>
        <p>Hi <strong>{user_name}</strong>,</p>
        <p>We received a request to reset your {cls.APP_NAME} account password. Use the OTP below:</p>
        <div class="otp-box">
          <div class="otp-label">Password Reset OTP</div>
          <div class="otp-code">{otp}</div>
          <div class="otp-expiry">⏱ This OTP expires in <strong>{expires_in}</strong></div>
        </div>
        <div class="alert-box danger">
          🚨 If you did NOT request a password reset, your account may be at risk. Please secure your account immediately.
        </div>
        {_footer_note(f'Contact support at <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a> if you need help.')}
        """
        return subject, _base_template(content, subject)

    # ── 5. Login Attempt Alert ──────────────────────────────────────────────
    @classmethod
    def login_attempt(cls, user_name: str, login_time: str, ip_address: str,
                      device: str, location: str, was_successful: bool = True) -> tuple:
        """
        Returns: (subject, html_body)
        """
        status_label = "Successful Login" if was_successful else "Failed Login Attempt"
        badge_class  = "badge-success" if was_successful else "badge-failed"
        subject = f"{'✅' if was_successful else '⚠️'} {status_label} Detected – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Login {"Notification" if was_successful else "Alert"}</h2>
        <p class="email-subtitle">A {'successful' if was_successful else 'failed'} login was detected on your account.</p>
        <p>Hi <strong>{user_name}</strong>, here are the details:</p>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge {badge_class}">{status_label}</span></span>
          </div>
          <div class="info-row">
            <span class="info-label">Date & Time</span>
            <span class="info-value">{login_time}</span>
          </div>
          <div class="info-row">
            <span class="info-label">IP Address</span>
            <span class="info-value">{ip_address}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Device / Browser</span>
            <span class="info-value">{device}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Location</span>
            <span class="info-value">{location}</span>
          </div>
        </div>
        {'<div class="alert-box danger">🚨 If this was not you, please change your password immediately and contact support.</div>' if not was_successful else '<p>If this was you, no action is needed.</p>'}
        {_footer_note(f'For security help, contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 6. Wallet Creation – Success ────────────────────────────────────────
    @classmethod
    def wallet_creation_success(cls, user_name: str, wallet_id: str,
                                 wallet_type: str = "Standard Wallet",
                                 created_at: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"💳 Your Wallet is Ready – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Wallet Created Successfully! 💳</h2>
        <p class="email-subtitle">Your digital wallet is set up and ready to use.</p>
        <p>Hi <strong>{user_name}</strong>, your wallet has been successfully created.</p>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Wallet ID</span>
            <span class="info-value">{wallet_id}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Wallet Type</span>
            <span class="info-value">{wallet_type}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-success">Active</span></span>
          </div>
          {'<div class="info-row"><span class="info-label">Created At</span><span class="info-value">' + created_at + '</span></div>' if created_at else ''}
        </div>
        <p>You can now deposit funds, make transactions, and manage your wallet from your dashboard.</p>
        {_footer_note(f'Questions? Contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 7. Wallet Creation – Failed ─────────────────────────────────────────
    @classmethod
    def wallet_creation_failed(cls, user_name: str, reason: str = "An unexpected error occurred",
                                attempted_at: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"❌ Wallet Creation Failed – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Wallet Creation Failed ❌</h2>
        <p class="email-subtitle">We were unable to create your wallet.</p>
        <p>Hi <strong>{user_name}</strong>, unfortunately your wallet creation request could not be completed.</p>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-failed">Failed</span></span>
          </div>
          {'<div class="info-row"><span class="info-label">Attempted At</span><span class="info-value">' + attempted_at + '</span></div>' if attempted_at else ''}
          <div class="info-row">
            <span class="info-label">Reason</span>
            <span class="info-value">{reason}</span>
          </div>
        </div>
        <div class="alert-box danger">
          Please try again or contact our support team if the issue persists.
        </div>
        {_footer_note(f'Need help? Contact us at <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 8. Money Deposit – Success ──────────────────────────────────────────
    @classmethod
    def deposit_success(cls, user_name: str, amount: str, currency: str = "INR",
                         transaction_id: str = "", wallet_balance: str = "",
                         deposited_at: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"💰 Deposit Successful – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Deposit Successful! 💰</h2>
        <p class="email-subtitle">Your funds have been added to your wallet.</p>
        <p>Hi <strong>{user_name}</strong>, your deposit has been processed successfully.</p>
        <div class="amount-display">
          <div class="amount-label">Amount Deposited</div>
          <div class="amount-value">+ {currency} {amount}</div>
        </div>
        <div class="info-card">
          {'<div class="info-row"><span class="info-label">Transaction ID</span><span class="info-value">' + transaction_id + '</span></div>' if transaction_id else ''}
          {'<div class="info-row"><span class="info-label">Date & Time</span><span class="info-value">' + deposited_at + '</span></div>' if deposited_at else ''}
          {'<div class="info-row"><span class="info-label">Wallet Balance</span><span class="info-value">' + currency + ' ' + wallet_balance + '</span></div>' if wallet_balance else ''}
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-success">Successful</span></span>
          </div>
        </div>
        {_footer_note(f'Not your transaction? Contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a> immediately.')}
        """
        return subject, _base_template(content, subject)

    # ── 9. Money Deposit – Failed ───────────────────────────────────────────
    @classmethod
    def deposit_failed(cls, user_name: str, amount: str, currency: str = "INR",
                        reason: str = "Payment could not be processed",
                        attempted_at: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"❌ Deposit Failed – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Deposit Failed ❌</h2>
        <p class="email-subtitle">Your deposit could not be processed.</p>
        <p>Hi <strong>{user_name}</strong>, unfortunately your deposit attempt was unsuccessful.</p>
        <div class="amount-display failed">
          <div class="amount-label">Amount Attempted</div>
          <div class="amount-value failed">{currency} {amount}</div>
        </div>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-failed">Failed</span></span>
          </div>
          {'<div class="info-row"><span class="info-label">Date & Time</span><span class="info-value">' + attempted_at + '</span></div>' if attempted_at else ''}
          <div class="info-row">
            <span class="info-label">Reason</span>
            <span class="info-value">{reason}</span>
          </div>
        </div>
        <div class="alert-box">No money has been deducted from your account.</div>
        {_footer_note(f'Need assistance? Contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 10. Money Withdraw – Success ────────────────────────────────────────
    @classmethod
    def withdraw_success(cls, user_name: str, amount: str, currency: str = "INR",
                          transaction_id: str = "", wallet_balance: str = "",
                          withdrawn_at: str = "", bank_account: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"💸 Withdrawal Successful – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Withdrawal Successful! 💸</h2>
        <p class="email-subtitle">Your withdrawal request has been processed.</p>
        <p>Hi <strong>{user_name}</strong>, your withdrawal has been completed successfully.</p>
        <div class="amount-display">
          <div class="amount-label">Amount Withdrawn</div>
          <div class="amount-value">- {currency} {amount}</div>
        </div>
        <div class="info-card">
          {'<div class="info-row"><span class="info-label">Transaction ID</span><span class="info-value">' + transaction_id + '</span></div>' if transaction_id else ''}
          {'<div class="info-row"><span class="info-label">Date & Time</span><span class="info-value">' + withdrawn_at + '</span></div>' if withdrawn_at else ''}
          {'<div class="info-row"><span class="info-label">Bank Account</span><span class="info-value">' + bank_account + '</span></div>' if bank_account else ''}
          {'<div class="info-row"><span class="info-label">Remaining Balance</span><span class="info-value">' + currency + ' ' + wallet_balance + '</span></div>' if wallet_balance else ''}
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-success">Successful</span></span>
          </div>
        </div>
        {_footer_note(f'Didn\'t initiate this? Contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a> immediately.')}
        """
        return subject, _base_template(content, subject)

    # ── 11. Money Withdraw – Failed ─────────────────────────────────────────
    @classmethod
    def withdraw_failed(cls, user_name: str, amount: str, currency: str = "INR",
                         reason: str = "Withdrawal could not be processed",
                         attempted_at: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"❌ Withdrawal Failed – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Withdrawal Failed ❌</h2>
        <p class="email-subtitle">Your withdrawal request could not be completed.</p>
        <p>Hi <strong>{user_name}</strong>, unfortunately your withdrawal was unsuccessful.</p>
        <div class="amount-display failed">
          <div class="amount-label">Amount Requested</div>
          <div class="amount-value failed">{currency} {amount}</div>
        </div>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-failed">Failed</span></span>
          </div>
          {'<div class="info-row"><span class="info-label">Date & Time</span><span class="info-value">' + attempted_at + '</span></div>' if attempted_at else ''}
          <div class="info-row">
            <span class="info-label">Reason</span>
            <span class="info-value">{reason}</span>
          </div>
        </div>
        <div class="alert-box">Your wallet balance remains unchanged. Please retry or contact support.</div>
        {_footer_note(f'Need help? Contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 12. Admin Approve Withdraw – Success ────────────────────────────────
    @classmethod
    def admin_withdraw_approved(cls, user_name: str, amount: str, currency: str = "INR",
                                  transaction_id: str = "", approved_at: str = "",
                                  bank_account: str = "", eta: str = "Within 24 hours") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"✅ Withdrawal Request Approved (Within 24 Hours) – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Your Withdrawal Has Been Approved ✅</h2>
        <p class="email-subtitle">Admin has approved your withdrawal request.</p>
        <p>Hi <strong>{user_name}</strong>, great news! Your withdrawal request has been reviewed and approved.</p>
        <div class="amount-display">
          <div class="amount-label">Approved Amount</div>
          <div class="amount-value">- {currency} {amount}</div>
        </div>
        <div class="info-card">
          {'<div class="info-row"><span class="info-label">Transaction ID</span><span class="info-value">' + transaction_id + '</span></div>' if transaction_id else ''}
          {'<div class="info-row"><span class="info-label">Approved At</span><span class="info-value">' + approved_at + '</span></div>' if approved_at else ''}
          {'<div class="info-row"><span class="info-label">Payment Mode / Details</span><span class="info-value">' + bank_account + '</span></div>' if bank_account else ''}
          <div class="info-row">
            <span class="info-label">Estimated Transfer</span>
            <span class="info-value">Within 24 hours</span>
          </div>
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-success">Approved</span></span>
          </div>
        </div>
        <p>The funds will be transferred to your account within <strong>24 hours</strong>.</p>
        {_footer_note(f'Questions? Contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 13. Admin Approve Withdraw – Rejected ───────────────────────────────
    @classmethod
    def admin_withdraw_rejected(cls, user_name: str, amount: str, currency: str = "INR",
                                  reason: str = "Request did not meet approval criteria",
                                  rejected_at: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"❌ Withdrawal Request Rejected – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Withdrawal Request Rejected ❌</h2>
        <p class="email-subtitle">Admin has reviewed and rejected your withdrawal request.</p>
        <p>Hi <strong>{user_name}</strong>, after review, your withdrawal request has been rejected.</p>
        <div class="amount-display failed">
          <div class="amount-label">Requested Amount</div>
          <div class="amount-value failed">{currency} {amount}</div>
        </div>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-failed">Rejected</span></span>
          </div>
          {'<div class="info-row"><span class="info-label">Rejected At</span><span class="info-value">' + rejected_at + '</span></div>' if rejected_at else ''}
          <div class="info-row">
            <span class="info-label">Reason</span>
            <span class="info-value">{reason}</span>
          </div>
        </div>
        <div class="alert-box danger">
          Your wallet balance has not been affected. You may submit a new request or contact support for clarification.
        </div>
        {_footer_note(f'To appeal this decision, contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)

    # ── 14. Account Credit ──────────────────────────────────────────────────
    @classmethod
    def account_credit(cls, user_name: str, amount: str, currency: str = "INR",
                        credit_reason: str = "Account Credit", transaction_id: str = "",
                        wallet_balance: str = "", credited_at: str = "") -> tuple:
        """
        Returns: (subject, html_body)
        """
        subject = f"🎁 Account Credited – {cls.APP_NAME}"
        content = f"""
        <h2 class="email-title">Your Account Has Been Credited! 🎁</h2>
        <p class="email-subtitle">Funds have been added to your wallet.</p>
        <p>Hi <strong>{user_name}</strong>, your {cls.APP_NAME} wallet has been credited.</p>
        <div class="amount-display">
          <div class="amount-label">Amount Credited</div>
          <div class="amount-value">+ {currency} {amount}</div>
        </div>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Credit Reason</span>
            <span class="info-value">{credit_reason}</span>
          </div>
          {'<div class="info-row"><span class="info-label">Transaction ID</span><span class="info-value">' + transaction_id + '</span></div>' if transaction_id else ''}
          {'<div class="info-row"><span class="info-label">Credited At</span><span class="info-value">' + credited_at + '</span></div>' if credited_at else ''}
          {'<div class="info-row"><span class="info-label">New Wallet Balance</span><span class="info-value">' + currency + ' ' + wallet_balance + '</span></div>' if wallet_balance else ''}
          <div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value"><span class="status-badge badge-success">Credited</span></span>
          </div>
        </div>
        <p>This amount is now available in your wallet. Enjoy!</p>
        {_footer_note(f'Unexpected credit? Contact <a href="mailto:{cls.SUPPORT_EMAIL}">{cls.SUPPORT_EMAIL}</a>')}
        """
        return subject, _base_template(content, subject)


# ─────────────────────────────────────────────
#  Quick Usage Examples
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # ── How to use ──────────────────────────────────────────────────────────
    # Each method returns a tuple: (subject, html_body)
    # Pass these to your email-sending function.

    # Example with smtplib:
    # import smtplib
    # from email.mime.multipart import MIMEMultipart
    # from email.mime.text import MIMEText
    #
    # def send_email(to: str, subject: str, html: str):
    #     msg = MIMEMultipart("alternative")
    #     msg["Subject"] = subject
    #     msg["From"]    = "noreply@myapp.com"
    #     msg["To"]      = to
    #     msg.attach(MIMEText(html, "html"))
    #     with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    #         server.login("your@gmail.com", "yourpassword")
    #         server.sendmail("noreply@myapp.com", to, msg.as_string())

    # ── Sample calls ─────────────────────────────────────────────────────────

    subject, html = EmailTemplates.user_registration(
        user_name="Rahul Sharma",
        email="rahul@example.com",
        login_url="https://myapp.com/login"
    )
    print(f"[1] {subject}")

    subject, html = EmailTemplates.forgot_password(
        user_name="Rahul Sharma",
        reset_url="https://myapp.com/reset?token=abc123",
        expires_in="30 minutes"
    )
    print(f"[2] {subject}")

    subject, html = EmailTemplates.registration_otp(
        user_name="Rahul Sharma",
        otp="482916"
    )
    print(f"[3] {subject}")

    subject, html = EmailTemplates.forgot_password_otp(
        user_name="Rahul Sharma",
        otp="739201"
    )
    print(f"[4] {subject}")

    subject, html = EmailTemplates.login_attempt(
        user_name="Rahul Sharma",
        login_time="20 May 2025, 10:32 AM",
        ip_address="103.21.58.101",
        device="Chrome on Windows",
        location="Surat, Gujarat, IN",
        was_successful=True
    )
    print(f"[5] {subject}")

    subject, html = EmailTemplates.wallet_creation_success(
        user_name="Rahul Sharma",
        wallet_id="WLT-20250520-0042",
        wallet_type="Standard Wallet",
        created_at="20 May 2025, 10:35 AM"
    )
    print(f"[6] {subject}")

    subject, html = EmailTemplates.wallet_creation_failed(
        user_name="Rahul Sharma",
        reason="KYC verification pending"
    )
    print(f"[7] {subject}")

    subject, html = EmailTemplates.deposit_success(
        user_name="Rahul Sharma",
        amount="5,000.00",
        currency="INR",
        transaction_id="TXN-DEP-78234",
        wallet_balance="12,500.00",
        deposited_at="20 May 2025, 11:00 AM"
    )
    print(f"[8] {subject}")

    subject, html = EmailTemplates.deposit_failed(
        user_name="Rahul Sharma",
        amount="5,000.00",
        reason="Insufficient funds in source account"
    )
    print(f"[9] {subject}")

    subject, html = EmailTemplates.withdraw_success(
        user_name="Rahul Sharma",
        amount="2,000.00",
        currency="INR",
        transaction_id="TXN-WDR-55102",
        wallet_balance="10,500.00",
        withdrawn_at="20 May 2025, 02:15 PM",
        bank_account="HDFC ****4321"
    )
    print(f"[10] {subject}")

    subject, html = EmailTemplates.withdraw_failed(
        user_name="Rahul Sharma",
        amount="2,000.00",
        reason="Bank account details mismatch"
    )
    print(f"[11] {subject}")

    subject, html = EmailTemplates.admin_withdraw_approved(
        user_name="Rahul Sharma",
        amount="2,000.00",
        transaction_id="TXN-WDR-55102",
        approved_at="20 May 2025, 03:00 PM",
        bank_account="HDFC ****4321"
    )
    print(f"[12] {subject}")

    subject, html = EmailTemplates.admin_withdraw_rejected(
        user_name="Rahul Sharma",
        amount="2,000.00",
        reason="Suspicious activity detected on account"
    )
    print(f"[13] {subject}")

    subject, html = EmailTemplates.account_credit(
        user_name="Rahul Sharma",
        amount="500.00",
        currency="INR",
        credit_reason="Referral Bonus",
        wallet_balance="13,000.00",
        credited_at="20 May 2025, 04:00 PM"
    )
    print(f"[14] {subject}")

    print("\n✅ All templates generated successfully!")