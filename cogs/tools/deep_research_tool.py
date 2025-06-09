"""
Deep research tool implementation using iterative web search and content analysis
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from .base_tool import BaseTool
from .web_search_tool import WebSearchTool
from .content_tool import ContentRetrievalTool
import logging

logger = logging.getLogger(__name__)


class DeepResearchTool(BaseTool):
    """Tool for conducting deep iterative research on a topic"""
    
    def __init__(self, exa_api_key: Optional[str] = None, openrouter_api_key: Optional[str] = None):
        super().__init__()
        self.exa_api_key = exa_api_key or os.getenv("EXA_API_KEY")
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        
        # Initialize sub-tools - use DuckDuckGo since it's more reliable without extra deps
        self.search_tool = WebSearchTool(use_ddg=True, exa_api_key=exa_api_key)
        self.content_tool = ContentRetrievalTool()
        
        # Research parameters
        self.min_iterations = 3
        self.max_iterations = 6
        self.max_sources_per_iteration = 5
    
    @property
    def name(self) -> str:
        return "deep_research"
    
    @property
    def description(self) -> str:
        return "Conduct deep iterative research on a topic using web search and content analysis. This tool performs multiple rounds of searching and content extraction to provide comprehensive, well-sourced answers."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The research topic or question to investigate thoroughly"
                },
                "min_iterations": {
                    "type": "integer",
                    "description": "Minimum number of research iterations (default: 3, max: 6)",
                    "default": 3
                },
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific focus areas to investigate",
                    "default": []
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, min_iterations: int = 3, focus_areas: List[str] = None) -> Dict[str, Any]:
        """Execute deep research on the given query"""
        # Validate and adjust parameters
        min_iterations = max(1, min(min_iterations, 6))
        focus_areas = focus_areas or []
        
        logger.info(f"Starting deep research for: {query}")
        
        # Initialize research session
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        research_state = {
            "query": query,
            "session_id": session_id,
            "iterations_completed": 0,
            "sources_found": [],
            "content_analyzed": [],
            "search_queries_used": set(),
            "findings": [],
            "focus_areas": focus_areas
        }
        
        try:
            # Conduct iterative research
            for iteration in range(self.max_iterations):
                logger.info(f"Research iteration {iteration + 1}/{self.max_iterations}")
                
                # Generate search query for this iteration
                search_query = await self._generate_search_query(research_state, iteration)
                
                if search_query in research_state["search_queries_used"]:
                    logger.info(f"Search query already used, trying variation")
                    search_query = await self._generate_search_query_variation(research_state, search_query)
                
                research_state["search_queries_used"].add(search_query)
                
                # Perform web search
                search_results = await self._perform_search(search_query)
                if not search_results.get("success"):
                    logger.warning(f"Search failed for query: {search_query}")
                    continue
                
                # Select and analyze top sources
                selected_urls = self._select_top_sources(search_results, research_state)
                if not selected_urls:
                    logger.warning(f"No new sources found in iteration {iteration + 1}")
                    continue
                
                # Extract and analyze content
                content_results = await self._analyze_content(selected_urls, query, research_state)
                
                # Update research state
                research_state["iterations_completed"] = iteration + 1
                research_state["sources_found"].extend(search_results.get("results", []))
                if content_results.get("success"):
                    research_state["content_analyzed"].extend(content_results.get("content", []))
                    research_state["findings"].extend(content_results.get("findings", []))
                
                # Check if we have enough information
                if (iteration + 1 >= min_iterations and 
                    len(research_state["findings"]) >= 3 and 
                    len(research_state["content_analyzed"]) >= 2):
                    logger.info(f"Sufficient information gathered after {iteration + 1} iterations")
                    break
            
            # Generate research data for LLM consumption
            research_data = await self._generate_final_report(research_state)
            
            return {
                "success": True,
                "session_id": session_id,
                "research_data": research_data
            }
        
        except Exception as e:
            logger.error(f"Deep research failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Research failed: {str(e)}",
                "query": query,
                "partial_results": research_state if 'research_state' in locals() else None
            }
    
    async def _generate_search_query(self, research_state: Dict, iteration: int) -> str:
        """Generate a search query for the current iteration"""
        base_query = research_state["query"]
        previous_queries = list(research_state["search_queries_used"])
        findings = research_state["findings"]
        focus_areas = research_state["focus_areas"]
        
        if iteration == 0:
            # First iteration: use base query
            return base_query
        
        # For subsequent iterations, generate focused queries
        if iteration == 1 and focus_areas:
            return f"{base_query} {focus_areas[0]}"
        elif iteration == 2 and len(focus_areas) > 1:
            return f"{base_query} {focus_areas[1]}"
        elif findings:
            # Generate query based on findings gap analysis
            return f"{base_query} latest developments recent updates"
        else:
            # Fallback variations
            variations = [
                f"{base_query} comprehensive guide",
                f"{base_query} expert analysis",
                f"{base_query} detailed review",
                f"{base_query} current trends"
            ]
            return variations[iteration % len(variations)]
    
    async def _generate_search_query_variation(self, research_state: Dict, original_query: str) -> str:
        """Generate a variation of a search query"""
        base_query = research_state["query"]
        variations = [
            f"{base_query} analysis",
            f"{base_query} overview",
            f"{base_query} comparison",
            f"{base_query} pros cons",
            f"{base_query} best practices"
        ]
        
        for variation in variations:
            if variation not in research_state["search_queries_used"]:
                return variation
        
        # If all variations used, add timestamp suffix
        return f"{original_query} {datetime.now().strftime('%Y')}"
    
    async def _perform_search(self, query: str) -> Dict[str, Any]:
        """Perform web search using the search tool"""
        try:
            return await self.search_tool.execute(query=query, max_results=self.max_sources_per_iteration)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _select_top_sources(self, search_results: Dict, research_state: Dict) -> List[str]:
        """Select top sources from search results, avoiding duplicates"""
        if not search_results.get("success") or not search_results.get("results"):
            return []
        
        # Get URLs we've already analyzed
        analyzed_urls = {content.get("url") for content in research_state["content_analyzed"]}
        
        # Select new URLs
        selected_urls = []
        for result in search_results["results"]:
            url = result.get("url")
            if url and url not in analyzed_urls and len(selected_urls) < 3:
                selected_urls.append(url)
        
        return selected_urls
    
    async def _analyze_content(self, urls: List[str], query: str, research_state: Dict) -> Dict[str, Any]:
        """Extract and analyze content from URLs using LLM for key content extraction"""
        if not urls:
            return {"success": False, "error": "No URLs to analyze"}
        
        try:
            # Extract content from each URL using content tool
            content_data = []
            findings = []
            previous_findings = research_state.get("findings", [])
            
            for url in urls:
                content_result = await self.content_tool.execute(url=url, extract_links=False)
                
                if content_result.get("success"):
                    raw_content_item = {
                        "url": url,
                        "title": content_result.get("title", ""),
                        "text": content_result.get("content", ""),
                        "content_length": content_result.get("content_length", 0)
                    }
                    
                    # Use LLM to extract key content and insights
                    extracted_data = await self._extract_key_content_with_llm(
                        raw_content_item, query, previous_findings
                    )
                    
                    # Only keep extracted, relevant content
                    content_item = {
                        "url": url,
                        "title": content_result.get("title", ""),
                        "extracted_content": extracted_data.get("extracted_content", ""),
                        "content_length": len(extracted_data.get("extracted_content", "")),
                        "original_length": content_result.get("content_length", 0)
                    }
                    content_data.append(content_item)
                    
                    # Create finding from LLM extraction
                    if extracted_data.get("new_information") and extracted_data.get("key_insights"):
                        finding = {
                            "url": url,
                            "title": content_result.get("title", ""),
                            "key_insights": extracted_data.get("key_insights", []),
                            "relevance_score": extracted_data.get("relevance_score", 0.0),
                            "new_information": extracted_data.get("new_information", True)
                        }
                        findings.append(finding)
                else:
                    logger.warning(f"Failed to extract content from {url}: {content_result.get('error')}")
            
            return {
                "success": True,
                "content": content_data,
                "findings": findings
            }
        
        except Exception as e:
            logger.error(f"Content analysis failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_key_points(self, text: str, query: str) -> List[str]:
        """Extract key points from text relevant to the query, following system prompt style"""
        # Simple keyword-based extraction
        query_terms = query.lower().split()
        sentences = text.split('.')
        
        relevant_sentences = []
        for sentence in sentences[:20]:  # Limit to first 20 sentences
            sentence = sentence.strip()
            if len(sentence) > 20 and any(term in sentence.lower() for term in query_terms):
                # Clean up sentence to follow style guidelines
                cleaned = self._clean_sentence_for_style(sentence)
                if cleaned:
                    relevant_sentences.append(cleaned)
        
        return relevant_sentences[:5]  # Return top 5 relevant sentences
    
    def _clean_sentence_for_style(self, sentence: str) -> str:
        """Clean sentence to follow system prompt writing style"""
        # Remove excessive punctuation and clean up
        sentence = sentence.strip()
        
        # Skip sentences that are mostly punctuation or very short
        if len(sentence.replace('.', '').replace(',', '').replace('!', '').strip()) < 15:
            return ""
        
        # Remove em dashes as per style guide
        sentence = sentence.replace('—', '-')
        
        # Ensure sentence doesn't end with multiple punctuation
        while sentence.endswith('..') or sentence.endswith('!!') or sentence.endswith('??'):
            sentence = sentence[:-1]
        
        # Ensure proper ending punctuation
        if not sentence.endswith('.') and not sentence.endswith('!') and not sentence.endswith('?'):
            sentence += '.'
            
        return sentence
    
    def _calculate_relevance(self, text: str, query: str) -> float:
        """Calculate relevance score between text and query"""
        if not text or not query:
            return 0.0
        
        query_terms = set(query.lower().split())
        text_terms = set(text.lower().split())
        
        if not query_terms:
            return 0.0
        
        # Simple Jaccard similarity
        intersection = len(query_terms.intersection(text_terms))
        union = len(query_terms.union(text_terms))
        
        return intersection / union if union > 0 else 0.0
    
    async def _generate_final_report(self, research_state: Dict) -> Dict[str, Any]:
        """Generate raw research data for LLM to use in crafting final response"""
        query = research_state["query"]
        findings = research_state["findings"]
        sources = research_state["sources_found"]
        content_analyzed = research_state["content_analyzed"]
        
        # Sort findings by relevance
        sorted_findings = sorted(findings, key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # Prepare unique sources with full content
        unique_sources = []
        seen_urls = set()
        for source in sources:
            url = source.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(source)
        
        # Compile all research data for LLM consumption
        research_data = {
            "query": query,
            "research_summary": {
                "iterations_completed": research_state['iterations_completed'],
                "sources_found": len(sources),
                "sources_analyzed": len(content_analyzed),
                "findings_extracted": len(findings)
            },
            "content_analyzed": content_analyzed,  # Full content from all analyzed sources
            "key_findings": sorted_findings,       # All findings with relevance scores
            "all_sources": unique_sources,         # All unique sources found
            "search_queries_used": list(research_state["search_queries_used"])
        }
        
        return research_data
    
    async def _extract_key_content_with_llm(self, content_item: Dict, query: str, previous_findings: List[Dict] = None) -> Dict[str, Any]:
        """Use LLM to extract key content relevant to the research query"""
        if not self.openrouter_api_key:
            # Fallback to simple extraction if no API key
            return {
                "extracted_content": content_item.get("text", "")[:1000],  # Simple truncation
                "key_insights": self._extract_key_points(content_item.get("text", ""), query),
                "relevance_score": self._calculate_relevance(content_item.get("text", ""), query)
            }
        
        try:
            # Import here to avoid circular imports
            import openai
            
            client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_api_key
            )
            
            # Prepare context about previous findings
            context = ""
            if previous_findings:
                context = "\nPrevious research findings:\n"
                for i, finding in enumerate(previous_findings[-3:], 1):  # Last 3 findings for context
                    context += f"{i}. From {finding.get('title', 'Source')}: {', '.join(finding.get('key_insights', [])[:2])}\n"
            
            # Create extraction prompt with research guidance
            extraction_prompt = f"""You are an autonomous research assistant conducting deep research on: "{query}"

{context}

You must analyze the following source content and extract key information. Follow these guidelines:

RESEARCH PRINCIPLES:
- Build upon information from previous findings
- Extract specific facts, statistics, and insights
- Focus on information directly relevant to the research query
- Identify unique information not covered in previous findings
- Prioritize authoritative and current information

CONTENT ANALYSIS TASK:
Source: {content_item.get('title', 'Unknown')}
URL: {content_item.get('url', 'Unknown')}

Content to analyze:
{content_item.get('text', '')[:3000]}  

Respond with a JSON object containing:
{{
  "key_insights": ["detailed insight paragraph with quotes if relevant", "another comprehensive insight", "third insight with specific details"],
  "extracted_content": "concise summary of most relevant content",
  "relevance_score": 0.8,
  "new_information": true/false
}}

Each key insight should be a comprehensive paragraph that includes specific details, quotes, and concrete information from the source."""

            response = client.chat.completions.create(
                model="openai/gpt-4.1-nano",
                messages=[
                    {
                        "role": "user",
                        "content": extraction_prompt
                    }
                ],
                max_tokens=800,
                temperature=0.1
            )
            
            # Parse the JSON response
            import json
            extracted_data = json.loads(response.choices[0].message.content)
            
            # Validate and clean the response
            result = {
                "extracted_content": extracted_data.get("extracted_content", "")[:1000],
                "key_insights": extracted_data.get("key_insights", [])[:5],  # Limit insights
                "relevance_score": min(1.0, max(0.0, extracted_data.get("relevance_score", 0.5))),
                "new_information": extracted_data.get("new_information", True)
            }
            
            return result
            
        except Exception as e:
            logger.error(f"LLM content extraction failed: {e}")
            # Fallback to simple extraction
            return {
                "extracted_content": content_item.get("text", "")[:1000],
                "key_insights": self._extract_key_points(content_item.get("text", ""), query),
                "relevance_score": self._calculate_relevance(content_item.get("text", ""), query),
                "new_information": True
            }
    
    def format_results_for_llm(self, result: Dict[str, Any]) -> str:
        """Format deep research results for LLM to use in crafting response"""
        if not result.get("success"):
            return f"Deep research failed: {result.get('error', 'Unknown error')}"
        
        research_data = result.get("research_data", {})
        if not research_data:
            return "Deep research completed but no research data available."
        
        # Present the research data clearly for LLM consumption
        formatted = f"Deep research completed for query: {research_data.get('query')}\n\n"
        
        # Research summary
        summary = research_data.get("research_summary", {})
        formatted += f"Research completed: {summary.get('iterations_completed')} iterations, "
        formatted += f"{summary.get('sources_analyzed')} sources analyzed, "
        formatted += f"{summary.get('sources_found')} total sources found\n\n"
        
        # Extracted content from analyzed sources
        content_analyzed = research_data.get("content_analyzed", [])
        if content_analyzed:
            formatted += "EXTRACTED CONTENT FROM SOURCES:\n"
            for i, content in enumerate(content_analyzed, 1):
                formatted += f"\nSource {i}: {content.get('title', 'Untitled')}\n"
                formatted += f"URL: {content.get('url', 'No URL')}\n"
                extracted = content.get('extracted_content', '')
                if extracted:
                    formatted += f"Key Content: {extracted}\n"
                formatted += f"Compression: {content.get('original_length', 0)} → {content.get('content_length', 0)} characters\n"
        
        # Key findings with insights
        key_findings = research_data.get("key_findings", [])
        if key_findings:
            formatted += "\nKEY FINDINGS AND INSIGHTS:\n"
            for i, finding in enumerate(key_findings, 1):
                formatted += f"\nFinding {i} (relevance: {finding.get('relevance_score', 0):.2f}):\n"
                formatted += f"Source: {finding.get('title', 'Unknown')} - {finding.get('url', 'No URL')}\n"
                insights = finding.get('key_insights', [])
                if insights:
                    formatted += "Key Insights:\n"
                    for insight in insights:
                        formatted += f"- {insight}\n"
        
        # Available sources for citations
        all_sources = research_data.get("all_sources", [])
        if all_sources:
            formatted += f"\nAVAILABLE SOURCES FOR CITATIONS ({len(all_sources)} total):\n"
            for i, source in enumerate(all_sources[:10], 1):  # Limit for readability
                formatted += f"{i}. {source.get('title', 'Untitled')} - {source.get('url', 'No URL')}\n"
        
        formatted += "\n" + self._get_research_system_prompt()
        
        return formatted
    
    def _get_research_system_prompt(self) -> str:
        """Get the system prompt that guides the deep research process"""
        return """RESEARCH ASSISTANT INSTRUCTIONS:

You are an autonomous research assistant. You have conducted comprehensive research with multiple iterations of web search and content analysis. Use this research data to provide a thorough, well-structured response.

IMPORTANT GUIDELINES:
1. Build upon information from all research iterations and synthesise findings
2. Reference and cite specific sources using the URLs provided
3. Structure your response with clear sections if appropriate
4. Include specific information, facts, and insights from your research
5. Use inline citations in the format [1], [2], etc. to reference sources
6. Provide a comprehensive, standalone response that reads like a research report
7. Be thorough but concise - focus on the most relevant and authoritative information

WRITING STYLE:
- Use clear, direct language and avoid overly complex terminology
- Use the active voice and avoid adverbs
- Avoid buzzwords and use plain English
- Use British spelling
- Express calm confidence, avoid being overly enthusiastic
- Do not use the em dash: —

DISCORD FORMATTING (use when appropriate):
*italics*, **bold**, ***bold italics***, __underline__, ~~strikethrough~~
# Big Header, ## Medium Header, ### Small Header
- List Item
  - Nested List Item
`Codeblock`, ```Multi-line codeblock```
> Single-line block quote
>>> Multi-line block quote

CITATION FORMAT:
- Use inline citations: [1], [2], [3] etc.
- Match citation numbers to the source URLs provided in the research data
- End with footnotes: -# 1. {url}

RESPONSE STRUCTURE:
- Start with a brief overview/summary
- Use clear headings and sections to organise information
- Include specific details, quotes, and data points from sources
- End with properly formatted source citations

Use the research data above to craft your comprehensive response following these guidelines."""
