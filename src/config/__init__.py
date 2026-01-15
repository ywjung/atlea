"""Configuration module

Application-wide configuration and constants.
"""

from .settings import *
from .production import ProductionConfig, config

__all__ = ['ProductionConfig', 'config']
