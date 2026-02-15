"""
Structured Logging Configuration
JSON logs with request ID correlation
"""
import sys
import logging
from typing import Any, Dict

from loguru import logger

from .config import settings


class InterceptHandler(logging.Handler):
    """Intercept standard logging and redirect to Loguru"""
    
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # Find caller
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging():
    """Configure Loguru logging"""
    
    # Remove default logger
    logger.remove()
    
    # Add console logger
    if settings.LOG_JSON_FORMAT and settings.ENVIRONMENT == "production":
        # JSON format for production
        logger.add(
            sys.stdout,
            format="{time} | {level} | {name}:{function}:{line} | {message}",
            level=settings.LOG_LEVEL,
            serialize=True,
        )
    else:
        # Human-readable format for development
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.LOG_LEVEL,
            colorize=True,
        )
    
    # Add file logger
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # Rotate daily
        retention="30 days",
        level=settings.LOG_LEVEL,
        format="{time} | {level} | {name}:{function}:{line} | {message}" if settings.LOG_JSON_FORMAT else "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        serialize=settings.LOG_JSON_FORMAT,
    )
    
    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Intercept uvicorn logs
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]
    
    # Intercept sqlalchemy logs
    logging.getLogger("sqlalchemy.engine").handlers = [InterceptHandler()]
    
    logger.info(f"Logging configured: level={settings.LOG_LEVEL}, json={settings.LOG_JSON_FORMAT}")


# Initialize logging on import
configure_logging()
