from typing import List, Dict
import nltk
from nltk.tokenize import sent_tokenize
from nltk.corpus import stopwords
from collections import defaultdict
import re

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

class InformationSynthesizer:
    def __init__(self):
        self.stop_words = set(stopwords.words('english'))
    
    def synthesize_information(self, sources: List[Dict], query: str) -> Dict:
        """Synthesize information from multiple sources"""
        
        # Extract key information from sources
        all_texts = []
        for source in sources:
            text = f"{source.get('title', '')}. {source.get('abstract', '')}"
            all_texts.append(text)
        
        # Extract key points
        key_points = self._extract_key_points(all_texts, query)
        
        # Find consensus and contradictions
        consensus, contradictions = self._analyze_agreement(all_texts)
        
        # Generate summary
        summary = self._generate_summary(key_points, consensus, contradictions)
        
        return {
            'summary': summary,
            'key_points': key_points,
            'consensus': consensus,
            'contradictions': contradictions,
            'sources_count': len(sources)
        }
    
    def _extract_key_points(self, texts: List[str], query: str) -> List[str]:
        """Extract key points from texts"""
        # Tokenize sentences
        all_sentences = []
        for text in texts:
            sentences = sent_tokenize(text)
            all_sentences.extend(sentences)
        
        # Score sentences based on relevance to query
        query_terms = set(query.lower().split())
        scored_sentences = []
        
        for sentence in all_sentences:
            # Remove citations and special characters
            clean_sentence = re.sub(r'\[\d+\]', '', sentence)
            clean_sentence = re.sub(r'\([^)]*\)', '', clean_sentence)
            
            # Calculate relevance score
            sentence_terms = set(clean_sentence.lower().split())
            common_terms = query_terms.intersection(sentence_terms)
            score = len(common_terms) / len(query_terms) if query_terms else 0
            
            # Bonus for academic indicators
            academic_indicators = ['study', 'research', 'found', 'results', 'conclusion',
                                 'evidence', 'data', 'analysis', 'significant', 'p <']
            for indicator in academic_indicators:
                if indicator in clean_sentence.lower():
                    score += 0.1
            
            if score > 0:
                scored_sentences.append((score, clean_sentence.strip()))
        
        # Sort by score and take top sentences
        scored_sentences.sort(reverse=True, key=lambda x: x[0])
        key_points = [sentence for _, sentence in scored_sentences[:10]]
        
        return list(set(key_points))  # Remove duplicates
    
    def _analyze_agreement(self, texts: List[str]) -> tuple:
        """Analyze agreement between sources"""
        # Extract claims/findings (simplified)
        claims = defaultdict(list)
        
        for i, text in enumerate(texts):
            sentences = sent_tokenize(text)
            for sentence in sentences:
                # Look for findings/claims (simplified pattern matching)
                if any(word in sentence.lower() for word in 
                      ['found', 'showed', 'demonstrated', 'indicated', 'suggested',
                       'concluded', 'revealed', 'confirmed']):
                    
                    # Clean the claim
                    claim = sentence.strip()
                    claim = re.sub(r'\[\d+\]', '', claim)
                    
                    # Group similar claims
                    key = claim[:50].lower()  # Simplified grouping key
                    claims[key].append({
                        'text': claim,
                        'source_index': i
                    })
        
        # Find consensus and contradictions
        consensus = []
        contradictions = []
        
        for claim_group in claims.values():
            if len(claim_group) > 1:
                # Multiple sources mention similar claim
                consensus.append({
                    'claim': claim_group[0]['text'],
                    'supporting_sources': len(claim_group)
                })
            else:
                # Single source claim - potential contradiction if others say different
                contradictions.append({
                    'claim': claim_group[0]['text'],
                    'source_index': claim_group[0]['source_index']
                })
        
        return consensus, contradictions
    
    def _generate_summary(self, key_points: List[str], 
                         consensus: List[Dict], 
                         contradictions: List[Dict]) -> str:
        """Generate a coherent summary"""
        
        summary_parts = []
        
        # Introduction
        if key_points:
            summary_parts.append("Based on analysis of multiple academic sources:")
        
        # Key findings
        if key_points:
            summary_parts.append("\nKey Findings:")
            for i, point in enumerate(key_points[:5], 1):
                summary_parts.append(f"{i}. {point}")
        
        # Consensus points
        if consensus:
            summary_parts.append("\nPoints of Consensus:")
            for item in consensus[:3]:
                summary_parts.append(f"• {item['claim']} "
                                   f"(supported by {item['supporting_sources']} sources)")
        
        # Contradictions/unique points
        if contradictions:
            summary_parts.append("\nUnique or Contradictory Points:")
            for item in contradictions[:3]:
                summary_parts.append(f"• {item['claim']} "
                                   f"(from a single source)")
        
        return "\n".join(summary_parts)