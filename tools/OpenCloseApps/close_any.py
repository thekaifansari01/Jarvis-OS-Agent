from AppOpener import close
from core.logger.logger import logger

def close_any_app(apps_to_close):
    closed = []

    if isinstance(apps_to_close, str):
        apps_to_close = [apps_to_close]

    for name in apps_to_close:
        name_lower = name.lower().strip()
        logger.info(f"Attempting to smoothly close '{name}'...")

        try:
            close(name_lower, match_closest=True, throw_error=True)
            logger.info(f"Successfully closed: {name}")
            closed.append(name)

        except Exception as e:
            error_msg = str(e).lower()

            if "not running" in error_msg:
                logger.warning(f"'{name}' is not currently running.")
            elif "not found" in error_msg:
                logger.warning(f"Could not find any app matching '{name}' on this system.")
            else:
                logger.error(f"Unexpected error while closing '{name}': {e}")

    return closed

if __name__ == "__main__":
    apps = ["calculator", "notepad", "whatsapp"]
    closed_apps = close_any_app(apps)
    logger.info(f"Final Closed List: {closed_apps}")