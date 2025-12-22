# /rpg
Opens a thread in which a ttrpg style game unfolds. This is similar to roleplaying services like SillyTavern https://github.com/SillyTavern/SillyTavern or Character AI https://character.ai/ except that the LLM has access to a variety of tools to manage the RP session. You see, LLMs excel at flavour text and character dialouge, but are lacklustre at game mechanics and reliably managing a world state. Therefore the LLM should play the role of a game master, with the mechanics handled by external systems like game rules, dice rolling, a character sheet, bestiary, etc.

## Implemented Features

### Dice Rolling
- [x] `roll_dice` tool for LLM-controlled dice rolling
- [x] Supports standard RPG dice (d4, d6, d8, d10, d12, d20, d100)
- [x] Multiple dice with modifiers (e.g., 2d6+3)

### Character Sheet
- [x] SQLite database with player character statistics (`/data/character_sheets.db`)
- [x] Per-user and per-channel character sheets (different characters for different threads)
- [x] Core stats: HP, MP, XP, Level, Gold
- [x] D&D-style attributes: STR, DEX, CON, INT, WIS, CHA
- [x] Inventory system (add/remove items)
- [x] Custom stats for game-specific attributes
- [x] `character_sheet` LLM tool for viewing and modifying stats
- [x] `/character` command to view character sheet
- [x] `/reset-character` command to reset to defaults

## Planned Features

### World State
- [ ] Persistent world state database
- [ ] Location tracking
- [ ] NPC relationships
- [ ] Quest progress

### Bestiary
- [ ] Database with monster statistics and information
- [ ] Monster lookup tool for LLM
- [ ] Combat stat blocks

### Combat System
- [ ] Turn-based combat mechanics
- [ ] Initiative tracking
- [ ] Damage calculation

### RPG Thread Mode
- [ ] `/rpg` command to start a dedicated RPG thread
- [ ] Custom system prompt for game master role
- [ ] Automatic character sheet context injection