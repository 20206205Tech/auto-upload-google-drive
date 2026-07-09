from environs import Env
from loguru import logger

env = Env()
logger.info("Loading environment variables...")


DATABASE_URL = env.str("DATABASE_URL")
GOOGLE_CREDENTIALS = env.str("GOOGLE_CREDENTIALS", "")
