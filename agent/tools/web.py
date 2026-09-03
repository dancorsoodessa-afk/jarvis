"""Web utilities and tools."""

import logging
import urllib.request
import urllib.parse
from typing import Dict, Any
import html.parser

logger = logging.getLogger("jarvis.tools.web")


class TitleParser(html.parser.HTMLParser):
    """Extract title from HTML."""
    
    def __init__(self):
        super().__init__()
        self.title = None
        self.in_title = False
    
    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
    
    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
    
    def handle_data(self, data):
        if self.in_title and not self.title:
            self.title = data.strip()


def open_url(url: str) -> str:
    """
    Open URL in default browser.
    
    Args:
        url: URL to open
    
    Returns:
        Confirmation message
    
    Raises:
        ValueError: If URL is invalid
    """
    if not url:
        raise ValueError("URL cannot be empty")
    
    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    try:
        # Validate URL format
        urllib.parse.urlparse(url)
        
        logger.info(f"Opening URL in browser: {url}")
        
        import webbrowser
        webbrowser.open(url)
        
        return f"Открыл {url} в браузере"
    
    except Exception as e:
        logger.error(f"Failed to open URL {url}: {e}")
        raise RuntimeError(f"Could not open URL: {e}")


def get_webpage_title(url: str) -> str:
    """
    Fetch and extract title from webpage.
    
    Args:
        url: URL to fetch
    
    Returns:
        Webpage title or error message
    """
    if not url:
        raise ValueError("URL cannot be empty")
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    try:
        logger.debug(f"Fetching title from {url}")
        
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.headers.get("content-type", "").startswith("text/html"):
                html_content = response.read(8192).decode("utf-8", errors="ignore")
                parser = TitleParser()
                parser.feed(html_content)
                
                if parser.title:
                    logger.info(f"Title found: {parser.title}")
                    return parser.title
                else:
                    logger.warning(f"No title found in {url}")
                    return "Заголовок не найден"
            else:
                logger.info(f"URL is not HTML: {url}")
                return "Страница не является HTML"
    
    except urllib.error.URLError as e:
        logger.error(f"URL error for {url}: {e}")
        return f"Ошибка доступа: {e}"
    except Exception as e:
        logger.error(f"Failed to fetch title from {url}: {e}")
        return f"Ошибка: {e}"


def search_web(query: str, num_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo (no API key required).
    
    Args:
        query: Search query
        num_results: Number of results to return
    
    Returns:
        String with search results or error message
    
    Raises:
        ValueError: If query is empty
    """
    if not query or not query.strip():
        raise ValueError("Search query cannot be empty")
    
    try:
        logger.info(f"Web search: {query}")
        
        # Use DuckDuckGo which is accessible without API
        search_url = f"https://duckduckgo.com/html?q={urllib.parse.quote(query)}"
        
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode("utf-8", errors="ignore")
            
            # Extract results (basic parsing)
            results = []
            lines = html_content.split('\n')
            
            for i, line in enumerate(lines):
                if 'class="result"' in line or 'class="result ' in line:
                    # Find title and link
                    for j in range(i, min(i + 10, len(lines))):
                        if '<a href=' in lines[j]:
                            # Extract URL and title
                            try:
                                start = lines[j].find('href="') + 6
                                end = lines[j].find('"', start)
                                link = lines[j][start:end]
                                
                                # Find title
                                title_start = lines[j].find('>') + 1
                                title_end = lines[j].find('<', title_start)
                                title = lines[j][title_start:title_end].strip()
                                
                                if link and title and not any(r[1] == title for r in results):
                                    results.append((link, title))
                                    if len(results) >= num_results:
                                        break
                            except:
                                continue
                    
                    if len(results) >= num_results:
                        break
            
            if results:
                logger.info(f"Found {len(results)} results")
                return '\n'.join(f"{i+1}. {title}\n   {link}" for i, (link, title) in enumerate(results))
            else:
                logger.warning(f"No results for: {query}")
                return "Результатов не найдено"
    
    except urllib.error.URLError as e:
        logger.error(f"Search error: {e}")
        return f"Ошибка подключения: {e}"
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return f"Ошибка поиска: {e}"
