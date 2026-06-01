import logging

LOG_FORMAT = '%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'


def setup_logging(level: int = logging.INFO, handlers=None) -> None:
    kwargs = {'level': level, 'format': LOG_FORMAT, 'datefmt': '%Y-%m-%d %H:%M:%S'}
    if handlers is not None:
        kwargs['handlers'] = handlers
    logging.basicConfig(**kwargs)
