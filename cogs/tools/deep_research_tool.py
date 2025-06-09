"""
Deep research tool implementation using LLM orchestration with tool calling
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from .base_tool import BaseTool
from .web_search_tool import WebSearchTool
from .content_tool import ContentRetrievalTool
import logging

logger = logging.getLogger(__name__)


class SourceRelevanceScorer:
    """Calculate relevance scores for sources based on multiple factors"""
    
    def __init__(self, user_query):
        self.user_query = user_query.lower()
        self.query_keywords = set(self.user_query.split())
        self.domain_authority_scores = {
            # High authority domains
            'wikipedia.org': 0.9, 'scholar.google.com': 0.95, 'arxiv.org': 0.9,
            'nature.com': 0.95, 'science.org': 0.95, 'ieee.org': 0.9,
            'acm.org': 0.9, 'springer.com': 0.85, 'sciencedirect.com': 0.85,
            'pubmed.ncbi.nlm.nih.gov': 0.9, 'ncbi.nlm.nih.gov': 0.9,
            
            # Medium authority domains  
            'github.com': 0.75, 'stackoverflow.com': 0.8, 'reddit.com': 0.6,
            'medium.com': 0.65, 'techcrunch.com': 0.7, 'wired.com': 0.75,
            'arstechnica.com': 0.75, 'theverge.com': 0.7, 'engadget.com': 0.65,
            
            # News sources
            'reuters.com': 0.8, 'bbc.com': 0.8, 'cnn.com': 0.7, 'nytimes.com': 0.8,
            'wsj.com': 0.8, 'guardian.com': 0.75, 'washingtonpost.com': 0.75
        }
    
    def extract_domain(self, url):
        """Extract domain from URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return ""
    
    def calculate_title_relevance(self, title):
        """Calculate relevance based on title content"""
        if not title:
            return 0.0
            
        title_lower = title.lower()
        title_words = set(title_lower.split())
        
        # Keyword overlap score
        keyword_overlap = len(self.query_keywords.intersection(title_words))
        max_possible_overlap = len(self.query_keywords)
        
        if max_possible_overlap == 0:
            return 0.5
            
        overlap_score = keyword_overlap / max_possible_overlap
        
        # Boost for exact phrase matches
        phrase_boost = 0.0
        if self.user_query in title_lower:
            phrase_boost = 0.3
        
        # Penalty for overly generic titles
        generic_penalty = 0.0
        generic_words = {'guide', 'tips', 'how', 'what', 'best', 'top', 'list'}
        if len(generic_words.intersection(title_words)) >= 2:
            generic_penalty = 0.1
            
        return min(1.0, overlap_score + phrase_boost - generic_penalty)
    
    def calculate_domain_authority(self, url):
        """Get domain authority score"""
        domain = self.extract_domain(url)
        return self.domain_authority_scores.get(domain, 0.5)
    
    def calculate_relevance_score(self, url, title, search_position=None, total_results=None):
        """Calculate overall relevance score for a source"""
        title_score = self.calculate_title_relevance(title)
        domain_score = self.calculate_domain_authority(url)
        
        # Position score (if available)
        position_score = 1.0
        if search_position is not None and total_results is not None:
            normalized_pos = (total_results - search_position + 1) / total_results
            position_score = normalized_pos ** 0.5
        
        # Weighted combination
        relevance_score = (
            title_score * 0.4 +      # Title relevance is most important
            domain_score * 0.3 +     # Domain authority
            position_score * 0.3     # Search ranking
        )
        
        return round(relevance_score, 3)


class ActivityTracker:
    """Track different types of research activities"""
    
    def __init__(self):
        self.activities = []
        self.activity_counts = {
            'search': 0,
            'extract': 0, 
            'analyze': 0,
            'reasoning': 0,
            'synthesis': 0
        }
    
    def add_activity(self, activity_type, message, status='complete'):
        """Add an activity with type categorization"""
        activity = {
            'type': activity_type,
            'status': status,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        self.activities.append(activity)
        if status == 'complete':
            self.activity_counts[activity_type] += 1
        return activity
    
    def get_summary(self):
        """Get activity summary for reporting"""
        return {
            'total_activities': len(self.activities),
            'by_type': self.activity_counts.copy(),
            'recent_activities': self.activities[-5:]
        }


class DeepResearchTool(BaseTool):
    """Tool for conducting deep iterative research using LLM orchestration"""
    
    def __init__(self, exa_api_key: Optional[str] = None, bot=None):
        super().__init__()
        self.exa_api_key = exa_api_key or os.getenv("EXA_API_KEY")
        self.bot = bot
        
        # Initialize sub-tools
        self.search_tool = WebSearchTool(use_ddg=True, exa_api_key=exa_api_key)
        self.content_tool = ContentRetrievalTool()
        
        # Research parameters
        self.min_actions = 6
        self.max_actions = 20
        self.search_results_per_query = 8
    
    @property
    def name(self) -> str:
        return "deep_research"
    
    @property
    def description(self) -> str:
        return "Conduct deep iterative research using LLM orchestration. The AI agent strategically searches web sources and extracts content to build comprehensive understanding of complex topics."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The research topic or question to investigate thoroughly"
                },
                "min_actions": {
                    "type": "integer",
                    "description": "Minimum number of research actions (default: 6, max: 12)",
                    "default": 6
                },
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific focus areas to investigate",
                    "default": []
                },
                "model": {
                    "type": "string",
                    "description": "Model to use for research orchestration (default: anthropic/claude-sonnet-4)",
                    "default": "anthropic/claude-sonnet-4"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, min_actions: int = 6, focus_areas: List[str] = None, model: str = "anthropic/claude-sonnet-4") -> Dict[str, Any]:
        """Execute deep research using LLM orchestration
        
        Args:
            query: The research topic or question
            min_actions: Minimum number of research actions (3-12)
            focus_areas: Optional list of specific focus areas
            model: Model to use for orchestration (defaults to Claude Sonnet 4)
                   Note: Content extraction always uses gpt-4.1-nano for efficiency
        """
        min_actions = max(3, min(min_actions, 12))
        focus_areas = focus_areas or []
        self.orchestrator_model = model
        
        logger.info(f"Starting LLM-orchestrated deep research for: {query}")
        
        # Initialize tracking
        searched_queries = set()
        scraped_urls = set()
        activity_tracker = ActivityTracker()
        relevance_scorer = SourceRelevanceScorer(query)
        sources = []
        
        # Statistics tracking
        stats = {
            "search_actions": 0,
            "scrape_actions": 0,
            "urls_scraped": 0,
            "total_cost": 0.0,
            "total_tokens": 0
        }
        
        try:
            # Initialize conversation with research system prompt
            conversation_history = [
                {
                    "role": "system", 
                    "content": self._get_research_system_prompt(min_actions, focus_areas)
                },
                {
                    "role": "user", 
                    "content": query
                }
            ]
            
            action_count = 0
            tool_action_count = 0
            
            # LLM orchestration loop
            while action_count < self.max_actions:
                action_count += 1
                logger.info(f"LLM orchestration iteration {action_count}/{self.max_actions}")
                activity_tracker.add_activity('reasoning', f"LLM iteration {action_count}")
                
                # Get LLM response with tool calling
                response = await self._call_orchestrator_llm(conversation_history, model)
                assistant_msg = response["choices"][0]["message"]
                
                # Track costs
                if "usage" in response:
                    usage = response["usage"]
                    stats["total_cost"] += usage.get("total_cost", 0.0)
                    stats["total_tokens"] += usage.get("total_tokens", 0)
                
                logger.info(f"LLM response received for iteration {action_count}")
                
                # Check for tool calls
                if not assistant_msg.get("tool_calls"):
                    # No tool calls - remind about minimum actions if needed
                    if tool_action_count < min_actions:
                        conversation_history.append(assistant_msg)
                        reminder_msg = {
                            "role": "user",
                            "content": f"You must use research tools to gather information. You need {min_actions} research actions total, but you've only completed {tool_action_count}. Please search for relevant information."
                        }
                        conversation_history.append(reminder_msg)
                        continue
                    else:
                        # Minimum actions met, can finish
                        if assistant_msg.get("content"):
                            conversation_history.append(assistant_msg)
                        break
                
                # Add assistant message to history
                conversation_history.append(assistant_msg)
                
                # Execute tool calls
                query_finished = False
                for tool_call in assistant_msg["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    arguments = json.loads(tool_call["function"]["arguments"])
                    
                    if tool_name == "finish_query":
                        if tool_action_count < min_actions:
                            tool_result = {"error": f"Must complete at least {min_actions} research actions before finishing (currently {tool_action_count})"}
                        else:
                            # Generate final comprehensive report
                            final_answer = arguments.get("answer", "")
                            research_data = await self._generate_final_research_data(
                                query, final_answer, conversation_history, sources, stats, activity_tracker
                            )
                            tool_result = {"status": "complete", "research_data": research_data}
                            query_finished = True
                    
                    elif tool_name == "search_web":
                        search_query = arguments.get("query", "")
                        num_results = arguments.get("num_results", self.search_results_per_query)
                        
                        if search_query in searched_queries:
                            tool_result = {"error": f"Duplicate search: '{search_query}' already performed"}
                        else:
                            tool_result = await self._execute_search(search_query, num_results, relevance_scorer, sources)
                            searched_queries.add(search_query)
                            stats["search_actions"] += 1
                            tool_action_count += 1
                            activity_tracker.add_activity('search', f"Searched: {search_query}")
                    
                    elif tool_name == "get_contents":
                        urls = arguments.get("urls", [])
                        
                        # Filter out already scraped URLs
                        new_urls = [url for url in urls if url not in scraped_urls]
                        if not new_urls:
                            tool_result = {"error": "All URLs have already been scraped"}
                        else:
                            tool_result = await self._execute_content_extraction(new_urls, query)
                            for url in new_urls:
                                scraped_urls.add(url)
                            stats["scrape_actions"] += 1
                            stats["urls_scraped"] += len(new_urls)
                            tool_action_count += 1
                            activity_tracker.add_activity('extract', f"Extracted content from {len(new_urls)} URLs")
                    
                    else:
                        tool_result = {"error": f"Unknown tool: {tool_name}"}
                    
                    # Add tool result to conversation
                    conversation_history.append({
                        "role": "tool", 
                        "tool_call_id": tool_call["id"], 
                        "content": json.dumps(tool_result)
                    })
                
                if query_finished:
                    return tool_result
            
            # Max actions reached - force completion
            logger.warning(f"Max actions ({self.max_actions}) reached - forcing completion")
            force_finish_msg = {
                "role": "system",
                "content": "Maximum actions reached. Provide a comprehensive answer based on gathered information."
            }
            conversation_history.append(force_finish_msg)
            
            final_response = await self._call_orchestrator_llm(conversation_history, model)
            final_msg = final_response["choices"][0]["message"]
            final_answer = final_msg.get("content", "Research completed at maximum actions limit.")
            
            research_data = await self._generate_final_research_data(
                query, final_answer, conversation_history, sources, stats, activity_tracker
            )
            
            return {
                "success": True,
                "research_data": research_data,
                "status": "max_actions_reached"
            }
        
        except Exception as e:
            logger.error(f"Deep research failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Research failed: {str(e)}",
                "query": query
            }
    
    async def _call_orchestrator_llm(self, messages: List[Dict], model: str = "anthropic/claude-sonnet-4") -> Dict[str, Any]:
        """Call the orchestrator LLM with tool calling capabilities"""
        # Get the API utils instance from the bot
        api_utils = self.bot.get_cog('APIUtils')
        if not api_utils:
            raise ValueError("APIUtils cog not found")
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return (default: 8)",
                                "default": 8
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_contents",
                    "description": "Extract full content from specific URLs to read detailed information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of URLs to extract content from"
                            }
                        },
                        "required": ["urls"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "finish_query",
                    "description": "Complete research with a comprehensive answer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                                "description": "The final comprehensive answer with citations"
                            }
                        },
                        "required": ["answer"]
                    }
                }
            }
        ]
        
        # Use the established API pattern from api_utils
        response = await api_utils.send_request_with_tools(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            api="openrouter",
            max_tokens=2000
        )
        
        if "error" in response:
            raise ValueError(f"API error: {response['error']}")
        
        return {
            "choices": [{
                "message": {
                    "content": response.get("content"),
                    "tool_calls": response.get("tool_calls", [])
                }
            }],
            "usage": {
                "total_tokens": 0,  # API utils doesn't return usage stats in this format
                "total_cost": 0.0
            }
        }
    
    async def _execute_search(self, query: str, num_results: int, relevance_scorer: SourceRelevanceScorer, sources: List) -> Dict[str, Any]:
        """Execute web search and calculate relevance scores"""
        try:
            search_result = await self.search_tool.execute(query=query, max_results=num_results)
            
            if not search_result.get("success"):
                return search_result
            
            # Add relevance scores to results
            results = search_result.get("results", [])
            total_results = len(results)
            
            for i, result in enumerate(results):
                url = result.get("url", "")
                title = result.get("title", "")
                
                relevance_score = relevance_scorer.calculate_relevance_score(
                    url, title, i + 1, total_results
                )
                result["relevance_score"] = relevance_score
                
                # Track source
                sources.append({
                    "url": url,
                    "title": title,
                    "relevance": relevance_score,
                    "timestamp": datetime.now().isoformat()
                })
            
            return search_result
            
        except Exception as e:
            logger.error(f"Search execution failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_content_extraction(self, urls: List[str], query: str) -> Dict[str, Any]:
        """Execute content extraction with GPT-4o-mini for key content extraction"""
        try:
            content_results = []
            
            for url in urls:
                content_result = await self.content_tool.execute(url=url, extract_links=False)
                
                if content_result.get("success"):
                    raw_content = content_result.get("content", "")
                    title = content_result.get("title", "")
                    
                    # Use GPT-4o-mini for extraction
                    extracted_data = await self._extract_key_content_with_mini(
                        raw_content, title, url, query
                    )
                    
                    content_results.append({
                        "url": url,
                        "title": title,
                        "extracted_content": extracted_data.get("extracted_content", ""),
                        "key_insights": extracted_data.get("key_insights", []),
                        "relevance_score": extracted_data.get("relevance_score", 0.5),
                        "original_length": len(raw_content),
                        "compressed_length": len(extracted_data.get("extracted_content", ""))
                    })
                else:
                    logger.warning(f"Failed to extract content from {url}: {content_result.get('error')}")
                    content_results.append({
                        "url": url,
                        "error": content_result.get("error", "Unknown error")
                    })
            
            return {
                "success": True,
                "results": content_results
            }
            
        except Exception as e:
            logger.error(f"Content extraction failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_key_content_with_mini(self, raw_content: str, title: str, url: str, query: str) -> Dict[str, Any]:
        """Use GPT-4o-mini to extract key content for context management"""
        if not self.openrouter_api_key:
            # Fallback to simple extraction
            return {
                "extracted_content": raw_content[:1000],
                "key_insights": [],
                "relevance_score": 0.5
            }
        
        try:
            import openai
            
            client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_api_key
            )
            
            extraction_prompt = f"""Extract key information from this content for research on: "{query}"

Source: {title}
URL: {url}

Content (first 3000 chars):
{raw_content[:3000]}

Respond with JSON:
{{
  "extracted_content": "relevant content summary (max 500 words)",
  "key_insights": ["insight 1", "insight 2", "insight 3"],
  "relevance_score": 0.8
}}

Focus on:
- Facts, statistics, and specific details
- Information directly relevant to the research query
- Quotes and authoritative statements
- Unique insights not commonly known"""

            response = client.chat.completions.create(
                model="openai/gpt-4.1-nano",
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=600,
                temperature=0.1
            )
            
            # Track API usage
            if hasattr(response, 'usage') and response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                # Get actual cost from API response
                cost = getattr(response.usage, 'total_cost', 0.0)
                self.add_session_usage(input_tokens, output_tokens, cost)
            
            # Parse JSON response
            extracted_data = json.loads(response.choices[0].message.content)
            
            return {
                "extracted_content": extracted_data.get("extracted_content", "")[:2000],  # Limit size
                "key_insights": extracted_data.get("key_insights", [])[:5],
                "relevance_score": min(1.0, max(0.0, extracted_data.get("relevance_score", 0.5)))
            }
            
        except Exception as e:
            logger.error(f"Content extraction with mini failed: {e}")
            return {
                "extracted_content": raw_content[:1000],
                "key_insights": [],
                "relevance_score": 0.5
            }
    
    async def _generate_final_research_data(self, query: str, final_answer: str, conversation_history: List, sources: List, stats: Dict, activity_tracker: ActivityTracker) -> Dict[str, Any]:
        """Generate comprehensive research data for final response"""
        
        # Extract all sources from conversation history
        all_sources = []
        source_counter = 1
        seen_urls = set()
        
        for msg in conversation_history:
            if msg["role"] == "tool":
                try:
                    result = json.loads(msg["content"])
                    if "results" in result:
                        for res in result["results"]:
                            url = res.get("url", "")
                            title = res.get("title", "Untitled")
                            if url and url not in seen_urls:
                                all_sources.append({
                                    "num": source_counter,
                                    "url": url,
                                    "title": title,
                                    "relevance": res.get("relevance_score", 0.5)
                                })
                                seen_urls.add(url)
                                source_counter += 1
                except:
                    pass
        
        # Get activity summary
        activity_summary = activity_tracker.get_summary()
        
        # Sort sources by relevance
        sorted_sources = sorted(sources, key=lambda x: x.get('relevance', 0), reverse=True)
        
        research_data = {
            "query": query,
            "final_answer": final_answer,
            "research_summary": {
                "search_actions": stats["search_actions"],
                "urls_scraped": stats["urls_scraped"],
                "total_cost": stats["total_cost"],
                "total_tokens": stats["total_tokens"]
            },
            "activity_summary": activity_summary,
            "sources": all_sources,
            "top_sources_by_relevance": sorted_sources[:10],
            "conversation_length": len(conversation_history)
        }
        
        return research_data
    
    def _get_research_system_prompt(self, min_actions: int, focus_areas: List[str]) -> str:
        """Get the system prompt for LLM orchestration"""
        focus_text = f"\n\nFOCUS AREAS: {', '.join(focus_areas)}" if focus_areas else ""
        
        return f"""You are an autonomous research assistant conducting deep research. You must complete at least {min_actions} research actions before calling finish_query.

WORKFLOW:
1. Use search_web to find relevant information with strategic queries
2. Use get_contents to extract detailed content from promising URLs  
3. Build comprehensive understanding through multiple search/extract cycles
4. Reference previous findings when planning next searches
5. Call finish_query when sufficient information is gathered (after {min_actions}+ actions)

RESEARCH STRATEGY:
- Start with broad searches, then narrow to specific aspects
- Select high-quality, authoritative sources for content extraction
- Build upon previous findings - avoid duplicate searches
- Look for gaps in knowledge and search to fill them
- Prioritize recent and authoritative information{focus_text}

WHEN CALLING finish_query:
- Provide comprehensive, well-structured markdown response
- Include specific facts, statistics, and insights from research
- Use inline citations [1], [2], etc. to reference sources
- Structure with clear sections if appropriate
- Be thorough but concise
- Focus on most relevant and authoritative information

WRITING STYLE:
- Clear, direct language
- Use active voice, avoid adverbs
- British spelling
- Express calm confidence
- No em dashes (—)

CITATION FORMAT:
- Inline citations: [1], [2], [3]
- End with horizontal line ~~‎ ‎ ‎~~
- Footnotes: -# 1. [Title] (url)

PROCEED STRATEGICALLY - each search should build on previous findings."""
    
    def format_results_for_llm(self, result: Dict[str, Any]) -> str:
        """Format deep research results for final LLM response"""
        if not result.get("success"):
            return f"Deep research failed: {result.get('error', 'Unknown error')}"
        
        research_data = result.get("research_data", {})
        if not research_data:
            return "Deep research completed but no research data available."
        
        # Start with the final answer if available
        final_answer = research_data.get("final_answer", "")
        if final_answer:
            formatted = final_answer
        else:
            formatted = f"Deep research completed for: {research_data.get('query', 'Unknown query')}"
        
        # Add research statistics
        summary = research_data.get("research_summary", {})
        if summary:
            formatted += "\n\n---\n\n### Research Statistics\n"
            formatted += f"- Searches performed: {summary.get('search_actions', 0)}\n"
            formatted += f"- Pages analyzed: {summary.get('urls_scraped', 0)}\n"
            if summary.get('total_cost', 0) > 0:
                formatted += f"- Research cost: ${summary.get('total_cost', 0):.4f}\n"
            formatted += f"- Tokens used: {summary.get('total_tokens', 0):,}\n"
        
        # Add activity breakdown
        activity_summary = research_data.get("activity_summary", {})
        if activity_summary.get('total_activities', 0) > 0:
            formatted += "\n### Activity Breakdown\n"
            for activity_type, count in activity_summary.get('by_type', {}).items():
                if count > 0:
                    formatted += f"- {activity_type.title()}: {count}\n"
        
        # Add source quality information if available
        sources = research_data.get("sources", [])
        if sources:
            high_relevance = len([s for s in sources if s.get('relevance', 0) >= 0.7])
            medium_relevance = len([s for s in sources if 0.5 <= s.get('relevance', 0) < 0.7])
            low_relevance = len([s for s in sources if s.get('relevance', 0) < 0.5])
            
            if high_relevance + medium_relevance + low_relevance > 0:
                formatted += "\n### Source Quality\n"
                formatted += f"- High relevance (≥0.7): {high_relevance}\n"
                formatted += f"- Medium relevance (0.5-0.7): {medium_relevance}\n"
                formatted += f"- Low relevance (<0.5): {low_relevance}\n"
        
        return formatted