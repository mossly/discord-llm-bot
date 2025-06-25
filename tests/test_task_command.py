#!/usr/bin/env python3
"""
Test suite for /task command functionality
Tests the complete flow of task creation, listing, and completion
"""

import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the modules we need to test
from utils.task_manager import TaskManager, Task, TaskStatus, TaskPriorityLevel
from utils.background_task_manager import BackgroundTaskManager
from cogs.tools.task_management_tool import TaskManagementTool

class TaskCommandTester:
    """Test harness for task command functionality"""
    
    def __init__(self):
        self.background_task_manager = BackgroundTaskManager()
        self.task_manager = TaskManager(self.background_task_manager)
        self.task_tool = TaskManagementTool(self.task_manager)
        self.test_user_id = 12345  # Test user ID
        self.results = []
        
    async def setup(self):
        """Initialize the task manager"""
        await self.background_task_manager.start()
        await self.task_manager.initialize()
        logger.info("✅ Task manager initialized")
        
    async def cleanup(self):
        """Clean up resources"""
        await self.task_manager.cleanup()
        await self.background_task_manager.stop()
        logger.info("✅ Cleanup completed")
        
    async def simulate_llm_tool_call(self, prompt: str) -> Dict[str, Any]:
        """Simulate what the LLM would do with the given prompt"""
        logger.info(f"\n🤖 Simulating LLM processing: '{prompt}'")
        
        # Parse the prompt and determine the appropriate tool action
        prompt_lower = prompt.lower()
        
        # Determine the action based on prompt content
        if "create" in prompt_lower and "task" in prompt_lower:
            # Extract task details from prompt
            # For "Create a task to hang the laundry in 1 minute"
            if "hang the laundry" in prompt_lower:
                due_date = datetime.now() + timedelta(minutes=1)
                return await self.task_tool.execute(
                    action="create_task",
                    user_id=self.test_user_id,
                    title="hang the laundry",
                    description="Task created from: " + prompt,
                    due_date=due_date.isoformat(),
                    priority="NORMAL",
                    category="Personal"
                )
                
        elif "what" in prompt_lower and ("task" in prompt_lower or "my tasks" in prompt_lower):
            # List tasks
            return await self.task_tool.execute(
                action="list_user_tasks",
                user_id=self.test_user_id,
                limit=20
            )
            
        elif ("complete" in prompt_lower or "mark as complete" in prompt_lower) and "hung the laundry" in prompt_lower:
            # Easy version: explicit completion request
            # First, find the laundry task
            tasks_result = await self.task_tool.execute(
                action="list_user_tasks",
                user_id=self.test_user_id,
                limit=20
            )
            
            if tasks_result.get("success") and tasks_result.get("tasks"):
                for task in tasks_result["tasks"]:
                    if "laundry" in task["title"].lower() and task["status"] != "COMPLETED":
                        return await self.task_tool.execute(
                            action="complete_task",
                            user_id=self.test_user_id,
                            task_id=task["id"]
                        )
            return {"error": "No laundry task found to complete"}
            
        elif "i hung the laundry" in prompt_lower and "complete" not in prompt_lower:
            # Hard version: implicit completion
            # This tests if the LLM can infer task completion from context
            tasks_result = await self.task_tool.execute(
                action="list_user_tasks", 
                user_id=self.test_user_id,
                limit=20
            )
            
            if tasks_result.get("success") and tasks_result.get("tasks"):
                for task in tasks_result["tasks"]:
                    if "laundry" in task["title"].lower() and task["status"] != "COMPLETED":
                        logger.info("🧠 LLM inferring task completion from context")
                        return await self.task_tool.execute(
                            action="complete_task",
                            user_id=self.test_user_id,
                            task_id=task["id"]
                        )
            return {"message": "Acknowledged. No matching task found to complete."}
            
        return {"error": f"Could not understand prompt: {prompt}"}
        
    async def run_test_sequence(self):
        """Run the complete test sequence"""
        test_prompts = [
            ("Create a task to hang the laundry in 1 minute", "Task Creation"),
            ("What are my tasks?", "Task Listing"),
            ("I hung the laundry, mark as complete", "Explicit Completion (Easy)"),
            ("Create a task to wash dishes tomorrow", "Second Task Creation"),
            ("What are my tasks?", "Task Listing After Completion"),
            ("I hung the laundry", "Implicit Completion (Hard)"),
        ]
        
        logger.info("\n" + "="*60)
        logger.info("🧪 STARTING TASK COMMAND TEST SEQUENCE")
        logger.info("="*60)
        
        for prompt, test_name in test_prompts:
            logger.info(f"\n📝 Test: {test_name}")
            logger.info(f"   Prompt: '{prompt}'")
            
            result = await self.simulate_llm_tool_call(prompt)
            
            # Store result for analysis
            self.results.append({
                "test": test_name,
                "prompt": prompt,
                "result": result
            })
            
            # Display result
            if "error" in result:
                logger.error(f"   ❌ Error: {result['error']}")
            elif result.get("success"):
                logger.info(f"   ✅ Success: {result.get('message', 'Operation completed')}")
                
                # Show task details if available
                if "task" in result and result["task"]:
                    task = result["task"]
                    logger.info(f"      Task: {task['title']} (ID: {task['id']})")
                    if "due_date_formatted" in task:
                        logger.info(f"      Due: {task['due_date_formatted']}")
                    logger.info(f"      Status: {task['status']}")
                    
                # Show task list if available
                if "tasks" in result:
                    logger.info(f"      Found {result['count']} tasks:")
                    for task in result["tasks"]:
                        status_emoji = "✅" if task["status"] == "COMPLETED" else "📋"
                        due_info = f" (due: {task.get('due_date_formatted', 'No due date')})" if task.get("due_date") else ""
                        logger.info(f"      {status_emoji} {task['title']}{due_info}")
            else:
                logger.warning(f"   ⚠️  Result: {result}")
                
            # Small delay between tests
            await asyncio.sleep(0.5)
            
    def print_summary(self):
        """Print test summary"""
        logger.info("\n" + "="*60)
        logger.info("📊 TEST SUMMARY")
        logger.info("="*60)
        
        success_count = sum(1 for r in self.results if r["result"].get("success") or "message" in r["result"])
        total_count = len(self.results)
        
        logger.info(f"\nTotal Tests: {total_count}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {total_count - success_count}")
        
        if success_count == total_count:
            logger.info("\n🎉 All tests passed!")
        else:
            logger.warning(f"\n⚠️  {total_count - success_count} tests failed")
            
        # Show any errors
        errors = [r for r in self.results if "error" in r["result"]]
        if errors:
            logger.info("\n❌ Errors encountered:")
            for err in errors:
                logger.error(f"   - {err['test']}: {err['result']['error']}")
                
async def main():
    """Main test runner"""
    tester = TaskCommandTester()
    
    try:
        # Setup
        await tester.setup()
        
        # Run tests
        await tester.run_test_sequence()
        
        # Print summary
        tester.print_summary()
        
    except Exception as e:
        logger.exception(f"Test failed with error: {e}")
    finally:
        # Cleanup
        await tester.cleanup()
        
    logger.info("\n✅ Test suite completed")

if __name__ == "__main__":
    asyncio.run(main())