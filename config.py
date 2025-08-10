#!/usr/bin/env python3
"""
Configuration wrapper for Han Dating Bot.
This file maintains backward compatibility while using the new src/ structure.
"""

import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and re-export all configuration
from src.config.config import *