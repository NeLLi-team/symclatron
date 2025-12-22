"""
symclatron: symbiont classifier

Machine Learning-based classification of microbial symbiotic lifestyles

symclatron is a tool that classifies microbial genomes into three symbiotic lifestyle categories:
- Free-living
- Symbiont; Host-associated
- Symbiont; Obligate-intracellular

External dependencies (must be installed separately):
- HMMER (hmmsearch command must be available in PATH)

Author: Juan C. Villada <jvillada@lbl.gov>
US Department of Energy Joint Genome Institute (JGI)
Lawrence Berkeley National Laboratory (LBNL)
"""

# Version information - required by flit for dynamic version
__version__ = "0.7.0"

# Author information - required by flit
__author__ = "Juan C. Villada"
__email__ = "jvillada@lbl.gov"

# Package metadata
__title__ = "symclatron"
__description__ = "Machine Learning-based classification of microbial symbiotic lifestyles"
__url__ = "https://github.com/NeLLi-team/symclatron"
__license__ = "MIT"

# Import main components for easy access
from .symclatron import (
    # Main application
    app,

    # Version and info functions
    __version__ as version,
    print_header,
    greetings,

    # Main classification function
    classify,

    # Command functions
    setup_data,
    classify_genomes,
    run_test,

    # Data setup function
    extract_data,

    # Utility classes
    ResourceMonitor,

    # Additional utility functions that may be useful for advanced users
    validate_input,
    setup_logging,
    generate_classification_summary,
)

# Define what gets imported with "from symclatron import *"
__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "__title__",
    "__description__",
    "__url__",
    "__license__",
    "app",
    "version",
    "print_header",
    "greetings",
    "classify",
    "setup_data",
    "classify_genomes",
    "run_test",
    "extract_data",
    "ResourceMonitor",
    "validate_input",
    "setup_logging",
    "generate_classification_summary",
]

# Package-level convenience functions
def get_version():
    """Return the package version."""
    return __version__

def get_info():
    """Return package information."""
    return {
        "name": __title__,
        "version": __version__,
        "description": __description__,
        "author": __author__,
        "email": __email__,
        "url": __url__,
        "license": __license__,
    }

# Entry point for command line usage
def main():
    """Main entry point for the symclatron command line interface."""
    app()