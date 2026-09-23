import os
import hashlib
import requests
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

# ─────────────────────────────────────────────
# CONFIG  (secrets are loaded from .env — see .env.example)
# ─────────────────────────────────────────────
load_dotenv()

DB_PATH           = os.getenv("DB_PATH", "hr_database.db")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ADMIN_USERNAME    = "admin"
ADMIN_PASSWORD    = os.environ["ADMIN_PASSWORD"]
# Demo accounts created on first run, as "user:password,user:password"
SEED_USERS        = os.getenv("SEED_USERS", "")
LANGFLOW_HOST     = os.getenv("LANGFLOW_HOST", "http://localhost:7860")
LANGFLOW_URL      = (
    f"{LANGFLOW_HOST}/api/v1/run/"
    f"{os.getenv('LANGFLOW_FLOW_ID', 'hr-policy-rag')}?stream=false"
)
LANGFLOW_API_KEY  = os.getenv("LANGFLOW_API_KEY")
N8N_LEAVE_WEBHOOK = os.getenv("N8N_LEAVE_WEBHOOK")
N8N_LOG_WEBHOOK   = os.getenv("N8N_LOG_WEBHOOK")
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_MINUTES    = int(os.getenv("LOCKOUT_MINUTES", "15"))


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate(username: str, password: str) -> bool:
    """Returns True if username + password match a DB record."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT password_hash FROM employees WHERE username = ?",
                (username.lower(),)
            ).fetchone()
        return row is not None and row[0] == hash_password(password)
    except Exception:
        return False


def locked_until(username: str) -> datetime | None:
    """Returns when the account's lockout ends, or None if it isn't locked."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT locked_until FROM employees WHERE username = ?", (username,)
        ).fetchone()
    if row and row[0]:
        until = datetime.fromisoformat(row[0])
        if until > datetime.now():
            return until
    return None


def record_failed_login(username: str) -> bool:
    """Counts a failed login; locks the account on the 3rd in a row. Returns True if it just locked."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT failed_attempts FROM employees WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return False
        failures = row[0] + 1
        until = None
        if failures >= MAX_LOGIN_ATTEMPTS:
            until = (datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
            failures = 0
        conn.execute(
            "UPDATE employees SET failed_attempts = ?, locked_until = ? WHERE username = ?",
            (failures, until, username),
        )
        conn.commit()
    return until is not None


def reset_failed_logins(username: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE employees SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
            (username,),
        )
        conn.commit()


def is_admin(username: str) -> bool:
    return username.lower() == ADMIN_USERNAME


def log_to_sheet(action: str, details: str, user: str = "system",
                 days: int = None, reason: str = None) -> None:
    """Silently sends an activity log entry to n8n → Google Sheets."""
    try:
        requests.post(
            N8N_LOG_WEBHOOK,
            json={
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action":    action,
                "details":   details,
                "user":      user,
                "days":      days or "",
                "reason":    reason or "",
            },
            timeout=10,
        )
        print(f"[LOG] Logged: {action} — {details}")
    except Exception as e:
        print(f"[LOG] Warning: Could not log to sheet: {e}")


# ─────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────
def init_db() -> None:
    """Creates the employees table with username/password/leave_balance."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id             INTEGER PRIMARY KEY,
                username       TEXT UNIQUE NOT NULL,
                password_hash  TEXT NOT NULL,
                leave_balance  INTEGER DEFAULT 15,
                failed_attempts INTEGER DEFAULT 0,
                locked_until   TEXT
            )
        ''')
        # Add lockout columns to databases created before they existed
        columns = {row[1] for row in conn.execute("PRAGMA table_info(employees)")}
        if "failed_attempts" not in columns:
            conn.execute("ALTER TABLE employees ADD COLUMN failed_attempts INTEGER DEFAULT 0")
        if "locked_until" not in columns:
            conn.execute("ALTER TABLE employees ADD COLUMN locked_until TEXT")
        # Seed default users only if table is empty
        if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            defaults = [(ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), 0)]
            for entry in filter(None, SEED_USERS.split(",")):
                uname, pwd = entry.strip().split(":", 1)
                defaults.append((uname.lower(), hash_password(pwd), 15))
            conn.executemany(
                "INSERT INTO employees (username, password_hash, leave_balance) VALUES (?, ?, ?)",
                defaults,
            )
            conn.commit()
            print("[DB] Database initialised with default users.")

init_db()


# ─────────────────────────────────────────────
# TOOLS  (current_user injected at runtime)
# ─────────────────────────────────────────────

@tool
def ask_hr_policy(query: str) -> str:
    """Query the Langflow HR policy RAG pipeline for general HR rules and policies."""
    print(f"\n[TOOL] ask_hr_policy → '{query}'")
    payload = {
        "output_type": "chat",
        "input_type":  "chat",
        "input_value": query,
        "session_id":  "hr_agent_session",
    }
    try:
        resp = requests.post(
            LANGFLOW_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": LANGFLOW_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        print(f"[DEBUG] Raw Langflow response: {str(data)[:500]}")

        try:
            output = data["outputs"][0]["outputs"][0]
            msg    = output.get("results", {}).get("message", {})
            answer = (
                msg.get("text")
                or msg.get("data", {}).get("text")
                or output.get("artifacts", {}).get("message", "")
                or output.get("outputs", {}).get("message", {}).get("message", "")
                or str(output)
            )
        except (KeyError, IndexError) as e:
            print(f"[DEBUG] Parse error: {e}")
            answer = str(data)

        return answer

    except requests.exceptions.ConnectionError:
        return f"Error: Cannot reach Langflow at {LANGFLOW_HOST}. Is it running?"
    except requests.exceptions.Timeout:
        return "Error: The HR policy database timed out."
    except requests.exceptions.HTTPError as e:
        return f"Error: Langflow returned HTTP {e.response.status_code}."
    except Exception as e:
        return f"Error contacting HR policy database: {type(e).__name__}: {e}"


@tool
def check_leave_balance(username: str) -> str:
    """Check how many leave days a specific employee has remaining."""
    print(f"\n[TOOL] check_leave_balance → '{username}'")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT leave_balance FROM employees WHERE username = ?",
                (username.lower(),),
            ).fetchone()

        if row:
            return f"{username} has {row[0]} leave day(s) remaining."
        return f"No employee with username '{username}' was found."
    except Exception as e:
        return f"Database error: {e}"


@tool
def apply_for_leave(username: str, days: int, reason: str) -> str:
    """Submit a leave application via the n8n webhook."""
    print(f"\n[TOOL] apply_for_leave → {username}, {days} day(s), reason='{reason}'")
    try:
        # Check current balance first
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT leave_balance FROM employees WHERE username = ?",
                (username.lower(),)
            ).fetchone()

        if not row:
            return f"No employee with username '{username}' found."

        current_balance = row[0]
        if days > current_balance:
            return f"❌ Insufficient leave balance. You have {current_balance} day(s) remaining but requested {days}."

        # Send to n8n
        resp = requests.post(
            N8N_LEAVE_WEBHOOK,
            json={"username": username, "days": days, "reason": reason},
            timeout=15,
        )
        resp.raise_for_status()

        # Deduct from DB only after successful n8n submission
        new_balance = current_balance - days
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE employees SET leave_balance = ? WHERE username = ?",
                (new_balance, username.lower())
            )
            conn.commit()

        log_to_sheet("LEAVE_APPLIED", f"{username} applied {days} day(s) for: {reason}",
                     user=username, days=days, reason=reason)
        return f"✅ Leave application submitted: {days} day(s) for '{reason}'. Remaining balance: {new_balance} day(s)."

    except requests.exceptions.Timeout:
        return "Error: The leave submission server timed out."
    except requests.exceptions.HTTPError as e:
        return f"Error: Webhook returned HTTP {e.response.status_code}."
    except Exception as e:
        return f"Failed to submit leave application: {e}"


@tool
def add_new_employee(username: str, password: str, admin_password: str) -> str:
    """Add a new employee. Requires the admin password."""
    print(f"\n[TOOL] add_new_employee → '{username}'")
    if admin_password != ADMIN_PASSWORD:
        log_to_sheet("ADD_EMPLOYEE_FAILED", f"Failed attempt to add '{username}'", user="admin")
        return "❌ Incorrect admin password. Employee was NOT added."
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO employees (username, password_hash, leave_balance) VALUES (?, ?, ?)",
                (username.lower(), hash_password(password), 15),
            )
            conn.commit()
            affected = conn.execute("SELECT changes()").fetchone()[0]

        if affected:
            log_to_sheet("EMPLOYEE_ADDED", f"Added: {username} (15 days)", user="admin")
            return f"✅ '{username}' added with password '{password}' and 15 leave days."
        return f"'{username}' already exists in the database."
    except Exception as e:
        return f"Database error: {e}"


@tool
def list_all_employees(admin_password: str) -> str:
    """List all employees and their leave balances. Requires the admin password."""
    print("\n[TOOL] list_all_employees")
    if admin_password != ADMIN_PASSWORD:
        log_to_sheet("LIST_EMPLOYEES_FAILED", "Failed admin access (wrong password)", user="admin")
        return "❌ Incorrect admin password. Access denied."
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT username, leave_balance FROM employees ORDER BY username"
            ).fetchall()

        if not rows:
            return "No employees found."

        log_to_sheet("LIST_EMPLOYEES", f"Admin viewed all {len(rows)} employee(s)", user="admin")
        lines = ["Employee Roster:"]
        for uname, balance in rows:
            lines.append(f"  • {uname}: {balance} leave day(s) remaining")
        return "\n".join(lines)
    except Exception as e:
        return f"Database error: {e}"


# ─────────────────────────────────────────────
# AGENT SETUP
# ─────────────────────────────────────────────

TOOLS = [ask_hr_policy, apply_for_leave, check_leave_balance,
         add_new_employee, list_all_employees]

llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0)


def make_system_prompt(username: str) -> str:
    admin_note = (
        "\nYou are logged in as ADMIN. You can add employees and list all employees."
        if is_admin(username)
        else f"\nThe logged-in user is '{username}'. Use this username automatically for leave balance and leave applications — do NOT ask for it again."
    )
    return f"""You are a helpful HR assistant.{admin_note}

1. POLICY QUESTIONS   → use 'ask_hr_policy' for HR rules, benefits, or policies.
2. APPLY FOR LEAVE    → use 'apply_for_leave'. Ask for days and reason if not provided.
                        Always use the logged-in username automatically.
3. LEAVE BALANCE      → use 'check_leave_balance'. Use the logged-in username automatically.
4. ADD EMPLOYEE       → use 'add_new_employee'. Ask for new username, their password, then admin password.
5. LIST ALL EMPLOYEES → use 'list_all_employees'. Ask for admin password first.
6. NO GUESSING        → Never invent data. Only use tool results.
7. NO REPETITION      → Once a tool returns a result, give a clear answer and stop."""


# ─────────────────────────────────────────────
# LOGIN FLOW
# ─────────────────────────────────────────────

def login() -> str:
    """Handles login at startup. Returns the authenticated username."""
    print("\n" + "═" * 50)
    print("  HR Assistant — Please log in")
    print("═" * 50)

    attempts = 0
    while attempts < MAX_LOGIN_ATTEMPTS:
        username = input("\nUsername: ").strip().lower()
        password = input("Password: ").strip()

        until = locked_until(username)
        if until:
            print(f"🔒 Account '{username}' is locked until {until:%H:%M}. Try again later.")
            log_to_sheet("LOGIN_BLOCKED", f"Login attempt on locked account {username}", user=username)
            exit(1)

        if authenticate(username, password):
            reset_failed_logins(username)
            print(f"\n✅ Welcome, {username}!")
            log_to_sheet("LOGIN", f"{username} logged in", user=username)
            return username
        else:
            attempts += 1
            if record_failed_login(username):
                print(f"🔒 Too many failed attempts. '{username}' is locked for {LOCKOUT_MINUTES} minutes.")
                log_to_sheet("ACCOUNT_LOCKED", f"{username} locked after {MAX_LOGIN_ATTEMPTS} failed logins", user=username)
                exit(1)
            remaining = MAX_LOGIN_ATTEMPTS - attempts
            if remaining > 0:
                print(f"❌ Incorrect username or password. {remaining} attempt(s) left.")
            else:
                print("❌ Too many failed attempts. Exiting.")
                exit(1)


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def main() -> None:
    current_user = login()

    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        prompt=make_system_prompt(current_user),
    )

    print("\n" + "─" * 50)
    print("  Type your question, or 'exit' to quit.")
    print("─" * 50 + "\n")

    history = []

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "bye"}:
            log_to_sheet("LOGOUT", f"{current_user} logged out", user=current_user)
            print("Goodbye! 👋")
            break

        history.append(HumanMessage(content=user_input))
        print("\n[thinking...]\n")

        try:
            result  = agent.invoke({"messages": history})
            history = result["messages"]
            raw     = history[-1].content
            reply   = raw[0].get("text", str(raw)) if isinstance(raw, list) else raw
        except Exception as exc:
            reply = f"⚠️  Agent error: {exc}"

        print(f"Bot: {reply}\n")
        print("─" * 50)


if __name__ == "__main__":
    main()