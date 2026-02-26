from datetime import datetime, timedelta
from astral import LocationInfo
from astral.sun import azimuth, elevation


def sun_series(
    lat: float,
    lon: float,
    date: datetime,
    tz: str,
    step_minutes: int = 30,
):
    loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz)

    current = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = current + timedelta(days=1)

    series = []
    while current < end:
        # Astral calcule azimuth/altitude comme ça :
        azi = azimuth(loc.observer, current)
        alt = elevation(loc.observer, current)

        series.append(
            {
                "time": current,
                "azimuth": float(azi),
                "altitude": float(alt),
            }
        )
        current += timedelta(minutes=step_minutes)

    return series