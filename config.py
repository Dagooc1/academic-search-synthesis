import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Keys (store in .env file)
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
    SEMANTIC_SCHOLAR_API_KEY = os.getenv('SEMANTIC_SCHOLAR_API_KEY')
    
    # Search settings
    DEFAULT_MAX_RESULTS = 10
    TIMEOUT = 30
    
    # Academic domains (priority sources)
    ACADEMIC_DOMAINS = [
        '.edu',
        '.ac.',
        '.edu.',
        'arxiv.org',
        'scholar.google.com',
        'researchgate.net',
        'academia.edu',
        'springer.com',
        'scienceDirect.com',
        'ieee.org',
        'acm.org',
        'jstor.org',
        'pubmed.ncbi.nlm.nih.gov',
        'ncbi.nlm.nih.gov',
        'plos.org',
        'nature.com',
        'science.org',
        'pnas.org',
        'thelancet.com',
        'nejm.org'
    ]
    
    # Reliability scoring weights
    RELIABILITY_WEIGHTS = {
        'domain_score': 0.3,
        'citation_count': 0.25,
        'author_credentials': 0.2,
        'publication_date': 0.15,
        'journal_impact': 0.1
    }