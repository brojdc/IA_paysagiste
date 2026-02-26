from datetime import datetime
from .solar import sun_series


def classify_exposure(hours: float) -> str:
    if hours < 2:
        return "ombre dense"
    if hours < 4:
        return "mi-ombre"
    if hours < 6:
        return "soleil modéré"
    return "plein soleil"


def compute_exposition_v2(
    lat: float,
    lon: float,
    date: datetime,
    tz: str,
    north_offset: float,
    step_minutes: int = 30,
):
    series = sun_series(lat, lon, date, tz, step_minutes)

    total_minutes_sun = 0
    morning = 0
    midday = 0
    evening = 0

    for entry in series:
        altitude = entry["altitude"]

        if altitude > 0:
            total_minutes_sun += step_minutes

            hour = entry["time"].hour
            if hour < 11:
                morning += step_minutes
            elif hour < 15:
                midday += step_minutes
            else:
                evening += step_minutes

    total_hours = total_minutes_sun / 60.0

    return {
        "total_hours": total_hours,
        "morning_hours": morning / 60.0,
        "midday_hours": midday / 60.0,
        "evening_hours": evening / 60.0,
        "classification": classify_exposure(total_hours),
    }