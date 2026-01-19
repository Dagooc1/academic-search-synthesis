from typing import List, Dict
import re
from datetime import datetime
from config import Config

class ReliabilityChecker:
    def __init__(self):
        self.config = Config()
    
    def score_sources(self, results: List[Dict]) -> List[Dict]:
        """Score sources based on reliability criteria"""
        scored_results = []
        
        for result in results:
            score = self._calculate_reliability_score(result)
            result['reliability_score'] = score
            result['reliability_level'] = self._get_reliability_level(score)
            scored_results.append(result)
        
        # Sort by reliability score
        scored_results.sort(key=lambda x: x['reliability_score'], reverse=True)
        
        return scored_results
    
    def _calculate_reliability_score(self, result: Dict) -> float:
        """Calculate reliability score (0-1)"""
        score = 0.0
        
        # Domain-based scoring
        domain_score = self._get_domain_score(result.get('url', ''))
        score += domain_score * self.config.RELIABILITY_WEIGHTS['domain_score']
        
        # Citation count scoring
        citation_score = self._get_citation_score(result.get('citations', 0))
        score += citation_score * self.config.RELIABILITY_WEIGHTS['citation_count']
        
        # Publication date scoring
        date_score = self._get_date_score(result.get('year', ''))
        score += date_score * self.config.RELIABILITY_WEIGHTS['publication_date']
        
        # Journal/venue impact
        venue_score = self._get_venue_score(result.get('venue', ''))
        score += venue_score * self.config.RELIABILITY_WEIGHTS['journal_impact']
        
        return min(1.0, score)  # Cap at 1.0
    
    def _get_domain_score(self, url: str) -> float:
        """Score based on domain"""
        if not url:
            return 0.3
        
        url_lower = url.lower()
        
        # High reliability domains
        high_trust = ['.edu', '.ac.', 'arxiv.org', 'pubmed', 'nih.gov', 
                     'science.org', 'nature.com', 'thelancet.com']
        for domain in high_trust:
            if domain in url_lower:
                return 0.9
        
        # Medium reliability
        medium_trust = ['researchgate', 'academia.edu', 'springer', 
                       'ieee.org', 'acm.org', 'jstor.org']
        for domain in medium_trust:
            if domain in url_lower:
                return 0.7
        
        # Government domains
        if '.gov' in url_lower:
            return 0.8
        
        return 0.4  # Default score for unknown domains
    
    def _get_citation_score(self, citations: int) -> float:
        """Score based on citation count"""
        if not citations:
            return 0.3
        
        if citations > 1000:
            return 1.0
        elif citations > 100:
            return 0.8
        elif citations > 10:
            return 0.6
        elif citations > 0:
            return 0.4
        else:
            return 0.3
    
    def _get_date_score(self, year: str) -> float:
        """Score based on publication date (prefer recent but not too recent)"""
        if not year:
            return 0.5
        
        try:
            pub_year = int(year)
            current_year = datetime.now().year
            
            age = current_year - pub_year
            
            if age <= 2:  # Very recent
                return 0.8
            elif age <= 5:  # Recent
                return 0.9
            elif age <= 10:  # Established
                return 0.7
            elif age <= 20:  # Classic but might be outdated
                return 0.5
            else:  # Possibly outdated
                return 0.3
        except:
            return 0.5
    
    def _get_venue_score(self, venue: str) -> float:
        """Score based on journal/conference venue"""
        if not venue:
            return 0.5
        
        venue_lower = venue.lower()
        
        # High-impact journals
        high_impact = ['nature', 'science', 'cell', 'lancet', 'nejm',
                      'pnas', 'jama', 'bmj', 'plos one']
        for journal in high_impact:
            if journal in venue_lower:
                return 0.9
        
        # Good journals
        good_journals = ['ieee', 'acm', 'springer', 'elsevier', 'wiley',
                        'taylor & francis', 'oxford university press']
        for journal in good_journals:
            if journal in venue_lower:
                return 0.7
        
        return 0.5
    
    def _get_reliability_level(self, score: float) -> str:
        """Convert score to reliability level"""
        if score >= 0.8:
            return "Very High"
        elif score >= 0.7:
            return "High"
        elif score >= 0.6:
            return "Medium-High"
        elif score >= 0.5:
            return "Medium"
        elif score >= 0.4:
            return "Medium-Low"
        else:
            return "Low"