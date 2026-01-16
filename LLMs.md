# Instructions for implementing LLM APIs (Do NOT modify this file)

The following are strict instructions for implementing LLM integration. The targeted model families are OpenAI GPT-5 (Responses API), Anthropic Claude 4.5 (Messages API), and Google Gemini 3 (GenAI SDK).

**Important:** Always use the latest stable API versions and official SDKs as defined below.

## 1. OpenAI (GPT-5 & Responses API)

When implementing OpenAI integration, **strictly use the Responses API**. This is the modern, stateful, agent-centric replacement for the legacy "Chat Completions" API.

- **Target Model:** `gpt-5.1-preview` (or `gpt-5.1` if available)
- **SDK Version:** `openai>=2.14.0`
- **Key Implementation Details:**
  - Use `client.responses.create()` instead of `client.chat.completions.create()`.
  - The API returns a single `output` object, not a `choices` array.
  - For structured data, use `text.format` (JSON Schema) instead of the old `response_format`.
  - **Do NOT use:** The legacy Chat Completions API (`v1/chat/completions`) or Assistants API (deprecated).

### Example Pattern (OpenAI)
response = client.responses.create(
    model="gpt-5.1-preview",
    input=[{"role": "user", "content": "Hello"}],
    text={"format": {"type": "json_schema", "schema": MyPydanticModel.model_json_schema()}}
)
print(response.output.text)


## 2. Anthropic (Claude 4.5 & Messages API)

Target the **Messages API** which supports advanced tool use and computer use capabilities.

- **Target Model:** `claude-4-5-sonnet-20251022` (High Intelligence) or `claude-3-7-sonnet-20250219` (Efficiency)
- **SDK Version:** `anthropic>=0.75.0`
- **Key Implementation Details:**
  - Use `client.messages.create()`.
  - Always set `max_tokens` (required).
  - Use the native `tools` parameter for function calling (MCP-style).
  - **Do NOT use:** The Text Completions API (`v1/complete`) or `claude-2` models.


## 3. Google (Gemini 3 & GenAI SDK)

Use the new **Google GenAI SDK** (`google-genai`), which unifies Vertex AI and AI Studio.

- **Target Model:** `gemini-3.0-pro-001`
- **SDK Version:** `google-genai>=1.57.0`
- **Key Implementation Details:**
  - Import path: `from google import genai` (NOT `google.generativeai`).
  - Client initialization: `client = genai.Client(api_key=...)`.
  - Use `client.models.generate_content()`.
  - For structured outputs, pass a Pydantic model class directly to the `config` parameter.
  - **Do NOT use:** The legacy `PaLM` API, `google-generativeai` package, or `gemini-1.0` models.

### Example Pattern (Google)
from google import genai
from pydantic import BaseModel

class Recipe(BaseModel):
    title: str

client = genai.Client(api_key="...")
response = client.models.generate_content(
    model="gemini-3.0-pro-001",
    contents="Cookie recipe",
    config={"response_mime_type": "application/json", "response_schema": Recipe}
)


## General Best Practices
- **Environment Variables:** Load API keys via `pydantic-settings` (e.g., `OPENAI_API_KEY`).
- **Streaming:** Implement `stream=True` handlers for all user-facing interactions.
- **Async:** Prefer `async`/`await` methods (e.g., `client.responses.create_async`) for FastAPI endpoints.
