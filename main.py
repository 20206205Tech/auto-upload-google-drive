from loguru import logger

import env


def main():
    logger.info(len(env.DATABASE_URL))
    logger.info(len(env.GOOGLE_CREDENTIALS))


if __name__ == "__main__":
    main()
