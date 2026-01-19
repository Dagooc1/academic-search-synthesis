import requests
import arxiv
from typing import List, Dict
import time
from bs4 import BeautifulSoup
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import Config
except ImportError:
    class Config:
        ACADEMIC_DOMAINS = [
            '.edu', '.ac.', 'arxiv.org', 'scholar.google.com',
            'researchgate.net', 'academia.edu', 'springer.com',
            'ieee.org', 'acm.org', 'jstor.org', 'pubmed.ncbi.nlm.nih.gov'
        ]
        SEMANTIC_SCHOLAR_API_KEY = None
        TIMEOUT = 30

class AcademicSearcher:
    def __init__(self):
        self.config = Config()
    
    def search_all_sources(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search across multiple academic sources"""
        all_results = []
        
        try:
            # Search arXiv
            arxiv_results = self.search_arxiv(query, max(3, max_results//3))
            all_results.extend(arxiv_results)
        except Exception as e:
            print(f"arXiv search error: {e}")
        
        try:
            # Search Semantic Scholar
            semantic_results = self.search_semantic_scholar(query, max(3, max_results//3))
            all_results.extend(semantic_results)
        except Exception as e:
            print(f"Semantic Scholar search error: {e}")
        
        try:
            # Try Google Scholar (might not work without proper setup)
            scholar_results = self.search_google_scholar(query, max(3, max_results//3))
            all_results.extend(scholar_results)
        except Exception as e:
            print(f"Google Scholar search error: {e}")
        
        # Remove duplicates
        unique_results = self._remove_duplicates(all_results)
        
        return unique_results[:max_results]
    
    def search_google_scholar(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search Google Scholar - simplified version"""
        results = []
        try:
            # Using requests and BeautifulSoup as fallback
            url = f"https://scholar.google.com/scholar?q={requests.utils.quote(query)}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=self.config.TIMEOUT)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Simple extraction - Google Scholar structure might change
                for gs_div in soup.select('.gs_ri')[:max_results]:
                    title_elem = gs_div.select_one('.gs_rt')
                    author_elem = gs_div.select_one('.gs_a')
                    snippet_elem = gs_div.select_one('.gs_rs')
                    
                    if title_elem:
                        result = {
                            'source': 'Google Scholar',
                            'title': title_elem.text.replace('[PDF]', '').replace('[HTML]', '').strip(),
                            'authors': author_elem.text if author_elem else '',
                            'abstract': snippet_elem.text if snippet_elem else '',
                            'year': '',
                            'url': title_elem.find('a')['href'] if title_elem.find('a') else '',
                            'citations': 0
                        }
                        results.append(result)
        except Exception as e:
            print(f"Google Scholar simplified search error: {e}")
            # Return empty results if fails
            pass
        
        return results
    
    def search_arxiv(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search arXiv"""
        results = []
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance
            )
            
            for paper in search.results():
                result = {
                    'source': 'arXiv',
                    'title': paper.title,
                    'authors': [author.name for author in paper.authors],
                    'abstract': paper.summary[:500] + '...' if len(paper.summary) > 500 else paper.summary,
                    'year': paper.published.year,
                    'url': paper.entry_id,
                    'pdf_url': paper.pdf_url,
                    'doi': paper.doi if hasattr(paper, 'doi') else '',
                    'categories': paper.categories
                }
                results.append(result)
        except Exception as e:
            print(f"arXiv search error: {e}")
        
        return results
    
    def search_semantic_scholar(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search Semantic Scholar API"""
        results = []
        try:
            headers = {}
            if hasattr(self.config, 'SEMANTIC_SCHOLAR_API_KEY') and self.config.SEMANTIC_SCHOLAR_API_KEY:
                headers['x-api-key'] = self.config.SEMANTIC_SCHOLAR_API_KEY
            
            params = {
                'query': query,
                'limit': max_results,
                'fields': 'title,authors,abstract,venue,year,citationCount,url,openAccessPdf,paperId'
            }
            
            response = requests.get(
                'https://api.semanticscholar.org/graph/v1/paper/search',
                params=params,
                headers=headers,
                timeout=self.config.TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                for paper in data.get('data', []):
                    authors_list = []
                    for author in paper.get('authors', []):
                        if isinstance(author, dict):
                            authors_list.append(author.get('name', ''))
                        else:
                            authors_list.append(str(author))
                    
                    result = {
                        'source': 'Semantic Scholar',
                        'title': paper.get('title', ''),
                        'authors': authors_list,
                        'abstract': paper.get('abstract', '')[:500] + '...' if paper.get('abstract') and len(paper.get('abstract', '')) > 500 else paper.get('abstract', ''),
                        'year': paper.get('year', ''),
                        'url': f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}" if paper.get('paperId') else paper.get('url', ''),
                        'citations': paper.get('citationCount', 0),
                        'venue': paper.get('venue', ''),
                        'pdf_url': paper.get('openAccessPdf', {}).get('url', '') if isinstance(paper.get('openAccessPdf'), dict) else ''
                    }
                    results.append(result)
            else:
                print(f"Semantic Scholar API error: {response.status_code}")
        except Exception as e:
            print(f"Semantic Scholar search error: {e}")
        
        return results
    
    def _remove_duplicates(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate results"""
        unique_results = []
        seen_titles = set()
        
        for result in results:
            title = result.get('title', '').lower().strip()
            if not title:
                continue
                
            # Simple duplicate detection
            title_key = title[:50]  # Use first 50 chars as key
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_results.append(result)
        
        return unique_results