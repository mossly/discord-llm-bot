"""
Character Sheet Manager - Database layer for RPG character sheets
Provides persistent storage for player stats like HP, MP, XP, Level, and Inventory
"""

import asyncio
import time
import logging
import os
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class CharacterSheet:
    """Represents a player's character sheet"""
    id: Optional[int] = None
    user_id: int = 0  # Discord user ID
    channel_id: Optional[int] = None  # Channel/thread where this character is active
    name: str = "Adventurer"

    # Core stats
    hp: int = 100
    max_hp: int = 100
    mp: int = 50
    max_mp: int = 50
    xp: int = 0
    level: int = 1

    # Optional stats (can be customized per game)
    gold: int = 0
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    # Inventory stored as JSON
    inventory: str = "[]"  # JSON array of items

    # Custom stats for flexibility (stored as JSON)
    custom_stats: str = "{}"  # JSON object for game-specific stats

    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def get_inventory_list(self) -> List[str]:
        """Get inventory as a Python list"""
        try:
            return json.loads(self.inventory)
        except json.JSONDecodeError:
            return []

    def set_inventory_list(self, items: List[str]):
        """Set inventory from a Python list"""
        self.inventory = json.dumps(items)

    def add_item(self, item: str) -> bool:
        """Add an item to inventory"""
        items = self.get_inventory_list()
        items.append(item)
        self.set_inventory_list(items)
        return True

    def remove_item(self, item: str) -> bool:
        """Remove an item from inventory (first occurrence)"""
        items = self.get_inventory_list()
        if item in items:
            items.remove(item)
            self.set_inventory_list(items)
            return True
        return False

    def has_item(self, item: str) -> bool:
        """Check if item exists in inventory"""
        return item in self.get_inventory_list()

    def get_custom_stats(self) -> Dict[str, Any]:
        """Get custom stats as a Python dict"""
        try:
            return json.loads(self.custom_stats)
        except json.JSONDecodeError:
            return {}

    def set_custom_stat(self, key: str, value: Any):
        """Set a custom stat"""
        stats = self.get_custom_stats()
        stats[key] = value
        self.custom_stats = json.dumps(stats)

    def get_custom_stat(self, key: str, default: Any = None) -> Any:
        """Get a custom stat value"""
        return self.get_custom_stats().get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert character sheet to dictionary for display"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "xp": self.xp,
            "level": self.level,
            "gold": self.gold,
            "strength": self.strength,
            "dexterity": self.dexterity,
            "constitution": self.constitution,
            "intelligence": self.intelligence,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
            "inventory": self.get_inventory_list(),
            "custom_stats": self.get_custom_stats()
        }


class CharacterSheetManager:
    """Manages character sheet persistence and operations"""

    def __init__(self):
        self.db_path = "/data/character_sheets.db"
        self.connection_pool = asyncio.Queue(maxsize=5)
        self._initialized = False
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

    async def initialize(self):
        """Initialize the character sheet manager and create database tables"""
        if self._initialized:
            return

        try:
            # Ensure data directory exists
            os.makedirs("/data", exist_ok=True)

            # Initialize connection pool
            for _ in range(5):
                conn = await aiosqlite.connect(self.db_path)
                await self.connection_pool.put(conn)

            # Create database schema
            await self._create_tables()

            self._initialized = True
            logger.info("CharacterSheetManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CharacterSheetManager: {e}")
            while not self.connection_pool.empty():
                try:
                    conn = self.connection_pool.get_nowait()
                    await conn.close()
                except:
                    pass
            raise

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get a database connection from the pool"""
        return await self.connection_pool.get()

    async def _return_connection(self, conn: aiosqlite.Connection):
        """Return a database connection to the pool"""
        await self.connection_pool.put(conn)

    async def _create_tables(self):
        """Create database tables for character sheets"""
        conn = await self._get_connection()
        try:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS character_sheets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER,
                    name TEXT DEFAULT 'Adventurer',
                    hp INTEGER DEFAULT 100,
                    max_hp INTEGER DEFAULT 100,
                    mp INTEGER DEFAULT 50,
                    max_mp INTEGER DEFAULT 50,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    gold INTEGER DEFAULT 0,
                    strength INTEGER DEFAULT 10,
                    dexterity INTEGER DEFAULT 10,
                    constitution INTEGER DEFAULT 10,
                    intelligence INTEGER DEFAULT 10,
                    wisdom INTEGER DEFAULT 10,
                    charisma INTEGER DEFAULT 10,
                    inventory TEXT DEFAULT '[]',
                    custom_stats TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, channel_id)
                )
            ''')

            # Create indexes
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_character_user ON character_sheets(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_character_channel ON character_sheets(channel_id)')

            await conn.commit()
            logger.info("Character sheet database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating character sheet tables: {e}")
            raise
        finally:
            await self._return_connection(conn)

    def _character_from_row(self, row) -> CharacterSheet:
        """Convert database row to CharacterSheet object"""
        def safe_get(key, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default

        return CharacterSheet(
            id=safe_get('id'),
            user_id=safe_get('user_id', 0),
            channel_id=safe_get('channel_id'),
            name=safe_get('name', 'Adventurer'),
            hp=safe_get('hp', 100),
            max_hp=safe_get('max_hp', 100),
            mp=safe_get('mp', 50),
            max_mp=safe_get('max_mp', 50),
            xp=safe_get('xp', 0),
            level=safe_get('level', 1),
            gold=safe_get('gold', 0),
            strength=safe_get('strength', 10),
            dexterity=safe_get('dexterity', 10),
            constitution=safe_get('constitution', 10),
            intelligence=safe_get('intelligence', 10),
            wisdom=safe_get('wisdom', 10),
            charisma=safe_get('charisma', 10),
            inventory=safe_get('inventory', '[]'),
            custom_stats=safe_get('custom_stats', '{}'),
            created_at=safe_get('created_at', time.time()),
            updated_at=safe_get('updated_at', time.time())
        )

    async def create_character(self, character: CharacterSheet) -> int:
        """Create a new character sheet and return its ID"""
        conn = await self._get_connection()
        try:
            cursor = await conn.execute('''
                INSERT INTO character_sheets (
                    user_id, channel_id, name, hp, max_hp, mp, max_mp,
                    xp, level, gold, strength, dexterity, constitution,
                    intelligence, wisdom, charisma, inventory, custom_stats,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                character.user_id, character.channel_id, character.name,
                character.hp, character.max_hp, character.mp, character.max_mp,
                character.xp, character.level, character.gold,
                character.strength, character.dexterity, character.constitution,
                character.intelligence, character.wisdom, character.charisma,
                character.inventory, character.custom_stats,
                character.created_at, character.updated_at
            ))

            character_id = cursor.lastrowid
            await conn.commit()

            self._cache.clear()
            logger.info(f"Created character sheet {character_id} for user {character.user_id}")
            return character_id
        except Exception as e:
            logger.error(f"Error creating character sheet: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def get_character(self, user_id: int, channel_id: Optional[int] = None) -> Optional[CharacterSheet]:
        """Get a character sheet by user and optionally channel"""
        cache_key = f"char_{user_id}_{channel_id}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached['timestamp'] < self._cache_ttl:
            return cached['data']

        conn = await self._get_connection()
        try:
            conn.row_factory = aiosqlite.Row

            if channel_id is not None:
                cursor = await conn.execute(
                    'SELECT * FROM character_sheets WHERE user_id = ? AND channel_id = ?',
                    (user_id, channel_id)
                )
            else:
                cursor = await conn.execute(
                    'SELECT * FROM character_sheets WHERE user_id = ? AND channel_id IS NULL',
                    (user_id,)
                )

            row = await cursor.fetchone()

            if row:
                character = self._character_from_row(row)
                self._cache[cache_key] = {'data': character, 'timestamp': time.time()}
                return character
            return None
        except Exception as e:
            logger.error(f"Error getting character for user {user_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def get_or_create_character(self, user_id: int, channel_id: Optional[int] = None, name: str = "Adventurer") -> CharacterSheet:
        """Get existing character or create a new one"""
        character = await self.get_character(user_id, channel_id)
        if character:
            return character

        # Create new character
        new_character = CharacterSheet(
            user_id=user_id,
            channel_id=channel_id,
            name=name
        )
        character_id = await self.create_character(new_character)
        new_character.id = character_id
        return new_character

    async def update_character(self, character: CharacterSheet) -> bool:
        """Update an existing character sheet"""
        if not character.id:
            return False

        character.updated_at = time.time()

        conn = await self._get_connection()
        try:
            await conn.execute('''
                UPDATE character_sheets SET
                    name = ?, hp = ?, max_hp = ?, mp = ?, max_mp = ?,
                    xp = ?, level = ?, gold = ?, strength = ?, dexterity = ?,
                    constitution = ?, intelligence = ?, wisdom = ?, charisma = ?,
                    inventory = ?, custom_stats = ?, updated_at = ?
                WHERE id = ?
            ''', (
                character.name, character.hp, character.max_hp,
                character.mp, character.max_mp, character.xp, character.level,
                character.gold, character.strength, character.dexterity,
                character.constitution, character.intelligence, character.wisdom,
                character.charisma, character.inventory, character.custom_stats,
                character.updated_at, character.id
            ))

            await conn.commit()
            self._cache.clear()
            logger.info(f"Updated character sheet {character.id}")
            return True
        except Exception as e:
            logger.error(f"Error updating character sheet {character.id}: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def delete_character(self, character_id: int) -> bool:
        """Delete a character sheet"""
        conn = await self._get_connection()
        try:
            cursor = await conn.execute('DELETE FROM character_sheets WHERE id = ?', (character_id,))
            await conn.commit()

            self._cache.clear()

            if cursor.rowcount > 0:
                logger.info(f"Deleted character sheet {character_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting character sheet {character_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def modify_stat(self, user_id: int, channel_id: Optional[int], stat: str, delta: int) -> Optional[CharacterSheet]:
        """Modify a stat by a delta value (can be positive or negative)"""
        character = await self.get_or_create_character(user_id, channel_id)

        # Handle stat modification
        stat_lower = stat.lower()

        if stat_lower == "hp":
            character.hp = max(0, min(character.max_hp, character.hp + delta))
        elif stat_lower == "max_hp":
            character.max_hp = max(1, character.max_hp + delta)
            character.hp = min(character.hp, character.max_hp)
        elif stat_lower == "mp":
            character.mp = max(0, min(character.max_mp, character.mp + delta))
        elif stat_lower == "max_mp":
            character.max_mp = max(0, character.max_mp + delta)
            character.mp = min(character.mp, character.max_mp)
        elif stat_lower == "xp":
            character.xp = max(0, character.xp + delta)
        elif stat_lower == "level":
            character.level = max(1, character.level + delta)
        elif stat_lower == "gold":
            character.gold = max(0, character.gold + delta)
        elif stat_lower == "strength" or stat_lower == "str":
            character.strength = max(1, character.strength + delta)
        elif stat_lower == "dexterity" or stat_lower == "dex":
            character.dexterity = max(1, character.dexterity + delta)
        elif stat_lower == "constitution" or stat_lower == "con":
            character.constitution = max(1, character.constitution + delta)
        elif stat_lower == "intelligence" or stat_lower == "int":
            character.intelligence = max(1, character.intelligence + delta)
        elif stat_lower == "wisdom" or stat_lower == "wis":
            character.wisdom = max(1, character.wisdom + delta)
        elif stat_lower == "charisma" or stat_lower == "cha":
            character.charisma = max(1, character.charisma + delta)
        else:
            # Try custom stat
            current = character.get_custom_stat(stat_lower, 0)
            character.set_custom_stat(stat_lower, current + delta)

        await self.update_character(character)
        return character

    async def set_stat(self, user_id: int, channel_id: Optional[int], stat: str, value: int) -> Optional[CharacterSheet]:
        """Set a stat to a specific value"""
        character = await self.get_or_create_character(user_id, channel_id)

        stat_lower = stat.lower()

        if stat_lower == "hp":
            character.hp = max(0, min(character.max_hp, value))
        elif stat_lower == "max_hp":
            character.max_hp = max(1, value)
            character.hp = min(character.hp, character.max_hp)
        elif stat_lower == "mp":
            character.mp = max(0, min(character.max_mp, value))
        elif stat_lower == "max_mp":
            character.max_mp = max(0, value)
            character.mp = min(character.mp, character.max_mp)
        elif stat_lower == "xp":
            character.xp = max(0, value)
        elif stat_lower == "level":
            character.level = max(1, value)
        elif stat_lower == "gold":
            character.gold = max(0, value)
        elif stat_lower == "strength" or stat_lower == "str":
            character.strength = max(1, value)
        elif stat_lower == "dexterity" or stat_lower == "dex":
            character.dexterity = max(1, value)
        elif stat_lower == "constitution" or stat_lower == "con":
            character.constitution = max(1, value)
        elif stat_lower == "intelligence" or stat_lower == "int":
            character.intelligence = max(1, value)
        elif stat_lower == "wisdom" or stat_lower == "wis":
            character.wisdom = max(1, value)
        elif stat_lower == "charisma" or stat_lower == "cha":
            character.charisma = max(1, value)
        else:
            # Set custom stat
            character.set_custom_stat(stat_lower, value)

        await self.update_character(character)
        return character

    async def cleanup(self):
        """Cleanup resources"""
        if self._initialized:
            try:
                while not self.connection_pool.empty():
                    try:
                        conn = self.connection_pool.get_nowait()
                        await conn.close()
                    except:
                        pass

                self._initialized = False
                logger.info("CharacterSheetManager cleanup completed")
            except Exception as e:
                logger.error(f"Error during CharacterSheetManager cleanup: {e}")
                self._initialized = False


# Global instance
character_sheet_manager = CharacterSheetManager()
