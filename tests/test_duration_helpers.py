from datetime import timedelta

from app.services.batch import _duration_to_seconds as batch_duration_to_seconds
from app.services.realtime import _duration_to_seconds as realtime_duration_to_seconds


def test_duration_helpers_support_timedelta() -> None:
    value = timedelta(seconds=1, milliseconds=250)
    assert batch_duration_to_seconds(value) == 1.25
    assert realtime_duration_to_seconds(value) == 1.25
