import asyncio
import time
import logging
from typing import Dict, Set, Optional, List
from datetime import datetime, timedelta
import pytz
import discord
from discord.ext import commands

from .task_manager import TaskManager, Task, TaskStatus, TaskNotification
from .background_task_manager import BackgroundTaskManager, TaskPriority
from utils.embed_utils import create_error_embed, send_embed

logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self, bot: commands.Bot, task_manager: TaskManager, background_task_manager: BackgroundTaskManager):
        self.bot = bot
        self.task_manager = task_manager
        self.background_task_manager = background_task_manager
        self.running = False
        self.scheduler_task = None
        self.notification_task = None
        self.cleanup_task = None
        
        # Track users who have DM failures to avoid spam
        self.dm_failure_users: Set[int] = set()
        
        # Last notification times to prevent spam
        self.last_notifications: Dict[str, float] = {}
        
        # Notification intervals in seconds
        self.notification_intervals = {
            "24h": 24 * 3600,
            "6h": 6 * 3600, 
            "1h": 3600,
            "overdue": 0  # Immediate when overdue
        }
        
    async def start(self):
        """Start the task scheduler"""
        if self.running:
            return
            
        self.running = True
        
        # Start background tasks
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        self.notification_task = asyncio.create_task(self._notification_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("TaskScheduler started successfully")
        
    async def stop(self):
        """Stop the task scheduler"""
        if not self.running:
            return
            
        self.running = False
        
        # Cancel background tasks
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
                
        if self.notification_task:
            self.notification_task.cancel()
            try:
                await self.notification_task
            except asyncio.CancelledError:
                pass
                
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
                
        logger.info("TaskScheduler stopped")
        
    async def _scheduler_loop(self):
        """Main scheduler loop for checking due tasks and creating notifications"""
        while self.running:
            try:
                await self._schedule_notifications()
                await self._update_overdue_tasks()
                
                # Sleep for 5 minutes before next check
                await asyncio.sleep(300)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
                
    async def _notification_loop(self):
        """Loop for sending scheduled notifications"""
        while self.running:
            try:
                await self._send_due_notifications()
                
                # Sleep for 1 minute before checking again
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in notification loop: {e}")
                await asyncio.sleep(60)
                
    async def _cleanup_loop(self):
        """Cleanup old notifications and reset DM failures"""
        while self.running:
            try:
                await self._cleanup_old_notifications()
                
                # Reset DM failures every hour
                self.dm_failure_users.clear()
                
                # Sleep for 1 hour
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(300)
                
    async def _schedule_notifications(self):
        """Schedule notifications for upcoming tasks"""
        try:
            # Get upcoming tasks within next 25 hours (to catch 24h notifications)
            upcoming_tasks = await self.task_manager.get_upcoming_tasks(25)
            
            for task in upcoming_tasks:
                if not task.due_date:
                    continue
                    
                await self._schedule_task_notifications(task)
                
        except Exception as e:
            logger.error(f"Error scheduling notifications: {e}")
            
    async def _schedule_task_notifications(self, task: Task):
        """Schedule all notification types for a task"""
        if not task.due_date:
            return
            
        current_time = time.time()
        
        # Schedule 24h notification
        if task.notify_24h:
            notify_time = task.due_date - self.notification_intervals["24h"]
            if notify_time > current_time:
                await self._create_notification(task.id, "24h", notify_time)
                
        # Schedule 6h notification
        if task.notify_6h:
            notify_time = task.due_date - self.notification_intervals["6h"]
            if notify_time > current_time:
                await self._create_notification(task.id, "6h", notify_time)
                
        # Schedule 1h notification
        if task.notify_1h:
            notify_time = task.due_date - self.notification_intervals["1h"]
            if notify_time > current_time:
                await self._create_notification(task.id, "1h", notify_time)
                
    async def _create_notification(self, task_id: int, notification_type: str, scheduled_time: float):
        """Create a notification record in the database"""
        try:
            conn = await self.task_manager._get_connection()
            try:
                # Check if notification already exists
                cursor = await conn.execute('''
                    SELECT id FROM task_notifications 
                    WHERE task_id = ? AND notification_type = ? AND scheduled_time = ?
                ''', (task_id, notification_type, scheduled_time))
                
                existing = await cursor.fetchone()
                if existing:
                    return  # Notification already scheduled
                    
                # Create new notification
                await conn.execute('''
                    INSERT INTO task_notifications (task_id, notification_type, scheduled_time)
                    VALUES (?, ?, ?)
                ''', (task_id, notification_type, scheduled_time))
                
                await conn.commit()
                logger.debug(f"Scheduled {notification_type} notification for task {task_id}")
                
            finally:
                await self.task_manager._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error creating notification for task {task_id}: {e}")
            
    async def _send_due_notifications(self):
        """Send notifications that are due"""
        try:
            current_time = time.time()
            
            conn = await self.task_manager._get_connection()
            try:
                conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                
                # Get due notifications
                cursor = await conn.execute('''
                    SELECT tn.*, t.* FROM task_notifications tn
                    JOIN tasks t ON tn.task_id = t.id
                    WHERE tn.scheduled_time <= ? AND tn.sent = 0
                    AND t.status NOT IN ('COMPLETED', 'CANCELLED')
                    ORDER BY tn.scheduled_time ASC
                    LIMIT 50
                ''', (current_time,))
                
                notifications = await cursor.fetchall()
                
                for notification in notifications:
                    await self._send_notification(notification)
                    
            finally:
                await self.task_manager._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error sending due notifications: {e}")
            
    async def _send_notification(self, notification: dict):
        """Send a single notification"""
        try:
            task_id = notification['task_id']
            notification_id = notification['id']
            notification_type = notification['notification_type']
            
            # Get the task
            task = await self.task_manager.get_task(task_id)
            if not task or task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
                # Mark notification as sent to prevent retries
                await self._mark_notification_sent(notification_id)
                return
                
            # Create notification embed
            embed = await self._create_notification_embed(task, notification_type)
            
            # Get the channel where the task was created
            channel = None
            if task.channel_id:
                try:
                    channel = self.bot.get_channel(task.channel_id)
                    if not channel:
                        channel = await self.bot.fetch_channel(task.channel_id)
                except:
                    channel = None
                    
            # Try to send in the original channel first
            sent = False
            if channel:
                try:
                    mention = f"<@{task.created_by}>"
                    await channel.send(content=mention, embed=embed)
                    sent = True
                    logger.info(f"Sent {notification_type} notification for task {task_id} to channel {channel.id}")
                except discord.Forbidden:
                    logger.warning(f"No permission to send notification in channel {channel.id}")
                except Exception as e:
                    logger.error(f"Error sending notification to channel {channel.id}: {e}")
                    
            # Fallback to DM if channel failed and user hasn't failed DMs recently
            if not sent and task.created_by not in self.dm_failure_users:
                try:
                    user = self.bot.get_user(task.created_by)
                    if not user:
                        user = await self.bot.fetch_user(task.created_by)
                        
                    if user:
                        await user.send(embed=embed)
                        sent = True
                        logger.info(f"Sent {notification_type} notification for task {task_id} via DM to user {task.created_by}")
                        
                except discord.Forbidden:
                    self.dm_failure_users.add(task.created_by)
                    logger.warning(f"Cannot send DM to user {task.created_by}")
                except Exception as e:
                    logger.error(f"Error sending DM notification to user {task.created_by}: {e}")
                    
            # Mark notification as sent
            await self._mark_notification_sent(notification_id)
            
            # Rate limiting to prevent spam
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error sending notification {notification.get('id')}: {e}")
            
    async def _create_notification_embed(self, task: Task, notification_type: str) -> discord.Embed:
        """Create a notification embed for a task"""
        from .task_manager import TaskPriorityLevel
        
        # Priority emoji
        priority_emoji = {
            TaskPriorityLevel.LOW: "🟢",
            TaskPriorityLevel.NORMAL: "🟡",
            TaskPriorityLevel.HIGH: "🟠",
            TaskPriorityLevel.CRITICAL: "🔴"
        }.get(task.priority, "🟡")
        
        # Create embed based on notification type
        if notification_type == "24h":
            title = "📅 Task Due in 24 Hours"
            color = 0x3498db  # Blue
        elif notification_type == "6h":
            title = "⏰ Task Due in 6 Hours"
            color = 0xff9500  # Orange
        elif notification_type == "1h":
            title = "⚠️ Task Due in 1 Hour"
            color = 0xff6b35  # Red-orange
        elif notification_type == "overdue":
            title = "🚨 Task is Overdue!"
            color = 0xdc3545  # Red
        else:
            title = "📋 Task Reminder"
            color = 0x3498db
            
        embed = discord.Embed(
            title=title,
            description=f"{priority_emoji} **{task.title}**",
            color=color
        )
        
        if task.description:
            embed.add_field(
                name="📝 Description",
                value=task.description[:200] + ("..." if len(task.description) > 200 else ""),
                inline=False
            )
            
        # Due date info
        if task.due_date:
            try:
                tz = pytz.timezone(task.timezone)
                due_dt = datetime.fromtimestamp(task.due_date, tz)
                
                if notification_type == "overdue":
                    now = datetime.now(tz)
                    overdue_time = now - due_dt
                    if overdue_time.days > 0:
                        overdue_text = f"{overdue_time.days} days overdue"
                    else:
                        hours = int(overdue_time.total_seconds() // 3600)
                        overdue_text = f"{hours} hours overdue"
                    embed.add_field(
                        name="⏰ Was Due",
                        value=f"{due_dt.strftime('%A, %B %d at %I:%M %p')}\n({overdue_text})",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="⏰ Due Date",
                        value=due_dt.strftime("%A, %B %d at %I:%M %p"),
                        inline=False
                    )
            except Exception as e:
                logger.error(f"Error formatting due date: {e}")
                
        embed.add_field(name="📂 Category", value=task.category, inline=True)
        embed.add_field(name="🆔 Task ID", value=str(task.id), inline=True)
        
        # Add action hint
        embed.set_footer(text="Use /task complete <task_id> to mark as completed")
        
        return embed
        
    async def _mark_notification_sent(self, notification_id: int):
        """Mark a notification as sent"""
        try:
            conn = await self.task_manager._get_connection()
            try:
                await conn.execute('''
                    UPDATE task_notifications 
                    SET sent = 1, sent_at = ?
                    WHERE id = ?
                ''', (time.time(), notification_id))
                await conn.commit()
            finally:
                await self.task_manager._return_connection(conn)
        except Exception as e:
            logger.error(f"Error marking notification {notification_id} as sent: {e}")
            
    async def _update_overdue_tasks(self):
        """Update task status for overdue tasks and schedule overdue notifications"""
        try:
            overdue_tasks = await self.task_manager.get_overdue_tasks()
            current_time = time.time()
            
            for task in overdue_tasks:
                # Update status to overdue if not already
                if task.status != TaskStatus.OVERDUE:
                    task.status = TaskStatus.OVERDUE
                    await self.task_manager.update_task(task)
                    
                # Schedule overdue notification if enabled
                if task.notify_overdue:
                    # Check if we need to send another overdue notification
                    notification_key = f"overdue_{task.id}"
                    last_sent = self.last_notifications.get(notification_key, 0)
                    
                    # Send overdue notifications based on escalation hours
                    escalation_interval = task.overdue_escalation_hours * 3600
                    if current_time - last_sent >= escalation_interval:
                        await self._create_notification(task.id, "overdue", current_time)
                        self.last_notifications[notification_key] = current_time
                        
        except Exception as e:
            logger.error(f"Error updating overdue tasks: {e}")
            
    async def _cleanup_old_notifications(self):
        """Clean up old sent notifications"""
        try:
            # Remove notifications older than 30 days
            cutoff_time = time.time() - (30 * 24 * 3600)
            
            conn = await self.task_manager._get_connection()
            try:
                cursor = await conn.execute('''
                    DELETE FROM task_notifications 
                    WHERE sent = 1 AND sent_at < ?
                ''', (cutoff_time,))
                
                deleted_count = cursor.rowcount
                await conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old notifications")
                    
            finally:
                await self.task_manager._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error cleaning up old notifications: {e}")
            
    async def schedule_immediate_notification(self, task_id: int, notification_type: str):
        """Schedule an immediate notification for a task"""
        current_time = time.time()
        await self._create_notification(task_id, notification_type, current_time)
        
    async def cancel_task_notifications(self, task_id: int):
        """Cancel all pending notifications for a task"""
        try:
            conn = await self.task_manager._get_connection()
            try:
                cursor = await conn.execute('''
                    DELETE FROM task_notifications 
                    WHERE task_id = ? AND sent = 0
                ''', (task_id,))
                
                deleted_count = cursor.rowcount
                await conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cancelled {deleted_count} notifications for task {task_id}")
                    
            finally:
                await self.task_manager._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error cancelling notifications for task {task_id}: {e}")
            
    async def reschedule_task_notifications(self, task: Task):
        """Reschedule notifications for a task (e.g., when due date changes)"""
        # Cancel existing notifications
        await self.cancel_task_notifications(task.id)
        
        # Schedule new notifications
        await self._schedule_task_notifications(task)