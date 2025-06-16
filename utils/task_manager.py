import asyncio
import time
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
import json
import os
import aiosqlite
from datetime import datetime, timedelta
import pytz
from .background_task_manager import BackgroundTaskManager, TaskPriority

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"

class TaskPriorityLevel(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

class ResponsibilityType(Enum):
    ANY_USER = "ANY_USER"  # Any assigned user can complete the task
    ALL_USERS = "ALL_USERS"  # All assigned users must complete the task
    SPECIFIC_USER = "SPECIFIC_USER"  # Only specific user can complete

class RecurrenceType(Enum):
    NONE = "NONE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    WEEKDAYS = "WEEKDAYS"  # Monday-Friday only
    WEEKENDS = "WEEKENDS"  # Saturday-Sunday only
    SPECIFIC_DAYS = "SPECIFIC_DAYS"  # Specific days of week (e.g., Mon, Wed, Fri)
    MONTHLY_POSITION = "MONTHLY_POSITION"  # First Monday, Last Friday, etc.
    QUARTERLY = "QUARTERLY"  # Every 3 months
    BIWEEKLY = "BIWEEKLY"  # Every 2 weeks
    CUSTOM_INTERVAL = "CUSTOM_INTERVAL"  # Custom day intervals
    MULTIPLE_TIMES_WEEK = "MULTIPLE_TIMES_WEEK"  # X times per week
    MULTIPLE_TIMES_MONTH = "MULTIPLE_TIMES_MONTH"  # X times per month
    CUSTOM = "CUSTOM"

@dataclass
class Task:
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    due_date: Optional[float] = None  # Unix timestamp
    priority: TaskPriorityLevel = TaskPriorityLevel.NORMAL
    status: TaskStatus = TaskStatus.TODO
    category: str = "General"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    created_by: int = 0  # Discord user ID
    channel_id: Optional[int] = None  # Channel where task was created
    timezone: str = "UTC"
    
    # Recurrence settings
    recurrence_type: RecurrenceType = RecurrenceType.NONE
    recurrence_interval: int = 1  # Every N days/weeks/months
    recurrence_end_date: Optional[float] = None
    
    # Advanced recurrence settings
    recurrence_days_of_week: Optional[str] = None  # JSON: [0,1,2,3,4] for Mon-Fri
    recurrence_day_of_month: Optional[int] = None  # 1-31 for specific day of month
    recurrence_week_of_month: Optional[int] = None  # 1-5 for "first week", "last week" = -1
    recurrence_times_per_period: Optional[int] = None  # For "3 times per week"
    recurrence_skip_holidays: bool = False  # Skip weekends/holidays
    recurrence_custom_rule: Optional[str] = None  # JSON rule for complex patterns
    
    # Notification settings
    notify_24h: bool = True
    notify_6h: bool = True
    notify_1h: bool = True
    notify_overdue: bool = True
    overdue_escalation_hours: int = 24  # How often to escalate overdue notifications
    
    # Completion tracking
    completed_at: Optional[float] = None
    completed_by: Optional[int] = None
    
    # Parent task for subtasks
    parent_task_id: Optional[int] = None

@dataclass
class TaskAssignment:
    id: Optional[int] = None
    task_id: int = 0
    user_id: int = 0  # Discord user ID
    responsibility_type: ResponsibilityType = ResponsibilityType.SPECIFIC_USER
    assigned_at: float = field(default_factory=time.time)
    assigned_by: int = 0  # Discord user ID who made the assignment
    completed: bool = False
    completed_at: Optional[float] = None

@dataclass
class TaskNotification:
    id: Optional[int] = None
    task_id: int = 0
    notification_type: str = ""  # "24h", "6h", "1h", "overdue"
    scheduled_time: float = 0
    sent: bool = False
    sent_at: Optional[float] = None

class TaskManager:
    def __init__(self, background_task_manager: BackgroundTaskManager):
        self.background_task_manager = background_task_manager
        self.db_path = "/data/tasks.db"
        self.connection_pool = asyncio.Queue(maxsize=5)
        self._initialized = False
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        
    async def initialize(self):
        """Initialize the task manager and create database tables"""
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
            
            # Run migrations for existing databases
            await self._run_migrations()
            
            self._initialized = True
            logger.info("TaskManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize TaskManager: {e}")
            # Cleanup any partial connections
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
        """Create database tables for tasks"""
        conn = await self._get_connection()
        try:
            # Tasks table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    due_date REAL,
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'TODO',
                    category TEXT DEFAULT 'General',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    created_by INTEGER NOT NULL,
                    channel_id INTEGER,
                    timezone TEXT DEFAULT 'UTC',
                    recurrence_type TEXT DEFAULT 'NONE',
                    recurrence_interval INTEGER DEFAULT 1,
                    recurrence_end_date REAL,
                    recurrence_days_of_week TEXT,
                    recurrence_day_of_month INTEGER,
                    recurrence_week_of_month INTEGER,
                    recurrence_times_per_period INTEGER,
                    recurrence_skip_holidays BOOLEAN DEFAULT 0,
                    recurrence_custom_rule TEXT,
                    notify_24h BOOLEAN DEFAULT 1,
                    notify_6h BOOLEAN DEFAULT 1,
                    notify_1h BOOLEAN DEFAULT 1,
                    notify_overdue BOOLEAN DEFAULT 1,
                    overdue_escalation_hours INTEGER DEFAULT 24,
                    completed_at REAL,
                    completed_by INTEGER,
                    parent_task_id INTEGER,
                    FOREIGN KEY (parent_task_id) REFERENCES tasks (id)
                )
            ''')
            
            # Task assignments table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS task_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    responsibility_type TEXT DEFAULT 'SPECIFIC_USER',
                    assigned_at REAL NOT NULL,
                    assigned_by INTEGER NOT NULL,
                    completed BOOLEAN DEFAULT 0,
                    completed_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
                    UNIQUE(task_id, user_id)
                )
            ''')
            
            # Task notifications table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS task_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,
                    scheduled_time REAL NOT NULL,
                    sent BOOLEAN DEFAULT 0,
                    sent_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
                )
            ''')
            
            # Task categories table for custom categories
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS task_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    color INTEGER DEFAULT 0x3498db,
                    created_at REAL NOT NULL,
                    UNIQUE(user_id, name)
                )
            ''')
            
            # Create indexes for performance
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_task_assignments_user_id ON task_assignments(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_task_notifications_scheduled_time ON task_notifications(scheduled_time)')
            
            await conn.commit()
            logger.info("Database tables created successfully")
            
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def _run_migrations(self):
        """Run database migrations for existing databases"""
        conn = await self._get_connection()
        try:
            # Check if all new columns exist, add if missing
            migrations = [
                ("recurrence_days_of_week", "TEXT"),
                ("recurrence_day_of_month", "INTEGER"),
                ("recurrence_week_of_month", "INTEGER"),
                ("recurrence_times_per_period", "INTEGER"),
                ("recurrence_skip_holidays", "BOOLEAN DEFAULT 0"),
                ("recurrence_custom_rule", "TEXT"),
                ("notify_24h", "BOOLEAN DEFAULT 1"),
                ("notify_6h", "BOOLEAN DEFAULT 1"),
                ("notify_1h", "BOOLEAN DEFAULT 1"),
                ("notify_overdue", "BOOLEAN DEFAULT 1"),
                ("overdue_escalation_hours", "INTEGER DEFAULT 24"),
                ("completed_at", "REAL"),
                ("completed_by", "INTEGER"),
                ("parent_task_id", "INTEGER")
            ]
            
            for column_name, column_type in migrations:
                try:
                    # Try to add the column - if it exists, this will fail silently
                    await conn.execute(f'ALTER TABLE tasks ADD COLUMN {column_name} {column_type}')
                    logger.info(f"Added missing column: {column_name}")
                except Exception:
                    # Column likely already exists, which is fine
                    pass
                    
            await conn.commit()
            logger.info("Database migrations completed successfully")
            
        except Exception as e:
            logger.error(f"Error running database migrations: {e}")
            # Don't raise, as this might be due to existing columns
        finally:
            await self._return_connection(conn)
            
    def _task_from_row(self, row) -> Task:
        """Convert database row to Task object"""
        # Helper function to safely get column values with defaults
        def safe_get(key, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default
        
        return Task(
            id=safe_get('id'),
            title=safe_get('title', ''),
            description=safe_get('description', ''),  
            due_date=safe_get('due_date'),
            priority=TaskPriorityLevel(safe_get('priority', 2)),
            status=TaskStatus(safe_get('status', 'TODO')),
            category=safe_get('category', 'General'),
            created_at=safe_get('created_at', time.time()),
            updated_at=safe_get('updated_at', time.time()),
            created_by=safe_get('created_by', 0),
            channel_id=safe_get('channel_id'),
            timezone=safe_get('timezone', 'UTC'),
            recurrence_type=RecurrenceType(safe_get('recurrence_type', 'NONE')),
            recurrence_interval=safe_get('recurrence_interval', 1),
            recurrence_end_date=safe_get('recurrence_end_date'),
            recurrence_days_of_week=safe_get('recurrence_days_of_week'),
            recurrence_day_of_month=safe_get('recurrence_day_of_month'),
            recurrence_week_of_month=safe_get('recurrence_week_of_month'),
            recurrence_times_per_period=safe_get('recurrence_times_per_period'),
            recurrence_skip_holidays=bool(safe_get('recurrence_skip_holidays', False)),
            recurrence_custom_rule=safe_get('recurrence_custom_rule'),
            notify_24h=bool(safe_get('notify_24h', True)),
            notify_6h=bool(safe_get('notify_6h', True)),
            notify_1h=bool(safe_get('notify_1h', True)),
            notify_overdue=bool(safe_get('notify_overdue', True)),
            overdue_escalation_hours=safe_get('overdue_escalation_hours', 24),
            completed_at=safe_get('completed_at'),
            completed_by=safe_get('completed_by'),
            parent_task_id=safe_get('parent_task_id')
        )
        
    def _assignment_from_row(self, row) -> TaskAssignment:
        """Convert database row to TaskAssignment object"""
        # Helper function to safely get column values with defaults
        def safe_get(key, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default
        
        return TaskAssignment(
            id=safe_get('id'),
            task_id=safe_get('task_id', 0),
            user_id=safe_get('user_id', 0),
            responsibility_type=ResponsibilityType(safe_get('responsibility_type', 'SPECIFIC_USER')),
            assigned_at=safe_get('assigned_at', time.time()),
            assigned_by=safe_get('assigned_by', 0),
            completed=bool(safe_get('completed', False)),
            completed_at=safe_get('completed_at')
        )
        
    async def create_task(self, task: Task) -> int:
        """Create a new task and return its ID"""
        conn = await self._get_connection()
        try:
            cursor = await conn.execute('''
                INSERT INTO tasks (
                    title, description, due_date, priority, status, category,
                    created_at, updated_at, created_by, channel_id, timezone,
                    recurrence_type, recurrence_interval, recurrence_end_date,
                    recurrence_days_of_week, recurrence_day_of_month, recurrence_week_of_month,
                    recurrence_times_per_period, recurrence_skip_holidays, recurrence_custom_rule,
                    notify_24h, notify_6h, notify_1h, notify_overdue,
                    overdue_escalation_hours, parent_task_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task.title, task.description, task.due_date, task.priority.value,
                task.status.value, task.category, task.created_at, task.updated_at,
                task.created_by, task.channel_id, task.timezone,
                task.recurrence_type.value, task.recurrence_interval, task.recurrence_end_date,
                task.recurrence_days_of_week, task.recurrence_day_of_month, task.recurrence_week_of_month,
                task.recurrence_times_per_period, task.recurrence_skip_holidays, task.recurrence_custom_rule,
                task.notify_24h, task.notify_6h, task.notify_1h, task.notify_overdue,
                task.overdue_escalation_hours, task.parent_task_id
            ))
            
            task_id = cursor.lastrowid
            await conn.commit()
            
            # Clear cache
            self._cache.clear()
            
            logger.info(f"Created task {task_id}: {task.title}")
            return task_id
            
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def get_task(self, task_id: int) -> Optional[Task]:
        """Get a task by ID"""
        cache_key = f"task_{task_id}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached['timestamp'] < self._cache_ttl:
            return cached['data']
            
        conn = await self._get_connection()
        try:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            row = await cursor.fetchone()
            
            if row:
                task = self._task_from_row(row)
                self._cache[cache_key] = {'data': task, 'timestamp': time.time()}
                return task
            return None
            
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def update_task(self, task: Task) -> bool:
        """Update an existing task"""
        if not task.id:
            return False
            
        task.updated_at = time.time()
        
        conn = await self._get_connection()
        try:
            await conn.execute('''
                UPDATE tasks SET
                    title = ?, description = ?, due_date = ?, priority = ?,
                    status = ?, category = ?, updated_at = ?, timezone = ?,
                    recurrence_type = ?, recurrence_interval = ?, recurrence_end_date = ?,
                    recurrence_days_of_week = ?, recurrence_day_of_month = ?, recurrence_week_of_month = ?,
                    recurrence_times_per_period = ?, recurrence_skip_holidays = ?, recurrence_custom_rule = ?,
                    notify_24h = ?, notify_6h = ?, notify_1h = ?, notify_overdue = ?,
                    overdue_escalation_hours = ?, completed_at = ?, completed_by = ?
                WHERE id = ?
            ''', (
                task.title, task.description, task.due_date, task.priority.value,
                task.status.value, task.category, task.updated_at, task.timezone,
                task.recurrence_type.value, task.recurrence_interval, task.recurrence_end_date,
                task.recurrence_days_of_week, task.recurrence_day_of_month, task.recurrence_week_of_month,
                task.recurrence_times_per_period, task.recurrence_skip_holidays, task.recurrence_custom_rule,
                task.notify_24h, task.notify_6h, task.notify_1h, task.notify_overdue,
                task.overdue_escalation_hours, task.completed_at, task.completed_by,
                task.id
            ))
            
            await conn.commit()
            
            # Clear cache
            self._cache.clear()
            
            logger.info(f"Updated task {task.id}: {task.title}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating task {task.id}: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def delete_task(self, task_id: int) -> bool:
        """Delete a task and its assignments/notifications"""
        conn = await self._get_connection()
        try:
            # Delete task (cascade will handle assignments and notifications)
            cursor = await conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            await conn.commit()
            
            # Clear cache
            self._cache.clear()
            
            if cursor.rowcount > 0:
                logger.info(f"Deleted task {task_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def get_user_tasks(self, user_id: int, status: Optional[TaskStatus] = None, 
                           limit: int = 50, offset: int = 0) -> List[Task]:
        """Get tasks for a user, optionally filtered by status"""
        conn = await self._get_connection()
        try:
            conn.row_factory = aiosqlite.Row
            
            # Build query based on whether we're filtering by status
            if status:
                query = '''
                    SELECT DISTINCT t.* FROM tasks t
                    LEFT JOIN task_assignments ta ON t.id = ta.task_id
                    WHERE (t.created_by = ? OR ta.user_id = ?) AND t.status = ?
                    ORDER BY t.due_date ASC, t.created_at DESC
                    LIMIT ? OFFSET ?
                '''
                params = (user_id, user_id, status.value, limit, offset)
            else:
                query = '''
                    SELECT DISTINCT t.* FROM tasks t
                    LEFT JOIN task_assignments ta ON t.id = ta.task_id
                    WHERE (t.created_by = ? OR ta.user_id = ?)
                    ORDER BY t.due_date ASC, t.created_at DESC
                    LIMIT ? OFFSET ?
                '''
                params = (user_id, user_id, limit, offset)
                
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            tasks = [self._task_from_row(row) for row in rows]
            return tasks
            
        except Exception as e:
            logger.error(f"Error getting user tasks for {user_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def assign_task(self, task_id: int, user_id: int, assigned_by: int,
                         responsibility_type: ResponsibilityType = ResponsibilityType.SPECIFIC_USER) -> bool:
        """Assign a task to a user"""
        conn = await self._get_connection()
        try:
            await conn.execute('''
                INSERT OR REPLACE INTO task_assignments (
                    task_id, user_id, responsibility_type, assigned_at, assigned_by
                ) VALUES (?, ?, ?, ?, ?)
            ''', (task_id, user_id, responsibility_type.value, time.time(), assigned_by))
            
            await conn.commit()
            logger.info(f"Assigned task {task_id} to user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error assigning task {task_id} to user {user_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def complete_task(self, task_id: int, user_id: int) -> bool:
        """Mark a task as completed by a user"""
        conn = await self._get_connection()
        try:
            # Get the task and its assignments
            task = await self.get_task(task_id)
            if not task:
                return False
                
            # Check if user is assigned to this task
            cursor = await conn.execute('''
                SELECT * FROM task_assignments WHERE task_id = ? AND user_id = ?
            ''', (task_id, user_id))
            assignment_row = await cursor.fetchone()
            
            # If user is the creator or assigned, they can complete it
            if task.created_by != user_id and not assignment_row:
                return False
                
            # Mark assignment as completed if exists
            if assignment_row:
                await conn.execute('''
                    UPDATE task_assignments SET completed = 1, completed_at = ?
                    WHERE task_id = ? AND user_id = ?
                ''', (time.time(), task_id, user_id))
                
            # Check if all requirements are met to mark task as completed
            cursor = await conn.execute('''
                SELECT responsibility_type, COUNT(*) as total,
                       SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed
                FROM task_assignments WHERE task_id = ?
                GROUP BY responsibility_type
            ''', (task_id,))
            assignment_stats = await cursor.fetchall()
            
            task_completed = True
            if assignment_stats:
                for stat in assignment_stats:
                    resp_type = ResponsibilityType(stat[0])
                    if resp_type == ResponsibilityType.ALL_USERS and stat[2] < stat[1]:
                        task_completed = False
                        break
                    elif resp_type == ResponsibilityType.ANY_USER and stat[2] == 0:
                        task_completed = False
                        break
            
            # Update task status if completed
            if task_completed:
                await conn.execute('''
                    UPDATE tasks SET status = ?, completed_at = ?, completed_by = ?, updated_at = ?
                    WHERE id = ?
                ''', (TaskStatus.COMPLETED.value, time.time(), user_id, time.time(), task_id))
                
                # Handle recurrence
                if task.recurrence_type != RecurrenceType.NONE:
                    await self._create_recurring_task(task)
                    
            await conn.commit()
            self._cache.clear()
            
            logger.info(f"Task {task_id} completed by user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error completing task {task_id} by user {user_id}: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def _create_recurring_task(self, original_task: Task):
        """Create the next occurrence of a recurring task"""
        if not original_task.due_date:
            return
            
        # Calculate next due date
        tz = pytz.timezone(original_task.timezone)
        current_due = datetime.fromtimestamp(original_task.due_date, tz)
        
        if original_task.recurrence_type == RecurrenceType.DAILY:
            next_due = current_due + timedelta(days=original_task.recurrence_interval)
        elif original_task.recurrence_type == RecurrenceType.WEEKLY:
            next_due = current_due + timedelta(weeks=original_task.recurrence_interval)
        elif original_task.recurrence_type == RecurrenceType.MONTHLY:
            # Handle month boundaries carefully
            if current_due.month == 12:
                next_due = current_due.replace(year=current_due.year + 1, month=1)
            else:
                next_due = current_due.replace(month=current_due.month + original_task.recurrence_interval)
        else:
            return
            
        # Check if we've passed the end date
        if (original_task.recurrence_end_date and 
            next_due.timestamp() > original_task.recurrence_end_date):
            return
            
        # Create new task
        new_task = Task(
            title=original_task.title,
            description=original_task.description,
            due_date=next_due.timestamp(),
            priority=original_task.priority,
            status=TaskStatus.TODO,
            category=original_task.category,
            created_by=original_task.created_by,
            channel_id=original_task.channel_id,
            timezone=original_task.timezone,
            recurrence_type=original_task.recurrence_type,
            recurrence_interval=original_task.recurrence_interval,
            recurrence_end_date=original_task.recurrence_end_date,
            notify_24h=original_task.notify_24h,
            notify_6h=original_task.notify_6h,
            notify_1h=original_task.notify_1h,
            notify_overdue=original_task.notify_overdue,
            overdue_escalation_hours=original_task.overdue_escalation_hours,
            parent_task_id=original_task.parent_task_id
        )
        
        await self.create_task(new_task)
        logger.info(f"Created recurring task from {original_task.id}, next due: {next_due}")
        
    async def get_overdue_tasks(self) -> List[Task]:
        """Get all overdue tasks"""
        current_time = time.time()
        conn = await self._get_connection()
        
        try:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute('''
                SELECT * FROM tasks 
                WHERE due_date < ? AND status NOT IN ('COMPLETED', 'CANCELLED')
                ORDER BY due_date ASC
            ''', (current_time,))
            rows = await cursor.fetchall()
            
            tasks = [self._task_from_row(row) for row in rows]
            return tasks
            
        except Exception as e:
            logger.error(f"Error getting overdue tasks: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def get_upcoming_tasks(self, hours_ahead: int = 24) -> List[Task]:
        """Get tasks due within the next N hours"""
        current_time = time.time()
        future_time = current_time + (hours_ahead * 3600)
        
        conn = await self._get_connection()
        try:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute('''
                SELECT * FROM tasks 
                WHERE due_date BETWEEN ? AND ? AND status NOT IN ('COMPLETED', 'CANCELLED')
                ORDER BY due_date ASC
            ''', (current_time, future_time))
            rows = await cursor.fetchall()
            
            tasks = [self._task_from_row(row) for row in rows]
            return tasks
            
        except Exception as e:
            logger.error(f"Error getting upcoming tasks: {e}")
            raise
        finally:
            await self._return_connection(conn)
            
    async def cleanup(self):
        """Cleanup resources"""
        if self._initialized:
            try:
                # Close all connections in the pool
                while not self.connection_pool.empty():
                    try:
                        conn = self.connection_pool.get_nowait()
                        await conn.close()
                    except:
                        pass
                        
                self._initialized = False
                logger.info("TaskManager cleanup completed")
            except Exception as e:
                logger.error(f"Error during TaskManager cleanup: {e}")
                self._initialized = False