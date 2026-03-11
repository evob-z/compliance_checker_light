"""
Configuration settings for Compliance Checker
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List


# Default paths
DEFAULT_CONFIG_DIR = Path(__file__).parent
DEFAULT_CHECKLISTS_DIR = DEFAULT_CONFIG_DIR / "checklists"
DEFAULT_DOCUMENT_PATH = Path("./documents")
DEFAULT_OUTPUT_DIR = Path("./output")


# Concurrency defaults
DEFAULT_MAX_CONCURRENT_CHECKS = 3
DEFAULT_ENABLE_THROTTLING = True
DEFAULT_CHECK_TIMEOUT = 300  # 5 minutes


# Semantic matching defaults
DEFAULT_SIMILARITY_THRESHOLD = 0.75
DEFAULT_USE_SEMANTIC = True


# Visual inspection defaults
DEFAULT_USE_VISUAL = True


def get_concurrency_config() -> Dict[str, Any]:
    """
    Get concurrency configuration
    
    Returns:
        Dictionary with concurrency settings
    """
    return {
        "max_concurrent_checks": int(os.getenv("CC_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT_CHECKS)),
        "enable_throttling": os.getenv("CC_ENABLE_THROTTLING", "true").lower() == "true",
        "check_timeout": int(os.getenv("CC_CHECK_TIMEOUT", DEFAULT_CHECK_TIMEOUT)),
    }


def generate_output_path(project_id: str) -> Path:
    """
    Generate output path for report
    
    Args:
        project_id: Project identifier
        
    Returns:
        Path object for output file
    """
    output_dir = Path(os.getenv("CC_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"compliance_report_{project_id}.pdf"


def scan_default_documents() -> List[str]:
    """
    Scan default documents directory
    
    Returns:
        List of document file paths
    """
    doc_path = Path(os.getenv("CC_DOCUMENT_PATH", DEFAULT_DOCUMENT_PATH))
    
    if not doc_path.exists():
        return []
    
    supported_extensions = {".pdf", ".docx", ".doc"}
    document_paths = []
    
    for ext in supported_extensions:
        for file_path in doc_path.glob(f"*{ext}"):
            if file_path.is_file():
                document_paths.append(str(file_path))
    
    return sorted(document_paths)


def get_default_similarity_threshold() -> float:
    """
    Get default similarity threshold for semantic matching
    
    Returns:
        Similarity threshold value (0.0 - 1.0)
    """
    return float(os.getenv("CC_SIMILARITY_THRESHOLD", DEFAULT_SIMILARITY_THRESHOLD))


def get_default_use_semantic() -> bool:
    """
    Get default setting for using semantic matching
    
    Returns:
        True if semantic matching should be used by default
    """
    return os.getenv("CC_USE_SEMANTIC", "true").lower() == "true"


def get_default_use_visual() -> bool:
    """
    Get default setting for using visual inspection
    
    Returns:
        True if visual inspection should be used by default
    """
    return os.getenv("CC_USE_VISUAL", "true").lower() == "true"


def get_checklist_path(checklist_id: str) -> Optional[Path]:
    """
    Get path to checklist file by ID
    
    Args:
        checklist_id: Checklist identifier (e.g., "default")
        
    Returns:
        Path to checklist file or None if not found
    """
    if not checklist_id:
        checklist_id = "default"
    
    # Try YAML extension first
    checklist_path = DEFAULT_CHECKLISTS_DIR / f"{checklist_id}.yaml"
    if checklist_path.exists():
        return checklist_path
    
    # Try YML extension
    checklist_path = DEFAULT_CHECKLISTS_DIR / f"{checklist_id}.yml"
    if checklist_path.exists():
        return checklist_path
    
    return None
