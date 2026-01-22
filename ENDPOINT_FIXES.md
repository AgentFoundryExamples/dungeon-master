# Endpoint and URL Fixes

## Issues Fixed

### 1. Character Creation Endpoint Mismatch

**Problem**: 307 Temporary Redirect errors when calling POST /characters/

**Root Cause**: 
- Dungeon Master API defined endpoint as `/character` (singular)
- Journey-log service expects `/characters` (plural)
- This caused FastAPI to redirect `/character` → `/characters`, resulting in 307 responses

**Evidence from logs**:
```
INFO: 169.254.169.126:64694 - "POST /characters/ HTTP/1.1" 307 Temporary Redirect
```

**Fix Applied**:
- Changed route in `app/api/routes.py` from `/character` to `/characters`
- This aligns with REST conventions (plural for collections)

### 2. Trailing Slash in Journey-Log Client

**Problem**: Journey-log client was calling `/characters/` with trailing slash

**Root Cause**:
- Client was using `f"{self.base_url}/characters/"` 
- Journey-log service expects `/characters` without trailing slash
- Some frameworks (like FastAPI) treat these as different endpoints

**Fix Applied**:
- Removed trailing slash from `app/services/journey_log_client.py`
- Changed from `/characters/` to `/characters`
- Updated docstring to reflect correct endpoint

### 3. TurnStorage Initialization (False Alarm)

**Initial Concern**: TurnStorage might not be initialized

**Investigation Result**: ✅ No issue found
- TurnStorage is properly initialized in `app/main.py` during lifespan startup (line 169)
- Stored in `app.state.turn_storage`
- Passed to TurnOrchestrator correctly
- All dependencies properly configured

## Files Modified

### app/api/routes.py
```python
# Before:
@router.post("/character", ...)

# After:
@router.post("/characters", ...)
```

### app/services/journey_log_client.py
```python
# Before:
url = f"{self.base_url}/characters/"

# After:
url = f"{self.base_url}/characters"
```

## Endpoint Naming Conventions

The following conventions are now consistent across the service:

| Purpose | Dungeon Master Endpoint | Journey-Log Endpoint |
|---------|------------------------|---------------------|
| Create character | POST /characters | POST /characters |
| Get context | N/A | GET /characters/{id}/context |
| Save narrative | N/A | POST /characters/{id}/narrative |
| Manage quest | N/A | PUT/DELETE /characters/{id}/quest |
| Manage combat | N/A | PUT /characters/{id}/combat |
| Manage POIs | N/A | POST /characters/{id}/pois |

**Rules**:
1. ✅ Use **plural** for collection endpoints: `/characters`, `/pois`
2. ✅ **No trailing slash** on endpoints (FastAPI convention)
3. ✅ Use singular resource IDs: `/characters/{character_id}`
4. ✅ Use REST conventions: POST for create, GET for read, PUT for update, DELETE for delete

## Testing

All tests pass after fixes:

```bash
pytest tests/test_character_creation.py -v
# ✅ test_journey_log_client_create_character PASSED
# ✅ test_turn_orchestrator_orchestrate_intro PASSED  
# ✅ test_create_character_route_handler PASSED
```

## HTTP Status Codes

### Before Fix
- **307 Temporary Redirect**: Client called wrong endpoint, FastAPI redirected
- **Potential 404**: If redirect failed or wasn't followed

### After Fix
- **201 Created**: Successful character creation
- **4xx/5xx**: Only on actual errors (auth, validation, server issues)

## Journey-Log Client URL Construction

The client safely handles `base_url` variations:

```python
# In __init__:
self.base_url = base_url.rstrip('/')  # Removes trailing slash if present

# Examples:
# Input: "http://localhost:8000"  → base_url: "http://localhost:8000"
# Input: "http://localhost:8000/" → base_url: "http://localhost:8000"

# Then constructs URLs:
url = f"{self.base_url}/characters"  # Always: http://localhost:8000/characters
```

## Deployment Considerations

When deploying:

1. **No configuration changes needed** - fixes are in code
2. **No database migrations** - only endpoint routing changes
3. **Backward compatibility** - existing clients may need updates if they called `/character`
4. **Update documentation** - any API docs should reference `/characters` (plural)
5. **Monitor logs** - watch for 307s which indicate other endpoint mismatches

## Related Endpoints to Verify

If you have other services or clients calling dungeon-master, verify they use:

- ✅ POST `/characters` (not `/character` or `/characters/`)
- ✅ POST `/turn` (not `/turns`)
- ✅ GET `/health`
- ✅ GET `/metrics` (if enabled)

## Debugging Future 307 Errors

If you see 307 redirects in logs:

1. **Check trailing slashes**: `/endpoint/` vs `/endpoint`
2. **Check plural vs singular**: `/character` vs `/characters`
3. **Check HTTP method**: Some frameworks redirect GET → POST or vice versa
4. **Check FastAPI route definition**: Must match exactly what clients call
5. **Check reverse proxy config**: NGINX/load balancers may add/remove trailing slashes

## Prevention

To prevent similar issues:

1. **Follow REST conventions** consistently (plural collections)
2. **No trailing slashes** in route definitions (FastAPI best practice)
3. **Document API contract** clearly (OpenAPI/Swagger)
4. **Integration tests** that catch endpoint mismatches
5. **Monitor 3xx responses** in production (should be rare/zero)
