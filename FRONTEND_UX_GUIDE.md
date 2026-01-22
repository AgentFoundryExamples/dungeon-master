# Frontend UX Guide for Dungeon Master Service

This guide provides comprehensive recommendations for building engaging frontend user experiences on top of the Dungeon Master service API.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Character Creation Flow](#character-creation-flow)
3. [Gameplay Loop](#gameplay-loop)
4. [UI Component Design](#ui-component-design)
5. [State Management](#state-management)
6. [Error Handling & User Feedback](#error-handling--user-feedback)
7. [Advanced Features](#advanced-features)
8. [Performance Considerations](#performance-considerations)
9. [Example Code Snippets](#example-code-snippets)

---

## Architecture Overview

### Service Communication

```
┌─────────────────┐
│   Frontend UI   │
│  (React/Vue/    │
│   Svelte etc)   │
└────────┬────────┘
         │
         │ HTTP/HTTPS
         │
┌────────▼────────┐      ┌──────────────┐
│ Dungeon Master  │◄────►│ Journey-Log  │
│    Service      │      │   Service    │
└─────────────────┘      └──────────────┘
```

### Key API Endpoints

- **POST /turn** - Main gameplay endpoint, processes player actions
- **GET /health** - Service health check
- **GET /metrics** - Service metrics (if enabled)
- **POST /debug/parse_llm** - Debug endpoint for testing (dev only)

---

## Character Creation Flow

### 1. Initial Character Creation (Journey-Log)

Call the Journey-Log service to create a new character:

```javascript
// POST https://journey-log-service/characters
const response = await fetch(`${JOURNEY_LOG_URL}/characters`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-User-Id': userId // Important: Track the user
  },
  body: JSON.stringify({
    name: "Aric Stormwind",
    race: "Human",
    class: "Warrior",
    custom_prompt: "A war-torn medieval fantasy world..." // Optional
  })
});

const { character_id, narrative } = await response.json();
```

**UX Design Tips:**
- Provide race/class selection with visual cards showing artwork
- Include tooltips explaining each race/class
- Optional custom prompt field for experienced users
- Show loading state: "Creating your character..."
- Display the generated intro narrative with dramatic reveal animation

### 2. Display Introduction Narrative

The Journey-Log returns an opening narrative. Display this prominently:

```javascript
// Display narrative with typewriter effect or fade-in
function displayNarrative(narrative) {
  // Example: Typewriter effect
  const container = document.getElementById('narrative');
  let index = 0;
  const speed = 30; // ms per character
  
  function type() {
    if (index < narrative.length) {
      container.textContent += narrative.charAt(index);
      index++;
      setTimeout(type, speed);
    }
  }
  type();
}
```

**UX Design Tips:**
- Use atmospheric background music/sound effects
- Consider parchment/scroll aesthetic for narrative text
- Add character portrait display alongside narrative
- Include starting location prominently (will be a POI)

---

## Gameplay Loop

### Core Turn Flow

```
User Input → Dungeon Master → Narrative Response → Display → Repeat
```

### 1. User Input Component

```javascript
async function submitAction(characterId, userAction, userId) {
  // Show loading state
  setIsProcessing(true);
  
  try {
    const response = await fetch(`${DM_SERVICE_URL}/turn`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId
      },
      body: JSON.stringify({
        character_id: characterId,
        user_action: userAction,
        user_id: userId // Optional but recommended
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const turnResult = await response.json();
    return turnResult;
    
  } catch (error) {
    handleError(error);
  } finally {
    setIsProcessing(false);
  }
}
```

**UX Design Tips:**
- Disable input during processing (show spinner/loading state)
- Auto-focus input field after response
- Provide action suggestions (buttons for common actions)
- Show character count (keep actions concise, 1-500 chars recommended)
- Implement command shortcuts (e.g., "/look", "/inventory")

### 2. Response Handling

```javascript
function handleTurnResponse(response) {
  const { narrative, intents, subsystem_summary } = response;
  
  // Display narrative (primary content)
  displayNarrative(narrative);
  
  // Handle subsystem changes
  if (subsystem_summary) {
    handleSubsystemUpdates(subsystem_summary);
  }
  
  // Update UI based on intents (optional, informational only)
  if (intents) {
    updateUIHints(intents);
  }
  
  // Scroll to new content
  scrollToLatestNarrative();
}
```

### 3. Subsystem Summary Handling

The `subsystem_summary` tells you what actually changed:

```javascript
function handleSubsystemUpdates(summary) {
  // Quest changes
  if (summary.quest_change) {
    const { action, success, error } = summary.quest_change;
    if (success) {
      switch(action) {
        case 'offered':
          showQuestNotification('New Quest Available!');
          refreshCharacterState(); // Fetch updated quest from Journey-Log
          break;
        case 'completed':
          showQuestNotification('Quest Completed!');
          playSuccessSound();
          refreshCharacterState();
          break;
        case 'abandoned':
          showQuestNotification('Quest Abandoned');
          refreshCharacterState();
          break;
      }
    }
  }
  
  // Combat changes
  if (summary.combat_change) {
    const { action, success } = summary.combat_change;
    if (success) {
      switch(action) {
        case 'started':
          enterCombatMode();
          break;
        case 'ended':
          exitCombatMode();
          break;
        case 'continued':
          updateCombatDisplay();
          break;
      }
    }
  }
  
  // POI changes
  if (summary.poi_change) {
    const { action, success } = summary.poi_change;
    if (success && action === 'create') {
      showPOIDiscoveryAnimation('New Location Discovered!');
    }
  }
  
  // Narrative persistence
  if (!summary.narrative_persisted) {
    console.warn('Narrative not saved:', summary.narrative_error);
    // Optional: Show warning to user
  }
}
```

---

## UI Component Design

### Narrative Display

**Recommended Layout:**

```
┌─────────────────────────────────────────┐
│  [Character Portrait]  [Status: Healthy]│
│  Aric Stormwind                         │
│  Location: The Nexus                    │
├─────────────────────────────────────────┤
│                                         │
│  NARRATIVE HISTORY                      │
│  (Scrollable feed)                      │
│                                         │
│  > You search the tavern...             │
│  [AI Response...]                       │
│                                         │
│  > I examine the old map...             │
│  [AI Response...]                       │
│                                         │
├─────────────────────────────────────────┤
│  [Quest Panel]     [Combat Panel]       │
│  [Inventory]       [Map/POIs]           │
├─────────────────────────────────────────┤
│  [Action Input Field]        [Submit]   │
└─────────────────────────────────────────┘
```

### Quest Panel

```jsx
function QuestPanel({ quest }) {
  if (!quest) {
    return (
      <div className="quest-panel empty">
        <p>No active quest</p>
      </div>
    );
  }
  
  return (
    <div className="quest-panel active">
      <h3>{quest.name}</h3>
      <p className="description">{quest.description}</p>
      
      {quest.requirements && (
        <div className="requirements">
          <h4>Objectives:</h4>
          <ul>
            {quest.requirements.map((req, i) => (
              <li key={i}>{req}</li>
            ))}
          </ul>
        </div>
      )}
      
      {quest.rewards && (
        <div className="rewards">
          <h4>Rewards:</h4>
          <ul>
            {quest.rewards.items?.map((item, i) => (
              <li key={i}>{item.name} (x{item.quantity})</li>
            ))}
            {quest.rewards.xp && <li>{quest.rewards.xp} XP</li>}
          </ul>
        </div>
      )}
      
      <button onClick={() => abandonQuest()}>
        Abandon Quest
      </button>
    </div>
  );
}
```

### Combat Panel

```jsx
function CombatPanel({ combatState }) {
  if (!combatState || !combatState.active) {
    return null; // Hide when not in combat
  }
  
  return (
    <div className="combat-panel">
      <h3>⚔️ Combat - Turn {combatState.turn_number}</h3>
      
      <div className="enemies">
        {combatState.enemies.map((enemy, i) => (
          <div key={i} className="enemy">
            <span className="name">{enemy.name}</span>
            <div className="health-bar">
              <div 
                className="health-fill"
                style={{ width: `${enemy.current_hp / enemy.max_hp * 100}%` }}
              />
              <span>{enemy.current_hp}/{enemy.max_hp}</span>
            </div>
          </div>
        ))}
      </div>
      
      <div className="combat-actions">
        <button onClick={() => submitAction(characterId, "I attack the enemy")}>
          Attack
        </button>
        <button onClick={() => submitAction(characterId, "I try to flee")}>
          Flee
        </button>
        <button onClick={() => submitAction(characterId, "I defend")}>
          Defend
        </button>
      </div>
    </div>
  );
}
```

### Points of Interest (POI) Map

```jsx
function POIMap({ pois, currentLocation }) {
  return (
    <div className="poi-map">
      <h3>Discovered Locations</h3>
      <div className="poi-grid">
        {pois.map(poi => (
          <div 
            key={poi.id}
            className={`poi-card ${poi.id === currentLocation.id ? 'current' : ''}`}
          >
            <h4>{poi.name}</h4>
            <p className="description">{poi.description}</p>
            {poi.tags && (
              <div className="tags">
                {poi.tags.map(tag => (
                  <span key={tag} className="tag">{tag}</span>
                ))}
              </div>
            )}
            {poi.id !== currentLocation.id && (
              <button onClick={() => travelTo(poi)}>
                Travel Here
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## State Management

### Recommended State Structure

```javascript
// Using React/Redux/Context as example
const GameState = {
  // Character Info
  character: {
    id: "uuid",
    name: "Aric Stormwind",
    race: "Human",
    class: "Warrior",
    status: "Healthy" // Healthy, Wounded, Dead
  },
  
  // Current Location
  location: {
    id: "origin:nexus",
    display_name: "The Nexus"
  },
  
  // Active Quest
  quest: null, // or Quest object
  
  // Combat State
  combat: null, // or CombatState object
  
  // Narrative History
  narrativeHistory: [
    { player_action: "...", ai_response: "...", timestamp: "..." }
  ],
  
  // Discovered POIs
  discoveredPOIs: [],
  
  // UI State
  ui: {
    isProcessing: false,
    lastError: null,
    combatMode: false
  }
};
```

### Syncing with Journey-Log

After each turn, optionally refresh full character state:

```javascript
async function refreshCharacterState(characterId, userId) {
  const response = await fetch(
    `${JOURNEY_LOG_URL}/characters/${characterId}/context?recent_n=20`,
    {
      headers: { 'X-User-Id': userId }
    }
  );
  
  const context = await response.json();
  
  // Update local state
  updateCharacter(context.player_state);
  updateLocation(context.location);
  updateQuest(context.quest);
  updateCombat(context.combat);
  updateNarrativeHistory(context.narrative.recent_turns);
}
```

**When to Refresh:**
- After subsystem changes (quest offered/completed, combat started/ended)
- On page load/reconnection
- Periodically if multiple devices access same character (polling/websocket)

---

## Error Handling & User Feedback

### HTTP Error Handling

```javascript
async function handleTurnRequest(characterId, userAction, userId) {
  try {
    const response = await fetch(`${DM_SERVICE_URL}/turn`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId
      },
      body: JSON.stringify({ character_id: characterId, user_action: userAction, user_id: userId })
    });
    
    if (response.status === 404) {
      const error = await response.json();
      showError('Character not found. Please create a new character.');
      redirectToCharacterCreation();
      return;
    }
    
    if (response.status === 429) {
      const error = await response.json();
      const retryAfter = error.detail.retry_after_seconds || 1;
      showError(`Please wait ${retryAfter} seconds before your next action.`);
      startCooldownTimer(retryAfter);
      return;
    }
    
    if (response.status === 502 || response.status === 504) {
      showError('The dungeon master is currently unavailable. Please try again.');
      return;
    }
    
    if (!response.ok) {
      const error = await response.json();
      showError(error.detail?.error?.message || 'An error occurred');
      return;
    }
    
    const data = await response.json();
    return data;
    
  } catch (error) {
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      showError('Unable to connect to the game server. Please check your connection.');
    } else {
      showError('An unexpected error occurred. Please try again.');
    }
    console.error('Turn request error:', error);
  }
}
```

### User-Friendly Error Messages

```javascript
const ERROR_MESSAGES = {
  'character_not_found': 'Your character could not be found. Please create a new character.',
  'journey_log_timeout': 'The story archive is taking too long to respond. Please try again.',
  'llm_error': 'The dungeon master is having trouble generating a response. Please try again.',
  'rate_limit_exceeded': 'You\'re acting too quickly! Please wait a moment.',
  'invalid_action': 'That action couldn\'t be processed. Please try something else.',
  'default': 'Something went wrong. Please try again.'
};

function showError(errorType) {
  const message = ERROR_MESSAGES[errorType] || ERROR_MESSAGES.default;
  // Display error in UI
  toast.error(message);
}
```

### Status Indicators

```jsx
function StatusIndicator({ status }) {
  const statusConfig = {
    'Healthy': { color: 'green', icon: '❤️' },
    'Wounded': { color: 'orange', icon: '🩹' },
    'Dead': { color: 'red', icon: '💀' }
  };
  
  const config = statusConfig[status] || statusConfig['Healthy'];
  
  return (
    <div className={`status-indicator ${config.color}`}>
      <span className="icon">{config.icon}</span>
      <span className="text">{status}</span>
    </div>
  );
}
```

---

## Advanced Features

### 1. Action Suggestions

Provide context-aware action buttons:

```javascript
function ActionSuggestions({ context, onSelect }) {
  const suggestions = generateSuggestions(context);
  
  return (
    <div className="action-suggestions">
      <p>Suggested actions:</p>
      {suggestions.map((suggestion, i) => (
        <button 
          key={i}
          onClick={() => onSelect(suggestion)}
          className="suggestion-btn"
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}

function generateSuggestions(context) {
  const suggestions = ["Look around", "Check inventory"];
  
  if (context.quest) {
    suggestions.push("Continue quest");
  }
  
  if (context.combat?.active) {
    suggestions.push("Attack", "Defend", "Use item", "Flee");
  } else {
    suggestions.push("Explore", "Rest");
  }
  
  return suggestions;
}
```

### 2. Auto-Save & Session Recovery

```javascript
// Save state to localStorage
function saveGameState(characterId, state) {
  localStorage.setItem(
    `game_state_${characterId}`,
    JSON.stringify({
      ...state,
      lastSaved: Date.now()
    })
  );
}

// Restore on page load
function restoreGameState(characterId) {
  const saved = localStorage.getItem(`game_state_${characterId}`);
  if (saved) {
    const state = JSON.parse(saved);
    // Check if state is recent (< 24 hours old)
    if (Date.now() - state.lastSaved < 24 * 60 * 60 * 1000) {
      return state;
    }
  }
  return null;
}
```

### 3. Narrative History Search

```jsx
function NarrativeSearch({ history }) {
  const [searchTerm, setSearchTerm] = useState('');
  
  const filtered = history.filter(turn =>
    turn.player_action.toLowerCase().includes(searchTerm.toLowerCase()) ||
    turn.gm_response.toLowerCase().includes(searchTerm.toLowerCase())
  );
  
  return (
    <div className="narrative-search">
      <input
        type="search"
        placeholder="Search your adventure..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />
      <div className="results">
        {filtered.map((turn, i) => (
          <NarrativeTurn key={i} turn={turn} />
        ))}
      </div>
    </div>
  );
}
```

### 4. Death/Game Over Screen

When character status becomes "Dead":

```jsx
function GameOverScreen({ character, restartGame }) {
  return (
    <div className="game-over-screen">
      <h1>💀 Game Over 💀</h1>
      <p>{character.name} has fallen...</p>
      <p className="epitaph">
        Their story ends here, but their legacy lives on.
      </p>
      
      <div className="stats">
        <h3>Final Statistics</h3>
        <p>Quests Completed: {character.quests_completed || 0}</p>
        <p>Locations Discovered: {character.pois_discovered || 0}</p>
        <p>Turns Survived: {character.total_turns || 0}</p>
      </div>
      
      <button onClick={restartGame} className="restart-btn">
        Create New Character
      </button>
    </div>
  );
}
```

### 5. Accessibility Features

```jsx
// Keyboard shortcuts
useEffect(() => {
  function handleKeyPress(e) {
    if (e.key === 'Enter' && e.ctrlKey) {
      submitAction();
    }
    if (e.key === 'Escape') {
      clearInput();
    }
  }
  
  window.addEventListener('keypress', handleKeyPress);
  return () => window.removeEventListener('keypress', handleKeyPress);
}, []);

// Screen reader support
<button 
  aria-label="Submit your action to the dungeon master"
  onClick={submitAction}
>
  Submit
</button>

// Focus management
useEffect(() => {
  if (!isProcessing) {
    inputRef.current?.focus();
  }
}, [isProcessing]);
```

---

## Performance Considerations

### 1. Debounce User Input Validation

```javascript
import { debounce } from 'lodash';

const validateAction = debounce((action) => {
  if (action.length < 1) {
    setValidation({ valid: false, message: 'Action too short' });
  } else if (action.length > 8000) {
    setValidation({ valid: false, message: 'Action too long' });
  } else {
    setValidation({ valid: true });
  }
}, 300);
```

### 2. Optimize Narrative Rendering

```jsx
// Virtualized list for long narrative history
import { FixedSizeList } from 'react-window';

function NarrativeHistory({ turns }) {
  const Row = ({ index, style }) => (
    <div style={style}>
      <NarrativeTurn turn={turns[index]} />
    </div>
  );
  
  return (
    <FixedSizeList
      height={600}
      itemCount={turns.length}
      itemSize={200}
      width="100%"
    >
      {Row}
    </FixedSizeList>
  );
}
```

### 3. Lazy Load Components

```javascript
const QuestPanel = lazy(() => import('./components/QuestPanel'));
const CombatPanel = lazy(() => import('./components/CombatPanel'));
const POIMap = lazy(() => import('./components/POIMap'));
```

### 4. Request Caching

```javascript
// Simple in-memory cache for character context
const contextCache = new Map();

async function getCachedContext(characterId, userId) {
  const cacheKey = `${characterId}_${userId}`;
  const cached = contextCache.get(cacheKey);
  
  if (cached && Date.now() - cached.timestamp < 60000) {
    return cached.data;
  }
  
  const data = await fetchContext(characterId, userId);
  contextCache.set(cacheKey, { data, timestamp: Date.now() });
  return data;
}
```

---

## Example Code Snippets

### Complete React Component Example

```jsx
import React, { useState, useEffect, useRef } from 'react';

function DungeonMasterGame({ characterId, userId }) {
  const [gameState, setGameState] = useState({
    character: null,
    narrative: [],
    quest: null,
    combat: null,
    isProcessing: false,
    error: null
  });
  
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef(null);
  
  // Load initial character state
  useEffect(() => {
    loadCharacterState();
  }, [characterId]);
  
  async function loadCharacterState() {
    try {
      const response = await fetch(
        `${process.env.JOURNEY_LOG_URL}/characters/${characterId}/context?recent_n=20`,
        { headers: { 'X-User-Id': userId } }
      );
      
      if (!response.ok) throw new Error('Failed to load character');
      
      const context = await response.json();
      setGameState(prev => ({
        ...prev,
        character: { id: characterId, status: context.status },
        narrative: context.narrative?.recent_turns || [],
        quest: context.quest,
        combat: context.combat
      }));
    } catch (error) {
      setGameState(prev => ({ ...prev, error: error.message }));
    }
  }
  
  async function submitAction() {
    if (!inputValue.trim() || gameState.isProcessing) return;
    
    setGameState(prev => ({ ...prev, isProcessing: true, error: null }));
    
    try {
      const response = await fetch(`${process.env.DM_SERVICE_URL}/turn`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': userId
        },
        body: JSON.stringify({
          character_id: characterId,
          user_action: inputValue,
          user_id: userId
        })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.error?.message || 'Request failed');
      }
      
      const result = await response.json();
      
      // Add to narrative history
      setGameState(prev => ({
        ...prev,
        narrative: [
          ...prev.narrative,
          { player_action: inputValue, ai_response: result.narrative }
        ],
        isProcessing: false
      }));
      
      // Clear input
      setInputValue('');
      
      // Handle subsystem changes
      if (result.subsystem_summary) {
        handleSubsystemChanges(result.subsystem_summary);
      }
      
      // Refresh character state if needed
      if (result.subsystem_summary?.quest_change?.success ||
          result.subsystem_summary?.combat_change?.success) {
        await loadCharacterState();
      }
      
    } catch (error) {
      setGameState(prev => ({
        ...prev,
        isProcessing: false,
        error: error.message
      }));
    }
    
    // Re-focus input
    inputRef.current?.focus();
  }
  
  function handleSubsystemChanges(summary) {
    if (summary.quest_change?.success) {
      console.log('Quest changed:', summary.quest_change.action);
    }
    if (summary.combat_change?.success) {
      console.log('Combat changed:', summary.combat_change.action);
    }
    if (summary.poi_change?.success) {
      console.log('POI discovered');
    }
  }
  
  // Check if character is dead
  if (gameState.character?.status === 'Dead') {
    return <GameOverScreen character={gameState.character} />;
  }
  
  return (
    <div className="dungeon-master-game">
      {/* Character Header */}
      <div className="character-header">
        <StatusIndicator status={gameState.character?.status} />
      </div>
      
      {/* Narrative Display */}
      <div className="narrative-container">
        {gameState.narrative.map((turn, i) => (
          <div key={i} className="turn">
            <div className="player-action">
              <strong>You:</strong> {turn.player_action}
            </div>
            <div className="ai-response">
              <strong>DM:</strong> {turn.ai_response}
            </div>
          </div>
        ))}
      </div>
      
      {/* Sidebar Panels */}
      <div className="sidebar">
        {gameState.quest && <QuestPanel quest={gameState.quest} />}
        {gameState.combat && <CombatPanel combat={gameState.combat} />}
      </div>
      
      {/* Input Area */}
      <div className="input-area">
        {gameState.error && (
          <div className="error-message">{gameState.error}</div>
        )}
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && submitAction()}
          placeholder="What do you do?"
          disabled={gameState.isProcessing}
        />
        <button 
          onClick={submitAction}
          disabled={gameState.isProcessing || !inputValue.trim()}
        >
          {gameState.isProcessing ? 'Processing...' : 'Submit'}
        </button>
      </div>
    </div>
  );
}

export default DungeonMasterGame;
```

---

## Design Patterns & Best Practices

### 1. Optimistic UI Updates

```javascript
// Add player action immediately to UI
function optimisticSubmit(action) {
  // Immediately show player's action
  setNarrative(prev => [...prev, { 
    player_action: action, 
    ai_response: '...',
    pending: true 
  }]);
  
  // Then make API call
  submitAction(action).then(result => {
    // Replace pending with actual response
    setNarrative(prev => 
      prev.map(turn => 
        turn.pending ? { ...turn, ai_response: result.narrative, pending: false } : turn
      )
    );
  });
}
```

### 2. Progressive Enhancement

```javascript
// Start with basic functionality, add features progressively
const features = {
  basicNarrative: true,        // Always available
  questTracking: hasQuests(),   // If quest system active
  combatMode: hasCombat(),      // If combat system active
  poiMap: hasPOIs(),           // If POI system active
  audioEffects: hasAudio(),    // If audio enabled
  animations: hasAnimations()  // If animations enabled
};
```

### 3. Mobile Responsiveness

```css
/* Mobile-first responsive design */
.dungeon-master-game {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

@media (min-width: 768px) {
  .dungeon-master-game {
    flex-direction: row;
  }
  
  .narrative-container {
    flex: 2;
  }
  
  .sidebar {
    flex: 1;
    max-width: 400px;
  }
}

/* Touch-friendly buttons on mobile */
@media (max-width: 767px) {
  button {
    min-height: 44px;
    min-width: 44px;
  }
}
```

---

## Conclusion

This guide provides a foundation for building rich, engaging frontend experiences on top of the Dungeon Master service. Key principles:

1. **Responsive Feedback** - Always show loading states and clear error messages
2. **Persistent State** - Save progress and sync with Journey-Log
3. **Progressive Enhancement** - Start simple, add features as needed
4. **Accessibility** - Support keyboard navigation and screen readers
5. **Performance** - Optimize rendering, cache where appropriate

For additional help:
- Review the OpenAPI spec at `journey-log.openapi.json`
- Check service metrics at `/metrics` endpoint
- Test with debug endpoint `/debug/parse_llm` during development
- Monitor Journey-Log health at `/health` endpoint

Happy building! 🎲⚔️🗺️
