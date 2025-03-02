import os
import asyncio
import logging
from embed_utils import send_embed  
from duckduckgo_search import DDGS
import discord
from discord.ext import commands
import time
from status_utils import update_status

logger = logging.getLogger(__name__)

class DuckDuckGo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def extract_search_query(self, user_message: str) -> str:
        logger.info("Extracting search query for message: %s", user_message)
        api_utils = self.bot.get_cog("APIUtils")
        if not api_utils:
            logger.error("APIUtils cog not found")
            return ""
        
        try:
            extracted_query = await api_utils.send_request(
                model="gpt-4o-mini",
                message_content=(
                    "Generate a concise search query that would fetch relevant information to answer or "
                    "address the following user message. Focus on extracting key terms, topics, names, or questions. "
                    "Return only the search query text, nothing else.\n\n"
                    f"User message: {user_message}"
                )
            )
            
            extracted_query = extracted_query.strip()
            logger.info("Extracted search query: %s", extracted_query)
            return extracted_query
            
        except Exception as e:
            logger.exception("Error extracting search query: %s", e)
            return ""

    async def perform_ddg_search(self, query: str) -> str:
        logger.info("Performing DDG search for query: %s", query)
        if not query.strip():
            logger.info("Blank query provided. Skipping DDG search.")
            return ""
        def _ddg_search(q):
            try:
                proxy = os.getenv("DUCK_PROXY")
                duck = DDGS(proxy=proxy) if proxy else DDGS()
                results = duck.text(q.strip('"').strip(), max_results=10)
                logger.info("DDG search results retrieved for query '%s': %s", q, results)
                return results
            except Exception as e:
                logger.exception("Error during DDG search: %s", e)
                return None
        results = await asyncio.to_thread(_ddg_search, query)
        if not results:
            logger.info("No results returned from DDG for query: %s", query)
            return ""
        concat_result = f"Search query: {query}\n\n"
        for i, result in enumerate(results, start=1):
            title = result.get("title", "")
            description = result.get("body", "")
            concat_result += f"{i} -- {title}: {description}\n\n"
        logger.info("Formatted DDG search results for query: %s", query)
        return concat_result

    async def summarize_search_results(self, search_results: str) -> str:
        logger.info("Summarizing search results")
        api_utils = self.bot.get_cog("APIUtils")
        if not api_utils:
            logger.error("APIUtils cog not found")
            return search_results
        
        try:
            summary = await api_utils.send_request(
                model="gpt-4o-mini",
                message_content=(
                    "Please summarize the following DuckDuckGo search results. "
                    "Extract and present only the key information in a concise summary, and return just the summary.\n\n"
                    f"{search_results}"
                )
            )
            logger.info("Summary generated: %s", summary)
            return summary
        except Exception as e:
            logger.exception("Error summarizing search results: %s", e)
            return search_results

    async def search_and_summarize(self, full_message: str) -> str:
        logger.info("Running combined search and summarization for message: %s", full_message)
        search_query = await self.extract_search_query(full_message)
        if not search_query:
            logger.info("No search query was extracted; skipping search.")
            return ""
        raw_results = await self.perform_ddg_search(search_query)
        if not raw_results:
            logger.info("No search results found for query: %s", search_query)
            return ""
        summary = await self.summarize_search_results(raw_results)
        return summary

    @commands.command(name="ddg")
    async def ddg(self, ctx, *, message: str):
        start = time.monotonic()
        logger.info("DDG command triggered by %s with message: %s", ctx.author, message)
        
        summary = await self.search_and_summarize(message)
        if not summary:
            await ctx.send("No valuable search results found.")
            logger.info("No summarized results to show for message: %s", message)
            return

        elapsed = time.monotonic() - start

        response_embed = discord.Embed(title="", description=summary, color=0x32a956)
        response_embed.set_footer(text=f"DuckDuckGo Search (summarized) | generated in {elapsed:.2f} seconds")
        await send_embed(ctx.channel, response_embed, reply_to=ctx.message)
        logger.info("Sent summarized DDG search results.")

async def setup(bot):
    await bot.add_cog(DuckDuckGo(bot))