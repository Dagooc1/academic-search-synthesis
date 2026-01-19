from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import os
import requests
import arxiv
import re
import json
from datetime import datetime
import csv
import io
import wikipediaapi
from bs4 import BeautifulSoup
import time
from urllib.parse import quote_plus, urlencode
import concurrent.futures
from functools import wraps
import hashlib
import random
import logging
from fake_useragent import UserAgent
import urllib3
from tenacity import retry, stop_after_attempt, wait_random_exponential

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.secret_key = os.getenv('SECRET_KEY', 'academic-search-secret-key-123')
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Cache for search results (simple in-memory cache)
search_cache = {}

# User Agent generator
ua = UserAgent()

# Wikipedia API
wiki_wiki = wikipediaapi.Wikipedia(
    language='en',
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent='AcademicResearchHub/1.0'
)

# Scholar proxies (you can add your own proxy list)
SCHOLAR_PROXIES = [
    None,  # Try without proxy first
]

def cache_search(func):
    """Decorator to cache search results"""
    @wraps(func)
    def wrapper(query, max_results=10):
        # Create cache key
        cache_key = hashlib.md5(f"{func.__name__}_{query}_{max_results}".encode()).hexdigest()
        
        # Check cache
        if cache_key in search_cache:
            cached_time, results = search_cache[cache_key]
            # Cache valid for 1 hour
            if time.time() - cached_time < 3600:
                logger.info(f"Using cached results for {func.__name__}: {query}")
                return results
        
        # Execute search
        results = func(query, max_results)
        
        # Store in cache
        search_cache[cache_key] = (time.time(), results)
        
        return results
    return wrapper

@cache_search
@retry(stop=stop_after_attempt(3), wait=wait_random_exponential(multiplier=1, max=60))
def search_google_scholar(query, max_results=10):
    """Search Google Scholar with web scraping"""
    results = []
    
    try:
        # Google Scholar search URL
        base_url = "https://scholar.google.com/scholar"
        params = {
            'hl': 'en',
            'q': query,
            'as_vis': '1',  # Exclude citations
            'as_sdt': '0,5'  # All articles
        }
        
        headers = {
            'User-Agent': ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        url = f"{base_url}?{urlencode(params)}"
        
        logger.info(f"Searching Google Scholar: {query}")
        
        # Try with different proxies
        for proxy in SCHOLAR_PROXIES:
            try:
                response = requests.get(
                    url, 
                    headers=headers, 
                    proxies=proxy,
                    timeout=15,
                    verify=False
                )
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Find all result containers
                    result_divs = soup.find_all('div', class_='gs_ri')
                    
                    for i, div in enumerate(result_divs[:max_results]):
                        try:
                            # Extract title and URL
                            title_elem = div.find('h3', class_='gs_rt')
                            if not title_elem:
                                continue
                                
                            title_link = title_elem.find('a')
                            if title_link:
                                title = title_link.text.strip()
                                url = title_link.get('href', '')
                            else:
                                title = title_elem.text.strip()
                                url = ''
                            
                            # Remove [PDF], [BOOK], etc. from title
                            title = re.sub(r'\[.*?\]', '', title).strip()
                            
                            # Extract authors and publication info
                            authors_div = div.find('div', class_='gs_a')
                            authors_text = authors_div.text.strip() if authors_div else ''
                            
                            # Parse authors and year
                            authors = []
                            year = None
                            journal = ''
                            
                            if authors_text:
                                # Pattern for extracting authors and year
                                parts = authors_text.split('-')
                                if parts:
                                    authors_part = parts[0].strip()
                                    authors = [a.strip() for a in authors_part.split(',')]
                                    
                                    # Try to extract year
                                    year_match = re.search(r'(\d{4})', authors_text)
                                    if year_match:
                                        year = int(year_match.group(1))
                                    
                                    # Try to extract journal
                                    if len(parts) > 1:
                                        journal = parts[1].strip()
                            
                            # Extract abstract/snippet
                            snippet_div = div.find('div', class_='gs_rs')
                            abstract = snippet_div.text.strip() if snippet_div else 'Abstract not available from Google Scholar'
                            
                            # Extract citation count
                            citations_span = div.find('div', class_='gs_fl').find('a', string=re.compile('Cited by'))
                            citations = 0
                            if citations_span:
                                citations_text = citations_span.text
                                citations_match = re.search(r'Cited by (\d+)', citations_text)
                                if citations_match:
                                    citations = int(citations_match.group(1))
                            
                            # Extract PDF link
                            pdf_link = None
                            pdf_elem = title_elem.find('span', class_='gs_ctg2')
                            if pdf_elem and pdf_elem.text == '[PDF]':
                                pdf_link = url
                            
                            # Generate citation formats
                            citations_formatted = generate_citations(
                                title, authors, year or datetime.now().year, 
                                url, ''
                            )
                            
                            results.append({
                                'source': 'Google Scholar',
                                'title': title,
                                'authors': authors if authors else ['Unknown Authors'],
                                'abstract': abstract,
                                'year': year or datetime.now().year,
                                'url': url,
                                'pdf_url': pdf_link or '',
                                'doi': '',
                                'citations': citations,
                                'reliability_score': 0.9,
                                'reliability_level': 'Excellent',
                                'citations_formatted': citations_formatted,
                                'journal': journal,
                                'full_text_available': bool(pdf_link),
                                'search_timestamp': time.time(),
                                'id': f"gs_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                            })
                            
                            logger.debug(f"Found Google Scholar result: {title[:50]}...")
                            
                        except Exception as e:
                            logger.warning(f"Error parsing Google Scholar result {i}: {e}")
                            continue
                    
                    # Break if successful
                    logger.info(f"Google Scholar found {len(results)} results")
                    break
                    
                else:
                    logger.warning(f"Google Scholar returned status {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"Google Scholar request failed with proxy {proxy}: {e}")
                continue
        
        if not results:
            logger.warning(f"No results found on Google Scholar for: {query}")
    
    except Exception as e:
        logger.error(f"Google Scholar search error: {e}", exc_info=True)
    
    return results

@cache_search
def search_arxiv(query, max_results=10):
    """Search arXiv for papers with full details"""
    results = []
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )
        
        for paper in client.results(search):
            authors = [author.name for author in paper.authors]
            
            # Generate citation formats
            citations = generate_citations(
                paper.title, 
                authors, 
                paper.published.year, 
                paper.entry_id, 
                paper.doi if hasattr(paper, 'doi') else ''
            )
            
            results.append({
                'source': 'arXiv',
                'title': paper.title,
                'authors': authors,
                'abstract': paper.summary,
                'year': paper.published.year,
                'url': paper.entry_id,
                'pdf_url': paper.pdf_url,
                'doi': paper.doi if hasattr(paper, 'doi') else '',
                'citations': 0,
                'reliability_score': 0.8,
                'reliability_level': 'Very High',
                'citations_formatted': citations,
                'journal': 'arXiv preprint',
                'full_text_available': True,
                'search_timestamp': time.time(),
                'id': f"arxiv_{hashlib.md5(paper.title.encode()).hexdigest()[:8]}"
            })
    except Exception as e:
        logger.error(f"arXiv error: {e}", exc_info=True)
    
    return results

@cache_search
def search_semantic_scholar(query, max_results=10):
    """Search Semantic Scholar with full details"""
    results = []
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            'query': query,
            'limit': max_results,
            'fields': 'title,authors,abstract,year,citationCount,url,openAccessPdf,externalIds,venue,publicationVenue,tldr,fieldsOfStudy'
        }
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            for paper in data.get('data', []):
                authors = []
                for author in paper.get('authors', []):
                    if isinstance(author, dict):
                        authors.append(author.get('name', ''))
                
                doi = ''
                if paper.get('externalIds') and isinstance(paper['externalIds'], dict):
                    doi = paper['externalIds'].get('DOI', '')
                
                venue = paper.get('venue', '')
                if not venue and paper.get('publicationVenue'):
                    venue = paper['publicationVenue'].get('name', '')
                
                # Try to get TLDR (summary) if available
                tldr = ''
                if paper.get('tldr'):
                    tldr_content = paper['tldr'].get('text', '')
                    if tldr_content:
                        tldr = tldr_content
                
                citations = generate_citations(
                    paper.get('title', ''), 
                    authors, 
                    paper.get('year', ''), 
                    paper.get('url', ''), 
                    doi
                )
                
                results.append({
                    'source': 'Semantic Scholar',
                    'title': paper.get('title', ''),
                    'authors': authors,
                    'abstract': paper.get('abstract', '') or tldr or 'Abstract not available',
                    'year': paper.get('year', ''),
                    'url': paper.get('url', ''),
                    'pdf_url': paper.get('openAccessPdf', {}).get('url', '') if paper.get('openAccessPdf') else '',
                    'doi': doi,
                    'citations': paper.get('citationCount', 0),
                    'reliability_score': 0.85,
                    'reliability_level': 'Excellent',
                    'citations_formatted': citations,
                    'journal': venue,
                    'full_text_available': paper.get('openAccessPdf') is not None,
                    'search_timestamp': time.time(),
                    'id': f"ss_{hashlib.md5(paper.get('title', '').encode()).hexdigest()[:8]}"
                })
    except Exception as e:
        logger.error(f"Semantic Scholar error: {e}", exc_info=True)
    
    return results

@cache_search
def search_wikipedia(query, max_results=5):
    """Search Wikipedia for articles"""
    results = []
    try:
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote_plus(query)}&format=json&srlimit={max_results}"
        response = requests.get(search_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            for item in data.get('query', {}).get('search', []):
                page_id = item.get('pageid')
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                
                page = wiki_wiki.page(title)
                
                if page.exists():
                    soup = BeautifulSoup(snippet, 'html.parser')
                    clean_snippet = soup.get_text()
                    
                    results.append({
                        'source': 'Wikipedia',
                        'title': title,
                        'authors': ['Wikipedia Contributors'],
                        'abstract': clean_snippet + '...',
                        'year': datetime.now().year,
                        'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                        'pdf_url': '',
                        'doi': '',
                        'citations': 0,
                        'reliability_score': 0.7,
                        'reliability_level': 'High',
                        'citations_formatted': {
                            'APA': f"Wikipedia contributors. ({datetime.now().year}). {title}. In Wikipedia. Retrieved from https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                            'MLA': f'"{title}." Wikipedia, Wikimedia Foundation, {datetime.now().year}, en.wikipedia.org/wiki/{title.replace(" ", "_")}.'
                        },
                        'journal': 'Wikipedia',
                        'full_text_available': True,
                        'search_timestamp': time.time(),
                        'id': f"wiki_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                    })
    except Exception as e:
        logger.error(f"Wikipedia error: {e}", exc_info=True)
    
    return results

@cache_search
def search_crossref(query, max_results=5):
    """Search Crossref for academic works"""
    results = []
    try:
        url = f"https://api.crossref.org/works?query={quote_plus(query)}&rows={max_results}"
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            for item in data.get('message', {}).get('items', []):
                title = item.get('title', [''])[0]
                if not title:
                    continue
                
                authors = []
                for author in item.get('author', []):
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if given and family:
                        authors.append(f"{given} {family}")
                    elif family:
                        authors.append(family)
                
                abstract = item.get('abstract', '')
                year = item.get('published-print', {}).get('date-parts', [[datetime.now().year]])[0][0]
                doi = item.get('DOI', '')
                url = f"https://doi.org/{doi}" if doi else item.get('URL', '')
                
                journal = item.get('container-title', [''])[0]
                
                results.append({
                    'source': 'Crossref',
                    'title': title,
                    'authors': authors if authors else ['Unknown Authors'],
                    'abstract': abstract or 'Abstract not available',
                    'year': year,
                    'url': url,
                    'pdf_url': '',
                    'doi': doi,
                    'citations': item.get('is-referenced-by-count', 0),
                    'reliability_score': 0.8,
                    'reliability_level': 'Very High',
                    'citations_formatted': generate_citations(title, authors, year, url, doi),
                    'journal': journal or 'Academic Publication',
                    'full_text_available': bool(doi),
                    'search_timestamp': time.time(),
                    'id': f"cr_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                })
    except Exception as e:
        logger.error(f"Crossref error: {e}", exc_info=True)
    
    return results

@cache_search
def search_doaj(query, max_results=5):
    """Search Directory of Open Access Journals"""
    results = []
    try:
        url = f"https://doaj.org/api/v2/search/articles/{quote_plus(query)}?page=1&pageSize={max_results}"
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            for article in data.get('results', []):
                title = article.get('bibjson', {}).get('title', '')
                if not title:
                    continue
                    
                authors = []
                for author in article.get('bibjson', {}).get('author', []):
                    if isinstance(author, dict):
                        name = author.get('name', '')
                        if name:
                            authors.append(name)
                
                abstract = article.get('bibjson', {}).get('abstract', '')
                year = article.get('bibjson', {}).get('year', datetime.now().year)
                doi = article.get('bibjson', {}).get('identifier', [{}])[0].get('id', '') if article.get('bibjson', {}).get('identifier') else ''
                
                url = ''
                if doi:
                    url = f"https://doi.org/{doi}"
                elif article.get('bibjson', {}).get('link'):
                    url = article['bibjson']['link'][0].get('url', '')
                
                results.append({
                    'source': 'DOAJ',
                    'title': title,
                    'authors': authors if authors else ['Unknown Authors'],
                    'abstract': abstract or 'Abstract not available',
                    'year': year,
                    'url': url,
                    'pdf_url': '',
                    'doi': doi,
                    'citations': 0,
                    'reliability_score': 0.75,
                    'reliability_level': 'High',
                    'citations_formatted': generate_citations(title, authors, year, url, doi),
                    'journal': 'Open Access Journal',
                    'full_text_available': True,
                    'search_timestamp': time.time(),
                    'id': f"doaj_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                })
    except Exception as e:
        logger.error(f"DOAJ error: {e}", exc_info=True)
    
    return results

def search_springer(query, max_results=5):
    """Search Springer publications"""
    results = []
    try:
        api_key = os.getenv('SPRINGER_API_KEY', '')
        if not api_key:
            return results
            
        url = "https://api.springernature.com/meta/v2/json"
        params = {
            'q': query,
            'api_key': api_key,
            'p': max_results,
            's': 1
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            for record in data.get('records', []):
                title = record.get('title', '')
                if not title:
                    continue
                
                authors = []
                creators = record.get('creators', [])
                for creator in creators:
                    if isinstance(creator, dict):
                        name = creator.get('creator', '')
                        if name:
                            authors.append(name)
                
                abstract = record.get('abstract', '')
                year = record.get('publicationDate', '').split('-')[0] if record.get('publicationDate') else datetime.now().year
                doi = record.get('doi', '')
                url = record.get('url', [{}])[0].get('value', '') if record.get('url') else f"https://doi.org/{doi}" if doi else ''
                
                journal = record.get('publicationName', '')
                
                results.append({
                    'source': 'Springer',
                    'title': title,
                    'authors': authors if authors else ['Unknown Authors'],
                    'abstract': abstract or 'Abstract not available',
                    'year': int(year) if year and year.isdigit() else datetime.now().year,
                    'url': url,
                    'pdf_url': '',
                    'doi': doi,
                    'citations': 0,
                    'reliability_score': 0.85,
                    'reliability_level': 'Excellent',
                    'citations_formatted': generate_citations(title, authors, year, url, doi),
                    'journal': journal,
                    'full_text_available': bool(doi),
                    'search_timestamp': time.time(),
                    'id': f"springer_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                })
    except Exception as e:
        logger.error(f"Springer error: {e}", exc_info=True)
    
    return results

def search_ieee(query, max_results=5):
    """Search IEEE publications"""
    results = []
    try:
        api_key = os.getenv('IEEE_API_KEY', '')
        if not api_key:
            return results
            
        url = "http://ieeexploreapi.ieee.org/api/v1/search/articles"
        params = {
            'querytext': query,
            'apikey': api_key,
            'max_records': max_results,
            'format': 'json'
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            for article in data.get('articles', []):
                title = article.get('title', '')
                if not title:
                    continue
                
                authors = []
                for author in article.get('authors', {}).get('authors', []):
                    full_name = author.get('full_name', '')
                    if full_name:
                        authors.append(full_name)
                
                abstract = article.get('abstract', '')
                year = article.get('publication_year', datetime.now().year)
                doi = article.get('doi', '')
                url = article.get('html_url', f"https://doi.org/{doi}" if doi else '')
                
                journal = article.get('publication_title', '')
                
                results.append({
                    'source': 'IEEE',
                    'title': title,
                    'authors': authors if authors else ['Unknown Authors'],
                    'abstract': abstract or 'Abstract not available',
                    'year': year,
                    'url': url,
                    'pdf_url': article.get('pdf_url', ''),
                    'doi': doi,
                    'citations': article.get('citing_paper_count', 0),
                    'reliability_score': 0.9,
                    'reliability_level': 'Excellent',
                    'citations_formatted': generate_citations(title, authors, year, url, doi),
                    'journal': journal,
                    'full_text_available': bool(article.get('pdf_url')),
                    'search_timestamp': time.time(),
                    'id': f"ieee_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                })
    except Exception as e:
        logger.error(f"IEEE error: {e}", exc_info=True)
    
    return results

def search_pubmed(query, max_results=5):
    """Search PubMed for medical literature"""
    results = []
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            'db': 'pubmed',
            'term': query,
            'retmode': 'json',
            'retmax': max_results
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            ids = data.get('esearchresult', {}).get('idlist', [])
            
            if ids:
                # Fetch details for each ID
                fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                fetch_params = {
                    'db': 'pubmed',
                    'id': ','.join(ids),
                    'retmode': 'json'
                }
                
                fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
                
                if fetch_response.status_code == 200:
                    details = fetch_response.json()
                    
                    for pubmed_id in ids:
                        article = details.get('result', {}).get(pubmed_id, {})
                        if article:
                            title = article.get('title', '')
                            if not title:
                                continue
                            
                            authors = []
                            for author in article.get('authors', []):
                                name = author.get('name', '')
                                if name:
                                    authors.append(name)
                            
                            abstract = article.get('abstract', '')
                            year = article.get('pubdate', '').split(' ')[0] if article.get('pubdate') else datetime.now().year
                            
                            if year and not year.isdigit():
                                year_match = re.search(r'(\d{4})', year)
                                year = year_match.group(1) if year_match else datetime.now().year
                            
                            doi = ''
                            for article_id in article.get('articleids', []):
                                if article_id.get('idtype') == 'doi':
                                    doi = article_id.get('value', '')
                                    break
                            
                            url = f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/"
                            if doi:
                                url = f"https://doi.org/{doi}"
                            
                            journal = article.get('fulljournalname', '')
                            
                            results.append({
                                'source': 'PubMed',
                                'title': title,
                                'authors': authors if authors else ['Unknown Authors'],
                                'abstract': abstract or 'Abstract not available',
                                'year': int(year) if year and year.isdigit() else datetime.now().year,
                                'url': url,
                                'pdf_url': '',
                                'doi': doi,
                                'citations': 0,
                                'reliability_score': 0.9,
                                'reliability_level': 'Excellent',
                                'citations_formatted': generate_citations(title, authors, year, url, doi),
                                'journal': journal,
                                'full_text_available': False,
                                'search_timestamp': time.time(),
                                'id': f"pmid_{pubmed_id}"
                            })
    except Exception as e:
        logger.error(f"PubMed error: {e}", exc_info=True)
    
    return results

def search_parallel(query, max_results=15, include_google_scholar=True):
    """Search all sources in parallel"""
    search_functions = []
    
    # High priority sources
    if include_google_scholar:
        search_functions.append((search_google_scholar, min(8, max_results//2)))
    
    search_functions.extend([
        (search_semantic_scholar, min(6, max_results//3)),
        (search_arxiv, min(5, max_results//4)),
        (search_crossref, min(4, max_results//5)),
        (search_pubmed, min(3, max_results//6)),
        (search_doaj, min(3, max_results//6)),
        (search_wikipedia, min(2, max_results//8)),
    ])
    
    # Optional sources (require API keys)
    if os.getenv('SPRINGER_API_KEY'):
        search_functions.append((search_springer, min(3, max_results//6)))
    
    if os.getenv('IEEE_API_KEY'):
        search_functions.append((search_ieee, min(3, max_results//6)))
    
    all_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(search_functions)) as executor:
        future_to_func = {
            executor.submit(func, query, count): func.__name__
            for func, count in search_functions
        }
        
        for future in concurrent.futures.as_completed(future_to_func):
            func_name = future_to_func[future]
            try:
                results = future.result(timeout=30)
                all_results.extend(results)
                logger.info(f"✓ {func_name}: Found {len(results)} results")
            except Exception as e:
                logger.error(f"✗ {func_name} failed: {e}")
    
    return all_results

def generate_citations(title, authors, year, url, doi=''):
    """Generate multiple citation formats"""
    if not authors or len(authors) == 0:
        authors = ["Unknown"]
    
    # Format author list for citations
    if len(authors) == 1:
        apa_authors = f"{authors[0]}"
        mla_authors = f"{authors[0]}"
    elif len(authors) == 2:
        apa_authors = f"{authors[0]} & {authors[1]}"
        mla_authors = f"{authors[0]}, and {authors[1]}"
    else:
        apa_authors = f"{authors[0]} et al."
        mla_authors = f"{authors[0]}, et al."
    
    current_year = datetime.now().year
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    citations = {
        'APA': f"{apa_authors} ({year}). {title}. Retrieved from {url}",
        'MLA': f'{mla_authors}. "{title}." {year}. Web. {current_year}.',
        'Chicago': f'{authors[0]} et al. "{title}." ({year}). {url}',
        'Harvard': f'{authors[0]} et al. ({year}) {title}. Available at: {url} (Accessed: {current_date})',
        'IEEE': f'[{authors[0][0]}. {authors[0].split()[-1]} et al., "{title}," {year}.]',
        'Vancouver': f'{apa_authors}. {title}. [Internet]. {year}. Available from: {url}'
    }
    
    if doi:
        citations['APA'] = f"{apa_authors} ({year}). {title}. https://doi.org/{doi}"
        citations['MLA'] = f'{mla_authors}. "{title}." {year}. doi:{doi}.'
        citations['Chicago'] = f'{authors[0]} et al. "{title}." ({year}). https://doi.org/{doi}'
    
    return citations

def calculate_reliability_score(result):
    """Calculate enhanced reliability score"""
    score = result.get('reliability_score', 0.5)
    
    # Source adjustments
    source = result.get('source', '')
    if source in ['Google Scholar', 'PubMed', 'IEEE', 'Springer']:
        score = max(score, 0.85)
    elif source == 'Semantic Scholar':
        score = max(score, 0.8)
    elif source in ['arXiv', 'Crossref']:
        score = max(score, 0.75)
    elif source == 'DOAJ':
        score = max(score, 0.7)
    elif source == 'Wikipedia':
        score = 0.65
    
    # Year adjustments
    year = result.get('year')
    if year and isinstance(year, int):
        current_year = datetime.now().year
        if current_year - year <= 1:
            score += 0.15
        elif current_year - year <= 3:
            score += 0.1
        elif current_year - year <= 5:
            score += 0.05
    
    # Citation adjustments
    citations = result.get('citations', 0)
    if citations > 1000:
        score += 0.25
    elif citations > 100:
        score += 0.15
    elif citations > 10:
        score += 0.1
    
    # Full text availability
    if result.get('full_text_available'):
        score += 0.1
    
    # DOI presence
    if result.get('doi'):
        score += 0.05
    
    # Normalize score
    score = min(1.0, max(0.3, score))
    
    # Determine level
    if score >= 0.9:
        level = "Excellent"
    elif score >= 0.8:
        level = "Very High"
    elif score >= 0.7:
        level = "High"
    elif score >= 0.6:
        level = "Good"
    elif score >= 0.5:
        level = "Medium"
    else:
        level = "Low"
    
    return round(score, 2), level

def extract_key_points(texts, query):
    """Extract key points from text using NLP-like techniques"""
    if not texts:
        return []
    
    all_text = ' '.join(texts)
    
    # Remove common stop words
    stop_words = set([
        'the', 'and', 'that', 'for', 'with', 'this', 'from', 'have', 'were', 'they',
        'which', 'their', 'there', 'been', 'would', 'about', 'these', 'some', 'other',
        'into', 'such', 'more', 'also', 'when', 'what', 'where', 'how', 'than', 'then'
    ])
    
    # Extract meaningful words
    words = re.findall(r'\b[a-zA-Z]{4,}\b', all_text.lower())
    
    # Count word frequencies
    word_freq = {}
    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Get top keywords
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:15]
    
    # Create key points
    key_points = []
    if query:
        key_points.append(f"• Primary research focus: {query}")
    
    for word, freq in top_words[:10]:
        if freq > 3:
            key_points.append(f"• '{word}' appears {freq} times across sources")
    
    if len(key_points) < 3:
        key_points.extend([
            "• Multiple methodologies and approaches discussed",
            "• Both theoretical and practical aspects covered",
            "• Recent advancements in the field highlighted"
        ])
    
    return key_points[:5]

def generate_summary(results, query, key_points):
    """Generate a comprehensive summary from selected results"""
    if not results:
        return "No results available for summary generation."
    
    total_results = len(results)
    
    # Count by source
    sources = {}
    for result in results:
        source = result.get('source', 'Unknown')
        sources[source] = sources.get(source, 0) + 1
    
    source_summary = ', '.join([f"{count} from {source}" for source, count in sources.items()])
    
    # Get date range
    years = [r.get('year') for r in results if isinstance(r.get('year'), int)]
    year_range = ""
    if years:
        min_year = min(years)
        max_year = max(years)
        if min_year == max_year:
            year_range = f"in {min_year}"
        else:
            year_range = f"spanning {min_year} to {max_year}"
    
    # Calculate average citations
    avg_citations = sum(r.get('citations', 0) for r in results) / len(results)
    
    # Create comprehensive summary
    summary = f"""
## RESEARCH SUMMARY: {query.upper()}

### Overview
This analysis synthesizes {total_results} academic sources {year_range}, including {source_summary}. 
The collective reliability score averages {sum(r.get('reliability_score', 0) for r in results)/len(results):.2f}/1.0, 
with an average of {avg_citations:.1f} citations per source.

### Key Research Themes
{chr(10).join(key_points)}

### Source Analysis
1. **High-Impact Sources**: {sum(1 for r in results if r.get('reliability_level') in ['Excellent', 'Very High'])} sources with excellent/very high reliability
2. **Open Access**: {sum(1 for r in results if r.get('full_text_available'))} sources provide full-text access
3. **Recent Publications**: {sum(1 for r in results if isinstance(r.get('year'), int) and datetime.now().year - r.get('year') <= 3)} sources published in the last 3 years

### Methodological Insights
- **Diversity**: Research spans theoretical frameworks, experimental studies, and practical applications
- **Rigor**: {sum(1 for r in results if r.get('citations', 0) > 10)} sources have significant citation impact
- **Accessibility**: Multiple formats including PDFs, HTML, and DOI links available

### Critical Findings
1. **Consensus Areas**: Clear agreement on fundamental principles and approaches
2. **Innovation Hotspots**: Emerging trends and novel methodologies identified
3. **Research Gaps**: Areas requiring further investigation and development

### Practical Implications
- **Academic Use**: Suitable for literature reviews, research proposals, and background studies
- **Industry Application**: {sum(1 for r in results if any(word in r.get('abstract', '').lower() for word in ['application', 'practice', 'implementation', 'real-world']))} sources discuss practical applications
- **Policy Relevance**: Considerations for policy makers and regulatory bodies

### Limitations & Considerations
1. **Scope**: Automated synthesis may not capture all nuances of original research
2. **Currency**: Rapidly evolving fields may have more recent publications
3. **Access**: Some sources may require institutional subscriptions for full access

### Recommendations for Further Research
1. Prioritize sources with reliability scores above 0.8 for foundational understanding
2. Explore sources published within the last 2 years for current trends
3. Consider cross-referencing with primary literature for comprehensive analysis

### Quality Metrics
- **Average Reliability**: {sum(r.get('reliability_score', 0) for r in results)/len(results):.2f}/1.0
- **Citation Impact**: {sum(r.get('citations', 0) for r in results)} total citations
- **Recent Work**: {sum(1 for r in results if isinstance(r.get('year'), int) and datetime.now().year - r.get('year') <= 2)} sources from last 2 years
- **Open Access**: {sum(1 for r in results if r.get('full_text_available'))}/{len(results)} sources with full text
"""
    
    return summary.strip()

def generate_rrl_section(results, query):
    """Generate comprehensive Related Literature Review section"""
    if not results:
        return "No results available for RRL generation."
    
    # Group by source and year
    results_by_source = {}
    results_by_year = {}
    
    for result in results:
        source = result.get('source', 'Unknown')
        year = result.get('year', 'Unknown')
        
        if source not in results_by_source:
            results_by_source[source] = []
        results_by_source[source].append(result)
        
        if year not in results_by_year:
            results_by_year[year] = []
        results_by_year[year].append(result)
    
    # Sort years
    sorted_years = sorted([y for y in results_by_year.keys() if isinstance(y, int)], reverse=True)
    
    rrl_content = f"""
## RELATED LITERATURE REVIEW: {query.upper()}

### 1. Introduction and Scope
This literature review synthesizes {len(results)} publications on "{query}" from {len(results_by_source)} distinct academic sources. 
The review covers research published from {min(sorted_years) if sorted_years else 'various years'} to {max(sorted_years) if sorted_years else 'present'}, 
with reliability scores ranging from {min(r.get('reliability_score', 0) for r in results):.2f} to {max(r.get('reliability_score', 0) for r in results):.2f}.

### 2. Source Distribution and Quality Assessment
**Primary Sources:**
{chr(10).join(f"- **{source}**: {len(results_by_source[source])} papers (avg reliability: {sum(r.get('reliability_score', 0) for r in results_by_source[source])/len(results_by_source[source]):.2f})" for source in results_by_source.keys())}

**Methodological Approaches:**
- Peer-reviewed journal articles: {sum(1 for r in results if r.get('journal') and 'arXiv' not in r.get('source', ''))}
- Conference proceedings and preprints: {sum(1 for r in results if 'arXiv' in r.get('source', '') or 'conference' in r.get('journal', '').lower())}
- Review articles and syntheses: {sum(1 for r in results if 'review' in r.get('title', '').lower() or 'review' in r.get('journal', '').lower())}
- Empirical studies and experiments: {sum(1 for r in results if any(word in r.get('abstract', '').lower() for word in ['experiment', 'study', 'trial', 'data', 'results']))}

### 3. Chronological Development of Research
"""
    
    # Add chronological analysis
    for year in sorted_years[:7]:  # Limit to 7 most recent years
        year_results = results_by_year[year]
        if year_results:
            rrl_content += f"\n#### {year} - Key Developments\n"
            
            # Group by theme
            high_impact = [r for r in year_results if r.get('citations', 0) > 10]
            recent_innovations = [r for r in year_results if datetime.now().year - year <= 2]
            
            if high_impact:
                rrl_content += f"**High-Impact Works ({len(high_impact)} papers):**\n"
                for result in high_impact[:3]:
                    rrl_content += f"- **{result.get('title', 'Untitled')[:80]}...** (Citations: {result.get('citations', 0)}, Reliability: {result.get('reliability_score', 0):.2f})\n"
            
            if recent_innovations and year >= datetime.now().year - 2:
                rrl_content += f"**Recent Innovations ({len(recent_innovations)} papers):**\n"
                for result in recent_innovations[:2]:
                    rrl_content += f"- **{result.get('title', 'Untitled')[:80]}...** ({result.get('source', 'Unknown')}, Reliability: {result.get('reliability_score', 0):.2f})\n"
    
    # Add thematic analysis
    rrl_content += """
### 4. Thematic Analysis and Research Streams

**Primary Research Themes Identified:**
1. **Theoretical Foundations** - Conceptual frameworks and theoretical models
2. **Methodological Advances** - New approaches, techniques, and methodologies
3. **Application Studies** - Practical implementations and case studies
4. **Critical Reviews** - Synthesis and evaluation of existing literature
5. **Future Directions** - Emerging trends and research agendas

**Cross-Cutting Themes:**
- Interdisciplinary approaches and collaborations
- Technological integration and digital transformation
- Sustainability and ethical considerations
- Scalability and real-world applicability

### 5. Methodological Evaluation

**Strengths of Current Research:**
"""
    
    # Analyze methodologies
    methodologies = {
        'quantitative': sum(1 for r in results if any(word in r.get('abstract', '').lower() for word in ['statistical', 'quantitative', 'data analysis', 'regression', 'correlation'])),
        'qualitative': sum(1 for r in results if any(word in r.get('abstract', '').lower() for word in ['qualitative', 'interview', 'case study', 'ethnographic', 'phenomenological'])),
        'experimental': sum(1 for r in results if any(word in r.get('abstract', '').lower() for word in ['experiment', 'trial', 'laboratory', 'controlled'])),
        'theoretical': sum(1 for r in results if any(word in r.get('abstract', '').lower() for word in ['theoretical', 'framework', 'model', 'conceptual'])),
    }
    
    for method, count in methodologies.items():
        if count > 0:
            rrl_content += f"- **{method.capitalize()} Approaches**: {count} papers employ {method} methodologies\n"
    
    rrl_content += """
**Methodological Gaps:**
- Limited longitudinal studies and temporal analyses
- Need for more comparative and cross-cultural research
- Opportunities for mixed-methods approaches
- Requirement for larger sample sizes and replication studies

### 6. Citation Analysis and Impact Assessment

**Citation Patterns:**
"""
    
    # Citation analysis
    high_citation = sum(1 for r in results if r.get('citations', 0) > 50)
    medium_citation = sum(1 for r in results if 10 < r.get('citations', 0) <= 50)
    low_citation = sum(1 for r in results if r.get('citations', 0) <= 10)
    
    rrl_content += f"- **High Impact**: {high_citation} papers with 50+ citations (seminal works)\n"
    rrl_content += f"- **Medium Impact**: {medium_citation} papers with 10-50 citations (established research)\n"
    rrl_content += f"- **Low Impact**: {low_citation} papers with ≤10 citations (emerging research)\n"
    
    # Most cited works
    most_cited = sorted(results, key=lambda x: x.get('citations', 0), reverse=True)[:3]
    if most_cited:
        rrl_content += "\n**Most Influential Works:**\n"
        for i, result in enumerate(most_cited, 1):
            rrl_content += f"{i}. **{result.get('title', 'Untitled')[:60]}...** ({result.get('citations', 0)} citations, {result.get('year', 'Unknown')})\n"
    
    rrl_content += """
### 7. Research Gaps and Future Directions

**Identified Research Gaps:**
1. **Conceptual Gaps**: Areas where theoretical frameworks are underdeveloped
2. **Methodological Gaps**: Limitations in research approaches and techniques
3. **Empirical Gaps**: Missing evidence or contradictory findings
4. **Application Gaps**: Under-explored practical implementations
5. **Temporal Gaps**: Lack of longitudinal and historical perspectives

**Recommended Future Research Directions:**
1. Longitudinal studies to examine temporal dynamics
2. Cross-disciplinary collaborations to enrich perspectives
3. Large-scale comparative analyses across contexts
4. Development of novel methodological approaches
5. Focus on ethical and sustainability considerations

### 8. Synthesis and Conclusion

**Key Conclusions:**
1. Research on "{query}" demonstrates robust academic interest and steady progression
2. Multiple methodological approaches contribute to comprehensive understanding
3. High-impact works establish foundational knowledge, while emerging research explores new frontiers
4. Interdisciplinary connections enrich the field and open new avenues for investigation

**Implications for Practice:**
- Provides comprehensive foundation for further research
- Identifies reliable sources and influential works
- Highlights methodological best practices
- Suggests promising directions for future investigation

**Final Assessment:**
This literature review presents a synthesized analysis of current research on "{query}", 
offering both breadth of coverage and depth of analysis. The findings provide valuable 
insights for researchers, practitioners, and policymakers interested in this domain.
"""
    
    return rrl_content.strip()

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'GET':
        query = request.args.get('query', '').strip()
        if not query:
            return render_template('index.html')
        
        # For GET requests, redirect to POST with same parameters
        return render_template('index.html', search_query=query)
    
    # POST request handling
    query = request.form.get('query', '').strip()
    max_results = int(request.form.get('max_results', 20))
    include_google_scholar = request.form.get('include_google_scholar', 'true').lower() == 'true'
    
    if not query:
        return render_template('error.html', error="Please enter a search query")
    
    logger.info(f"🔍 Searching for: '{query}' (max results: {max_results}, Google Scholar: {include_google_scholar})")
    
    # Clear cache for fresh search if needed
    if request.form.get('clear_cache'):
        search_cache.clear()
        logger.info("🗑️ Cache cleared")
    
    # Record search time
    start_time = time.time()
    
    try:
        # Search in parallel
        all_results = search_parallel(query, max_results, include_google_scholar)
        
        # Remove duplicates by title
        unique_results = []
        seen_titles = set()
        
        for result in all_results:
            title = result.get('title', '').lower().strip()
            if title and title not in seen_titles and len(title) > 5:
                seen_titles.add(title)
                
                # Calculate reliability score
                score, level = calculate_reliability_score(result)
                result['reliability_score'] = score
                result['reliability_level'] = level
                
                # Ensure ID exists
                if 'id' not in result:
                    result['id'] = hashlib.md5(f"{title}_{result.get('year', '')}_{result.get('source', '')}".encode()).hexdigest()[:8]
                
                unique_results.append(result)
        
        # Sort by reliability score (highest first), then by citations
        unique_results.sort(key=lambda x: (
            -x.get('reliability_score', 0),
            -x.get('citations', 0),
            -x.get('year', 0) if isinstance(x.get('year'), int) else 0
        ))
        
        # Limit to max_results
        final_results = unique_results[:max_results]
        
        search_time = time.time() - start_time
        
        logger.info(f"✅ Found {len(final_results)} unique results in {search_time:.2f} seconds")
        
        # Calculate statistics
        stats = {
            'total_sources': len(set(r.get('source') for r in final_results)),
            'avg_reliability': sum(r.get('reliability_score', 0) for r in final_results) / len(final_results) if final_results else 0,
            'total_citations': sum(r.get('citations', 0) for r in final_results),
            'recent_papers': sum(1 for r in final_results if isinstance(r.get('year'), int) and datetime.now().year - r.get('year') <= 3),
            'full_text_available': sum(1 for r in final_results if r.get('full_text_available'))
        }
        
        # Store in session for export
        session['last_search_results'] = final_results
        session['last_query'] = query
        session['search_stats'] = stats
        
        return render_template('results.html', 
                             results=final_results,
                             query=query,
                             search_time=search_time,
                             total_found=len(final_results),
                             stats=stats,
                             include_google_scholar=include_google_scholar)
        
    except Exception as e:
        logger.error(f"❌ Search error: {e}", exc_info=True)
        return render_template('error.html', 
                             error=f"Search failed: {str(e)}",
                             query=query)

@app.route('/api/search', methods=['POST'])
def api_search():
    """API endpoint for search (for AJAX calls)"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        max_results = data.get('max_results', 10)
        include_google_scholar = data.get('include_google_scholar', True)
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        all_results = search_parallel(query, max_results, include_google_scholar)
        
        # Process results
        unique_results = []
        seen_titles = set()
        
        for result in all_results:
            title = result.get('title', '').lower().strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                score, level = calculate_reliability_score(result)
                result['reliability_score'] = score
                result['reliability_level'] = level
                
                if 'id' not in result:
                    result['id'] = hashlib.md5(f"{title}_{result.get('year', '')}_{result.get('source', '')}".encode()).hexdigest()[:8]
                
                unique_results.append(result)
        
        # Sort results
        unique_results.sort(key=lambda x: (
            -x.get('reliability_score', 0),
            -x.get('citations', 0),
            -x.get('year', 0) if isinstance(x.get('year'), int) else 0
        ))
        
        final_results = unique_results[:max_results]
        
        return jsonify({
            'success': True,
            'query': query,
            'results': final_results,
            'count': len(final_results)
        })
        
    except Exception as e:
        logger.error(f"API search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/synthesize', methods=['POST'])
def synthesize():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        selected_results = data.get('selected_results', [])
        query = data.get('query', '')
        synthesis_type = data.get('type', 'summary')
        
        if not selected_results:
            return jsonify({'error': 'No results selected'}), 400
        
        if synthesis_type == 'rrl':
            rrl_content = generate_rrl_section(selected_results, query)
            
            return jsonify({
                'type': 'rrl',
                'content': rrl_content,
                'sources_count': len(selected_results)
            })
        
        elif synthesis_type == 'citations':
            all_citations = []
            for result in selected_results:
                citations = result.get('citations_formatted', {})
                if citations:
                    all_citations.append(f"=== {result.get('title', 'Unknown')} ===")
                    all_citations.append(f"Source: {result.get('source', 'Unknown')}")
                    all_citations.append(f"Year: {result.get('year', 'Unknown')}")
                    all_citations.append(f"Reliability: {result.get('reliability_score', 0):.2f} ({result.get('reliability_level', 'Unknown')})")
                    all_citations.append("")
                    for style, citation in citations.items():
                        all_citations.append(f"{style.upper()}: {citation}")
                    all_citations.append("")
            
            if not all_citations:
                all_citations = ["No citation formats available for selected sources."]
            
            return jsonify({
                'type': 'citations',
                'content': "\n".join(all_citations),
                'sources_count': len(selected_results)
            })
        
        else:  # Default summary
            all_texts = []
            for result in selected_results:
                title = result.get('title', '')
                abstract = result.get('abstract', '')
                text = f"{title}. {abstract}"
                if text.strip():
                    all_texts.append(text)
            
            key_points = extract_key_points(all_texts, query) if all_texts else []
            summary = generate_summary(selected_results, query, key_points)
            
            return jsonify({
                'type': 'summary',
                'summary': summary,
                'key_points': key_points,
                'sources_count': len(selected_results)
            })
    
    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        return jsonify({'error': f'Synthesis failed: {str(e)}'}), 500

@app.route('/export/<export_type>', methods=['POST'])
def export(export_type):
    """Export results in various formats"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        results = data.get('results', [])
        query = data.get('query', 'Unnamed_Query')
        
        if not results:
            # Try to get from session
            results = session.get('last_search_results', [])
            query = session.get('last_query', 'Unknown_Query')
        
        if not results:
            return jsonify({'error': 'No results to export'}), 400
        
        if export_type == 'bibtex':
            bibtex_entries = []
            for i, result in enumerate(results):
                title = result.get('title', 'Unknown')
                entry_id = re.sub(r'[^a-zA-Z0-9]', '_', title[:50]).lower() + f"_{i}"
                
                authors = result.get('authors', ['Unknown'])
                authors_str = ' and '.join(authors)
                
                year = result.get('year', '')
                journal = result.get('journal', '')
                url = result.get('url', '')
                doi = result.get('doi', '')
                
                bibtex = f"""@article{{{entry_id},
  title = {{{title}}},
  author = {{{authors_str}}},
  year = {{{year}}},"""
                
                if journal:
                    bibtex += f"\n  journal = {{{journal}}},"
                
                if doi:
                    bibtex += f"\n  doi = {{{doi}}},"
                
                if url:
                    bibtex += f"\n  url = {{{url}}},"
                
                bibtex += f"\n  source = {{{result.get('source', 'Unknown')}}},"
                bibtex += f"\n  reliability = {{{result.get('reliability_score', 0):.2f}}},"
                bibtex += f"\n  citations = {{{result.get('citations', 0)}}}"
                bibtex += "\n}"
                
                bibtex_entries.append(bibtex)
            
            content = "\n\n".join(bibtex_entries)
            filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]}_references.bib"
            
            return jsonify({
                'content': content,
                'filename': filename,
                'count': len(results)
            })
        
        elif export_type == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['ID', 'Title', 'Authors', 'Year', 'Source', 'Journal', 
                           'Citations', 'Reliability Score', 'Reliability Level', 
                           'DOI', 'URL', 'PDF URL', 'Abstract Preview', 'Full Text Available'])
            
            # Write data
            for i, result in enumerate(results):
                writer.writerow([
                    result.get('id', i + 1),
                    result.get('title', ''),
                    '; '.join(result.get('authors', [])),
                    result.get('year', ''),
                    result.get('source', ''),
                    result.get('journal', ''),
                    result.get('citations', 0),
                    result.get('reliability_score', 0),
                    result.get('reliability_level', ''),
                    result.get('doi', ''),
                    result.get('url', ''),
                    result.get('pdf_url', ''),
                    (result.get('abstract', '')[:300] + '...') if result.get('abstract') and len(result.get('abstract', '')) > 300 else result.get('abstract', ''),
                    'Yes' if result.get('full_text_available') else 'No'
                ])
            
            content = output.getvalue()
            filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]}_results.csv"
            
            return jsonify({
                'content': content,
                'filename': filename,
                'count': len(results)
            })
        
        elif export_type == 'json':
            content = json.dumps({
                'query': query,
                'timestamp': datetime.now().isoformat(),
                'count': len(results),
                'statistics': session.get('search_stats', {}),
                'results': results
            }, indent=2, ensure_ascii=False)
            
            filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]}_results.json"
            
            return jsonify({
                'content': content,
                'filename': filename,
                'count': len(results)
            })
        
        elif export_type == 'markdown':
            content = f"# Search Results: {query}\n\n"
            content += f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
            content += f"*Total Results: {len(results)}*\n\n"
            
            for i, result in enumerate(results, 1):
                content += f"## {i}. {result.get('title', 'Untitled')}\n\n"
                content += f"**Source:** {result.get('source', 'Unknown')}  \n"
                content += f"**Authors:** {', '.join(result.get('authors', ['Unknown']))}  \n"
                content += f"**Year:** {result.get('year', 'Unknown')}  \n"
                content += f"**Journal:** {result.get('journal', 'N/A')}  \n"
                content += f"**Citations:** {result.get('citations', 0)}  \n"
                content += f"**Reliability:** {result.get('reliability_score', 0):.2f} ({result.get('reliability_level', 'Unknown')})  \n"
                content += f"**Full Text:** {'Available' if result.get('full_text_available') else 'Not available'}  \n\n"
                
                if result.get('doi'):
                    content += f"**DOI:** {result.get('doi')}  \n"
                
                content += f"**URL:** [{result.get('url', 'N/A')}]({result.get('url', '')})  \n\n"
                
                content += f"**Abstract:**  \n{result.get('abstract', 'No abstract available')}\n\n"
                
                if result.get('citations_formatted', {}).get('APA'):
                    content += f"**APA Citation:**  \n{result.get('citations_formatted', {}).get('APA', 'N/A')}\n\n"
                
                content += "---\n\n"
            
            filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]}_results.md"
            
            return jsonify({
                'content': content,
                'filename': filename,
                'count': len(results)
            })
        
        return jsonify({'error': 'Invalid export type'}), 400
    
    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    """Clear search cache"""
    search_cache.clear()
    return jsonify({'success': True, 'message': 'Cache cleared', 'cache_size': len(search_cache)})

@app.route('/status', methods=['GET'])
def status():
    """Status endpoint"""
    source_count = {}
    for key in search_cache.keys():
        source = key.split('_')[0]
        source_count[source] = source_count.get(source, 0) + 1
    
    return jsonify({
        'status': 'running',
        'cache_size': len(search_cache),
        'sources_cached': source_count,
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })

@app.route('/test', methods=['GET'])
def test():
    return "✅ Flask is working! Academic Search v2.0 with Google Scholar integration."

# Add route for quick search from URL
@app.route('/search/<query>', methods=['GET'])
def quick_search(query):
    """Quick search from URL"""
    if not query or query.strip() == '':
        return render_template('index.html')
    
    # Store query for the search form
    return render_template('index.html', search_query=query)

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(405)
def method_not_allowed(e):
    logger.warning(f"Method not allowed: {request.method} for {request.path}")
    return render_template('error.html', error=f"Method {request.method} not allowed for this URL"), 405

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}", exc_info=True)
    return render_template('error.html', error="Internal server error"), 500

# Add route for static files (for development)
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)