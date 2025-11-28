"""Main application entry point."""
import logging
import time
import threading
from config import Config
from coordinator import EnergyCoordinator
from api_server import APIServer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def auto_update_loop(coordinator: EnergyCoordinator, interval: int):
    """Auto-update loop running in background."""
    logger.info(f"Auto-update loop started (interval: {interval}s)")

    # Initial delay to let things settle
    time.sleep(30)

    while True:
        try:
            coordinator.update()
        except Exception as e:
            logger.error(f"Error in auto-update loop: {e}", exc_info=True)

        time.sleep(interval)


def main():
    """Main application."""
    logger.info("=" * 60)
    logger.info("Energy Demand Predictor & Battery Optimizer")
    logger.info("=" * 60)

    # Load configuration
    logger.info("Loading configuration...")
    config = Config()

    # Initialize coordinator
    logger.info("Initializing coordinator...")
    coordinator = EnergyCoordinator(config)

    # Train model on startup
    logger.info("Training initial model...")
    coordinator.train_model()

    # Run initial update
    logger.info("Running initial update...")
    coordinator.update()

    # Start auto-update thread
    if config.auto_update_interval > 0:
        logger.info(f"Starting auto-update thread (every {config.auto_update_interval}s)...")
        update_thread = threading.Thread(
            target=auto_update_loop,
            args=(coordinator, config.auto_update_interval),
            daemon=True
        )
        update_thread.start()
    else:
        logger.info("Auto-update disabled")

    # Start API server (blocking)
    logger.info("Starting API server...")
    api_server = APIServer(config, coordinator)
    api_server.run()


if __name__ == '__main__':
    main()
