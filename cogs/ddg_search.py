import os
import asyncio
from duckduckgo_search import DDGS
from discord.ext import commands
import openai
from openai import OpenAI

# Set up the OpenAI client (this example uses the API key for GPT-4o-mini extraction)
oaiclient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class DuckDuckGo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def extract_search_query(self, user_message: str) -> str:
        """
        Uses GPT-4o-mini to extract a concise search query from the user’s message.
        """
        def _extract_search_query(um):
            try:
                response = oaiclient.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Determine if a web search would be relevant to addressing the users query."
                                "If so, extract a concise search query string from the following text that captures its key intent. "
                                "Only return the query and nothing else."
                                "If not, return nothing at all."
                            ),
                        },
                        {"role": "user", "content": um},
                    ],
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print("Error extracting search query:", e)
                return ""
        return await asyncio.to_thread(_extract_search_query, user_message)

    async def perform_ddg_search(self, query: str) -> str:
        """
        Uses DuckDuckGo (via DDGS) to search for the given query and formats up to 10 results.
        """
        def _ddg_search(q):
            try:
                proxy = os.getenv("DUCK_PROXY")
                duck = DDGS(proxy=proxy) if proxy else DDGS()
                results = duck.text(q, max_results=10)
                return results
            except Exception as e:
                print("Error during DDG search:", e)
                return None
        results = await asyncio.to_thread(_ddg_search, query)
        if not results:
            return ""
        concat_result = f"Search query: {query}\n\n"
        for i, result in enumerate(results, start=1):
            title = result.get("title", "")
            description = result.get("body", "")
            concat_result += f"{i} -- {title}: {description}\n\n"
        return concat_result

    # (Optional) You can also add a command to let users trigger DDG search directly.
    @commands.command(name="ddg")
    async def ddg(self, ctx, *, query: str):
        """Search DuckDuckGo for the provided query."""
        results = await self.perform_ddg_search(query)
        if results:
            # Wrap the output in a code block to preserve formatting.
            await ctx.send(f"```{results}```")
        else:
            await ctx.send("No results found.")

async def setup(bot):
    await bot.add_cog(DuckDuckGo(bot))