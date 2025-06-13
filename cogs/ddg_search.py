import os
import asyncio
import logging
from utils.embed_utils import send_embed  
from duckduckgo_search import DDGS
import discord
from discord.ext import commands
import time

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
            extracted_result = await api_utils.send_request(
                model="gpt-4o-mini",
                message_content=(
                    "Generate a concise search query that would fetch relevant information to answer or "
                    "address the following user message. Focus on extracting key terms, topics, names, or questions. "
                    "Return only the search query text, nothing else.\n\n"
                    f"User message: {user_message}"
                )
            )
            
            extracted_query = extracted_result[0] if isinstance(extracted_result, tuple) else extracted_result
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
        async def _ddg_search_with_retry(q):
            max_retries = 3
            base_delay = 1.0
            
            for attempt in range(max_retries):
                def _ddg_search():
                    try:
                        proxy = os.getenv("DUCK_PROXY")
                        duck = DDGS(proxy=proxy) if proxy else DDGS()
                        results = duck.text(q.strip('"').strip(), max_results=10)
                        return results
                    except Exception as e:
                        raise e
                
                try:
                    results = await asyncio.to_thread(_ddg_search)
                    logger.info("DDG search results retrieved for query '%s': %s", q, results)
                    return results
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # Check for rate limiting indicators
                    if any(indicator in error_msg for indicator in ['ratelimit', 'rate limit', '202', 'backoff']):
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(f"DDG rate limit detected (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(f"DDG rate limited after {max_retries} attempts: {e}")
                            return None
                    
                    # Other errors - don't retry
                    else:
                        logger.exception("Error during DDG search: %s", e)
                        return None
            
            return None
            
        results = await _ddg_search_with_retry(query)
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
            summary_result = await api_utils.send_request(
                model="gpt-4o-mini",
                message_content=(
                    "Please summarize the following DuckDuckGo search results. "
                    "Extract and present only the key information in a concise summary, and return just the summary.\n\n"
                    f"{search_results}"
                )
            )
            
            summary = summary_result[0] if isinstance(summary_result, tuple) else summary_result
            logger.info("Summary generated: %s", summary)
            return summary
        except Exception as e:
            logger.exception("Error summarizing search results: %s", e)
            return search_results

async def setup(bot):
    await bot.add_cog(DuckDuckGo(bot))