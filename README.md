# EvoDoc Clinical Drug Safety Engine

EvoDoc is a high-performance, AI-powered clinical decision support API designed to enhance patient safety by identifying drug-drug interactions, allergy cross-reactions, and condition contraindications in real-time.

It features a hybrid analysis engine that prioritizes medical-grade LLM insights (via Ollama) while maintaining a high-reliability rule-based fallback system for clinical continuity.

## 🚀 Key Features

-   **Hybrid Analysis Engine:** Intelligent LLM analysis with an automated rule-based fallback system.
-   **Clinical Safety Checks:** Scans for interactions, allergy cross-reactivity, and patient condition contraindications.
-   **Smart Risk Scoring:** Calculates a weighted patient risk score (0-100) based on clinical severity.
-   **High-Speed Caching:** In-memory request caching for sub-millisecond responses on repeat clinical profiles.
-   **Premium Interface:** A botanical, high-contrast dashboard inspired by modern wellness aesthetics (TerraElix tone).

## 🛠 Tech Stack

-   **Backend:** Python 3.11, FastAPI, Pydantic v2, Uvicorn
-   **AI Infrastructure:** Ollama (BioMistral model recommended)
-   **Frontend:** Vanilla JavaScript (ES6+), HTML5, CSS3 (Glassmorphism & Custom Properties)
-   **Deployment:** Railway (Production ready with Nixpacks/Railpack support)

## ⚙️ Environment Variables

Configure these in your `.env` file or hosting provider:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OLLAMA_BASE_URL` | Endpoint for the Ollama server | `http://localhost:11434` |
| `LLM_MODEL_NAME` | The medical LLM model to use | `biomistral` |
| `CACHE_TTL_SECONDS` | Cache duration in seconds | `3600` |
| `REQUIRE_REVIEW_ON_UNCERTAINTY` | Flag to force physician review banners | `true` |

## 💻 Local Setup

### 1. Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/) (Optional, for LLM features)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/swoyamsiddhi/Evodocs.git
cd Evodocs

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Application
```bash
# Start the FastAPI server
python main.py
```
Visit `http://localhost:8000` in your browser.

## 🚢 Deployment (Railway)

This project is optimized for **Railway**.
1.  Connect your GitHub repository to Railway.
2.  Add the environment variables listed above.
3.  Railway will automatically detect the `Procfile` and `runtime.txt` to deploy the app.

*Note: On Railway, the app will automatically operate in **Fallback Mode** unless connected to an external Ollama host.*

## 📁 Project Structure

-   `main.py`: Entry point and API routing.
-   `engine.py`: Core hybrid analysis logic.
-   `cache.py`: High-performance hashing and caching system.
-   `models.py`: Pydantic V2 data schemas.
-   `data/`: Rule-based clinical fallback datasets.
-   `static/`: Modern dashboard frontend assets.
-   `prompts/`: System instruction sets for clinical LLMs.

## ⚖️ Disclaimer

This tool is designed for clinical reference only and should be used by qualified healthcare professionals. It is not a substitute for professional medical judgment.
