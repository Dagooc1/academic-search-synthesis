from flask import Flask, render_template, request, jsonify
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

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins for now
app.secret_key = os.getenv('SECRET_KEY', 'academic-search-secret-key-123')

# Wikipedia API
wiki_wiki = wikipediaapi.Wikipedia(
    language='en',
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent='AcademicResearchHub/1.0'
)

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
            # Get all authors
            authors = [author.name for author in paper.authors]
            
            # Generate citation formats
            citations = generate_citations(paper.title, authors, paper.published.year, 
                                         paper.entry_id, paper.doi if hasattr(paper, 'doi') else '')
            
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
                'full_text_available': True
            })
    except Exception as e:
        print(f"arXiv error: {e}")
    
    return results

def search_semantic_scholar(query, max_results=10):
    """Search Semantic Scholar with full details"""
    results = []
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            'query': query,
            'limit': max_results,
            'fields': 'title,authors,abstract,year,citationCount,url,openAccessPdf,externalIds,venue,publicationVenue'
        }
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            for paper in data.get('data', []):
                # Extract authors
                authors = []
                for author in paper.get('authors', []):
                    if isinstance(author, dict):
                        authors.append(author.get('name', ''))
                
                # Get DOI
                doi = ''
                if paper.get('externalIds') and isinstance(paper['externalIds'], dict):
                    doi = paper['externalIds'].get('DOI', '')
                
                # Get venue/journal
                venue = paper.get('venue', '')
                if not venue and paper.get('publicationVenue'):
                    venue = paper['publicationVenue'].get('name', '')
                
                # Generate citation formats
                citations = generate_citations(paper.get('title', ''), authors, 
                                             paper.get('year', ''), paper.get('url', ''), doi)
                
                results.append({
                    'source': 'Semantic Scholar',
                    'title': paper.get('title', ''),
                    'authors': authors,
                    'abstract': paper.get('abstract', ''),
                    'year': paper.get('year', ''),
                    'url': paper.get('url', ''),
                    'pdf_url': paper.get('openAccessPdf', {}).get('url', '') if paper.get('openAccessPdf') else '',
                    'doi': doi,
                    'citations': paper.get('citationCount', 0),
                    'reliability_score': 0.7,
                    'reliability_level': 'High',
                    'citations_formatted': citations,
                    'journal': venue,
                    'full_text_available': paper.get('openAccessPdf') is not None
                })
    except Exception as e:
        print(f"Semantic Scholar error: {e}")
    
    return results

def search_wikipedia(query, max_results=5):
    """Search Wikipedia for articles"""
    results = []
    try:
        # Search Wikipedia
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote_plus(query)}&format=json&srlimit={max_results}"
        response = requests.get(search_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            for item in data.get('query', {}).get('search', []):
                page_id = item.get('pageid')
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                
                # Get full page details
                page = wiki_wiki.page(title)
                
                if page.exists():
                    # Clean HTML from snippet
                    soup = BeautifulSoup(snippet, 'html.parser')
                    clean_snippet = soup.get_text()
                    
                    results.append({
                        'source': 'Wikipedia',
                        'title': title,
                        'authors': ['Wikipedia Contributors'],
                        'abstract': clean_snippet + '...',
                        'year': datetime.now().year,  # Wikipedia articles are current
                        'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                        'pdf_url': '',
                        'doi': '',
                        'citations': 0,
                        'reliability_score': 0.6,  # Good for general knowledge
                        'reliability_level': 'Good',
                        'citations_formatted': {
                            'APA': f"Wikipedia contributors. ({datetime.now().year}). {title}. In Wikipedia. Retrieved from https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                            'MLA': f'"{title}." Wikipedia, Wikimedia Foundation, {datetime.now().year}, en.wikipedia.org/wiki/{title.replace(" ", "_")}.'
                        },
                        'journal': 'Wikipedia',
                        'full_text_available': True
                    })
    except Exception as e:
        print(f"Wikipedia error: {e}")
    
    return results

def search_google_scholar(query, max_results=5):
    """Search Google Scholar (simulated - actual API requires subscription)"""
    results = []
    try:
        # Note: Google Scholar doesn't have a public API
        # This is a simulated search using Semantic Scholar as alternative
        return search_semantic_scholar(query, max_results)
    except Exception as e:
        print(f"Google Scholar error: {e}")
    
    return results

def search_research_gate(query, max_results=5):
    """Search ResearchGate for research papers"""
    results = []
    try:
        # ResearchGate search simulation
        search_url = f"https://www.researchgate.net/search/publication?q={quote_plus(query)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find publication items (simplified parsing)
            publications = soup.find_all('div', class_='nova-legacy-c-card__body', limit=max_results)
            
            for pub in publications:
                try:
                    title_elem = pub.find('a', class_='nova-legacy-e-link')
                    if title_elem:
                        title = title_elem.text.strip()
                        url = "https://www.researchgate.net" + title_elem.get('href', '')
                        
                        # Try to extract abstract
                        abstract_elem = pub.find('div', class_='nova-legacy-c-card__content')
                        abstract = abstract_elem.text.strip()[:500] + '...' if abstract_elem else "Abstract not available"
                        
                        # Extract authors
                        authors_elem = pub.find('ul', class_='nova-legacy-c-card__body')
                        authors = []
                        if authors_elem:
                            author_items = authors_elem.find_all('li', class_='nova-legacy-c-card__item')
                            authors = [item.text.strip() for item in author_items[:3]]
                        
                        results.append({
                            'source': 'ResearchGate',
                            'title': title,
                            'authors': authors if authors else ['Various Researchers'],
                            'abstract': abstract,
                            'year': datetime.now().year,
                            'url': url,
                            'pdf_url': '',
                            'doi': '',
                            'citations': 0,
                            'reliability_score': 0.6,
                            'reliability_level': 'Good',
                            'citations_formatted': generate_citations(title, authors, datetime.now().year, url, ''),
                            'journal': 'ResearchGate',
                            'full_text_available': False
                        })
                except Exception as e:
                    print(f"Error parsing ResearchGate result: {e}")
                    continue
    except Exception as e:
        print(f"ResearchGate error: {e}")
    
    return results

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
                
                # Find URL
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
                    'full_text_available': True
                })
    except Exception as e:
        print(f"DOAJ error: {e}")
    
    return results

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
                
                # Get journal name
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
                    'full_text_available': bool(doi)
                })
    except Exception as e:
        print(f"Crossref error: {e}")
    
    return results

def search_theses(query, max_results=5):
    """Search for theses and dissertations"""
    results = []
    try:
        # Search ProQuest dissertations via their API
        # This is a simplified version - in production you'd use proper API keys
        base_url = "https://pqdtopen.proquest.com/search.html"
        search_url = f"{base_url}?q={quote_plus(query)}"
        
        results.append({
            'source': 'Theses/Dissertations',
            'title': f'Research on "{query}" - Theses and Dissertations',
            'authors': ['Various Researchers'],
            'abstract': f'Search for academic theses and dissertations related to {query}. Visit ProQuest or university repositories for detailed results.',
            'year': datetime.now().year,
            'url': search_url,
            'pdf_url': '',
            'doi': '',
            'citations': 0,
            'reliability_score': 0.6,
            'reliability_level': 'Good',
            'citations_formatted': {
                'APA': f'Various Researchers. ({datetime.now().year}). Research on "{query}". In Academic Theses and Dissertations.',
                'MLA': f'Research on "{query}". Academic Theses and Dissertations, {datetime.now().year}.'
            },
            'journal': 'University Theses',
            'full_text_available': False,
            'note': 'Visit university repositories or ProQuest for complete thesis collections'
        })
    except Exception as e:
        print(f"Theses search error: {e}")
    
    return results

def search_research_institutions(query, max_results=3):
    """Search research institutions and organizations"""
    results = []
    
    # List of major research institutions
    institutions = [
        ('MIT', 'Massachusetts Institute of Technology', 'https://www.mit.edu'),
        ('Stanford', 'Stanford University', 'https://www.stanford.edu'),
        ('Harvard', 'Harvard University', 'https://www.harvard.edu'),
        ('Oxford', 'University of Oxford', 'https://www.ox.ac.uk'),
        ('Cambridge', 'University of Cambridge', 'https://www.cam.ac.uk'),
        ('NIH', 'National Institutes of Health', 'https://www.nih.gov'),
        ('NASA', 'National Aeronautics and Space Administration', 'https://www.nasa.gov'),
        ('CERN', 'European Organization for Nuclear Research', 'https://home.cern'),
        ('Max Planck', 'Max Planck Society', 'https://www.mpg.de'),
        ('CNRS', 'French National Centre for Scientific Research', 'https://www.cnrs.fr')
    ]
    
    query_lower = query.lower()
    for short, full_name, url in institutions:
        if query_lower in short.lower() or query_lower in full_name.lower():
            results.append({
                'source': 'Research Institution',
                'title': f'{full_name} - Research on {query}',
                'authors': [f'{full_name} Researchers'],
                'abstract': f'{full_name} conducts cutting-edge research on {query} and related fields. Visit their website for publications, research projects, and academic resources.',
                'year': datetime.now().year,
                'url': url,
                'pdf_url': '',
                'doi': '',
                'citations': 0,
                'reliability_score': 0.9,
                'reliability_level': 'Very High',
                'citations_formatted': {
                    'APA': f'{full_name}. ({datetime.now().year}). Research on {query}. Retrieved from {url}',
                    'MLA': f'{full_name}. "Research on {query}." {datetime.now().year}, {url}.'
                },
                'journal': 'Institutional Research',
                'full_text_available': True
            })
            if len(results) >= max_results:
                break
    
    return results

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
    
    # Get current year for accessed date
    current_year = datetime.now().year
    
    citations = {
        'APA': f"{apa_authors} ({year}). {title}. Retrieved from {url}",
        'MLA': f'{mla_authors}. "{title}." {year}. Web. {current_year}.',
        'Chicago': f'{authors[0]} et al. "{title}." ({year}). {url}',
        'Harvard': f'{authors[0]} et al. ({year}) {title}. Available at: {url} (Accessed: {datetime.now().strftime("%d %B %Y")})',
        'IEEE': f'[{authors[0][0]}. {authors[0].split()[-1]} et al., "{title}," {year}.]',
        'Vancouver': f'{apa_authors}. {title}. [Internet]. {year}. Available from: {url}'
    }
    
    if doi:
        citations['APA'] = f"{apa_authors} ({year}). {title}. https://doi.org/{doi}"
        citations['MLA'] = f'{mla_authors}. "{title}." {year}. doi:{doi}.'
    
    return citations

# Rest of your functions remain the same (extract_key_points, generate_rrl_section, generate_summary)...

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '').strip()
    max_results = int(request.form.get('max_results', 15))
    
    if not query:
        return render_template('error.html', error="Please enter a search query")
    
    print(f"Searching for: {query}")
    
    # Search ALL sources in parallel (simplified sequential for reliability)
    all_results = []
    
    # 1. Academic Databases (High Priority)
    try:
        arxiv_results = search_arxiv(query, min(3, max_results//3))
        all_results.extend(arxiv_results)
        print(f"Found {len(arxiv_results)} arXiv results")
    except Exception as e:
        print(f"arXiv search failed: {e}")
    
    try:
        semantic_results = search_semantic_scholar(query, min(3, max_results//3))
        all_results.extend(semantic_results)
        print(f"Found {len(semantic_results)} Semantic Scholar results")
    except Exception as e:
        print(f"Semantic Scholar search failed: {e}")
    
    try:
        crossref_results = search_crossref(query, min(2, max_results//4))
        all_results.extend(crossref_results)
        print(f"Found {len(crossref_results)} Crossref results")
    except Exception as e:
        print(f"Crossref search failed: {e}")
    
    try:
        doaj_results = search_doaj(query, min(2, max_results//4))
        all_results.extend(doaj_results)
        print(f"Found {len(doaj_results)} DOAJ results")
    except Exception as e:
        print(f"DOAJ search failed: {e}")
    
    # 2. General Knowledge (Medium Priority)
    try:
        wiki_results = search_wikipedia(query, min(2, max_results//4))
        all_results.extend(wiki_results)
        print(f"Found {len(wiki_results)} Wikipedia results")
    except Exception as e:
        print(f"Wikipedia search failed: {e}")
    
    # 3. Research Platforms
    try:
        researchgate_results = search_research_gate(query, min(2, max_results//4))
        all_results.extend(researchgate_results)
        print(f"Found {len(researchgate_results)} ResearchGate results")
    except Exception as e:
        print(f"ResearchGate search failed: {e}")
    
    # 4. Theses and Institutions (Lower Priority)
    try:
        theses_results = search_theses(query, min(1, max_results//5))
        all_results.extend(theses_results)
        print(f"Found {len(theses_results)} Theses results")
    except Exception as e:
        print(f"Theses search failed: {e}")
    
    try:
        institution_results = search_research_institutions(query, min(1, max_results//5))
        all_results.extend(institution_results)
        print(f"Found {len(institution_results)} Institution results")
    except Exception as e:
        print(f"Institution search failed: {e}")
    
    # Remove duplicates by title
    unique_results = []
    seen_titles = set()
    
    for result in all_results:
        title = result.get('title', '').lower().strip()
        if title and title not in seen_titles and len(title) > 3:
            seen_titles.add(title)
            
            # Calculate or adjust reliability score
            score = result.get('reliability_score', 0.5)
            
            # Adjust based on source
            source = result.get('source', '')
            if source in ['arXiv', 'Crossref', 'DOAJ']:
                score = max(score, 0.7)
            elif source == 'Wikipedia':
                score = 0.6  # Good for general knowledge
            elif source == 'Research Institution':
                score = 0.9  # Very high for reputable institutions
            
            # Adjust based on year (recent = better)
            year = result.get('year')
            if year and isinstance(year, int):
                current_year = datetime.now().year
                if current_year - year <= 3:
                    score += 0.1
                elif current_year - year <= 10:
                    score += 0.05
            
            # Adjust based on citations
            citations = result.get('citations', 0)
            if citations > 100:
                score += 0.2
            elif citations > 10:
                score += 0.1
            
            score = min(1.0, max(0.3, score))  # Keep between 0.3 and 1.0
            
            # Determine level
            if score >= 0.8:
                level = "Very High"
            elif score >= 0.7:
                level = "High"
            elif score >= 0.6:
                level = "Good"
            elif score >= 0.5:
                level = "Medium"
            else:
                level = "Low"
            
            result['reliability_score'] = round(score, 2)
            result['reliability_level'] = level
            unique_results.append(result)
    
    # Sort by reliability score (highest first)
    unique_results.sort(key=lambda x: x['reliability_score'], reverse=True)
    
    # Limit to max_results
    final_results = unique_results[:max_results]
    
    print(f"Total unique results found: {len(final_results)}")
    
    return render_template('results.html', 
                         results=final_results,
                         query=query)

# The rest of your routes (synthesize, export, etc.) remain the same...

@app.route('/synthesize', methods=['POST'])
def synthesize():
    try:
        print("Synthesis endpoint called")
        
        # Parse JSON data
        data = request.get_json()
        if not data:
            print("No data received")
            return jsonify({'error': 'No data received'}), 400
            
        selected_results = data.get('selected_results', [])
        query = data.get('query', '')
        synthesis_type = data.get('type', 'summary')
        
        print(f"Synthesis type: {synthesis_type}, Query: {query}, Sources: {len(selected_results)}")
        
        if not selected_results:
            print("No results selected")
            return jsonify({'error': 'No results selected'}), 400
        
        # Ensure selected_results is a list
        if not isinstance(selected_results, list):
            print("Invalid data format")
            return jsonify({'error': 'Invalid data format'}), 400
        
        if synthesis_type == 'rrl':
            # Generate RRL section
            print("Generating RRL...")
            rrl_content = generate_rrl_section(selected_results, query)
            
            return jsonify({
                'type': 'rrl',
                'content': rrl_content,
                'sources_count': len(selected_results)
            })
        
        elif synthesis_type == 'citations':
            # Generate formatted citations
            print("Generating citations...")
            all_citations = []
            for result in selected_results:
                citations = result.get('citations_formatted', {})
                if citations:
                    all_citations.append(f"=== {result.get('title', 'Unknown')} ===")
                    for style, citation in citations.items():
                        all_citations.append(f"{style}: {citation}")
                    all_citations.append("")  # Add empty line between entries
            
            if not all_citations:
                all_citations = ["No citation formats available for selected sources."]
            
            return jsonify({
                'type': 'citations',
                'content': "\n".join(all_citations),
                'sources_count': len(selected_results)
            })
        
        else:  # Default summary
            # Extract all text
            print("Generating summary...")
            all_texts = []
            for result in selected_results:
                title = result.get('title', '')
                abstract = result.get('abstract', '')
                text = f"{title}. {abstract}"
                if text.strip():
                    all_texts.append(text)
            
            # Extract key points
            key_points = extract_key_points(all_texts, query) if all_texts else []
            
            # Generate summary
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
        print(f"Export endpoint called for type: {export_type}")
        
        # Parse JSON data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        results = data.get('results', [])
        query = data.get('query', 'Unnamed_Query')
        
        print(f"Exporting {len(results)} results for query: {query}")
        
        if not results:
            return jsonify({'error': 'No results to export'}), 400
        
        if export_type == 'bibtex':
            # Generate BibTeX entries
            print("Generating BibTeX...")
            bibtex_entries = []
            for result in results:
                # Create a safe entry ID
                title = result.get('title', 'Unknown')
                entry_id = re.sub(r'[^a-zA-Z0-9]', '_', title[:50]).lower()
                
                authors = result.get('authors', ['Unknown'])
                authors_str = ' and '.join(authors)
                
                year = result.get('year', '')
                journal = result.get('journal', '')
                url = result.get('url', '')
                doi = result.get('doi', '')
                
                bibtex = f"""@article{{{entry_id},
  title = {{{title}}},
  author = {{{authors_str}}},
  year = {{{year}}},
  journal = {{{journal}}},"""
                
                if doi:
                    bibtex += f"\n  doi = {{{doi}}},"
                
                if url:
                    bibtex += f"\n  url = {{{url}}},"
                
                bibtex += "\n  note = {Retrieved from Academic Research Hub}"
                bibtex += "\n}"
                
                bibtex_entries.append(bibtex)
            
            content = "\n\n".join(bibtex_entries)
            filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]}_references.bib"
            
            return jsonify({
                'content': content,
                'filename': filename
            })
        
        elif export_type == 'csv':
            # Generate CSV
            print("Generating CSV...")
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Title', 'Authors', 'Year', 'Source', 'Citations', 'Reliability Score', 'DOI', 'URL', 'Abstract Preview'])
            
            # Write data
            for result in results:
                writer.writerow([
                    result.get('title', ''),
                    '; '.join(result.get('authors', [])),
                    result.get('year', ''),
                    result.get('source', ''),
                    result.get('citations', 0),
                    result.get('reliability_score', 0),
                    result.get('doi', ''),
                    result.get('url', ''),
                    (result.get('abstract', '')[:200] + '...') if result.get('abstract') and len(result.get('abstract', '')) > 200 else result.get('abstract', '')
                ])
            
            content = output.getvalue()
            filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]}_results.csv"
            
            return jsonify({
                'content': content,
                'filename': filename
            })
        
        return jsonify({'error': 'Invalid export type'}), 400
    
    except Exception as e:
        print(f"Export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

@app.route('/test')
def test():
    return "✅ Flask is working! Academic Search ready."

@app.route('/debug', methods=['POST'])
def debug():
    """Debug endpoint to check data"""
    data = request.get_json()
    return jsonify({
        'received_data': str(data)[:500],
        'data_type': type(data).__name__,
        'keys': list(data.keys()) if isinstance(data, dict) else 'Not a dict'
    })
CORS(app, resources={r"/*": {"origins": ["https://your-project.up.railway.app", "http://localhost:5000"]}})

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error="Internal server error"), 500
# Add to the end of your app.py file
# Remove the required_packages line from here
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)