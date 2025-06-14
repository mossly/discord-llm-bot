"""
Background task manager for separating I/O and compute-heavy operations
Provides better performance isolation and monitoring
"""

import asyncio
import logging
import time
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import weakref
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class BackgroundTask:
    """Background task definition"""
    id: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    retries: int = 0
    
    def __post_init__(self):
        if self.timeout is None:
            # Default timeouts based on priority
            if self.priority == TaskPriority.CRITICAL:
                self.timeout = 30.0
            elif self.priority == TaskPriority.HIGH:
                self.timeout = 60.0
            else:
                self.timeout = 300.0  # 5 minutes


@dataclass
class TaskResult:
    """Task execution result"""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    execution_time: float = 0.0
    completed_at: float = field(default_factory=time.time)


class BackgroundTaskManager:
    """Manages background tasks with priority queues and thread pools"""
    
    def __init__(self, max_workers: int = 4, max_queue_size: int = 1000):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        
        # Priority queues for different types of tasks
        self.task_queues: Dict[TaskPriority, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=max_queue_size)
            for priority in TaskPriority
        }
        
        # Thread pools for CPU-intensive and blocking I/O tasks
        self.cpu_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="bg-cpu")
        self.io_executor = ThreadPoolExecutor(max_workers=max_workers * 2, thread_name_prefix="bg-io")
        
        # Task tracking
        self.active_tasks: Dict[str, BackgroundTask] = {}
        self.task_history: List[TaskResult] = []
        self.max_history = 1000
        
        # Performance metrics
        self.metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "average_execution_time": 0.0,
            "queue_sizes": {},
        }
        
        # Worker tasks
        self.worker_tasks: List[asyncio.Task] = []
        self.running = False
        
        # Weak references to avoid circular dependencies
        self._callbacks: Dict[str, List] = {}
    
    async def start(self):
        """Start the background task manager"""
        if self.running:
            logger.warning("BackgroundTaskManager is already running")
            return
        
        self.running = True
        
        # Start worker tasks for each priority level
        for priority in TaskPriority:
            for i in range(self.max_workers):
                task = asyncio.create_task(
                    self._worker(priority, f"worker-{priority.name.lower()}-{i}")
                )
                self.worker_tasks.append(task)
        
        # Start metrics collection task
        metrics_task = asyncio.create_task(self._metrics_collector())
        self.worker_tasks.append(metrics_task)
        
        logger.info(f"Started BackgroundTaskManager with {len(self.worker_tasks)} workers")
    
    async def stop(self):
        """Stop the background task manager"""
        if not self.running:
            return
        
        self.running = False
        
        # Cancel all worker tasks
        for task in self.worker_tasks:
            task.cancel()
        
        # Wait for tasks to complete with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.worker_tasks, return_exceptions=True),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for background tasks to complete")
        
        # Shutdown thread pools
        self.cpu_executor.shutdown(wait=True)
        self.io_executor.shutdown(wait=True)
        
        self.worker_tasks.clear()
        logger.info("BackgroundTaskManager stopped")
    
    async def submit_task(self, task: BackgroundTask) -> bool:
        """Submit a task for background execution"""
        if not self.running:
            logger.error("BackgroundTaskManager is not running")
            return False
        
        queue = self.task_queues[task.priority]
        
        try:
            # Check if queue is full
            if queue.full():
                logger.warning(f"Task queue for priority {task.priority.name} is full")
                return False
            
            await queue.put(task)
            self.active_tasks[task.id] = task
            self.metrics["total_tasks"] += 1
            
            logger.debug(f"Submitted task {task.id} with priority {task.priority.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to submit task {task.id}: {e}")
            return False
    
    async def submit_function(self, func: Callable, *args, task_id: str = None, 
                            priority: TaskPriority = TaskPriority.NORMAL, **kwargs) -> bool:
        """Submit a function for background execution"""
        if task_id is None:
            task_id = f"{func.__name__}_{int(time.time() * 1000)}"
        
        task = BackgroundTask(
            id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority
        )
        
        return await self.submit_task(task)
    
    async def submit_cpu_intensive(self, func: Callable, *args, task_id: str = None, **kwargs) -> bool:
        """Submit a CPU-intensive task"""
        return await self.submit_function(
            func, *args, task_id=task_id, priority=TaskPriority.HIGH, **kwargs
        )
    
    async def submit_io_task(self, func: Callable, *args, task_id: str = None, **kwargs) -> bool:
        """Submit an I/O-bound task"""
        return await self.submit_function(
            func, *args, task_id=task_id, priority=TaskPriority.NORMAL, **kwargs
        )
    
    def add_completion_callback(self, task_id: str, callback: Callable[[TaskResult], None]):
        """Add a callback for task completion"""
        if task_id not in self._callbacks:
            self._callbacks[task_id] = []
        
        # Store weak reference to avoid memory leaks
        if hasattr(callback, '__self__'):
            # Method callback
            self._callbacks[task_id].append(weakref.WeakMethod(callback))
        else:
            # Function callback
            self._callbacks[task_id].append(weakref.ref(callback))
    
    async def _worker(self, priority: TaskPriority, worker_name: str):
        """Worker coroutine for processing tasks"""
        queue = self.task_queues[priority]
        
        logger.debug(f"Started worker {worker_name} for priority {priority.name}")
        
        while self.running:
            try:
                # Get task from queue with timeout
                try:
                    task = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                logger.debug(f"Worker {worker_name} processing task {task.id}")
                
                # Execute the task
                result = await self._execute_task(task)
                
                # Store result and clean up
                self._store_result(result)
                self.active_tasks.pop(task.id, None)
                
                # Call completion callbacks
                await self._call_callbacks(task.id, result)
                
                # Mark queue task as done
                queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in worker {worker_name}: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Prevent tight error loops
        
        logger.debug(f"Worker {worker_name} stopped")
    
    async def _execute_task(self, task: BackgroundTask) -> TaskResult:
        """Execute a single task"""
        start_time = time.time()
        
        try:
            # Determine which executor to use based on function type
            if hasattr(task.func, '_cpu_intensive'):
                executor = self.cpu_executor
            elif hasattr(task.func, '_io_bound'):
                executor = self.io_executor
            else:
                # Default to I/O executor for most async operations
                executor = self.io_executor
            
            # Execute with timeout
            if asyncio.iscoroutinefunction(task.func):
                # Async function
                result = await asyncio.wait_for(
                    task.func(*task.args, **task.kwargs),
                    timeout=task.timeout
                )
            else:
                # Sync function - run in executor
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        executor,
                        lambda: task.func(*task.args, **task.kwargs)
                    ),
                    timeout=task.timeout
                )
            
            execution_time = time.time() - start_time
            
            self.metrics["successful_tasks"] += 1
            self._update_average_execution_time(execution_time)
            
            return TaskResult(
                task_id=task.id,
                success=True,
                result=result,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            # Check if we should retry
            if task.retries < task.max_retries and not isinstance(e, asyncio.TimeoutError):
                task.retries += 1
                logger.warning(f"Task {task.id} failed, retry {task.retries}/{task.max_retries}: {e}")
                
                # Re-queue with delay
                await asyncio.sleep(task.retry_delay * task.retries)
                await self.task_queues[task.priority].put(task)
                
                # Return a retry result
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error=e,
                    execution_time=execution_time
                )
            
            self.metrics["failed_tasks"] += 1
            
            logger.error(f"Task {task.id} failed after {task.retries} retries: {e}")
            
            return TaskResult(
                task_id=task.id,
                success=False,
                error=e,
                execution_time=execution_time
            )
    
    def _store_result(self, result: TaskResult):
        """Store task result in history"""
        self.task_history.append(result)
        
        # Limit history size
        if len(self.task_history) > self.max_history:
            self.task_history = self.task_history[-self.max_history:]
    
    async def _call_callbacks(self, task_id: str, result: TaskResult):
        """Call completion callbacks for a task"""
        if task_id not in self._callbacks:
            return
        
        callbacks = self._callbacks[task_id]
        valid_callbacks = []
        
        for callback_ref in callbacks:
            callback = callback_ref()
            if callback is not None:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                    valid_callbacks.append(callback_ref)
                except Exception as e:
                    logger.error(f"Error in completion callback for task {task_id}: {e}")
        
        # Update callbacks list with only valid references
        if valid_callbacks:
            self._callbacks[task_id] = valid_callbacks
        else:
            del self._callbacks[task_id]
    
    def _update_average_execution_time(self, execution_time: float):
        """Update average execution time metric"""
        current_avg = self.metrics["average_execution_time"]
        successful_tasks = self.metrics["successful_tasks"]
        
        if successful_tasks == 1:
            self.metrics["average_execution_time"] = execution_time
        else:
            # Exponential moving average
            alpha = 0.1  # Smoothing factor
            self.metrics["average_execution_time"] = (
                alpha * execution_time + (1 - alpha) * current_avg
            )
    
    async def _metrics_collector(self):
        """Collect and log metrics periodically"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Collect metrics every minute
                
                # Update queue sizes
                for priority, queue in self.task_queues.items():
                    self.metrics["queue_sizes"][priority.name] = queue.qsize()
                
                # Log metrics
                active_count = len(self.active_tasks)
                total_tasks = self.metrics["total_tasks"]
                success_rate = (
                    self.metrics["successful_tasks"] / total_tasks * 100
                    if total_tasks > 0 else 0
                )
                avg_time = self.metrics["average_execution_time"]
                
                logger.info(
                    f"Background task metrics: "
                    f"Active: {active_count}, "
                    f"Total: {total_tasks}, "
                    f"Success rate: {success_rate:.1f}%, "
                    f"Avg execution time: {avg_time:.2f}s"
                )
                
            except Exception as e:
                logger.error(f"Error in metrics collector: {e}")
    
    def get_metrics(self) -> dict:
        """Get current metrics"""
        return self.metrics.copy()
    
    def get_active_tasks(self) -> List[str]:
        """Get list of active task IDs"""
        return list(self.active_tasks.keys())
    
    def get_task_history(self, limit: int = 100) -> List[TaskResult]:
        """Get recent task history"""
        return self.task_history[-limit:]


# Decorators for marking function types
def cpu_intensive(func):
    """Mark a function as CPU-intensive"""
    func._cpu_intensive = True
    return func


def io_bound(func):
    """Mark a function as I/O-bound"""
    func._io_bound = True
    return func


# Global instance
background_task_manager = BackgroundTaskManager()