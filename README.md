# Production Process Guide

## 1. Backend Setup
The backend has been refactored into a modular, production-ready architecture.

### Directory Structure
- `backend/routers`: API Endpoints (Auth, Prompts, Users).
- `backend/core`: Configuration, Database, Security.
- `backend/services`: Isolated business logic (Email, LLM, Memory).

### How to Run
We have created a `run_prod.bat` script for easy startup.
1. Double-click `run_prod.bat`.
2. It will detect your environment, activate it, and start the high-performance `uvicorn` server at `http://localhost:8000`.

## 2. Chrome Extension Setup
The extension is capable of persistent tracking and seamless authentication.

### Configuration
- The extension is configured to talk to `http://localhost:8000` by default.
- If you deploy the backend to a cloud server (like Hugging Face), update `API_URL` in `extension/content.js`.

### Installation
1. Open Chrome and go to `chrome://extensions`.
2. Enable "Developer Mode" (top right).
3. Click "Load Unpacked".
4. Select the `prompt_engineering_skeleton/extension` folder.

## 3. Workflow
1. **Start Backend**: Run `run_prod.bat`.
2. **Login**: Open the Extension Popup -> Click "Login with Google". 
3. **Use**: Go to ChatGPT/Claude and start typing. The "Memory" button will appear.