# Email Automation with AI-Powered Replies

## Overview
This project is an AI-powered email automation system that sends batch emails, tracks replies, and generates AI-driven follow-ups. The system integrates:
- **SMTP & IMAP** for sending and receiving emails
- **SQLite** for tracking sent emails
- **LangChain & Gemini Pro** for AI-generated email content

---

## Features
✅ **Batch Email Sending:** Sends multiple investment-related emails using AI.
✅ **Email Tracking:** Logs sent emails and their statuses.
✅ **Reply Checking:** Fetches unread replies and updates email status.
✅ **AI-Powered Replies:** Uses Gemini Pro to generate follow-ups.
✅ **Auto-Reply Suggestions:** Asks before sending an AI-generated response.
✅ **Database Integration:** Tracks emails and their statuses.

---

## Installation & Setup
1. **Install Dependencies:**
   ```bash
   pip install smtplib imaplib email sqlite3 json langchain-google-genai
   ```
2. **Enable App Passwords for Gmail:**
   - Go to your Google Account Security settings.
   - Enable **2-Step Verification**.
   - Generate an **App Password**.
   - Replace `EMAIL_PASSWORD` in the script with this password.

3. **Set Up Google API Key for Gemini Pro:**
   - Get an API key from Google Cloud Console.
   - Replace `google_api_key` in the script.

---

## Code Breakdown

### 🔹 **Email Configuration**
```python
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
IMAP_SERVER = "imap.gmail.com"
```
Configures SMTP for sending emails and IMAP for checking replies.

### 🔹 **AI Model Initialization**
```python
llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key="your_api_key")
memory = ConversationBufferMemory(input_key="recipient", memory_key="history")
```
Initializes Gemini Pro for generating email content and stores conversation history.

### 🔹 **Database Setup**
```python
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
```
Creates an SQLite database to store sent email details.

### 🔹 **Email Generation Prompt**
```python
batch_email_prompt = PromptTemplate(
    input_variables=["batch_recipients"],
    template="""
    Generate professional investment emails in **valid JSON format only**.
    Each email must include:
    - recipient (email address)
    - subject (email subject)
    - body (email body)
    """
)
```
Defines an AI prompt to generate structured investment emails.

### 🔹 **Send Batch Emails**
```python
def send_emails(email_list):
    recipients_str = ", ".join(email_list)
    email_json = email_chain.run(batch_recipients=recipients_str)
    email_data = json.loads(email_json)
    for email_entry in email_data["emails"]:
        msg = MIMEText(email_entry["body"])
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = email_entry["recipient"]
        msg["Subject"] = email_entry["subject"]
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email_entry["recipient"], msg.as_string())
        cursor.execute("INSERT INTO sent_emails (recipient, subject, body, status) VALUES (?, ?, ?, 'Sent')", (email_entry["recipient"], email_entry["subject"], email_entry["body"]))
        conn.commit()
```
Generates and sends investment emails using Gemini and logs them in the database.

### 🔹 **Check Replies & Update Status**
```python
def check_replies():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    mail.select("inbox")
    status, messages = mail.search(None, 'UNSEEN')
    for email_id in messages[0].split():
        _, msg_data = mail.fetch(email_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        sender = msg["From"]
        subject = msg["Subject"]
        body = msg.get_payload(decode=True).decode(errors="ignore")
        cursor.execute("UPDATE sent_emails SET status = 'Replied' WHERE recipient = ?", (sender,))
        conn.commit()
```
Checks for unread email replies and updates their status in the database.

### 🔹 **AI-Generated Follow-ups**
```python
def suggest_followup(recipient, reply_text):
    followup_email = followup_chain.run(history=memory.load_memory_variables({}), reply=reply_text)
    print(f"🤖 AI Suggested Follow-Up for {recipient}: {followup_email}")
    cursor.execute("UPDATE sent_emails SET status = 'Follow-up Needed' WHERE recipient = ?", (recipient,))
    conn.commit()
```
Suggests AI-generated follow-ups if a response requires further action.

### 🔹 **Send Auto-Reply**
```python
def send_auto_reply(to_email, reply_content):
    subject = "Re: Your Email Regarding Investment"
    msg = MIMEText(reply_content)
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
    cursor.execute("UPDATE sent_emails SET status = 'Replied' WHERE recipient = ?", (to