import os
import asyncio
import logging

from duckduckgo_search import DDGS
from discord.ext import commands
import openai
from openai import OpenAI

# Set up a logger for this module.
logger = logging.getLogger(__name__)

# Set up the OpenAI client (this example uses the API key for GPT-4o-mini extraction)
oaiclient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class DuckDuckGo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("DuckDuckGo cog loaded.")

    async def extract_search_query(self, user_message: str) -> str:
        """
        Uses GPT-4o-mini to extract a concise search query from the user’s message.
        """
        logger.info("Extracting search query for message: %s", user_message)
        def _extract_search_query(um):
            try:
                response = oaiclient.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Determine if a web search would be relevant to addressing the user's query. "
                                "If so, extract a concise search query string from the following text that captures its key intent. "
                                "Only return the query and nothing else. "
                                "If not, return nothing at all."
                            ),
                        },
                        {"role": "user", "content": um},
                    ],
                )
                extracted_query = response.choices[0].message.content.strip()
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
        # If the query is blank, skip running the search.
        if not query.strip():
            logger.info("Blank query provided. Skipping DDG search.")
            return ""
        def _ddg_search(q):
            try:
                proxy = os.getenv("DUCK_PROXY")
                duck = DDGS(proxy=proxy) if proxy else DDGS()
                results = duck.text(q, max_results=10)
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

    # Command that lets users trigger DDG search by first extracting a search query.
    @commands.command(name="ddg")
    async def ddg(self, ctx, *, message: str):
        """
        Extracts a search query using GPT-4o-mini from the provided message.
        If a valid query is extracted, then performs a DDG search and returns the results.
        """
        logger.info("DDG command triggered by %s with message: %s", ctx.author, message)
        search_query = await self.extract_search_query(message)
        if not search_query:
            await ctx.send("No valuable search query could be extracted from your message; search cancelled.")
            logger.info("No valid search query extracted from message: %s", message)
            return

        results = await self.perform_ddg_search(search_query)
        if results:
            # Wrap the output in a code block to preserve formatting.
            await ctx.send(f"```{results}```")
            logger.info("Sent DDG search results for query: %s", search_query)
        else:
            await ctx.send("No results found.")
            logger.info("No DDG search results for query: %s", search_query)

async def setup(bot):
    await bot.add_cog(DuckDuckGo(bot))