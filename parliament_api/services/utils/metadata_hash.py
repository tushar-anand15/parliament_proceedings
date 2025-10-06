"""
Metadata Hash Service

Generates consistent hashes for questions and debates metadata to identify true duplicates.
Only generates hash from the FINAL metadata (with URLs), not intermediate steps.
"""
import hashlib
import json
from typing import Dict, Any


def generate_question_metadata_hash(metadata: Dict[str, Any]) -> str:
    """
    Generate a consistent hash for question metadata.
    
    Uses fields that define a unique question:
    - question_number
    - question_type (STARRED/UNSTARRED)
    - session info (lok_sabha_number, session_number)
    - subjects/title
    - ministry
    - date
    - PDF URLs (the actual file paths)
    
    Args:
        metadata: Dict containing question metadata
        
    Returns:
        SHA256 hash as hex string
    """
    # Extract key fields that define uniqueness
    hash_data = {
        'question_number': str(metadata.get('question_number', '')),
        'question_type': str(metadata.get('question_type', '')),
        'lok_sabha_number': str(metadata.get('lok_sabha_number', '')),
        'rajya_sabha_number': str(metadata.get('rajya_sabha_number', '')),
        'session_number': str(metadata.get('session_number', '')),
        'subjects': str(metadata.get('subjects', '')),
        'ministry': str(metadata.get('ministry', '')),
        'date': str(metadata.get('date', '')),
        'questions_file_path': str(metadata.get('questions_file_path', '')),
        'questions_file_path_hindi': str(metadata.get('questions_file_path_hindi', '')),
    }
    
    # Sort keys for consistency and convert to JSON
    hash_string = json.dumps(hash_data, sort_keys=True, ensure_ascii=True)
    
    # Generate SHA256 hash
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()


def generate_debate_metadata_hash(metadata: Dict[str, Any]) -> str:
    """
    Generate a consistent hash for debate metadata.
    
    Uses fields that define a unique debate:
    - lok_sabha_number, session_number
    - debate_date
    - debate_title
    - PDF URL
    
    Args:
        metadata: Dict containing debate metadata
        
    Returns:
        SHA256 hash as hex string
    """
    # Extract key fields that define uniqueness
    hash_data = {
        'lok_sabha_number': str(metadata.get('lok_sabha_number', '')),
        'rajya_sabha_number': str(metadata.get('rajya_sabha_number', '')),
        'session_number': str(metadata.get('session_number', '')),
        'debate_date': str(metadata.get('debate_date', '')),
        'debate_title': str(metadata.get('debate_title', '')),
        'pdf_url': str(metadata.get('pdf_url', '')),
        'time_slot': str(metadata.get('time_slot', '')),  # For RS verbatim debates
    }
    
    # Sort keys for consistency and convert to JSON
    hash_string = json.dumps(hash_data, sort_keys=True, ensure_ascii=True)
    
    # Generate SHA256 hash
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()


def verify_question_hash(metadata: Dict[str, Any], expected_hash: str) -> bool:
    """
    Verify if question metadata matches the expected hash.
    
    Args:
        metadata: Question metadata dict
        expected_hash: Expected hash string
        
    Returns:
        True if hash matches
    """
    actual_hash = generate_question_metadata_hash(metadata)
    return actual_hash == expected_hash


def verify_debate_hash(metadata: Dict[str, Any], expected_hash: str) -> bool:
    """
    Verify if debate metadata matches the expected hash.
    
    Args:
        metadata: Debate metadata dict
        expected_hash: Expected hash string
        
    Returns:
        True if hash matches
    """
    actual_hash = generate_debate_metadata_hash(metadata)
    return actual_hash == expected_hash
