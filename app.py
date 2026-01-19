from flask import Flask, render_template, request, jsonify
from flask_cors import CORS  # Add this import
import os
import requests
import arxiv
import re
import json
from datetime import datetime
import csv
import io

app = Flask(__name__)
CORS(app)  # Add CORS support to handle requests properly
app.secret_key = os.getenv('SECRET_KEY', 'academic-search-secret-key-123')

# Rest of your functions remain the same...
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

def extract_key_points(texts, query):
    """Extract key points from text"""
    key_points = []
    
    for text in texts:
        if not text:
            continue
            
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Score sentences based on relevance
        query_terms = set(query.lower().split())
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence.split()) >= 6:  # At least 6 words
                lower_sentence = sentence.lower()
                
                # Calculate relevance score
                sentence_terms = set(re.findall(r'\b\w+\b', lower_sentence))
                common_terms = query_terms.intersection(sentence_terms)
                relevance_score = len(common_terms) / len(query_terms) if query_terms else 0
                
                # Check for research indicators
                research_indicators = [
                    'found that', 'showed that', 'demonstrated that', 'concluded that',
                    'results show', 'results indicate', 'study found', 'research shows',
                    'significantly', 'evidence suggests', 'analysis reveals', 'the findings',
                    'in conclusion', 'implications are', 'contributes to', 'advances the',
                    'novel approach', 'innovative method', 'proposed framework'
                ]
                
                indicator_score = 0
                for indicator in research_indicators:
                    if indicator in lower_sentence:
                        indicator_score += 0.1
                
                total_score = relevance_score + indicator_score
                
                if total_score > 0.2:  # Lower threshold for inclusion
                    key_points.append({
                        'text': sentence,
                        'score': round(total_score, 2)
                    })
    
    # Sort by score and remove duplicates
    key_points.sort(key=lambda x: x['score'], reverse=True)
    
    # Remove similar sentences
    unique_points = []
    seen = set()
    for point in key_points[:20]:  # Limit to top 20
        words = set(re.findall(r'\b\w+\b', point['text'].lower()))
        is_similar = False
        for seen_words in seen:
            similarity = len(words.intersection(seen_words)) / len(words.union(seen_words)) if words.union(seen_words) else 0
            if similarity > 0.6:  # 60% similarity threshold
                is_similar = True
                break
        
        if not is_similar:
            unique_points.append(point['text'])
            seen.add(frozenset(words))
    
    return unique_points[:10]  # Return top 10

def generate_rrl_section(results, query):
    """Generate a complete RRL (Review of Related Literature) section"""
    
    if not results:
        return "No sources selected for RRL generation."
    
    rrl_parts = [
        f"# Review of Related Literature: {query}",
        "\n## Introduction",
        f"This review synthesizes literature on {query}. The search yielded {len(results)} relevant sources from academic databases including arXiv and Semantic Scholar.",
        
        "\n## Literature Review",
    ]
    
    # Group by year (most recent first)
    results_by_year = {}
    for result in results:
        year = str(result.get('year', 'Unknown'))
        if year not in results_by_year:
            results_by_year[year] = []
        results_by_year[year].append(result)
    
    # Sort years descending
    sorted_years = sorted(results_by_year.keys(), reverse=True)
    
    for year in sorted_years:
        rrl_parts.append(f"\n### {year}")
        for result in results_by_year[year]:
            # Summarize each paper
            summary = f"{result.get('title', 'No title')} ({result.get('source', 'Unknown source')})"
            authors = result.get('authors', [])
            if authors:
                summary += f" by {', '.join(authors[:3])}"
                if len(authors) > 3:
                    summary += " et al."
            
            rrl_parts.append(f"- {summary}")
            
            # Add key findings if available
            abstract = result.get('abstract', '')
            if abstract:
                # Extract first sentence or key phrase
                sentences = re.split(r'(?<=[.!?])\s+', abstract)
                if sentences:
                    first_sentence = sentences[0]
                    if len(first_sentence) > 150:
                        first_sentence = first_sentence[:150] + "..."
                    rrl_parts.append(f"  - Key finding: {first_sentence}")
    
    rrl_parts.extend([
        "\n## Synthesis",
        "The literature reveals several key themes and findings:",
        "1. [Theme 1 based on the reviewed literature]",
        "2. [Theme 2 based on the reviewed literature]",
        "3. [Theme 3 based on the reviewed literature]",
        
        "\n## Gaps and Future Research",
        "Based on the review, the following research gaps were identified:",
        "1. [Gap 1 - e.g., methodological limitations, understudied areas]",
        "2. [Gap 2 - e.g., contradictory findings, emerging trends]",
        "3. [Gap 3 - e.g., practical applications, theoretical extensions]",
        
        "\n## Conclusion",
        f"This review provides a comprehensive overview of current research on {query}, highlighting significant contributions and areas for future investigation."
    ])
    
    return "\n".join(rrl_parts)

def generate_summary(selected_results, query, key_points):
    """Generate comprehensive summary"""
    summary_parts = [
        f"# RESEARCH SYNTHESIS REPORT",
        f"## Topic: {query}",
        f"## Date: {datetime.now().strftime('%Y-%m-%d')}",
        f"## Sources Analyzed: {len(selected_results)}",
        "\n## EXECUTIVE SUMMARY",
    ]
    
    if key_points:
        summary_parts.append("The analysis of selected literature reveals the following key findings:")
        for i, point in enumerate(key_points, 1):
            summary_parts.append(f"{i}. {point}")
    else:
        summary_parts.append("Key points were extracted from the selected sources.")
    
    summary_parts.extend([
        "\n## METHODOLOGY",
        f"Searched databases: arXiv, Semantic Scholar",
        f"Search query: '{query}'",
        f"Selection criteria: Academic relevance, publication quality, citation count",
        
        "\n## DETAILED ANALYSIS",
    ])
    
    # Add detailed analysis of each source
    for i, source in enumerate(selected_results[:10], 1):  # Limit to 10 sources
        title = source.get('title', 'No title')
        if len(title) > 100:
            title = title[:100] + "..."
        
        summary_parts.append(f"\n### {i}. {title}")
        summary_parts.append(f"- **Authors:** {', '.join(source.get('authors', ['Unknown']))}")
        summary_parts.append(f"- **Year:** {source.get('year', 'Unknown')}")
        summary_parts.append(f"- **Source:** {source.get('source', 'Unknown')}")
        summary_parts.append(f"- **Citations:** {source.get('citations', 0)}")
        summary_parts.append(f"- **Reliability Score:** {source.get('reliability_score', 0)}/1.0")
        
        abstract = source.get('abstract', '')
        if abstract:
            if len(abstract) > 300:
                abstract = abstract[:300] + "..."
            summary_parts.append(f"- **Summary:** {abstract}")
    
    summary_parts.extend([
        "\n## IMPLICATIONS",
        "The synthesized findings have several implications for research and practice:",
        "1. Theoretical implications: Contributes to the understanding of the field",
        "2. Practical applications: Provides insights for real-world implementation",
        "3. Future research directions: Identifies areas needing further investigation",
        
        "\n## LIMITATIONS",
        "This synthesis has the following limitations:",
        "1. Limited to selected sources from specific databases",
        "2. May not capture all recent developments in the field",
        "3. Automated extraction may miss nuanced interpretations",
        
        "\n## CONCLUSION",
        f"This synthesis provides a comprehensive overview of current research on {query}, ",
        "highlighting key findings, methodological approaches, and areas for future investigation."
    ])
    
    return "\n".join(summary_parts)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '')
    max_results = int(request.form.get('max_results', 10))
    
    if not query:
        return render_template('error.html', error="Please enter a search query")
    
    # Search all sources
    all_results = []
    
    # Search arXiv
    arxiv_results = search_arxiv(query, min(5, max_results))
    all_results.extend(arxiv_results)
    
    # Search Semantic Scholar
    semantic_results = search_semantic_scholar(query, min(5, max_results))
    all_results.extend(semantic_results)
    
    # Remove duplicates
    unique_results = []
    seen_titles = set()
    for result in all_results:
        title = result.get('title', '').lower()
        if title and title not in seen_titles:
            seen_titles.add(title)
            
            # Calculate reliability score
            score = 0.0
            if result['source'] == 'arXiv':
                score += 0.8
            elif result['source'] == 'Semantic Scholar':
                score += 0.7
            
            if result.get('year'):
                try:
                    year = int(result['year'])
                    current_year = datetime.now().year
                    if current_year - year <= 2:
                        score += 0.2
                except:
                    pass
            
            citations = result.get('citations', 0)
            if citations > 100:
                score += 0.2
            elif citations > 10:
                score += 0.1
            
            score = min(1.0, score)
            
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
    
    # Sort by reliability score
    unique_results.sort(key=lambda x: x['reliability_score'], reverse=True)
    
    return render_template('results.html', 
                         results=unique_results[:max_results],
                         query=query)

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