# Reminder Tool for LLMs

## Overview

The Discord bot now includes a `manage_reminders` tool that allows LLMs to create, list, cancel, and manage reminders on behalf of users during conversations. This provides a seamless way for users to set reminders through natural conversation with the AI.

## Tool Name
`manage_reminders`

## Capabilities

### 1. Set Reminders (`action: "set"`)
Create new reminders with natural language time parsing.

**Required Parameters:**
- `action`: "set"
- `user_id`: Discord user ID (automatically injected for security)
- `reminder_text`: What to remind about
- `time_str`: When to remind (natural language)

**Natural Language Time Examples:**
- "tomorrow at 3pm"
- "in 2 hours"  
- "next Friday at 9am"
- "tonight"
- "noon"
- "midnight"
- "in 30 minutes"
- "Monday at 2pm"
- "December 25th at noon"

### 2. List Reminders (`action: "list"`)
Show all upcoming reminders for the user.

**Required Parameters:**
- `action`: "list"
- `user_id`: Discord user ID (automatically injected)

### 3. Cancel Reminders (`action: "cancel"`)
Cancel a specific reminder by timestamp.

**Required Parameters:**
- `action`: "cancel"
- `user_id`: Discord user ID (automatically injected)
- `reminder_timestamp`: Unix timestamp of the reminder to cancel

### 4. Get Next Reminder (`action: "next"`)
Get details of the next upcoming reminder.

**Required Parameters:**
- `action`: "next"
- `user_id`: Discord user ID (automatically injected)

## Security Features

- **User Isolation**: Users can only manage their own reminders
- **Automatic User ID Injection**: The system automatically sets the user_id to the requesting user
- **Data Persistence**: Reminders are stored in `data/reminders.json` and shared with the Discord slash commands

## Timezone Support

- Uses the user's configured timezone from Discord slash commands
- Defaults to "Pacific/Auckland" if no timezone is set
- Displays times in the user's local timezone
- Stores reminders in UTC internally

## Limitations

- Maximum 25 reminders per user
- Cannot set reminders in the past
- Cannot set duplicate reminders at the exact same time

## Integration with Discord Commands

The tool shares data with the existing `/reminder` slash commands, so:
- Reminders set via tool calls appear in `/reminder list`
- Reminders set via slash commands appear in tool list actions
- Users can cancel reminders created either way using either method

## Example Usage in LLM Conversations

**User:** "Remind me to call mom tomorrow at 3pm"
**LLM:** *Uses manage_reminders tool with action="set", reminder_text="call mom", time_str="tomorrow at 3pm"*
**Response:** "I've set a reminder for you to call mom tomorrow at 3:00 PM (in 18 hours)."

**User:** "What reminders do I have?"
**LLM:** *Uses manage_reminders tool with action="list"*
**Response:** "You have 2 upcoming reminders: 1. Call mom - Saturday, June 14 at 03:00 PM (in 18 hours), 2. Team meeting - Monday, June 16 at 09:00 AM (in 3 days)"

**User:** "Cancel the mom reminder"
**LLM:** *Uses manage_reminders tool with action="cancel" and the appropriate timestamp*
**Response:** "I've cancelled your reminder to call mom."

## Implementation Details

- **File:** `/cogs/tools/reminder_tool.py`
- **Data Storage:** `data/reminders.json` and `data/user_timezones.json`
- **Registration:** Automatically registered in `ToolCalling` cog
- **Error Handling:** Comprehensive validation and user-friendly error messages
- **Performance**: Efficient file-based storage with lazy loading