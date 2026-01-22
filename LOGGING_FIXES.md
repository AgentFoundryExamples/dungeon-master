# Logging and Authentication Fixes

## Summary

Fixed critical logging errors caused by using Python's reserved `LogRecord` field names, and added preventative measures to catch future occurrences.

## Issues Fixed

### 1. KeyError: "Attempt to overwrite 'name' in LogRecord"

**Root Cause**: Python's logging system has reserved field names that cannot be used in the `extra` dictionary passed to log methods. The code was using `name=request.name` which conflicts with the LogRecord's built-in `name` field (which stores the logger name).

**Reserved Fields in Python's LogRecord**:
- `name`, `msg`, `args`, `created`, `filename`, `funcName`, `levelname`, `levelno`
- `lineno`, `module`, `msecs`, `message`, `pathname`, `process`, `processName`
- `relativeCreated`, `thread`, `threadName`, `exc_info`, `exc_text`, `stack_info`, `taskName`

### 2. Files Modified

#### app/api/routes.py
- **Line 1328**: Changed `name=request.name` → `character_name=request.name`

#### app/services/journey_log_client.py
- **Line 608**: Changed `name=name` → `character_name=name`

#### app/services/turn_orchestrator.py
- **Line 482**: Changed `name=name` → `character_name=name`
- **Line 670**: Changed `name=intents.poi_intent.name` → `poi_name=intents.poi_intent.name`
- **Line 685**: Changed `name=intents.poi_intent.name` → `poi_name=intents.poi_intent.name`

#### app/logging.py
- Added validation in `_log()` method to detect and warn about reserved field usage
- Prevents silent failures by logging warnings when reserved attributes are used

#### app/services/auth.py
- Fixed typo: "SKD" → "SDK"

## Preventative Measures

### Enhanced StructuredLogger

Added automatic detection of reserved LogRecord attributes in `app/logging.py`:

```python
# List of reserved LogRecord attributes that cannot be used in 'extra'
RESERVED_ATTRS = {
    'name', 'msg', 'args', 'created', 'filename', 'funcName', 'levelname',
    'levelno', 'lineno', 'module', 'msecs', 'message', 'pathname', 'process',
    'processName', 'relativeCreated', 'thread', 'threadName', 'exc_info',
    'exc_text', 'stack_info', 'taskName'
}

# Check for reserved attributes and warn if found
for key in kwargs:
    if key in RESERVED_ATTRS:
        self.logger.warning(
            f"Attempted to use reserved LogRecord attribute '{key}' in log extras. "
            f"This may cause logging errors. Consider renaming to '{key}_value' or similar.",
            stacklevel=stacklevel + 2
        )
```

This ensures that if a developer accidentally uses a reserved field name in the future, they'll get a clear warning message instead of a cryptic KeyError.

## Testing

### New Test Suite: tests/test_logging_reserved_fields.py

Tests cover:
- ✅ `character_name` logging works without errors
- ✅ `poi_name` logging works without errors
- ✅ Using reserved field `name` triggers a warning
- ✅ Multiple reserved fields trigger multiple warnings
- ✅ Non-reserved fields work without warnings

All tests passing: **5/5**

### Existing Tests

All auth bypass tests still passing: **6/6**

## Best Practices

### DO ✅
```python
logger.info("Character created", character_name="Gandalf")
logger.debug("POI created", poi_name="Ancient Temple")
logger.info("Quest started", quest_id="quest_123")
```

### DON'T ❌
```python
logger.info("Character created", name="Gandalf")  # 'name' is reserved!
logger.debug("Processing", module="auth")         # 'module' is reserved!
logger.info("Message", msg="test")               # 'msg' is reserved!
```

### Naming Conventions

For commonly logged entities, use these field names:
- **Characters**: `character_name`, `character_id`
- **POIs**: `poi_name`, `poi_id`
- **Quests**: `quest_name`, `quest_id`
- **Users**: `user_id`, `user_name`
- **Items**: `item_name`, `item_id`

## Impact

### Before Fix
```
POST /character → 500 Internal Server Error
KeyError: "Attempt to overwrite 'name' in LogRecord"
```

### After Fix
```
POST /character → 200 OK
INFO: Character created character_name=Gandalf race=Human class_name=Warrior
```

## Related Files

- `app/logging.py` - Enhanced logging with reserved field detection
- `app/api/routes.py` - Fixed character creation logging
- `app/services/journey_log_client.py` - Fixed character creation logging
- `app/services/turn_orchestrator.py` - Fixed intro and POI logging
- `app/services/auth.py` - Fixed typo in comment
- `tests/test_logging_reserved_fields.py` - New test coverage

## Migration Notes

If you have any custom logging code, check for these patterns and update:

```bash
# Find potential issues
grep -r "logger\.(info|debug|warning|error).*name=" app/

# Common replacements needed:
# name=       → character_name= or poi_name=
# module=     → module_name=
# msg=        → message_text=
# process=    → process_name=
```

The enhanced logger will now warn you if you use reserved fields, making it easier to catch these issues during development.
