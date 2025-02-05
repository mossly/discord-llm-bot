import os
import asyncio
import logging
from embed_utils import send_embed  
from duckduckgo_search import DDGS
import discord
from discord.ext import commands
import openai
from openai import OpenAI
import time
from status_utils import update_status

# Set up a logger for this module.
logger = logging.getLogger(__name__)

# Set up the OpenAI client (using the API key for GPT-4o-mini extraction)
oaiclient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class DuckDuckGo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("DuckDuckGo cog loaded.")

    async def extract_search_query(self, user_message: str) -> str:
        """
        Uses GPT-4o-mini to extract a concise search query from the user's message.
        If GPT-4o-mini returns "NO_SEARCH" (case-insensitive), this function will return an empty string.
        """
        logger.info("Extracting search query for message: %s", user_message)
        def _extract_search_query(user_message):
            try:
                response = oaiclient.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Determine if a web search would help resolve the users last message. This will apply in all cases if the user asks a question that would benefit from information retrieval."
                                "Try not to make any assumptions, particularly about dates, and definitely search for any information the user requests that is after your knowledge cutoff."
                                "If a search would not be helpful, return NO_SEARCH."
                                "If a search would be helpful, return only a concise search query string, informed by the following text, that captures its key intent."
                                "Always return a search query if the user explicitly requests a web search."
                            ),
                        },
                        {"role": "user", "content": user_message},
                    ],
                )
                extracted_query = response.choices[0].message.content.strip()
                # If the extraction indicates no search is needed, return an empty string.
                if extracted_query.upper() == "NO_SEARCH":
                    logger.info("Extracted query indicates NO_SEARCH; skipping search.")
                    return ""
                logger.info("Extracted search query: %s", extracted_query)
                return extracted_query
            except Exception as e:
                logger.exception("Error extracting search query: %s", e)
                return ""
        return await asyncio.to_thread(_extract_search_query, user_message)

    async def perform_ddg_search(self, query: str) -> str:
        """
        Uses DuckDuckGo (via DDGS) to search for the given query and formats up to 10 results.
        """
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
        """
        Uses GPT-4o-mini to summarize the search results into a concise summary.
        """
        logger.info("Summarizing search results")
        def _summarize(text):
            try:
                response = oaiclient.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Please summarize the following DuckDuckGo search results."
                                "Extract and present only the key information in a concise summary, and return just the summary."
                            )
                        },
                        {"role": "user", "content": text},
                    ],
                )
                summary = response.choices[0].message.content.strip()
                logger.info("Summary generated: %s", summary)
                return summary
            except Exception as e:
                logger.exception("Error summarizing search results: %s", e)
                # Fallback: return the original text if summarization fails.
                return text
        summary_text = await asyncio.to_thread(_summarize, search_results)
        return summary_text

    async def search_and_summarize(self, full_message: str) -> str:
        """
        Combines the DDG search and summarization steps.
        1. Uses GPT-4o-mini to extract a search query from full_message.
        2. Performs a DuckDuckGo search with that query.
        3. Summarizes the search results via GPT-4o-mini.
        Returns the summary (or an empty string if no query or results are found).
        """
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

    # (The existing ddg command can still use the two-step approach if desired.)
    @commands.command(name="ddg")
    async def ddg(self, ctx, *, message: str):
        start = time.monotonic()
        logger.info("DDG command triggered by %s with message: %s", ctx.author, message)
        
        # Use combined search-and-summarize.
        summary = await self.search_and_summarize(message)
        if not summary:
            await ctx.send("No valuable search results found.")
            logger.info("No summarized results to show for message: %s", message)
            return

        elapsed = time.monotonic() - start

        # Build an embed with the summary.
        response_embed = discord.Embed(title="", description=summary, color=0x32a956)
        response_embed.set_footer(text=f"DuckDuckGo Search (summarized) | generated in {elapsed:.2f} seconds")
        await send_embed(ctx.channel, response_embed, reply_to=ctx.message)
        logger.info("Sent summarized DDG search results.")

async def setup(bot):
    await bot.add_cog(DuckDuckGo(bot))