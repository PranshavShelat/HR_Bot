# HR Bot

A command-line HR assistant. It uses a Gemini agent (LangGraph) with these tools:

- **HR policy questions**: sent to a Langflow flow (Groq LLM + the employee handbook)
- **Leave balance / apply for leave**: stored in a local SQLite DB and sent to an n8n webhook
- **Admin**: add employees, list employees

## Files

| File | What it is |
|---|---|
| `bot.py` | The chatbot. Run this. |
| `langflow/hr_bot_flow.json` | The Langflow flow export (API keys removed). |
| `EmployeeHandbook.txt` / `Employee Handbook.docx` | Policy document the flow answers from. |
| `.env.example` | Template for the secrets file. Copy to `.env` and fill in. |
| `requirements.txt` | Python packages. |

`hr_database.db` is not in the repo. `bot.py` creates it the first time you run it, with these users:
`pranshav / pass123`, `alice / alice456`, `admin / 1234`.

## Setting up on a new laptop (Windows)

### 1. Install the tools
- **Python 3.12**: https://www.python.org/downloads/ (tick "Add python.exe to PATH" during install)
- **Git**: https://git-scm.com/download/win

### 2. Clone the repo and install packages
Open PowerShell:
```powershell
cd E:\Work          # or wherever you want it
git clone https://github.com/PranshavShelat/HR_Bot.git
cd HR_Bot
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
If `Activate.ps1` is blocked, first run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
Installing Langflow takes a while.

### 3. Create the `.env` file
Git doesn't store `.env`. Pick one:
- **Copy it** from the old laptop (USB drive, or message it to yourself privately), or
- `copy .env.example .env` and fill in the values yourself.

`LANGFLOW_FLOW_ID` and `LANGFLOW_API_KEY` **change on a new laptop**. Step 4 shows how to get the new ones.

### 4. Set up Langflow
In one terminal (with the venv activated):
```powershell
langflow run
```
Open http://localhost:7860, then:
1. **Import the flow**: on the main page, click the Import / upload button and choose `langflow/hr_bot_flow.json`.
2. **Groq key**: open the flow, click the **Groq** component, and paste your Groq key (the `GROQ_API_KEY` value in `.env`) into its API Key field.
3. **Handbook file**: click the **File** component and upload `EmployeeHandbook.txt` from the repo folder.
4. Test it in the **Playground** with a question like "How many sick days do I get?"
5. **Flow ID**: look at the URL of the open flow (`http://localhost:7860/flow/<FLOW-ID>`). Copy that ID into `LANGFLOW_FLOW_ID` in `.env`. You can also find it under the **API / Share → API access** panel.
6. **Langflow API key**: go to **Settings → Langflow API Keys → Add New**, create a key, and put it in `LANGFLOW_API_KEY` in `.env`.

### 5. Run the bot
Leave Langflow running. Open a **second** terminal:
```powershell
cd E:\Work\HR_Bot
.venv\Scripts\Activate.ps1
python bot.py
```
Log in (e.g. `pranshav` / `pass123`) and chat. Type `exit` to quit.

## Syncing changes between laptops
Before you start working on a laptop:
```powershell
git pull
```
After you make changes:
```powershell
git add .
git commit -m "describe what you changed"
git push
```
If you change the flow in Langflow, export it again (leave "Save with my API keys" **unchecked**). Overwrite `langflow/hr_bot_flow.json` with it, then commit and push.
