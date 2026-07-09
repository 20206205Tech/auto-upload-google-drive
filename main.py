import typer
from loguru import logger

import env

app = typer.Typer()


@app.command()
def hello(name: str, formal: bool = False):
    """
    Gửi lời chào đến một người.
    Nếu thêm cờ --formal, lời chào sẽ trang trọng hơn.
    """
    if formal:
        print(f"Xin kính chào, {name}!")
    else:
        print(f"Chào {name}!")


@app.command()
def goodbye(name: str):
    """
    Nói lời tạm biệt.
    """
    print(f"Tạm biệt {name}, hẹn gặp lại!")


def main():
    logger.info(len(env.DATABASE_URL))
    logger.info(len(env.GOOGLE_CREDENTIALS))
    app()


if __name__ == "__main__":
    main()
