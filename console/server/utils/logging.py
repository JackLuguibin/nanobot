"""Logging configuration for the console server."""

from loguru import logger


def setup_logging() -> None:
    """Configure logging for the console server."""
    logger.remove()
    logger.add(
        "console/server/logs/console.log",
        rotation="10 MB",
        retention="7 days",
        level="INFO",
    )
    logger.add(
        "console/server/logs/error.log",
        rotation="10 MB",
        retention="7 days",
        level="ERROR",
    )
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
    )
