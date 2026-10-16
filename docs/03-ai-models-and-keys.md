# AI Models & Multi-Provider Cascade

Kayatix is powered by real, state-of-the-art Cloud Large Language Models configured with native structured output JSON validation. It never falls back to primitive regex heuristic analyzers for candidate scoring.

---

## 🤖 The Cascade Architecture

Candidate evaluation uses a resilient 3-tier cascade:

```
[Candidate CV / Portfolio]
            │
            ▼
┌─────────────────────────┐
│ 1. Google Gemini Flash  │  (Primary: Ultra-fast, deep reasoning)
└───────────┬─────────────┘
            │ (on 429 Quota or 503 Spike)
            ▼
┌─────────────────────────┐
│  2. Groq Cloud LPUs     │  (Secondary: Sub-second inference LPUs)
└───────────┬─────────────┘
            │ (on model unavailability)
            ▼
┌─────────────────────────┐
│  3. OpenRouter Cascade  │  (Tertiary: Global multi-model failover)
└─────────────────────────┘
```

---

## 🔑 Supported Models & Configuration

### 1. Google Gemini (Google AI Studio)
* **API Key Format**: `AIzaSy...` (from [Google AI Studio](https://aistudio.google.com/))
* **Active Models**:
  - `gemini-3.8-flash` (Recommended)
  - `gemini-3.6-flash`
  - `gemini-3.5-flash`
  - `gemini-3.5-flash-lite`
  - `gemini-flash-latest`
* **Handling High-Demand Spikes (503 UNAVAILABLE)**:
  If a specific Gemini model experiences temporary Google Cloud spikes (`503 UNAVAILABLE`), Kayatix automatically tests the next candidate model in the family before failing over to Groq.

### 2. Groq Cloud (Ultra-Fast LPUs)
* **API Key Format**: `gsk_...` (from [Groq Console](https://console.groq.com/))
* **Active Models**:
  - `openai/gpt-oss-120b` (High-reasoning candidate evaluator)
  - `openai/gpt-oss-20b`
  - `qwen/qwen3.8-27b`
  - `llama-3.3-70b-versatile`
  - `llama-3.1-8b-instant`

### 3. OpenRouter (Global Aggregator)
* **API Key Format**: `sk-or-v1-...` (from [OpenRouter](https://openrouter.ai/))
* **Active Models**:
  - `meta-llama/llama-3.1-8b-instruct:free`
  - `meta-llama/llama-3.3-70b-instruct:free`
  - `google/gemini-2.0-flash-exp:free`

---

## ⚙️ How to Configure Keys

1. Navigate to `/settings`.
2. Enter your **Gemini API Key**, **Groq API Key**, or **OpenRouter API Key**.
3. Click **Validate Credentials** to run real-time live connectivity checks.
4. Click **Save to Database**.

