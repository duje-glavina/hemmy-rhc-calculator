# Email Setup Guide - SendGrid Configuration

This guide will help you set up email functionality for the Hemmy RHC Calculator using SendGrid.

## Step 1: Sign Up for SendGrid

1. Go to [https://sendgrid.com](https://sendgrid.com)
2. Click "Start for Free"
3. Create your account (Free tier: 100 emails/day)
4. Verify your email address

## Step 2: Create an API Key

1. Log in to your SendGrid dashboard
2. Go to **Settings** → **API Keys** in the left sidebar
3. Click **Create API Key**
4. Give it a name (e.g., "Hemmy RHC Calculator")
5. Select **Full Access** permissions (or at minimum, **Mail Send** permissions)
6. Click **Create & View**
7. **IMPORTANT:** Copy the API key immediately - you won't be able to see it again!

## Step 3: Verify Sender Identity

SendGrid requires you to verify the sender email address:

1. Go to **Settings** → **Sender Authentication**
2. Choose one of these options:

   **Option A: Single Sender Verification** (Easier, recommended for testing)
   - Click "Verify a Single Sender"
   - Enter your email address (e.g., noreply@yourdomain.com)
   - Fill in the form
   - Check your email and click the verification link

   **Option B: Domain Authentication** (Better for production)
   - Click "Authenticate Your Domain"
   - Follow the DNS setup instructions
   - This gives you better email deliverability

## Step 4: Configure Your Application

1. Copy `.env.example` to create a new `.env` file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file with your SendGrid credentials:
   ```
   SMTP_SERVER=smtp.sendgrid.net
   SMTP_PORT=587
   SMTP_USERNAME=apikey
   SMTP_PASSWORD=YOUR_SENDGRID_API_KEY_HERE
   SENDER_EMAIL=your-verified-email@domain.com
   SENDER_NAME=Hemmy RHC Calculator
   ```

   Replace:
   - `YOUR_SENDGRID_API_KEY_HERE` with the API key you copied in Step 2
   - `your-verified-email@domain.com` with the email you verified in Step 3

## Step 5: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 6: Test the Email Functionality

1. Start your Flask application:
   ```bash
   python app.py
   ```

2. Open http://localhost:5000 in your browser
3. Complete a calculation
4. On the results page, enter your email address in the "Email Report" section
5. Click "Send Email"
6. Check your inbox!

## Troubleshooting

### "Email service not configured" error
- Make sure your `.env` file exists and has the correct credentials
- Restart your Flask application after creating/editing `.env`

### "Email authentication failed" error
- Double-check your API key in the `.env` file
- Make sure you copied it correctly (no extra spaces)
- The SMTP_USERNAME should be exactly `apikey` (not your email)

### Email not received
- Check your spam folder
- Verify that your sender email is verified in SendGrid
- Check SendGrid Activity dashboard for delivery status

### "Sender address not verified" error
- Complete Step 3 (Verify Sender Identity)
- Make sure the SENDER_EMAIL in `.env` matches the verified email in SendGrid

## Production Deployment

When deploying to production (Heroku, AWS, etc.):

1. **Never commit your `.env` file to git** (it's already in `.gitignore`)
2. Set environment variables in your hosting platform:
   - Heroku: `heroku config:set SMTP_PASSWORD=your_api_key`
   - AWS: Use AWS Secrets Manager or environment variables
   - Others: Refer to your hosting provider's documentation

## SendGrid Free Tier Limits

- 100 emails per day
- Good for testing and small-scale use
- If you need more, check SendGrid's paid plans

## Alternative: Upgrading to PDF Attachments

Currently, emails are sent as HTML. To add PDF attachments in the future:

1. Install a PDF library: `pip install weasyprint`
2. The email route in `app.py` is already structured to make this upgrade easy
3. Just add PDF generation and attachment code

## Support

If you encounter issues:
- Check SendGrid's [documentation](https://docs.sendgrid.com)
- Review SendGrid's Activity dashboard for email delivery logs
- Contact SendGrid support (available even on free tier)
