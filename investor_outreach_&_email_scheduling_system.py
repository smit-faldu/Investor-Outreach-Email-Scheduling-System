import smtplib
import imaplib
import email
import sqlite3
import json
from email.mime.text import MIMEText
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
import re

# 🔹 SMTP Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "EMAIL_ADDRESS"
EMAIL_PASSWORD = "EMAIL_PASSWORD"  # Use App Password

# 🔹 Configure IMAP (for reading replies)
IMAP_SERVER = "imap.gmail.com"

# 🔹 Initialize LangChain with Gemini Pro
llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key="GEMINI_API_KEY")

# 🔹 Memory for tracking conversation history
memory = ConversationBufferMemory(input_key="recipient", memory_key="history")

# 🔹 Email Database (SQLite)
conn = sqlite3.connect("email_tracking.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS sent_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT,
    subject TEXT,
    body TEXT,
    status TEXT DEFAULT 'Scheduled',
    category TEXT DEFAULT 'Investment'
)
""")
conn.commit()

# 🔹 Improved Batch Email Prompt
batch_email_prompt = PromptTemplate(
    input_variables=["batch_recipients"],
    template="""
    Generate professional investment emails in **valid JSON format only**.

    Each email must include:
    - recipient (email address)
    - subject (email subject)
    - body (email body)

    Do **not** add explanations, only return JSON.

    Recipients: {batch_recipients}

    Output format:
    ```json
    {{
        "emails": [
            {{
                "recipient": "email1@example.com",
                "subject": "Exclusive AI Investment Opportunity",
                "body": "Dear Investor, we have an amazing AI stocks opportunity..."
            }},
            {{
                "recipient": "email2@example.com",
                "subject": "Tech Stocks Boom Alert!",
                "body": "Hello, we have identified a profitable investment in tech stocks..."
            }}
        ]
    }}
    ```
    """
)

email_chain = LLMChain(llm=llm, prompt=batch_email_prompt)

def generate_email(recipient, investment_type):
    return email_chain.run(recipient=recipient, investment_type=investment_type)

# 🔹 Function to Send Batch Emails
def send_emails(email_list):
    """Generates and sends multiple emails using Gemini in a single API call."""
    recipients_str = ", ".join(email_list)
    email_json = email_chain.run(batch_recipients=recipients_str)

    # ✅ Debugging Step: Print Raw Output
    print("🔍 Raw Gemini Output:")
    print(email_json)

    try:
        # Extract JSON part if Gemini adds extra text
        match = re.search(r'\{.*\}', email_json, re.DOTALL)
        if match:
            email_json = match.group(0)

        # Parse JSON response
        email_data = json.loads(email_json)

        if "emails" not in email_data:
            print("❌ Invalid JSON structure received.")
            return

        for email_entry in email_data["emails"]:
            recipient = email_entry["recipient"]
            subject = email_entry["subject"]
            body = email_entry["body"]

            # Send Email
            msg = MIMEText(body)
            msg["From"] = EMAIL_ADDRESS
            msg["To"] = recipient
            msg["Subject"] = subject

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, recipient, msg.as_string())

            # ✅ Log Sent Email in Database
            cursor.execute("INSERT INTO sent_emails (recipient, subject, body, status) VALUES (?, ?, ?, 'Sent')",
                           (recipient, subject, body))
            conn.commit()

            print(f"✅ Email sent to {recipient}")

    except json.JSONDecodeError:
        print("❌ JSON Parsing Failed. Invalid format received from Gemini.")
    except Exception as e:
        print(f"❌ Failed to send emails: {e}")

# 🔹 Check for Replies
def check_replies():
    """Checks for unread replies, updates status, and suggests follow-ups."""
    try:
        print("🔄 Checking for replies...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        print(f"📥 Found {len(email_ids)} unread replies")

        for email_id in email_ids:
            _, msg_data = mail.fetch(email_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    sender = msg["From"]
                    subject = msg["Subject"]
                    body = ""

                    # Extract sender's email only
                    email_match = re.search(r'<(.+?)>', sender)
                    if email_match:
                        sender = email_match.group(1)

                    # Extract email body
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")

                    # Check if sender is in database
                    cursor.execute("SELECT * FROM sent_emails WHERE recipient = ?", (sender,))
                    sent_email = cursor.fetchone()

                    if sent_email:
                        print(f"✅ Reply from {sender}: {subject}")
                        print(f"✉ {body[:200]}...")  # Show preview of reply

                        # ✅ Update email status
                        if "urgent" in body.lower() or "question" in body.lower():
                            suggest_followup(sender, body)  # AI Suggests Manual Follow-up
                            cursor.execute("UPDATE sent_emails SET status = 'Follow-up Needed' WHERE recipient = ?", (sender,))
                        else:
                            confirm_and_send_auto_reply(sender, body)  # Ask before auto-replying
                            cursor.execute("UPDATE sent_emails SET status = 'Replied' WHERE recipient = ?", (sender,))

                        conn.commit()

    except Exception as e:
        print(f"❌ Error checking replies: {e}")

# 🔹 AI Auto-Reply Function
def confirm_and_send_auto_reply(to_email, received_message):
    """Asks user before sending AI-generated auto-reply."""
    try:
        reply_content = followup_chain.run({
            "history": memory.load_memory_variables({}),
            "reply": received_message,
            "recipient": to_email
        })

        print("\n🤖 AI-Generated Reply:")
        print(reply_content)
        send_reply = input("\nDo you want to send this auto-reply? (yes/no): ").strip().lower()

        if send_reply == "yes":
            send_auto_reply(to_email, reply_content)
        else:
            print("🚫 Auto-reply not sent.")

    except Exception as e:
        print(f"❌ Failed to generate auto-reply: {e}")

# 🔹 Auto-Reply Sender
def send_auto_reply(to_email, reply_content):
    """Sends an AI-generated auto-reply email."""
    try:
        subject = "Re: Your Email Regarding Investment"
        msg = MIMEText(reply_content)
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email
        msg["Subject"] = subject

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())

        print(f"✅ Auto-reply sent to {to_email}")

        # ✅ Update Database
        cursor.execute("UPDATE sent_emails SET status = 'Replied' WHERE recipient = ?", (to_email,))
        conn.commit()

    except Exception as e:
        print(f"❌ Failed to send auto-reply: {e}")

# 🔹 AI Follow-Up Suggestions
followup_prompt = PromptTemplate(
    input_variables=["history", "reply", "recipient"],
    template="Based on the past conversation: {history}, generate a follow-up email reply to {recipient} based on this reply: {reply}."
)
followup_chain = LLMChain(llm=llm, prompt=followup_prompt, memory=memory)

def suggest_followup(recipient, reply_text):
    """Suggests a follow-up email if needed."""
    followup_email = followup_chain.run(history=memory.load_memory_variables({}), reply=reply_text)

    print(f"🤖 AI Suggested Follow-Up for {recipient}: {followup_email}")

    # ✅ Mark Follow-up Needed
    cursor.execute("UPDATE sent_emails SET status = 'Follow-up Needed' WHERE recipient = ?", (recipient,))
    conn.commit()

# 🔹 Display Email Status
def get_email_status():
    """Fetch and display email statuses from the database."""
    cursor.execute("SELECT recipient, status FROM sent_emails")
    emails = cursor.fetchall()

    if not emails:
        print("📭 No emails found.")
        return

    print("\n📌 Email Statuses:")
    for recipient, status in emails:
        print(f"📧 {recipient}: {status}")

recipient_list = ["test123@gmail.com", "test456@gmail.com"]
send_emails(recipient_list)

# 🔹 Check for Replies & Ask Before Sending Auto-Replies

get_email_status()

while True:
    check_replies()