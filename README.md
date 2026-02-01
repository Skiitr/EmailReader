# Microsoft 365 Email Reader

A Python CLI tool that fetches emails from Microsoft 365 Outlook using the Microsoft Graph API with OAuth 2.0 delegated authentication. Includes optional AI-powered classification to identify emails that need action.

## Features

- 🔐 **Secure OAuth 2.0 authentication** via MSAL with interactive login
- 💾 **Token caching** - login once, reuse tokens for subsequent runs
- 📧 **Flexible email fetching** - filter by folder, read status, and count
- 🤖 **AI classification** - identify action requests, questions, and meetings (optional)
- 📄 **JSON output** - structured output to stdout and optional file
- 🖥️ **Cross-platform** - works on macOS (Apple Silicon) and Windows

## Prerequisites

- Python 3.11 or higher
- A Microsoft 365 account (work, school, or personal)
- An Azure App Registration (free - no paid services required)
- OpenAI API key (optional, for AI classification)

---

## Azure App Registration Setup

Follow these steps to create and configure your Azure App Registration:

### Step 1: Create the App Registration

1. Go to the [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **+ New registration**
4. Fill in the details:
   - **Name**: `Email Reader CLI` (or any name you prefer)
   - **Supported account types**: Choose based on your needs:
     - *Single tenant*: Only accounts in your organization
     - *Multitenant*: Accounts in any organization
     - *Personal Microsoft accounts*: Include personal Outlook.com accounts
   - **Redirect URI**: Leave blank for now (we'll add it next)
5. Click **Register**

### Step 2: Note Your Application (Client) ID

After registration, you'll see the **Overview** page. Copy the **Application (client) ID** - you'll need this later.

Optionally, also copy the **Directory (tenant) ID** if you want to restrict to a specific tenant.

### Step 3: Configure Redirect URI

1. Go to **Authentication** in the left menu
2. Click **+ Add a platform**
3. Select **Mobile and desktop applications**
4. Check the box for `http://localhost`
5. Click **Configure**

### Step 4: Enable Public Client Flows

Still in the **Authentication** section:

1. Scroll down to **Advanced settings**
2. Find **Allow public client flows**
3. Set it to **Yes**
4. Click **Save**

### Step 5: Add API Permissions

1. Go to **API permissions** in the left menu
2. Click **+ Add a permission**
3. Select **Microsoft Graph**
4. Select **Delegated permissions**
5. Search for and select:
   - `Mail.Read` - Read user mail
   - (Optional) `Mail.ReadBasic` - Read basic mail properties
6. Click **Add permissions**

> **Note**: If you see "Admin consent required" next to the permission, you may need an Azure AD admin to grant consent. For personal accounts or if you are the admin, you can grant consent yourself by clicking "Grant admin consent for [tenant]".

---

## Installation

### 1. Clone or Download

Navigate to your project directory:

**macOS / Linux:**
```bash
cd ~/Documents/GitHub/EmailReader
```

**Windows (PowerShell):**
```powershell
cd $HOME\Documents\GitHub\EmailReader
```

### 2. Create Virtual Environment

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

> **Note**: On Windows, if you get an execution policy error in PowerShell, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Set your Azure App Registration client ID:

**macOS / Linux:**
```bash
export M365_CLIENT_ID="your-application-client-id-here"
export M365_TENANT_ID="your-tenant-id-here"  # Optional
export M365_USER_EMAIL="your.email@domain.com" # Recommended for To vs Cc detection
```

**Windows (PowerShell):**
```powershell
$env:M365_CLIENT_ID = "your-application-client-id-here"
$env:M365_TENANT_ID = "your-tenant-id-here"  # Optional
$env:M365_USER_EMAIL = "your.email@domain.com" # Recommended for To vs Cc detection
```

**Windows (Command Prompt):**
```cmd
set M365_CLIENT_ID=your-application-client-id-here
set M365_TENANT_ID=your-tenant-id-here
set M365_USER_EMAIL=your.email@domain.com
```

### Persisting Environment Variables

**macOS / Linux** - Add to shell profile:
```bash
echo 'export M365_CLIENT_ID="your-client-id"' >> ~/.zshrc
source ~/.zshrc
```

**Windows** - Set permanently via System Properties:
1. Press `Win + R`, type `sysdm.cpl`, press Enter
2. Go to **Advanced** tab → **Environment Variables**
3. Under "User variables", click **New**
4. Add `M365_CLIENT_ID` with your client ID value
5. Click OK to save

### 5. Configure OpenAI API Key (Optional)

For AI-powered email classification, set your OpenAI API key:

**macOS / Linux:**
```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_KEY = "sk-your-api-key-here"
```

Get your API key from: https://platform.openai.com/api-keys

> **Note**: AI classification is optional. Use `--no-ai` to skip if you don't have an API key.

**Optional OpenAI settings:**
| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `OPENAI_MODEL` | gpt-4o-mini | Model for classification |
| `OPENAI_TIMEOUT_SECONDS` | 30 | Request timeout |
| `OPENAI_MAX_BODY_CHARS` | 2500 | Max body chars to send |

---

## Usage

### Basic Usage

```bash
python main.py                              # Fetch 25 unread inbox messages
python main.py --max 50 --pretty            # Fetch 50 messages, pretty-print
python main.py --no-ai --out emails.json    # Fetch without AI classification
python main.py --out-enriched enriched.json # Fetch with AI, save enriched output
python main.py --report report.md           # Generate markdown report of flagged emails
```

### Available Options

**Email Fetching:**
| Option | Default | Description |
|--------|---------|-------------|
| `--max` | 25 | Maximum number of messages to fetch |
| `--folder` | inbox | Mail folder to fetch from |
| `--unread-only` | true | Only fetch unread messages |
| `--out` | (none) | Output file for normalized JSON |
| `--pretty` | (flag) | Pretty-print JSON with indentation |
| `--no-body` | (flag) | Exclude body_text from output |

**AI Classification:**
| Option | Default | Description |
|--------|---------|-------------|
| `--no-ai` | (flag) | Disable AI classification |
| `--max-ai` | 50 | Max emails to send to AI |
| `--min-confidence` | 0.75 | Minimum confidence for flagging |
| `--out-enriched` | (none) | Output file for enriched JSON with AI fields |
| `--report` | (none) | Generate markdown report |
| `--apply` | (flag) | Apply flags to mailbox (not yet implemented) |

### Common Folder Names

- `inbox` - Inbox
- `sentitems` - Sent Items
- `drafts` - Drafts
- `deleteditems` - Deleted Items
- `junkemail` - Junk Email
- `archive` - Archive

---

## First Run - Authentication

On the first run (or when tokens expire), the script will:

1. Open your default browser to the Microsoft login page
2. Ask you to sign in with your Microsoft 365 account
3. Request permission to read your mail
4. Redirect back to `http://localhost` (the browser tab can be closed)

After successful authentication, tokens are cached in `token_cache.json` and subsequent runs won't require re-login.

---

## Example Output

Output is a JSON array of normalized message objects:

```json
[
  {
    "message_id": "AAMkAGI2...",
    "conversation_id": "AAQkAGI2...",
    "internet_message_id": "<abc123@mail.example.com>",
    "subject": "Weekly Team Update",
    "from": {
      "name": "John Doe",
      "email": "john.doe@company.com"
    },
    "to": ["jane.smith@company.com"],
    "cc": [],
    "received_at": "2026-01-24T14:30:00Z",
    "sent_at": "2026-01-24T14:29:55Z",
    "is_read": false,
    "web_link": "https://outlook.office365.com/owa/?ItemID=...",
    "has_attachments": false,
    "importance": "normal",
    "body_preview": "Hi team, Here's our weekly update...",
    "body_text": "Hi team,\n\nHere's our weekly update..."
  }
]
```

### Output Schema

| Field | Type | Description |
|-------|------|-------------|
| `message_id` | string | Graph message ID |
| `conversation_id` | string\|null | Thread/conversation ID |
| `internet_message_id` | string\|null | RFC 2822 Message-ID |
| `subject` | string\|null | Email subject |
| `from` | object | Sender with `name` and `email` |
| `to` | array | List of recipient email addresses |
| `cc` | array | List of CC email addresses |
| `received_at` | string\|null | ISO 8601 received timestamp |
| `sent_at` | string\|null | ISO 8601 sent timestamp |
| `is_read` | boolean | Read status |
| `web_link` | string\|null | Outlook Web App link |
| `has_attachments` | boolean | Has attachments |
| `importance` | string\|null | low/normal/high |
| `body_preview` | string\|null | Short preview text |
| `body_text` | string\|null | Cleaned plain text body (max 4000 chars) |

---

## Troubleshooting

### Common Errors and Solutions

#### AADSTS50011: The redirect URI '...' does not match

**Cause**: Redirect URI not configured correctly in Azure.

**Solution**:
1. Go to Azure Portal → App registrations → Your app → Authentication
2. Add `http://localhost` as a Mobile and desktop application redirect URI
3. Save changes

#### AADSTS7000218: Request body must contain client_secret or client_assertion

**Cause**: Public client flows not enabled.

**Solution**:
1. Go to Azure Portal → App registrations → Your app → Authentication
2. Under "Advanced settings", set "Allow public client flows" to **Yes**
3. Save changes

#### AADSTS700016: Application with identifier '...' was not found

**Cause**: Invalid client ID or app doesn't exist.

**Solution**:
- Verify `M365_CLIENT_ID` matches your App Registration's Application (client) ID
- Check that the app registration wasn't deleted

#### AADSTS65001: The user or administrator has not consented

**Cause**: Permissions haven't been granted.

**Solution**:
- For personal accounts: Review and accept permissions during login
- For work/school accounts: Ask your Azure AD admin to grant admin consent
- Or sign in with an admin account and consent on behalf of the organization

#### 403 Forbidden: Missing required permissions

**Cause**: Mail.Read permission not granted or consented.

**Solution**:
1. Verify Mail.Read is added in API permissions
2. Delete `token_cache.json` and re-authenticate to trigger consent prompt

#### 401 Unauthorized

**Cause**: Token expired or invalid.

**Solution**:

*macOS / Linux:*
```bash
rm token_cache.json
python main.py  # Re-authenticate
```

*Windows:*
```powershell
Remove-Item token_cache.json
python main.py  # Re-authenticate
```

#### Folder not found

**Cause**: Invalid folder name.

**Solution**: Use one of the well-known folder names:
- `inbox`, `sentitems`, `drafts`, `deleteditems`, `junkemail`, `archive`

---

## Files

| File | Description |
|------|-------------|
| `main.py` | CLI entry point with argument parsing |
| `graph_client.py` | MSAL auth + Graph API client |
| `normalize.py` | Email body cleaning and canonical schema normalization |
| `settings.py` | Configuration and environment variables |
| `smoke_test_normalize.py` | Smoke tests for normalization module |
| `requirements.txt` | Python dependencies |
| `token_cache.json` | Token cache (created after first login) |

---

## Security Notes

- **token_cache.json** contains sensitive tokens - do not commit to version control
- Add `token_cache.json` to your `.gitignore`
- Tokens are automatically refreshed when possible
- For production use, consider more secure token storage

---

## License

MIT License - feel free to use and modify.
