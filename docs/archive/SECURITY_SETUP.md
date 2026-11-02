# Security Features Setup Guide

This document explains the security features implemented in Libaraxia and how to configure them.

## Table of Contents
1. [Rate Limiting](#rate-limiting)
2. [Email Verification](#email-verification)
3. [Environment Variables](#environment-variables)
4. [Database Migration](#database-migration)
5. [Testing](#testing)

## Rate Limiting

Rate limiting has been implemented to protect against brute force attacks and abuse.

### Features
- **Authentication endpoints**: Limited to prevent brute force login/registration attempts
- **Profile updates**: Limited to prevent spam
- **Friend requests**: Limited to prevent friend request spam

### Configuration

Rate limiting is configured in `config.py`:

```python
# Rate Limiting Configuration
RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'memory://')
RATELIMIT_STRATEGY = 'fixed-window'
RATELIMIT_HEADERS_ENABLED = True
```

### Rate Limit Defaults

| Endpoint | Limit | Description |
|----------|-------|-------------|
| Global | 200 per day, 50 per hour | Default for all endpoints |
| Login | 10 per hour | Login attempts per IP |
| Registration | 5 per hour | New user registrations per IP |
| Password Update | 10 per hour | Password changes per user |
| Profile Updates | 20 per hour | Email, username changes per user |
| Avatar Upload | 10 per hour | Profile picture uploads per user |
| Friend Requests | 30 per hour | Sending friend requests per user |
| Friend Accept | 50 per hour | Accepting friend requests per user |

### Storage Options

**Development (Default - In-Memory):**
```bash
# No configuration needed - uses memory:// by default
```

**Production (Redis - Recommended):**
```bash
# In .env file
REDIS_URL=redis://localhost:6379
```

### Benefits of Rate Limiting
- Prevents brute force password attacks
- Protects against registration spam
- Prevents abuse of friend request system
- Reduces server load from automated attacks

## Email Verification

Email verification ensures that users have access to the email address they register with.

### Features
- Secure token generation (32-byte URL-safe tokens)
- Token expiration (24 hours by default)
- Email verification status tracking
- Resend verification email functionality
- Automatic email for new registrations

### Configuration

Add these settings to your `.env` file:

```bash
# Email Verification (Optional - disabled by default)
EMAIL_VERIFICATION_REQUIRED=False  # Set to True to enable

# Email Server Configuration (Required if verification is enabled)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

### Gmail Setup

If using Gmail, you need to create an App Password:

1. Go to your Google Account settings
2. Navigate to Security → 2-Step Verification
3. Scroll down to "App passwords"
4. Generate a new app password for "Mail"
5. Use this password in `MAIL_PASSWORD`

### Other Email Providers

**SendGrid:**
```bash
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=apikey
MAIL_PASSWORD=your-sendgrid-api-key
```

**Mailgun:**
```bash
MAIL_SERVER=smtp.mailgun.org
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=postmaster@your-domain.mailgun.org
MAIL_PASSWORD=your-mailgun-password
```

**AWS SES:**
```bash
MAIL_SERVER=email-smtp.us-east-1.amazonaws.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-ses-smtp-username
MAIL_PASSWORD=your-ses-smtp-password
```

### User Flow

1. **Registration:**
   - User registers with email and password
   - If `EMAIL_VERIFICATION_REQUIRED=True`, verification email is sent
   - User receives email with verification link

2. **Email Verification:**
   - User clicks link in email
   - Token is validated (checked for expiration and usage)
   - User's account is marked as verified
   - User can now log in

3. **Login:**
   - If verification is required and email is not verified, login is blocked
   - User is prompted to check their email
   - Link to resend verification email is provided

4. **Resend Verification:**
   - User can request a new verification email
   - Rate limited to 3 per hour per IP
   - Old tokens are invalidated when new one is sent

### Security Considerations

- Tokens are 32-byte random values (URL-safe)
- Tokens expire after 24 hours
- Tokens are single-use (marked as used after verification)
- Old tokens are invalidated when resending
- Email existence is not revealed for security
- Existing users are grandfathered as verified

## Environment Variables

Create a `.env` file in the project root:

```bash
# Application
SECRET_KEY=your-secret-key-here-change-this-in-production
FLASK_ENV=development  # or production

# Database
DATABASE_URI=sqlite:///library.db

# Rate Limiting (Optional)
REDIS_URL=memory://  # Use redis://localhost:6379 for production

# Email Verification (Optional)
EMAIL_VERIFICATION_REQUIRED=False  # Set to True to enable
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

## Database Migration

Run the email verification migration:

```bash
# Connect to your database
sqlite3 library.db

# Run the migration
.read migrations/010_add_email_verification.sql

# Verify the changes
.schema users
.schema email_verification_tokens

# Exit
.quit
```

Or use Python:

```python
import sqlite3

conn = sqlite3.connect('library.db')
with open('migrations/010_add_email_verification.sql', 'r') as f:
    conn.executescript(f.read())
conn.commit()
conn.close()
```

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

New dependencies added:
- `Flask-Limiter==3.5.0` - Rate limiting
- `Flask-Mail==0.10.0` - Email sending (already installed)

## Testing

### Test Rate Limiting

```bash
# Test login rate limiting (should fail after 10 attempts)
for i in {1..15}; do
  curl -X POST http://localhost:5000/auth/login \
    -d "email=test@example.com&password=wrong" \
    -c cookies.txt -b cookies.txt
done
```

### Test Email Verification

1. Enable email verification in `.env`:
   ```bash
   EMAIL_VERIFICATION_REQUIRED=True
   ```

2. Configure email settings (see above)

3. Register a new user and check the email

4. Click the verification link

5. Try to log in before and after verification

### Test Without Email Verification

Email verification is **disabled by default**. The app will work normally without any email configuration.

## Production Recommendations

1. **Use Redis for rate limiting:**
   ```bash
   REDIS_URL=redis://localhost:6379
   ```

2. **Enable email verification:**
   ```bash
   EMAIL_VERIFICATION_REQUIRED=True
   ```

3. **Use a production email service** (SendGrid, Mailgun, AWS SES)

4. **Set a strong SECRET_KEY:**
   ```bash
   SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
   ```

5. **Monitor rate limit violations** in your logs

6. **Consider adjusting rate limits** based on your user base

## Troubleshooting

### Rate Limiting Not Working
- Check that `Flask-Limiter` is installed
- Verify `REDIS_URL` if using Redis
- Check application logs for errors

### Emails Not Sending
- Verify `MAIL_USERNAME` and `MAIL_PASSWORD`
- Check that `EMAIL_VERIFICATION_REQUIRED=True`
- Review application logs for email errors
- Test with a simple email client using the same credentials

### Rate Limit Too Strict
- Adjust limits in the route decorators
- Consider using Redis for more accurate limiting
- Implement user-specific exemptions if needed

### Users Can't Verify Email
- Check that the verification link is valid
- Ensure tokens haven't expired (24 hours)
- Provide resend verification option
- Check email spam folder

## API Endpoints

### Email Verification Endpoints

- `GET /auth/verify_email/<token>` - Verify email with token
- `GET /auth/resend_verification` - Show resend form
- `POST /auth/resend_verification` - Resend verification email (rate limited: 3/hour)

### Rate Limited Endpoints

All endpoints have default rate limiting (200/day, 50/hour), with these specific overrides:

- `POST /auth/login` - 10/hour
- `POST /auth/register` - 5/hour
- `POST /user/update_password` - 10/hour
- `POST /user/update_email` - 20/hour
- `POST /user/update_username` - 20/hour
- `POST /user/upload_avatar` - 10/hour
- `POST /friends/send_request/<username>` - 30/hour
- `POST /friends/accept/<int:request_id>` - 50/hour

## Support

For issues or questions, please check the application logs and consult the Flask-Limiter and Flask-Mail documentation.
