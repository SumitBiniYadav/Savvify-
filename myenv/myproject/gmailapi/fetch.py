import re
import base64
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from bs4 import BeautifulSoup
from myapp.models import Order

EMAIL_SOURCES = {
    'zomato': ['order@zomato.com', 'noreply@zomato.com', 'noreply@mailers.zomato.com'],
    'swiggy': ['order@swiggy.in', 'no-reply@swiggy.in'],
    'blinkit': ['no-reply@blinkit.com'],
    'instamart': ['no-reply@instamart.com'],
    'zepto': ['no-reply@zeptonow.com'],
    'amazon': ['order-update@amazon.in'],
    'dominos': ['do-not-reply@dominos.co.in'],
}

# Build Gmail API service
def get_gmail_service(session):
    creds_data = session.get('credentials')
    if not creds_data:
        return None

    creds = Credentials(
        token=creds_data['token'],
        refresh_token=creds_data['refresh_token'],
        token_uri=creds_data['token_uri'],
        client_id=creds_data['client_id'],
        client_secret=creds_data['client_secret'],
        scopes=creds_data['scopes'],
    )

    service = build('gmail', 'v1', credentials=creds)
    return service

# Extract order number and amount from plain text
def parse_email(text):
    # Try various common formats for order number
    order_patterns = [
        r'ORDER\s*ID[:\s]*([A-Z0-9\-]+)',  # Zomato style
        r'Order\s*No\.?\s*[:\-]?\s*(\d+)',  # Domino's
        r'Order\s*ID[:\s]*([A-Z0-9\-]+)',
        r'Order\s*#[:\s]*([A-Z0-9\-]+)',
        r'Order\s*Number[:\s]*([A-Z0-9\-]+)',
        r'Order\s*Placed[:\s]*([A-Z0-9\-]+)',
        r'order\s*from\s*[A-Za-z\s]*\s*\(([A-Z0-9\-]+)\)',  # Fallback
    ]

    amount_patterns = [
        r'Total\s*paid\s*[-:]?\s*(?:₹|Rs\.?)\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)',  # Zomato style
        r'Order\s*Total\s*[:\-]?\s*Rs\.?\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)',       # Domino's
        r'(?:₹|Rs\.?)\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)',
        r'INR\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)',
    ]

    order_number = None
    for pattern in order_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_number = match.group(1)
            break

    amount = None
    for pattern in amount_patterns:
        match = re.search(pattern, text)
        if match:
            amount = float(match.group(1).replace(',', ''))
            break

    return order_number, amount

# Extract body from Gmail message payload
def get_email_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            body_data = part.get('body', {}).get('data')
            if mime_type in ['text/plain', 'text/html'] and body_data:
                decoded = base64.urlsafe_b64decode(body_data).decode('utf-8')
                return decoded
    else:
        # If there's no 'parts', check body directly
        body_data = payload.get('body', {}).get('data')
        if body_data:
            decoded = base64.urlsafe_b64decode(body_data).decode('utf-8')
            return decoded
    return ''

# Main order extraction logic
def extract_orders(session, user):
    credentials = Credentials(**session['credentials'])
    service = build('gmail', 'v1', credentials=credentials)

    # Gmail query: only recent order/invoice emails
    query = (
        'from:order@zomato.com OR '
        'from:order@swiggy.in OR '
        'from:no-reply@blinkit.com OR '
        'from:no-reply@zeptonow.com OR '
        'from:do-not-reply@dominos.co.in '
        'newer_than:30d'
    )
    results = service.users().messages().list(userId='me', q=query, maxResults=50).execute()
    messages = results.get('messages', [])

    print(f"📧 Fetched {len(messages)} messages")

    saved_orders = 0

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
        payload = msg_data.get('payload', {})
        headers = payload.get('headers', [])

        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '')

        print(f"\n📩 Subject: {subject}")
        print(f"📤 From: {sender}")

        # Get email content
        body = get_email_body(payload)
        if not body:
            print("❌ No body found, skipping.")
            continue

        # Convert HTML to text if needed
        soup = BeautifulSoup(body, 'html.parser')
        clean_text = soup.get_text(separator=' ', strip=True)

        # Extract order details
        order_number, amount = parse_email(clean_text)
        if not order_number or not amount:
            print("❌ Order data incomplete, skipping.")
            continue

        # Identify platform
        platform = "Unknown"
        for key, email_ids in EMAIL_SOURCES.items():
            if isinstance(email_ids, str):  # backward compatibility if any entry is still a string
                email_ids = [email_ids]
            if any(email_id.lower() in sender.lower() for email_id in email_ids):
                platform = key.capitalize()
                break


        # Check for duplicates
        if Order.objects.filter(order_number=order_number, user=user).exists():
            print(f"⚠️ Order {order_number} already exists, skipping.")
            continue

        # Save to DB
        Order.objects.create(
            user=user,
            platform=platform,
            order_number=order_number,
            amount=amount,
            timestamp=datetime.now()
        )
        print(f"✅ Order saved: {platform} - {order_number} - ₹{amount}")
        saved_orders += 1

    print(f"\n🎉 Total orders saved: {saved_orders}")
    return saved_orders
