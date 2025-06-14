"""
Response formatting utilities for Discord LLM bot
Handles footnote extraction and standardized footer building
"""

import re
import logging

logger = logging.getLogger(__name__)


def extract_footnotes(content: str) -> tuple[str, str]:
    """Extract footnotes from content and return (cleaned_content, footnotes)"""
    
    # First check for the explicit separator used by deep research
    if '===FOOTNOTES===' in content:
        parts = content.split('===FOOTNOTES===', 1)
        if len(parts) == 2:
            cleaned_content = parts[0].strip()
            footnotes = parts[1].strip()
            return cleaned_content, footnotes
    
    # Fallback to older patterns for backward compatibility
    # Patterns: "References:", "Sources:", "Footnotes:", or lines starting with [1], 1., etc.
    footnote_patterns = [
        r'\n\n(References?:.*?)$',
        r'\n\n(Sources?:.*?)$', 
        r'\n\n(Footnotes?:.*?)$',
        r'\n\n(\[[0-9]+\].*?)$',
        r'\n\n([0-9]+\..*?)$'
    ]
    
    for pattern in footnote_patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            footnotes = match.group(1).strip()
            # Remove the footnotes from the main content
            cleaned_content = content[:match.start()] + content[match.end():]
            return cleaned_content.strip(), footnotes
    
    # No footnotes found
    return content, ""


def build_standardized_footer(
    model_name: str, 
    input_tokens: int = 0, 
    output_tokens: int = 0, 
    cost: float = 0, 
    elapsed_time: float = 0, 
    footnotes: str = "",
    use_fun: bool = False
) -> str:
    """Build standardized footer for AI responses"""
    # First line: Clean model name with fun mode indicator
    first_line = model_name
    if use_fun:
        first_line += " | Fun Mode"
    
    # Second line: Usage stats
    usage_parts = []
    
    # Input tokens (abbreviate with k after 1000)
    if input_tokens > 0:
        if input_tokens >= 1000:
            input_str = f"{input_tokens / 1000:.1f}k"
        else:
            input_str = str(input_tokens)
        usage_parts.append(f"{input_str} input tokens")
    
    # Output tokens (abbreviate with k after 1000)
    if output_tokens > 0:
        if output_tokens >= 1000:
            output_str = f"{output_tokens / 1000:.1f}k"
        else:
            output_str = str(output_tokens)
        usage_parts.append(f"{output_str} output tokens")
    
    # Cost (show $x.xx, but to first non-zero digit if under $0.01)
    if cost >= 0.01:
        cost_str = f"${cost:.2f}"
    elif cost > 0:
        # Find first non-zero digit
        decimal_places = 2
        while cost < (1 / (10 ** decimal_places)) and decimal_places < 10:
            decimal_places += 1
        cost_str = f"${cost:.{decimal_places}f}"
    else:
        cost_str = "$0.00"
    usage_parts.append(cost_str)
    
    # Time
    if elapsed_time > 0:
        usage_parts.append(f"{elapsed_time} seconds")
    
    second_line = " | ".join(usage_parts)
    
    # Add footnotes if provided (utilize extra footer space)
    if footnotes:
        # Ensure we stay within Discord's 2048 character footer limit
        available_space = 2048 - len(first_line) - len(second_line) - 10  # Buffer for newlines
        if available_space > 50:  # Only add if we have reasonable space
            truncated_footnotes = footnotes[:available_space]
            if len(footnotes) > available_space:
                truncated_footnotes = truncated_footnotes.rsplit(' ', 1)[0] + "..."
            return f"{first_line}\n{second_line}\n{truncated_footnotes}"
    
    return f"{first_line}\n{second_line}"


def format_usage_stats(input_tokens: int, output_tokens: int, cost: float, elapsed_time: float) -> str:
    """Format usage statistics into a human-readable string"""
    usage_parts = []
    
    # Format token counts
    if input_tokens > 0:
        if input_tokens >= 1000:
            usage_parts.append(f"{input_tokens / 1000:.1f}k input tokens")
        else:
            usage_parts.append(f"{input_tokens} input tokens")
    
    if output_tokens > 0:
        if output_tokens >= 1000:
            usage_parts.append(f"{output_tokens / 1000:.1f}k output tokens")
        else:
            usage_parts.append(f"{output_tokens} output tokens")
    
    # Format cost
    if cost >= 0.01:
        usage_parts.append(f"${cost:.2f}")
    elif cost > 0:
        decimal_places = 2
        while cost < (1 / (10 ** decimal_places)) and decimal_places < 10:
            decimal_places += 1
        usage_parts.append(f"${cost:.{decimal_places}f}")
    else:
        usage_parts.append("$0.00")
    
    # Format time
    if elapsed_time > 0:
        usage_parts.append(f"{elapsed_time:.2f}s")
    
    return " | ".join(usage_parts)


# Export functions for easy importing
__all__ = [
    'extract_footnotes', 
    'build_standardized_footer', 
    'format_usage_stats'
]