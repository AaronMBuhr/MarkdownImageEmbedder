"""
Logging setup module for MarkdownImageEmbedder.
"""

import logging
import sys


class LoggerSetup:
    """Sets up and configures the process logger for the application."""
    
    # Logger instance
    _process_logger: logging.Logger = None
    
    @classmethod
    def initialize_logger(cls, debug: bool = False, verbose: bool = False) -> None:
        """
        Initialize and configure the process logger.
        
        Args:
            debug: Enable debug logging level
            verbose: Enable verbose logging level
        """
        # Determine log level based on flags
        if debug:
            log_level = logging.DEBUG
        elif verbose:
            log_level = logging.INFO
        else:
            log_level = logging.WARNING
            
        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format='%(levelname)s: %(message)s',
            stream=sys.stderr
        )
        
        # Create process logger
        cls._process_logger = logging.getLogger('process')
        cls._process_logger.setLevel(log_level)
        
    @classmethod
    def get_logger(cls) -> logging.Logger:
        """
        Get the process logger.
        
        Returns:
            logging.Logger: The process logger
        """
        if cls._process_logger is None:
            cls.initialize_logger()
        return cls._process_logger
