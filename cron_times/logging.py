import logging


def setup_logging(level: int | str = logging.INFO):
    logger = logging.getLogger("cron_times")
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s in cron-times: %(message)s"
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger.addHandler(handler)
