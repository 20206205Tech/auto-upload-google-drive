from loguru import logger

import env


def main():
    logger.info(env.DATABASE_URL[:3])


if __name__ == "__main__":
    main()
