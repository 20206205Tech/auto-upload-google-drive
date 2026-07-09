from datetime import datetime
from zoneinfo import ZoneInfo


def get_hanoi_time(format_str: str = "%d-%m-%Y %H-%M-%S") -> str:
    now_hanoi = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return now_hanoi.strftime(format_str)
