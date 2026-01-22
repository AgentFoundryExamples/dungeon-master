# Development Authentication Bypass

## Overview

The authentication system supports a development bypass mode that allows you to test authenticated endpoints without setting up Firebase authentication. This is useful for local development and testing.

## Configuration

Enable the development bypass by setting the `dev_bypass_auth` configuration option:

### Environment Variable
```bash
export DEV_BYPASS_AUTH=true
```

### In `.env` file
```
DEV_BYPASS_AUTH=true
```

## Usage

When `dev_bypass_auth` is enabled, you can authenticate requests using the `X-Dev-User-Id` header instead of a Firebase Bearer token:

```bash
curl -X POST http://localhost:8080/turn \
  -H "Content-Type: application/json" \
  -H "X-Dev-User-Id: test_user_123" \
  -d '{
    "character_id": "char_456",
    "user_input": "I explore the dungeon"
  }'
```

## Behavior

### Development Mode (`dev_bypass_auth=true`)
- **Required**: `X-Dev-User-Id` header
- **Optional**: `Authorization: Bearer <token>` header (ignored if present)
- The value of `X-Dev-User-Id` is used directly as the `user_id` throughout the system
- No Firebase authentication is performed
- Returns 401 if `X-Dev-User-Id` header is missing

### Production Mode (`dev_bypass_auth=false`, default)
- **Required**: `Authorization: Bearer <firebase_token>` header
- **Ignored**: `X-Dev-User-Id` header (for security)
- Firebase token is verified using Firebase Admin SDK
- Returns 401 if token is invalid, expired, or missing

## Security Warning

⚠️ **NEVER enable `dev_bypass_auth` in production environments!**

This feature completely bypasses authentication and allows any request with an `X-Dev-User-Id` header to access protected endpoints. It should only be used in local development or isolated testing environments.

## Testing

The authentication bypass is tested in `tests/test_auth_dev_bypass.py`. Run the tests with:

```bash
pytest tests/test_auth_dev_bypass.py -v
```

Test coverage includes:
- ✅ Dev bypass with `X-Dev-User-Id` header
- ✅ Dev bypass without header (401 error)
- ✅ Production mode requires Bearer token
- ✅ Production mode ignores dev header
- ✅ Production mode validates Firebase tokens
- ✅ Dev mode ignores Bearer tokens when dev header present

## Example: Development Workflow

1. Set up your local environment:
```bash
export DEV_BYPASS_AUTH=true
export JOURNEY_LOG_BASE_URL=http://localhost:8000
export OPENAI_API_KEY=your-api-key
```

2. Start the service:
```bash
uvicorn app.main:app --reload
```

3. Make authenticated requests:
```bash
# Create a character
curl -X POST http://localhost:8080/characters \
  -H "Content-Type: application/json" \
  -H "X-Dev-User-Id: alice" \
  -d '{
    "name": "Aria the Brave",
    "character_class": "warrior",
    "background": "noble"
  }'

# Process a turn
curl -X POST http://localhost:8080/turn \
  -H "Content-Type: application/json" \
  -H "X-Dev-User-Id: alice" \
  -d '{
    "character_id": "char_123",
    "user_input": "I draw my sword and face the dragon"
  }'
```

## Switching to Production Mode

To test Firebase authentication locally:

1. Disable dev bypass:
```bash
export DEV_BYPASS_AUTH=false
```

2. Set up Firebase credentials:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-service-account.json
```

3. Obtain a Firebase ID token (from your frontend or Firebase CLI)

4. Make authenticated requests with Bearer token:
```bash
curl -X POST http://localhost:8080/turn \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <firebase_id_token>" \
  -d '{
    "character_id": "char_123",
    "user_input": "I explore the dungeon"
  }'
```

## Implementation Details

The dev bypass is implemented in `app/api/deps.py` in the `get_current_user_id` dependency:

```python
def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_dev_user_id: Optional[str] = Header(None, alias="X-Dev-User-Id")
) -> str:
    settings = get_settings()
    
    # Development bypass mode
    if settings.dev_bypass_auth:
        if x_dev_user_id:
            return x_dev_user_id
        else:
            raise HTTPException(401, "X-Dev-User-Id header required in development mode")
    
    # Production mode - require Firebase token
    if not credentials:
        raise HTTPException(401, "Missing authentication credentials")
    
    return verify_id_token(credentials.credentials)
```

## Related Configuration

Other development/debug configurations that work well with auth bypass:

- `enable_debug_endpoints`: Enable `/debug/parse_llm` endpoint for testing LLM parsing
- `openai_stub_mode`: Use stub responses instead of real OpenAI API calls
- `log_level`: Set to `DEBUG` for detailed authentication logging

Example dev configuration:
```bash
export DEV_BYPASS_AUTH=true
export ENABLE_DEBUG_ENDPOINTS=true
export LOG_LEVEL=DEBUG
export OPENAI_STUB_MODE=true
```
