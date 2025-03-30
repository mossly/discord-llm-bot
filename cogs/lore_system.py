import os
import json
import discord
import asyncio
import logging
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Optional, Literal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class LoreEntry:
    def __init__(self, content: str, author_id: int, created_at: Optional[str] = None):
        self.content = content
        self.author_id = author_id
        self.created_at = created_at or datetime.utcnow().isoformat()
    
    def to_dict(self):
        return {
            "content": self.content,
            "author_id": self.author_id,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            content=data.get("content", ""),
            author_id=data.get("author_id", 0),
            created_at=data.get("created_at")
        )

class Lorebook:
    def __init__(
        self, 
        name: str, 
        owner_id: int, 
        description: str = "", 
        is_public: bool = False, 
        entries: Optional[List[LoreEntry]] = None,
        created_at: Optional[str] = None
    ):
        self.name = name
        self.owner_id = owner_id
        self.description = description
        self.is_public = is_public
        self.entries = entries or []
        self.created_at = created_at or datetime.utcnow().isoformat()
    
    def to_dict(self):
        return {
            "name": self.name,
            "owner_id": self.owner_id,
            "description": self.description,
            "is_public": self.is_public,
            "entries": [entry.to_dict() for entry in self.entries],
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data):
        lorebook = cls(
            name=data.get("name", "Unnamed Lorebook"),
            owner_id=data.get("owner_id", 0),
            description=data.get("description", ""),
            is_public=data.get("is_public", False),
            created_at=data.get("created_at")
        )
        lorebook.entries = [LoreEntry.from_dict(entry_data) for entry_data in data.get("entries", [])]
        return lorebook
    
    def add_entry(self, content: str, author_id: int) -> LoreEntry:
        entry = LoreEntry(content, author_id)
        self.entries.append(entry)
        return entry
    
    def can_edit(self, user_id: int) -> bool:
        """Checks if a user can edit this lorebook"""
        return user_id == self.owner_id or self.is_public
    
    def get_formatted_content(self) -> str:
        """Returns the formatted content of all entries for use in AI context"""
        result = f"## {self.name}\n"
        if self.description:
            result += f"{self.description}\n\n"
        
        for i, entry in enumerate(self.entries, 1):
            result += f"Entry {i}: {entry.content}\n\n"
        
        return result

class LoreSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lorebooks: Dict[str, Lorebook] = {}
        self.data_file = os.path.join("/data", "lorebooks.json")
        self.polls_channel_id = int(os.getenv("POLLS_CHANNEL_ID", "1355725206811054212"))
        self.pending_entries = {}  # {message_id: (lorebook_name, content, author_id)}
        self.load_lorebooks()
    
    async def lorebook_autocomplete(
        self, 
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        user_lorebooks = self.get_all_lorebooks_for_user(interaction.user.id)
        lorebook_names = list(user_lorebooks.keys())
        
        # Filter based on current input
        if current:
            lorebook_names = [name for name in lorebook_names if current.lower() in name.lower()]
        
        # Sort by relevance
        lorebook_names.sort(key=lambda name: (0 if current.lower() in name.lower() else 1, name))
        
        # Return as choices
        return [
            app_commands.Choice(name=name, value=name)
            for name in lorebook_names[:25]  # Discord limits to 25 choices
        ]

    def load_lorebooks(self):
        """Load lorebooks from the JSON file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.lorebooks = {
                    name: Lorebook.from_dict(book_data)
                    for name, book_data in data.items()
                }
                logger.info(f"Loaded {len(self.lorebooks)} lorebooks from disk")
            else:
                logger.info("No lorebooks file found. Starting with empty collection.")
                self.lorebooks = {}
        except Exception as e:
            logger.error(f"Error loading lorebooks: {e}")
            self.lorebooks = {}
    
    def save_lorebooks(self):
        """Save lorebooks to the JSON file"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            lorebooks_dict = {
                name: book.to_dict()
                for name, book in self.lorebooks.items()
            }
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(lorebooks_dict, f, indent=4, ensure_ascii=False)
            
            logger.info(f"Saved {len(self.lorebooks)} lorebooks to disk")
        except Exception as e:
            logger.error(f"Error saving lorebooks: {e}")
    
    def get_lorebook(self, name: str) -> Optional[Lorebook]:
        """Get a lorebook by name (case-insensitive)"""
        name_lower = name.lower()
        for lorebook_name, lorebook in self.lorebooks.items():
            if lorebook_name.lower() == name_lower:
                return lorebook
        return None
    
    def get_all_lorebooks_for_user(self, user_id: int) -> Dict[str, Lorebook]:
        """Get all lorebooks a user can access"""
        return {
            name: book for name, book in self.lorebooks.items()
            if book.is_public or book.owner_id == user_id
        }
    
    async def get_lorebook_content_for_ai(self, lorebook_name: str, user_id: int) -> str:
        """Get formatted lorebook content for AI, checking permissions"""
        lorebook = self.get_lorebook(lorebook_name)
        if not lorebook:
            return f"Lorebook '{lorebook_name}' not found."
        
        if not lorebook.is_public and lorebook.owner_id != user_id:
            return f"You don't have access to the '{lorebook_name}' lorebook."
        
        return lorebook.get_formatted_content()
    
    @app_commands.command(name="createlorebook", description="Create a new lorebook")
    @app_commands.describe(
        name="Name of the lorebook",
        is_public="Whether the lorebook can be edited by anyone",
        description="Description of the lorebook's purpose"
    )
    async def create_lorebook(
        self, 
        interaction: discord.Interaction, 
        name: str,
        is_public: bool = False,
        description: str = ""
    ):
        """Create a new lorebook"""
        # Check if name is valid (alphanumeric with spaces)
        if not all(c.isalnum() or c.isspace() or c in "-_" for c in name):
            await interaction.response.send_message(
                "❌ Lorebook name must contain only letters, numbers, spaces, hyphens, and underscores.",
                ephemeral=True
            )
            return
        
        # Check if name already exists
        if self.get_lorebook(name):
            await interaction.response.send_message(
                f"❌ A lorebook with the name '{name}' already exists.",
                ephemeral=True
            )
            return
        
        # Create the lorebook
        lorebook = Lorebook(
            name=name,
            owner_id=interaction.user.id,
            description=description,
            is_public=is_public
        )
        
        self.lorebooks[name] = lorebook
        self.save_lorebooks()
        
        visibility = "public" if is_public else "private"
        await interaction.response.send_message(
            f"✅ Created new {visibility} lorebook: **{name}**\n"
            f"Description: {description or 'No description provided'}\n\n"
            f"You can now add entries with `/addlore {name} <content>`",
            ephemeral=False
        )
    
    @app_commands.command(name="addlore", description="Add an entry to a lorebook")
    @app_commands.describe(
        lorebook="Name of the lorebook to add to",
        content="Content to add to the lorebook"
    )
    async def add_lore(
        self,
        interaction: discord.Interaction,
        lorebook: str,
        content: str
    ):
        """Add an entry to a lorebook"""
        await interaction.response.defer(ephemeral=False)
        
        # Get the lorebook
        target_book = self.get_lorebook(lorebook)
        if not target_book:
            await interaction.followup.send(f"❌ Lorebook '{lorebook}' not found.")
            return
        
        # Check permissions
        if not target_book.can_edit(interaction.user.id):
            await interaction.followup.send(
                f"❌ You don't have permission to edit the '{lorebook}' lorebook."
            )
            return
        
        # Handle public lorebooks (requires voting)
        if target_book.is_public and target_book.owner_id != interaction.user.id:
            # Create a poll in the polls channel
            polls_channel = self.bot.get_channel(self.polls_channel_id)
            if not polls_channel:
                logger.error(f"Could not find polls channel with ID {self.polls_channel_id}")
                await interaction.followup.send(
                    "❌ Error: Polls channel not found. Please notify an administrator."
                )
                return
            
            embed = discord.Embed(
                title=f"Lorebook Entry Suggestion: {target_book.name}",
                description=f"**Suggested by:** {interaction.user.mention}\n\n**Entry Content:**\n{content}",
                color=discord.Color.blue()
            )
            embed.set_footer(text="React with ✅ to approve or ❌ to reject | Poll closes in 24 hours")
            
            poll_message = await polls_channel.send(embed=embed)
            await poll_message.add_reaction("✅")
            await poll_message.add_reaction("❌")
            
            # Store the pending entry
            self.pending_entries[poll_message.id] = (lorebook, content, interaction.user.id)
            
            # Schedule to check the poll results after 24 hours
            self.bot.loop.create_task(self.check_poll_results(poll_message.id, 24))
            
            await interaction.followup.send(
                f"✅ Your entry has been submitted for approval in <#{polls_channel.id}>."
            )
            return
        
        # Add the entry directly for private lorebooks or the owner
        target_book.add_entry(content, interaction.user.id)
        self.save_lorebooks()
        
        await interaction.followup.send(
            f"✅ Added new entry to '{lorebook}' lorebook."
        )
    
    async def check_poll_results(self, message_id: int, hours: int):
        """Check the poll results after the specified hours"""
        await asyncio.sleep(hours * 3600)  # Convert hours to seconds
        
        if message_id not in self.pending_entries:
            return  # Poll was already processed or cancelled
        
        lorebook_name, content, author_id = self.pending_entries.pop(message_id)
        polls_channel = self.bot.get_channel(self.polls_channel_id)
        if not polls_channel:
            logger.error(f"Could not find polls channel with ID {self.polls_channel_id}")
            return
        
        try:
            message = await polls_channel.fetch_message(message_id)
            
            # Count votes
            approve_count = 0
            reject_count = 0
            
            for reaction in message.reactions:
                if str(reaction.emoji) == "✅":
                    approve_count = reaction.count - 1  # Subtract the bot's reaction
                elif str(reaction.emoji) == "❌":
                    reject_count = reaction.count - 1  # Subtract the bot's reaction
            
            lorebook = self.get_lorebook(lorebook_name)
            if not lorebook:
                await polls_channel.send(f"❌ Poll for lorebook '{lorebook_name}' failed: Lorebook no longer exists.")
                return
            
            result_embed = discord.Embed()
            
            # Entry is approved if there are more approve votes than reject votes
            if approve_count > reject_count:
                lorebook.add_entry(content, author_id)
                self.save_lorebooks()
                
                result_embed.title = "Lorebook Entry Approved"
                result_embed.description = f"The entry for '{lorebook_name}' has been approved and added."
                result_embed.color = discord.Color.green()
                result_embed.add_field(name="Votes", value=f"✅ {approve_count} | ❌ {reject_count}")
                
                user = await self.bot.fetch_user(author_id)
                if user:
                    try:
                        await user.send(f"✅ Your entry for the '{lorebook_name}' lorebook has been approved!")
                    except discord.HTTPException:
                        pass  # Failed to DM the user
            else:
                result_embed.title = "Lorebook Entry Rejected"
                result_embed.description = f"The entry for '{lorebook_name}' did not receive enough votes."
                result_embed.color = discord.Color.red()
                result_embed.add_field(name="Votes", value=f"✅ {approve_count} | ❌ {reject_count}")
            
            # Update the original message
            original_embed = message.embeds[0]
            original_embed.set_footer(text=f"Poll closed | Result: {'Approved' if approve_count > reject_count else 'Rejected'}")
            await message.edit(embed=original_embed)
            
            # Send the result as a reply to the original poll
            await polls_channel.send(embed=result_embed)
            
        except discord.NotFound:
            logger.warning(f"Poll message {message_id} not found, it may have been deleted.")
        except Exception as e:
            logger.error(f"Error checking poll results: {e}")
    
    @app_commands.command(name="lorebooks", description="List available lorebooks")
    async def list_lorebooks(self, interaction: discord.Interaction):
        """List all lorebooks accessible to the user"""
        user_lorebooks = self.get_all_lorebooks_for_user(interaction.user.id)
        
        if not user_lorebooks:
            await interaction.response.send_message(
                "No lorebooks available. Create one with `/createlorebook`!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="Available Lorebooks",
            color=discord.Color.blue()
        )
        
        for name, book in user_lorebooks.items():
            owner = "You" if book.owner_id == interaction.user.id else f"<@{book.owner_id}>"
            visibility = "Public" if book.is_public else "Private"
            entries_count = len(book.entries)
            
            value = f"Owner: {owner}\nVisibility: {visibility}\nEntries: {entries_count}"
            if book.description:
                value += f"\nDescription: {book.description}"
                
            embed.add_field(
                name=name,
                value=value,
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="viewlore", description="View the contents of a lorebook")
    @app_commands.describe(
        lorebook="Name of the lorebook to view"
    )
    async def view_lore(self, interaction: discord.Interaction, lorebook: str):
        """View the contents of a lorebook"""
        book = self.get_lorebook(lorebook)
        if not book:
            await interaction.response.send_message(
                f"❌ Lorebook '{lorebook}' not found.",
                ephemeral=True
            )
            return
        
        # Check permissions
        if not book.is_public and book.owner_id != interaction.user.id:
            await interaction.response.send_message(
                f"❌ You don't have permission to view the '{lorebook}' lorebook.",
                ephemeral=True
            )
            return
        
        # Create the embed
        embed = discord.Embed(
            title=f"Lorebook: {book.name}",
            description=book.description if book.description else "No description provided",
            color=discord.Color.blue()
        )
        
        owner = await self.bot.fetch_user(book.owner_id)
        owner_name = owner.name if owner else f"Unknown User ({book.owner_id})"
        embed.add_field(
            name="Details",
            value=f"Owner: {owner_name}\nVisibility: {'Public' if book.is_public else 'Private'}\nEntries: {len(book.entries)}",
            inline=False
        )
        
        if not book.entries:
            embed.add_field(
                name="No Entries",
                value="This lorebook is empty. Add entries with `/addlore`.",
                inline=False
            )
        else:
            # If the content is too long for one embed, we'll create a paginated view
            entries_per_page = 5
            total_pages = (len(book.entries) + entries_per_page - 1) // entries_per_page
            
            class LoreBookPaginator(discord.ui.View):
                def __init__(self, entries, *, timeout=180):
                    super().__init__(timeout=timeout)
                    self.entries = entries
                    self.current_page = 0
                    self.entries_per_page = entries_per_page
                    self.total_pages = total_pages
                
                async def update_page(self, interaction):
                    embed = discord.Embed(
                        title=f"Lorebook: {book.name} (Page {self.current_page+1}/{self.total_pages})",
                        description=book.description if book.description else "No description provided",
                        color=discord.Color.blue()
                    )
                    
                    embed.add_field(
                        name="Details",
                        value=f"Owner: {owner_name}\nVisibility: {'Public' if book.is_public else 'Private'}\nEntries: {len(book.entries)}",
                        inline=False
                    )
                    
                    start_idx = self.current_page * self.entries_per_page
                    end_idx = min(start_idx + self.entries_per_page, len(self.entries))
                    
                    for i in range(start_idx, end_idx):
                        entry = self.entries[i]
                        entry_author = await self.cog.bot.fetch_user(entry.author_id)
                        entry_author_name = entry_author.name if entry_author else f"Unknown User ({entry.author_id})"
                        
                        embed.add_field(
                            name=f"Entry {i+1} (by {entry_author_name})",
                            value=entry.content[:1024],  # Discord embed field value limit
                            inline=False
                        )
                    
                    self.update_buttons()
                    await interaction.response.edit_message(embed=embed, view=self)
                
                def update_buttons(self):
                    self.first_page.disabled = (self.current_page == 0)
                    self.prev_page.disabled = (self.current_page == 0)
                    self.next_page.disabled = (self.current_page == self.total_pages - 1)
                    self.last_page.disabled = (self.current_page == self.total_pages - 1)
                
                @discord.ui.button(label="⏪ First", style=discord.ButtonStyle.primary)
                async def first_page(self, interaction, button):
                    if interaction.user.id != interaction.message.interaction.user.id:
                        await interaction.response.send_message("This isn't your lorebook view!", ephemeral=True)
                        return
                    
                    self.current_page = 0
                    await self.update_page(interaction)
                
                @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary)
                async def prev_page(self, interaction, button):
                    if interaction.user.id != interaction.message.interaction.user.id:
                        await interaction.response.send_message("This isn't your lorebook view!", ephemeral=True)
                        return
                    
                    self.current_page = max(0, self.current_page - 1)
                    await self.update_page(interaction)
                
                @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.primary)
                async def next_page(self, interaction, button):
                    if interaction.user.id != interaction.message.interaction.user.id:
                        await interaction.response.send_message("This isn't your lorebook view!", ephemeral=True)
                        return
                    
                    self.current_page = min(self.total_pages - 1, self.current_page + 1)
                    await self.update_page(interaction)
                
                @discord.ui.button(label="⏩ Last", style=discord.ButtonStyle.primary)
                async def last_page(self, interaction, button):
                    if interaction.user.id != interaction.message.interaction.user.id:
                        await interaction.response.send_message("This isn't your lorebook view!", ephemeral=True)
                        return
                    
                    self.current_page = self.total_pages - 1
                    await self.update_page(interaction)
            
            # Initialize the paginator
            paginator = LoreBookPaginator(book.entries)
            paginator.cog = self
            paginator.update_buttons()
            
            # Show first page
            start_idx = 0
            end_idx = min(entries_per_page, len(book.entries))
            
            for i in range(start_idx, end_idx):
                entry = book.entries[i]
                entry_author = await self.bot.fetch_user(entry.author_id)
                entry_author_name = entry_author.name if entry_author else f"Unknown User ({entry.author_id})"
                
                embed.add_field(
                    name=f"Entry {i+1} (by {entry_author_name})",
                    value=entry.content[:1024],  # Discord embed field value limit
                    inline=False
                )
            
            if total_pages > 1:
                embed.title = f"Lorebook: {book.name} (Page 1/{total_pages})"
                await interaction.response.send_message(embed=embed, view=paginator, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    
    @app_commands.command(name="deletelore", description="Delete a lorebook or entry")
    @app_commands.describe(
        lorebook="Name of the lorebook to modify",
        entry_number="Entry number to delete (leave blank to delete entire lorebook)",
    )
    async def delete_lore(
        self, 
        interaction: discord.Interaction, 
        lorebook: str, 
        entry_number: Optional[int] = None
    ):
        """Delete a lorebook or entry"""
        book = self.get_lorebook(lorebook)
        if not book:
            await interaction.response.send_message(
                f"❌ Lorebook '{lorebook}' not found.",
                ephemeral=True
            )
            return
        
        # Only the owner can delete a lorebook or its entries
        if book.owner_id != interaction.user.id:
            await interaction.response.send_message(
                f"❌ Only the owner can delete the '{lorebook}' lorebook or its entries.",
                ephemeral=True
            )
            return
        
        # Delete an entry
        if entry_number is not None:
            if entry_number < 1 or entry_number > len(book.entries):
                await interaction.response.send_message(
                    f"❌ Invalid entry number. The lorebook has {len(book.entries)} entries.",
                    ephemeral=True
                )
                return
            
            # Delete the entry
            deleted_entry = book.entries.pop(entry_number - 1)
            self.save_lorebooks()
            
            await interaction.response.send_message(
                f"✅ Deleted entry #{entry_number} from '{lorebook}' lorebook."
            )
        else:
            # Delete the entire lorebook
            class ConfirmView(discord.ui.View):
                def __init__(self, cog, lorebook_name):
                    super().__init__(timeout=60)
                    self.cog = cog
                    self.lorebook_name = lorebook_name
                    self.confirmed = False
                
                @discord.ui.button(label="Delete Lorebook", style=discord.ButtonStyle.danger)
                async def confirm(self, interaction, button):
                    if interaction.user.id != book.owner_id:
                        await interaction.response.send_message(
                            "❌ Only the lorebook owner can perform this action.",
                            ephemeral=True
                        )
                        return
                    
                    self.cog.lorebooks.pop(self.lorebook_name)
                    self.cog.save_lorebooks()
                    self.confirmed = True
                    
                    await interaction.response.edit_message(
                        content=f"✅ Lorebook '{self.lorebook_name}' has been deleted.",
                        view=None
                    )
                
                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(self, interaction, button):
                    await interaction.response.edit_message(
                        content="Operation cancelled. The lorebook was not deleted.",
                        view=None
                    )

            view = ConfirmView(self, lorebook)
            await interaction.response.send_message(
                f"⚠️ Are you sure you want to delete the entire '{lorebook}' lorebook? This action cannot be undone.",
                view=view,
                ephemeral=True
            )
    
    @app_commands.command(name="editlore", description="Edit a lorebook entry or settings")
    @app_commands.describe(
        lorebook="Name of the lorebook to edit",
        entry_number="Entry number to edit (leave blank to edit lorebook settings)",
        new_content="New content for the entry (if editing an entry)",
        new_description="New description for the lorebook (if editing settings)",
        new_visibility="New visibility for the lorebook (if editing settings)"
    )
    async def edit_lore(
        self,
        interaction: discord.Interaction,
        lorebook: str,
        entry_number: Optional[int] = None,
        new_content: Optional[str] = None,
        new_description: Optional[str] = None,
        new_visibility: Optional[bool] = None
    ):
        """Edit a lorebook entry or settings"""
        book = self.get_lorebook(lorebook)
        if not book:
            await interaction.response.send_message(
                f"❌ Lorebook '{lorebook}' not found.",
                ephemeral=True
            )
            return
        
        # Check ownership
        is_owner = book.owner_id == interaction.user.id
        
        # Editing an entry
        if entry_number is not None:
            if entry_number < 1 or entry_number > len(book.entries):
                await interaction.response.send_message(
                    f"❌ Invalid entry number. The lorebook has {len(book.entries)} entries.",
                    ephemeral=True
                )
                return
            
            entry = book.entries[entry_number - 1]
            
            # Only the owner or entry author can edit entries
            if not is_owner and entry.author_id != interaction.user.id:
                await interaction.response.send_message(
                    f"❌ You can only edit your own entries unless you're the lorebook owner.",
                    ephemeral=True
                )
                return
            
            if not new_content:
                await interaction.response.send_message(
                    f"❌ You must provide new content when editing an entry.",
                    ephemeral=True
                )
                return
            
            # Update the entry
            entry.content = new_content
            self.save_lorebooks()
            
            await interaction.response.send_message(
                f"✅ Updated entry #{entry_number} in '{lorebook}' lorebook."
            )
        else:
            # Editing lorebook settings
            if not is_owner:
                await interaction.response.send_message(
                    f"❌ Only the owner can edit the '{lorebook}' lorebook settings.",
                    ephemeral=True
                )
                return
            
            # Update the settings
            updated_fields = []
            
            if new_description is not None:
                book.description = new_description
                updated_fields.append("description")
            
            if new_visibility is not None:
                book.is_public = new_visibility
                updated_fields.append("visibility")
            
            if not updated_fields:
                await interaction.response.send_message(
                    f"❌ You must provide at least one setting to update (description, visibility).",
                    ephemeral=True
                )
                return
            
            self.save_lorebooks()
            
            await interaction.response.send_message(
                f"✅ Updated '{lorebook}' lorebook settings: {', '.join(updated_fields)}."
            )
    
    # Integration with chat commands
    def get_active_lorebooks_content(self, user_id: int, lorebook_name: str = None) -> str:
        """Get content of active lorebooks for the user"""
        if lorebook_name:
            # Get a specific lorebook if requested
            lorebook = self.get_lorebook(lorebook_name)
            if not lorebook:
                return f"Lorebook '{lorebook_name}' not found."
            
            # Check access
            if not lorebook.is_public and lorebook.owner_id != user_id:
                return f"You don't have access to the '{lorebook_name}' lorebook."
            
            return lorebook.get_formatted_content()
        
        # Return a message if no lorebooks
        if not self.lorebooks:
            return "No lorebooks available."
        
        # Get all accessible lorebooks
        accessible_books = self.get_all_lorebooks_for_user(user_id)
        if not accessible_books:
            return "You don't have access to any lorebooks."
        
        return "Available lorebooks: " + ", ".join(accessible_books.keys()) + "\n\nUse 'lore: name' to access a specific lorebook."

async def setup(bot: commands.Bot):
    await bot.add_cog(LoreSystem(bot))