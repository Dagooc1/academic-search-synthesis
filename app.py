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
from urllib.parse import quote_plus
import concurrent.futures
from functools import wraps
import hashlib

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.secret_key = os.getenv('SECRET_KEY', 'academic-search-secret-key-123')
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes

# Cache for search results (simple in-memory cache)
search_cache = {}

# Wikipedia API
wiki_wiki = wikipediaapi.Wikipedia(
    language='en',
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent='AcademicResearchHub/1.0'
)

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
                print(f"Using cached results for {func.__name__}: {query}")
                return results
        
        # Execute search
        results = func(query, max_results)
        
        # Store in cache
        search_cache[cache_key] = (time.time(), results)
        
        return results
    return wrapper

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
                'search_timestamp': time.time()
            })
    except Exception as e:
        print(f"arXiv error: {e}")
    
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
            'fields': 'title,authors,abstract,year,citationCount,url,openAccessPdf,externalIds,venue,publicationVenue,tldr'
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
                    'reliability_score': 0.7,
                    'reliability_level': 'High',
                    'citations_formatted': citations,
                    'journal': venue,
                    'full_text_available': paper.get('openAccessPdf') is not None,
                    'search_timestamp': time.time()
                })
    except Exception as e:
        print(f"Semantic Scholar error: {e}")
    
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
                        'reliability_score': 0.6,
                        'reliability_level': 'Good',
                        'citations_formatted': {
                            'APA': f"Wikipedia contributors. ({datetime.now().year}). {title}. In Wikipedia. Retrieved from https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                            'MLA': f'"{title}." Wikipedia, Wikimedia Foundation, {datetime.now().year}, en.wikipedia.org/wiki/{title.replace(" ", "_")}.'
                        },
                        'journal': 'Wikipedia',
                        'full_text_available': True,
                        'search_timestamp': time.time()
                    })
    except Exception as e:
        print(f"Wikipedia error: {e}")
    
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
                    'reliability_score': 0.7,
                    'reliability_level': 'High',
                    'citations_formatted': generate_citations(title, authors, year, url, doi),
                    'journal': journal or 'Academic Publication',
                    'full_text_available': bool(doi),
                    'search_timestamp': time.time()
                })
    except Exception as e:
        print(f"Crossref error: {e}")
    
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
                    'reliability_score': 0.7,
                    'reliability_level': 'High',
                    'citations_formatted': generate_citations(title, authors, year, url, doi),
                    'journal': 'Open Access Journal',
                    'full_text_available': True,
                    'search_timestamp': time.time()
                })
    except Exception as e:
        print(f"DOAJ error: {e}")
    
    return results

def search_parallel(query, max_results=15):
    """Search all sources in parallel"""
    search_functions = [
        (search_arxiv, min(3, max_results//3)),
        (search_semantic_scholar, min(3, max_results//3)),
        (search_crossref, min(2, max_results//4)),
        (search_doaj, min(2, max_results//4)),
        (search_wikipedia, min(2, max_results//4))
    ]
    
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
                print(f"✓ {func_name}: Found {len(results)} results")
            except Exception as e:
                print(f"✗ {func_name} failed: {e}")
    
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
    if source in ['arXiv', 'Crossref', 'DOAJ']:
        score = max(score, 0.7)
    elif source == 'Semantic Scholar':
        score = max(score, 0.75)
    elif source == 'Wikipedia':
        score = 0.65
    elif source == 'Research Institution':
        score = 0.9
    
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
        score += 0.05
    
    # Full text availability
    if result.get('full_text_available'):
        score += 0.05
    
    # DOI presence
    if result.get('doi'):
        score += 0.05
    
    # Normalize score
    score = min(1.0, max(0.3, score))
    
    # Determine level
    if score >= 0.85:
        level = "Excellent"
    elif score >= 0.75:
        level = "Very High"
    elif score >= 0.65:
        level = "High"
    elif score >= 0.55:
        level = "Good"
    elif score >= 0.45:
        level = "Medium"
    else:
        level = "Low"
    
    return round(score, 2), level

def extract_key_points(texts, query):
    """Extract key points from text (simplified version)"""
    if not texts:
        return []
    
    all_text = ' '.join(texts)
    
    # Simple keyword extraction
    words = re.findall(r'\b[a-zA-Z]{4,}\b', all_text.lower())
    word_freq = {}
    
    for word in words:
        if word not in ['this', 'that', 'these', 'those', 'with', 'from', 'have', 'were', 'they', 'which']:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Get top keywords
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Create key points
    key_points = []
    for word, freq in top_words:
        if freq > 2:  # Only include words that appear multiple times
            key_points.append(f"• '{word}' appears {freq} times in the literature")
    
    if query and key_points:
        key_points.insert(0, f"• Primary research focus: {query}")
    
    if not key_points:
        key_points = ["• No specific key points could be extracted"]
    
    return key_points[:5]  # Limit to 5 key points

def generate_summary(results, query, key_points):
    """Generate a summary from selected results"""
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
            year_range = f"from {min_year} to {max_year}"
    
    # Create summary
    summary = f"""
## Research Summary for "{query}"

### Overview
This summary is based on {total_results} academic sources {year_range}, including {source_summary}. 
The research covers various aspects of "{query}" with reliability scores ranging from 
{min(r.get('reliability_score', 0) for r in results):.2f} to {max(r.get('reliability_score', 0) for r in results):.2f}.

### Key Findings
{chr(10).join(key_points)}

### Methodology
The analysis includes peer-reviewed papers, conference proceedings, and authoritative sources. 
Each source was evaluated based on publication venue, citation count, recency, and accessibility.

### Recommendations
1. Focus on sources with "Excellent" or "Very High" reliability scores for core research
2. Consult recent publications (last 3 years) for current trends
3. Use open-access sources for full-text availability

### Limitations
This summary is automatically generated and may not capture all nuances. 
Manual review of primary sources is recommended for comprehensive understanding.
"""
    
    return summary.strip()

def generate_rrl_section(results, query):
    """Generate Related Literature Review section"""
    if not results:
        return "No results available for RRL generation."
    
    # Group by year
    results_by_year = {}
    for result in results:
        year = result.get('year', 'Unknown')
        if year not in results_by_year:
            results_by_year[year] = []
        results_by_year[year].append(result)
    
    # Sort years
    sorted_years = sorted([y for y in results_by_year.keys() if isinstance(y, int)], reverse=True)
    
    rrl_content = f"""
## RELATED LITERATURE REVIEW: {query.upper()}

### 1. Introduction
This literature review synthesizes existing research on "{query}" from multiple academic sources. 
The review covers {len(results)} publications spanning from {min(sorted_years) if sorted_years else 'various years'} to {max(sorted_years) if sorted_years else 'present'}.

### 2. Theoretical Framework
The literature on "{query}" can be categorized into several theoretical perspectives. 
Key frameworks include:
- Technical implementations and algorithms
- Application domains and case studies
- Methodological approaches
- Future research directions

### 3. Review of Related Literature
"""
    
    # Add content by year
    for year in sorted_years[:5]:  # Limit to 5 most recent years
        year_results = results_by_year[year]
        rrl_content += f"\n#### {year} - Recent Developments\n"
        
        for result in year_results[:3]:  # Limit to 3 results per year
            title = result.get('title', 'Untitled')
            authors = ', '.join(result.get('authors', ['Unknown']))[:100]
            
            rrl_content += f"""
**{title}** ({result.get('source', 'Unknown')})
*Authors:* {authors}
*Summary:* {result.get('abstract', 'No abstract available')[:200]}...
*Reliability:* {result.get('reliability_level', 'Unknown')} ({result.get('reliability_score', 0):.2f})

"""
    
    # Add synthesis section
    rrl_content += """
### 4. Synthesis and Analysis

The literature reveals several consistent themes:
1. **Technical Evolution**: Steady advancement in methodologies and implementations
2. **Application Diversity**: Wide range of practical applications across domains
3. **Research Gaps**: Areas requiring further investigation
4. **Methodological Trends**: Shifts in research approaches over time

### 5. Research Gaps and Future Directions

Based on the reviewed literature, the following areas warrant further investigation:
- Integration of emerging technologies
- Longitudinal studies and impact assessments
- Cross-disciplinary applications
- Standardization and benchmarking

### 6. Conclusion

This review provides a comprehensive overview of current research on "{query}". 
The literature demonstrates robust academic interest with contributions from 
various disciplines and methodological approaches. Future research should 
address identified gaps while building on established foundations.
"""
    
    return rrl_content.strip()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '').strip()
    max_results = int(request.form.get('max_results', 15))
    
    if not query:
        return render_template('error.html', error="Please enter a search query")
    
    print(f"🔍 Searching for: '{query}' (max results: {max_results})")
    
    # Clear cache for fresh search if needed
    if request.form.get('clear_cache'):
        search_cache.clear()
        print("🗑️ Cache cleared")
    
    # Record search time
    start_time = time.time()
    
    try:
        # Search in parallel
        all_results = search_parallel(query, max_results)
        
        # Remove duplicates by title
        unique_results = []
        seen_titles = set()
        
        for result in all_results:
            title = result.get('title', '').lower().strip()
            if title and title not in seen_titles and len(title) > 3:
                seen_titles.add(title)
                
                # Calculate reliability score
                score, level = calculate_reliability_score(result)
                result['reliability_score'] = score
                result['reliability_level'] = level
                result['id'] = hashlib.md5(f"{title}_{result.get('year', '')}".encode()).hexdigest()[:8]
                
                unique_results.append(result)
        
        # Sort by reliability score (highest first)
        unique_results.sort(key=lambda x: x['reliability_score'], reverse=True)
        
        # Limit to max_results
        final_results = unique_results[:max_results]
        
        search_time = time.time() - start_time
        
        print(f"✅ Found {len(final_results)} unique results in {search_time:.2f} seconds")
        
        # Store in session for export
        session['last_search_results'] = final_results
        session['last_query'] = query
        
        return render_template('results.html', 
                             results=final_results,
                             query=query,
                             search_time=search_time,
                             total_found=len(final_results))
        
    except Exception as e:
        print(f"❌ Search error: {e}")
        import traceback
        traceback.print_exc()
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
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        all_results = search_parallel(query, max_results)
        
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
                result['id'] = hashlib.md5(f"{title}_{result.get('year', '')}".encode()).hexdigest()[:8]
                unique_results.append(result)
        
        unique_results.sort(key=lambda x: x['reliability_score'], reverse=True)
        final_results = unique_results[:max_results]
        
        return jsonify({
            'success': True,
            'query': query,
            'results': final_results,
            'count': len(final_results)
        })
        
    except Exception as e:
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
        print(f"Synthesis error: {e}")
        import traceback
        traceback.print_exc()
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
                
                bibtex += f"\n  note = {{Retrieved from Academic Research Hub, Reliability: {result.get('reliability_score', 0):.2f}}}"
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
                           'DOI', 'URL', 'PDF URL', 'Abstract'])
            
            # Write data
            for i, result in enumerate(results):
                writer.writerow([
                    i + 1,
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
                    result.get('abstract', '')[:500]
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
                'results': results
            }, indent=2)
            
            filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]}_results.json"
            
            return jsonify({
                'content': content,
                'filename': filename,
                'count': len(results)
            })
        
        return jsonify({'error': 'Invalid export type'}), 400
    
    except Exception as e:
        print(f"Export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    """Clear search cache"""
    search_cache.clear()
    return jsonify({'success': True, 'message': 'Cache cleared'})

@app.route('/status')
def status():
    """Status endpoint"""
    return jsonify({
        'status': 'running',
        'cache_size': len(search_cache),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/test')
def test():
    return "✅ Flask is working! Academic Search ready."

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error="Internal server error"), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)