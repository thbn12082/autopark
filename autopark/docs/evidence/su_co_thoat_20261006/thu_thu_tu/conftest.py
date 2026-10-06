"""Phản biện Việc 8 (06/10/2026): faulthandler có còn bật lúc gc.collect() trong pytest_unconfigure không?
Ghi thẳng ra fd 2 (không đệm) ở: sessionfinish, mỗi lần gc bắt đầu sau sessionfinish (kèm hàm gọi), unconfigure trylast,
atexit."""
import atexit
import faulthandler
import gc
import os
import traceback

import pytest

_armed = [False]


def _w(s):
    os.write(2, (s + "\n").encode("utf-8"))


def _cb(phase, info):
    if phase == "start" and _armed[0]:
        st = traceback.extract_stack(limit=6)[:-1]
        who = " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}" for f in reversed(st))
        _w(f"[gc start gen={info.get('generation')}] faulthandler.is_enabled={faulthandler.is_enabled()} | {who}")


def pytest_sessionfinish(session, exitstatus):
    _armed[0] = True
    gc.callbacks.append(_cb)
    _w(f"[sessionfinish] faulthandler.is_enabled={faulthandler.is_enabled()}")


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    _w(f"[unconfigure trylast] faulthandler.is_enabled={faulthandler.is_enabled()}")


atexit.register(lambda: _w(f"[atexit] faulthandler.is_enabled={faulthandler.is_enabled()}"))
