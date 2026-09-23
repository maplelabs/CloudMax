"""
Alert Grouping Configuration Loader

Loads alert grouping configuration from database or uses defaults.
"""

import logging

from src.server.models.api import AlertGroupingConfig
from src.server.utilities.config import load_config_from_db, should_use_database_config

logger = logging.getLogger(__name__)


async def get_grouping_config_async() -> AlertGroupingConfig:
    """
    Get alert grouping configuration.

    Loads from database if CONFIG_DB=true, otherwise uses defaults.
    """
    try:
        if should_use_database_config():
            config_dict = await load_config_from_db()
            if config_dict and "alert_grouping_config" in config_dict:
                logger.info("Loading alert grouping config from database")
                return AlertGroupingConfig(**config_dict["alert_grouping_config"])
            else:
                logger.warning("No alert grouping config in database, using defaults")
                return AlertGroupingConfig()
        else:
            logger.info("Using default alert grouping config (CONFIG_DB=false)")
            return AlertGroupingConfig()
    except Exception as e:
        logger.exception(f"Failed to load alert grouping config: {e}")
        logger.warning("Falling back to default alert grouping config")
        return AlertGroupingConfig()


def get_grouping_config_sync() -> AlertGroupingConfig:
    """
    Get alert grouping configuration (sync context).

    Uses default values only.
    """
    logger.info("Using default alert grouping config (sync context)")
    return AlertGroupingConfig()
