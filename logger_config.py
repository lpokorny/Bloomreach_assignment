import logging.handlers

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')

file_handler = logging.FileHandler('error.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)