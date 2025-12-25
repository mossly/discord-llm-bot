"""
Conversation Database - Stores thread metadata and configuration
Phase 1: Thread metadata only (model, modes, allowed tools)
Future phases will add message and tool call logging
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
class ThreadMetadata:
    """Represents metadata for an AI conversation thread"""
    id: Optional[int] = None
    thread_id: int = 0  # Discord thread ID
    guild_id: int = 0
    parent_channel_id: int = 0
    created_by_user_id: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Configuration
    model_key: str = "claude-haiku-4.5"
    is_fun_mode: bool = False
    is_rpg_mode: bool = False
    system_prompt_override: Optional[str] = None
    allowed_tools: str = "[]"  # JSON array

    def get_allowed_tools_list(self) -> List[str]:
        """Get allowed tools as a Python list"""
        try:
            return json.loads(self.allowed_tools)
        except json.JSONDecodeError:
            return []

    def set_allowed_tools_list(self, tools: List[str]):
        """Set allowed tools from a Python list"""
        self.allowed_tools = json.dumps(tools)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "guild_id": self.guild_id,
            "parent_channel_id": self.parent_channel_id,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model_key": self.model_key,
            "is_fun_mode": self.is_fun_mode,
            "is_rpg_mode": self.is_rpg_mode,
            "system_prompt_override": self.system_prompt_override,
            "allowed_tools": self.get_allowed_tools_list()
        }


class ConversationDB:
    """Manages conversation/thread metadata persistence"""

    def __init__(self):
        self.db_path = "/data/conversations.db"
        self.connection_pool = asyncio.Queue(maxsize=5)
        self._initialized = False
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

    async def initialize(self):
        """Initialize the database and create tables"""
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
            logger.info("ConversationDB initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ConversationDB: {e}")
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
        """Create database tables"""
        conn = await self._get_connection()
        try:
            # Thread metadata table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER UNIQUE NOT NULL,
                    guild_id INTEGER NOT NULL,
                    parent_channel_id INTEGER NOT NULL,
                    created_by_user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    model_key TEXT NOT NULL,
                    is_fun_mode BOOLEAN DEFAULT 0,
                    is_rpg_mode BOOLEAN DEFAULT 0,
                    system_prompt_override TEXT,
                    allowed_tools TEXT DEFAULT '[]'
                )
            ''')

            # Create indexes
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_threads_thread_id ON threads(thread_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_threads_guild ON threads(guild_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(created_by_user_id)')

            await conn.commit()
            logger.info("ConversationDB tables created successfully")
        except Exception as e:
            logger.error(f"Error creating ConversationDB tables: {e}")
            raise
        finally:
            await self._return_connection(conn)

    def _thread_from_row(self, row) -> ThreadMetadata:
        """Convert database row to ThreadMetadata object"""
        def safe_get(key, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default

        return ThreadMetadata(
            id=safe_get('id'),
            thread_id=safe_get('thread_id', 0),
            guild_id=safe_get('guild_id', 0),
            parent_channel_id=safe_get('parent_channel_id', 0),
            created_by_user_id=safe_get('created_by_user_id', 0),
            created_at=safe_get('created_at', time.time()),
            updated_at=safe_get('updated_at', time.time()),
            model_key=safe_get('model_key', 'claude-haiku-4.5'),
            is_fun_mode=bool(safe_get('is_fun_mode', False)),
            is_rpg_mode=bool(safe_get('is_rpg_mode', False)),
            system_prompt_override=safe_get('system_prompt_override'),
            allowed_tools=safe_get('allowed_tools', '[]')
        )

    async def create_thread(
        self,
        thread_id: int,
        guild_id: int,
        parent_channel_id: int,
        created_by_user_id: int,
        model_key: str,
        is_fun_mode: bool = False,
        is_rpg_mode: bool = False,
        system_prompt_override: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None
    ) -> ThreadMetadata:
        """Create a new thread metadata entry"""
        now = time.time()
        tools_json = json.dumps(allowed_tools) if allowed_tools else "[]"

        conn = await self._get_connection()
        try:
            cursor = await conn.execute('''
                INSERT INTO threads (
                    thread_id, guild_id, parent_channel_id, created_by_user_id,
                    created_at, updated_at, model_key, is_fun_mode, is_rpg_mode,
                    system_prompt_override, allowed_tools
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                thread_id, guild_id, parent_channel_id, created_by_user_id,
                now, now, model_key, is_fun_mode, is_rpg_mode,
                system_prompt_override, tools_json
            ))

            row_id = cursor.lastrowid
            await conn.commit()

            # Clear cache
            self._cache.pop(thread_id, None)

            thread = ThreadMetadata(
                id=row_id,
                thread_id=thread_id,
                guild_id=guild_id,
                parent_channel_id=parent_channel_id,
                created_by_user_id=created_by_user_id,
                created_at=now,
                updated_at=now,
                model_key=model_key,
                is_fun_mode=is_fun_mode,
                is_rpg_mode=is_rpg_mode,
                system_prompt_override=system_prompt_override,
                allowed_tools=tools_json
            )

            logger.info(f"Created thread metadata for thread {thread_id} (model={model_key}, rpg={is_rpg_mode}, fun={is_fun_mode})")
            return thread
        except Exception as e:
            logger.error(f"Error creating thread metadata: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def get_thread(self, thread_id: int) -> Optional[ThreadMetadata]:
        """Get thread metadata by Discord thread ID"""
        # Check cache first
        cached = self._cache.get(thread_id)
        if cached and time.time() - cached['timestamp'] < self._cache_ttl:
            return cached['data']

        conn = await self._get_connection()
        try:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                'SELECT * FROM threads WHERE thread_id = ?',
                (thread_id,)
            )
            row = await cursor.fetchone()

            if row:
                thread = self._thread_from_row(row)
                self._cache[thread_id] = {'data': thread, 'timestamp': time.time()}
                return thread
            return None
        except Exception as e:
            logger.error(f"Error getting thread {thread_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def update_thread(self, thread_id: int, **kwargs) -> bool:
        """Update thread metadata fields"""
        if not kwargs:
            return False

        # Build update query dynamically
        allowed_fields = {
            'model_key', 'is_fun_mode', 'is_rpg_mode',
            'system_prompt_override', 'allowed_tools'
        }
        updates = []
        values = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                if key == 'allowed_tools' and isinstance(value, list):
                    values.append(json.dumps(value))
                else:
                    values.append(value)

        if not updates:
            return False

        updates.append("updated_at = ?")
        values.append(time.time())
        values.append(thread_id)

        conn = await self._get_connection()
        try:
            query = f"UPDATE threads SET {', '.join(updates)} WHERE thread_id = ?"
            cursor = await conn.execute(query, values)
            await conn.commit()

            # Clear cache
            self._cache.pop(thread_id, None)

            if cursor.rowcount > 0:
                logger.info(f"Updated thread {thread_id}: {list(kwargs.keys())}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating thread {thread_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def delete_thread(self, thread_id: int) -> bool:
        """Delete thread metadata"""
        conn = await self._get_connection()
        try:
            cursor = await conn.execute(
                'DELETE FROM threads WHERE thread_id = ?',
                (thread_id,)
            )
            await conn.commit()

            # Clear cache
            self._cache.pop(thread_id, None)

            if cursor.rowcount > 0:
                logger.info(f"Deleted thread metadata for {thread_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting thread {thread_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def get_threads_by_guild(self, guild_id: int) -> List[ThreadMetadata]:
        """Get all threads for a guild"""
        conn = await self._get_connection()
        try:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                'SELECT * FROM threads WHERE guild_id = ? ORDER BY created_at DESC',
                (guild_id,)
            )
            rows = await cursor.fetchall()
            return [self._thread_from_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting threads for guild {guild_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)

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
                logger.info("ConversationDB cleanup completed")
            except Exception as e:
                logger.error(f"Error during ConversationDB cleanup: {e}")
                self._initialized = False


# Global instance
conversation_db = ConversationDB()
