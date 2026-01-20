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

## Dungeon Master Implementation Specifics

### Character Status Transitions and Game Over Rules

The Dungeon Master service enforces strict character status transitions that govern gameplay logic. These rules are embedded in the system prompt and must be respected by the LLM.

**Status Ordering:**
```
Healthy → Wounded → Dead
```

**Healing Rules:**
- Characters can be healed from **Wounded** back to **Healthy**
- Characters **CANNOT** be revived from **Dead** status
- Death is final and permanent

**Game Over Logic:**
When a character reaches **Dead** status:
1. The LLM must generate a final narrative describing their demise
2. The session is marked as **OVER**
3. All intents must be set to `"none"` (no quests, combat, POIs)
4. No further gameplay should be suggested or enabled
5. The narrative should be conclusive and mark the end of the journey

**Prompt Implementation:**
Status transition rules are documented in `app/prompting/prompt_builder.py` in the `SYSTEM_INSTRUCTIONS` constant:
```python
STATUS TRANSITIONS AND GAME OVER RULES:
Characters progress through health statuses in strict order: Healthy -> Wounded -> Dead
- Healing can move characters from Wounded back to Healthy
- Healing CANNOT revive characters from Dead status
- Once a character reaches Dead status, the session is OVER
- When a character dies, generate a final narrative describing their demise
- Do NOT continue gameplay, offer new quests, or suggest actions after death
- The Dead status is permanent and marks the end of the character's journey
```

**JSON Escaping Note:**
The arrow notation (`->`) is safe for inclusion in system prompts. It does not break JSON parsing when the prompt is embedded in API calls. If you encounter issues, use the HTML entity `&rarr;` or Unicode `→` as alternatives.

**Implementation Checklist:**
- [ ] LLM receives status transition rules in system prompt
- [ ] LLM sets all intents to "none" when character status is Dead
- [ ] LLM generates conclusive narrative on character death
- [ ] Game client detects Dead status and prevents further turn submissions
- [ ] Journey-log tracks character status accurately across turns

### Deterministic Write Order

The DungeonMaster service enforces a strict, deterministic order when writing subsystem changes to the journey-log service. This ensures predictable behavior and simplifies debugging.

**Write Order:**
1. **Quest** (PUT for offer/update, DELETE for abandon/complete) - Only if quest action derived
2. **Combat** (PUT for start/continue/end) - Only if combat action derived
3. **POI** (POST for create) - Only if POI action derived
4. **Narrative** (POST always attempted) - Always writes player action and AI response

**Rationale:**
- Quest writes first because they affect character state and may influence later decisions
- Combat writes second because they may reference quest context
- POI writes third because they may be mentioned in narrative
- Narrative writes last to ensure all context is finalized before persisting the story

**Determinism Benefits:**
- Predictable logs and debugging
- Consistent state ordering across all turns
- Easier to reason about race conditions
- Integration tests can assert exact write sequence

### Failure Handling Strategy

The service implements a "continue narrative" strategy for subsystem write failures:

**Core Principles:**
1. **Narrative Always Returns**: Even if subsystem writes fail, the narrative response is returned to the player
2. **No Retry on Destructive Ops**: DELETE operations (e.g., quest deletion) are never automatically retried
3. **Summary Tracking**: All write attempts and their outcomes are captured in `TurnSubsystemSummary`
4. **HTTP 200 with Failures**: Returns 200 OK even if some writes fail (check `subsystem_summary` for details)

**Failure Scenarios:**

| Scenario | Behavior | HTTP Status | Summary Fields |
|----------|----------|-------------|----------------|
| Quest write fails | Continue, log error, return narrative | 200 | `quest_change.success=false`, `quest_change.error="..."` |
| Combat write fails | Continue, log error, return narrative | 200 | `combat_change.success=false`, `combat_change.error="..."` |
| POI write fails | Continue, log error, return narrative | 200 | `poi_created.success=false`, `poi_created.error="..."` |
| Narrative write fails | Log error, return narrative anyway | 200 | `narrative_persisted=false`, `narrative_error="..."` |
| LLM generation fails | No writes attempted, return error | 502 | N/A (no subsystem_summary) |
| Context fetch fails | No writes attempted, return error | 502/504 | N/A (no subsystem_summary) |

**Why No Retry on DELETE?**
- Destructive operations should be idempotent and non-retriable
- Retrying a failed DELETE could succeed on a stale request, causing unexpected state
- The client should explicitly request the deletion again if needed

**Monitoring Failures:**
- Check `subsystem_summary` in responses for per-write success/failure status
- Enable DEBUG logging to see detailed error messages
- Use structured logs for alert thresholds (e.g., narrative_persistence_failure_rate > 5%)

### Prompt Construction and Policy Integration

**Policy Hints in Prompts:**

The PolicyEngine evaluates quest and POI trigger eligibility **before** LLM generation and injects hints into the prompt. This ensures the LLM respects deterministic policy decisions.

**Policy Hint Format:**
```
POLICY HINTS:
  Quest Trigger: ALLOWED / NOT ALLOWED
    Reason: (if not allowed)
  POI Creation: ALLOWED / NOT ALLOWED
    Reason: (if not allowed)

  Note: Only suggest quest offers or POI creation if marked as ALLOWED above.
```

**Key Points:**
- Policy hints are added to the user prompt, not system instructions
- The LLM is instructed to respect these hints when suggesting intents
- Even if the LLM suggests a blocked action, the orchestrator will skip the write
- Policy hints are never exposed in API responses (internal only)

**Memory Sparks (POI Injection):**

When `POI_MEMORY_SPARK_ENABLED=true`, the service probabilistically fetches random POIs at the start of each turn and injects them into the prompt to help the LLM recall previously discovered locations. The memory spark feature is controlled by two probabilities:

1. **Per-turn memory spark probability** (default 0.2): Each turn has a 20% chance of fetching random POIs
2. **Quest POI reference probability** (default 0.1): When a quest triggers and memory sparks are available, there's a 10% chance the quest will reference one of the POIs

**Memory Spark Format:**
```
MEMORY SPARKS (Previously Discovered Locations):
  3 previously discovered location(s):

  1. The Old Mill
     An abandoned mill at the edge of the forest
     Tags: mill, forest, abandoned

  2. Rusty Tavern
     A weathered tavern in the town square
     Tags: tavern, town
```

**Memory Spark Behavior:**
- Probabilistic fetching controlled by `MEMORY_SPARK_PROBABILITY` (0.0-1.0, default 0.2)
- Quest POI references controlled by `QUEST_POI_REFERENCE_PROBABILITY` (0.0-1.0, default 0.1)
- When a quest references a POI, the POI context is injected into the quest's details
- Sorted by timestamp descending (newest first) for determinism
- Descriptions truncated to 200 characters to manage token usage
- Tags limited to 5 per POI
- Section hidden completely if no POIs available or roll fails
- Non-fatal errors during fetch (empty list returned on failure)
- Set probabilities to 0.0 to disable without turning off the feature entirely

**Token Budget:**
- System instructions + schema: ~2,250 tokens
- User prompt sections: ~2,000-4,000 tokens (varies by history, memory sparks, combat)
- Total typical prompt: 4,000-6,000 tokens

**Configuring Token Usage:**
- `JOURNEY_LOG_RECENT_N`: Control history turns (default 20, range 1-100)
- `POI_MEMORY_SPARK_COUNT`: Control POI count when fetched (default 3, range 1-20)
- `MEMORY_SPARK_PROBABILITY`: Control fetch frequency (default 0.2, range 0.0-1.0)
- `QUEST_POI_REFERENCE_PROBABILITY`: Control quest-POI connection frequency (default 0.1, range 0.0-1.0)
- Automatic truncation for long descriptions and responses

### Structured Output Schema

The LLM must output valid JSON matching the `DungeonMasterOutcome` schema:

```json
{
  "narrative": "string (required, min 1 char)",
  "intents": {
    "quest_intent": {
      "action": "none | offer | complete | abandon",
      "quest_title": "string (optional)",
      "quest_summary": "string (optional)",
      "quest_details": {} // optional dict
    },
    "combat_intent": {
      "action": "none | start | continue | end",
      "enemies": [], // optional EnemyDescriptor[]
      "combat_notes": "string (optional)"
    },
    "poi_intent": {
      "action": "none | create | reference",
      "name": "string (optional)",
      "description": "string (optional)",
      "reference_tags": [] // optional string[]
    },
    "meta": {
      "player_mood": "string (optional)",
      "pacing_hint": "slow | normal | fast (optional)",
      "user_is_wandering": "boolean (optional)",
      "user_asked_for_guidance": "boolean (optional)"
    }
  }
}
```

**Schema Evolution:**
- Update `get_outcome_json_schema()` in `app/models.py` when schema changes
- Schema is automatically included in prompts
- Test with new models to ensure compatibility
- Monitor token counts as schema grows

**Validation Strategy:**
- Parse JSON response from LLM
- Validate against Pydantic model (DungeonMasterOutcome)
- If validation fails, fallback to narrative-only mode (extract narrative, skip intents)
- Log validation errors with schema version for debugging

### Best Practices for This Service

1. **Always call LLM with policy hints** - Ensures LLM respects deterministic decisions
2. **Validate all LLM outputs** - Never trust raw JSON from LLM without Pydantic validation
3. **Log all subsystem writes** - Use structured logging with success/failure status
4. **Return narrative even on failures** - Player experience takes priority over perfect state
5. **Never retry DELETE operations** - Destructive ops should be idempotent and non-retriable
6. **Monitor token usage** - Watch for prompt growth as features are added
7. **Test with deterministic seeds** - Use RNG_SEED for reproducible policy testing
8. **Include memory sparks carefully** - They improve coherence but increase token usage
