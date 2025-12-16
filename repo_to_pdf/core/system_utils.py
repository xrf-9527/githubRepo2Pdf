
import sys
import os
import ctypes
import ctypes.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def ensure_cairo_available():
    """
    Ensure Cairo library is available on macOS by explicitly loading it if necessary.
    This fixes the 'no library called "cairo-2" was found' error when using Homebrew cairo.
    """
    if sys.platform != 'darwin':
        return

    # Only attempt if we suspect we are running from a venv or standard install 
    # that might miss the brew library path
    
    # Common Homebrew paths for Cairo
    possible_paths = [
        # Apple Silicon / standard Homebrew
        '/opt/homebrew/lib/libcairo.2.dylib',
        # Intel Mac / old Homebrew
        '/usr/local/lib/libcairo.2.dylib',
    ]

    # Try to find the library
    found_path = None
    for path in possible_paths:
        if os.path.exists(path):
            found_path = path
            break
            
    if found_path:
        try:
            logger.debug(f"MacOS: Attempting to explicitly load cairo from {found_path}")
            # Explicitly load the library
            ctypes.CDLL(found_path)
            
            # Monkeypatch ctypes.util.find_library to return our found path
            # This is necessary because cairosvg uses find_library which fails
            # even if we loaded the library with CDLL.
            original_find_library = ctypes.util.find_library
            
            def new_find_library(name):
                # If looking for cairo/libcairo, return our path
                if 'cairo' in name:
                    logger.debug(f"MacOS: Intercepted find_library('{name}') -> {found_path}")
                    return found_path
                return original_find_library(name)
                
            ctypes.util.find_library = new_find_library
            logger.debug("MacOS: Monkeypatched ctypes.util.find_library for cairo")
            
        except OSError as e:
            logger.warning(f"MacOS: Failed to load cairo from {found_path}: {e}")
    else:
        logger.debug("MacOS: Could not find cairo in standard Homebrew paths")
