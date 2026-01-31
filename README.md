# 🧠 Prompt Memory: Context-Aware Prompt Engine

**Prompt Memory** is a full-stack AI optimization framework designed to transform raw ideas into high-precision LLM prompts. 

Unlike standard prompt enhancers, this tool features **Long-Term Vector Memory**. It "learns" from your successful interactions by storing them in a vector database, allowing it to recall your specific coding style, preferred tech stack, and past context to automatically engineer superior prompts using the **CO-STAR Framework** (Context, Objective, Style, Tone, Audience, Response).

---

## 🚀 Key Features

* **✨ Universal Integration:** Injects a "Memory" button directly into **ChatGPT, Gemini, Claude, and Perplexity**.
* **🧠 Vector-Based Recall:** Utilizes **Qdrant** to store and retrieve past prompts, effectively giving your AI a long-term memory.
* **💎 CO-STAR Optimization:** Automatically rewrites raw inputs (e.g., "fix this code") into expert-level instructions using **Groq (Llama 3.3-70b)**.
* **🛡️ Smart Redundancy Checks:** Prevents database bloat by calculating cosine similarity—if a prompt is >87% similar to an existing one, it skips saving.
* **⚡ Latency-First Architecture:** Uses local embeddings (`all-MiniLM-L6-v2`) via **Sentence Transformers** for fast vectorization before making API calls.

---

## 🛠️ Tech Stack

### **Frontend (Chrome Extension)**
* **Manifest V3**: Secure and modern extension architecture.
* **JavaScript (ES6+)**: Handles DOM manipulation and API communication.
* **Localtunnel**: Exposes the local FastAPI backend to the HTTPS-required extension environment.

### **Backend (API)**
* **FastAPI**: High-performance asynchronous API framework.
* **Groq API**: Powers the Llama 3.3-70b inference engine.
* **Qdrant**: Vector database for semantic search and memory retrieval.
* **Sentence-Transformers**: Local embedding generation (`all-MiniLM-L6-v2`).
* **MongoDB**: Stores user profiles and interaction logs.

---

## ⚡ Setup & Installation

### 1. Backend Setup
The backend handles the logic, memory storage, and prompt engineering.

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables:**
    Create a `.env` file in the `backend` folder with the following:
    ```env
    GROQ_API_KEY=your_groq_api_key_here
    MONGO_URI=mongodb://localhost:27017  # Optional, falls back to in-memory
    QDRANT_URL=:memory:                  # Or your cloud Qdrant URL
    QDRANT_API_KEY=your_key              # If using cloud Qdrant
    ```

4.  **Run the Server:**
    ```bash
    uvicorn main:app --reload
    ```
    *The server will start at `http://127.0.0.1:8000`*.

### 2. Networking (Localtunnel)
Chrome extensions require HTTPS. Use `localtunnel` to expose your local server.

1.  **Start the tunnel:**
    ```bash
    npx localtunnel --port 8000
    ```
2.  **Copy the URL** provided (e.g., `https://stale-peaches-check.loca.lt`).

### 3. Extension Setup
1.  Open `extension/content.js`.
2.  Update the `API_URL` variable with your **Localtunnel URL**:
    ```javascript
    const API_URL = "[https://your-url.loca.lt](https://your-url.loca.lt)";
    ```
3.  Open Chrome and navigate to `chrome://extensions`.
4.  Enable **Developer Mode** (top right toggle).
5.  Click **Load Unpacked** and select the `prompt-enhancer-extension/extension` folder.

---

## 🎮 Usage

1.  **Open an AI Chat Interface:** Navigate to ChatGPT, Gemini, Claude, or Perplexity.
2.  **Type a Prompt:** Enter a draft prompt (e.g., *"Write a Python script for web scraping"*).
3.  **Click "✨ Memory":** The button appears near the input field.
4.  **Review & Confirm:** The system will show the **Original** vs. **Enhanced** prompt. Click **OK** to use the optimized version.

---

## 📂 Project Structure
## prompt-enhancer-extension/ 
##├── backend/ 
##│ ├── main.py # FastAPI application & logic 
##│ └── requirements.txt # Python dependencies 
##├── extension/ 
##│ ├── content.js # Script injected into AI pages 
##│ ├── styles.css # Styling for the Memory button 
##│ └── manifest.json # Chrome extension configuration 
##└── README.md # Project documentation

---

## 📄 License

This project is open-source. Feel free to fork and build your own second brain!