# Company Ingestion Pipeline ('The Smart Hunter')

The Ingestion Pipeline is an advanced system designed to import company lists from unstructured sources (text files, markdown, etc.) into the JobDetector database. It handles data extraction using AI, deduplication via fuzzy matching, and automatic discovery of hiring platform (ATS) metadata.

## 🚀 Key Features

- **AI-Powered Extraction**: Uses LLMs (Gemini, Deepseek, Anthropic) to parse messy text and suggest domains.
- **Fuzzy Deduplication**: Intelligent matching to prevent duplicate entries (e.g., "Segment" vs "Twilio Segment").
- **Automatic ATS Probe**: Automatically identifies Greenhouse, Lever, Ashby, and Workable tokens.
- **Microservice-Ready**: Follows a decoupled architecture for easy integration.

## 🛠 Operation Guide

### 1. Preparation
Place your company list in a text file. The format can be messy, for example:
```text
1. Stripe
* Airbnb
FinTech / 金融科技: Plaid, Brex
```

### 2. Configuration
Ensure your `.env` file is configured with an AI provider and its corresponding API Key:
```bash
AI_PROVIDER=gemini  # Options: gemini, deepseek, anthropic, openai
GEMINI_API_KEY=your_key_here
```

### 3. Execution
Run the script using the dedicated Conda environment:
```bash
# Activate environment (manual)
conda activate jobdetector

# Run pipeline
python scripts/ingestion_pipeline.py data/ImportList/MidTechCompanies.txt
```

## 🧠 Technical Workflow

1. **Extraction**: The raw text is sent to the selected AI model with a prompt to return structured JSON `[{name, domain}]`.
2. **Deduplication**: 
   - **Exact Match**: Checks if the domain already exists.
   - **Fuzzy Match**: Uses `rapidfuzz` (threshold: 90) to check for similar names.
3. **ATS Discovery**: 
   - Uses `ATSDiscoveryService` to probe common URLs like `boards.greenhouse.io/{slug}`.
   - Crawls the company homepage to find "Careers" links.
4. **Persistence**: New verified companies are saved to MongoDB with `is_active: True`.

## ⚙️ Configuration Variables (.env)

| Variable | Description |
| :--- | :--- |
| `AI_PROVIDER` | `gemini`, `deepseek`, `anthropic`, or `openai` |
| `GEMINI_API_KEY` | API key from Google AI Studio (Free tier available) |
| `DEEPSEEK_API_KEY` | API key from Deepseek |
| `ANTHROPIC_API_KEY` | API key from Anthropic |

## 📊 Monitoring
After running, you can verify the status in the terminal output or check the database statistics:
```bash
python scripts/import_companies.py --stats
```
