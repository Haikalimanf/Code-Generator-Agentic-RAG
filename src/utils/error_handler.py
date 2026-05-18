import functools
import logging
from typing import Callable

logger = logging.getLogger("tools")


def wrap_tool_call(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Error executing tool '{func.__name__}': {e}"
            logger.error(error_msg)
            return error_msg
    return wrapper


def wrap_async_tool_call(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ConnectionRefusedError:
            return "Error: Gagal terhubung ke MCP server. Pastikan server atau aplikasi terkait aktif."
        except Exception as e:
            error_msg = f"Error executing tool '{func.__name__}': {e}"
            logger.error(error_msg)
            return error_msg
    return wrapper