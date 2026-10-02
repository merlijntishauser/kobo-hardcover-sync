"""Reading stats for one reader, as JSON for Home Assistant REST sensors.

Minutes come from reading_day: growth of TimeSpentReading between uploads,
counted only for books opened on the reader's own device, attributed to the
day of the upload (the Kobo keeps no per-session log).
"""

from __future__ import annotations

from datetime import date, timedelta

from ..engine import state
from ..engine.plan import desired


def stats(con, reader: str, today: str | None = None) -> dict:
    today = today or state.local_day()
    d = date.fromisoformat(today)

    def minutes(since):
        return (
            (
                con.execute(
                    "select coalesce(sum(seconds),0) from reading_day where reader=? and day>=? and day<=?", (reader, since, today)
                ).fetchone()[0]
            )
            // 60
        )

    week_start = (d - timedelta(days=d.weekday())).isoformat()
    cur = con.execute(
        """select title, author, percent, last_read from book
           where reader=? and first_event!='' and status=1 and coalesce(finished_at,'')=''
           order by last_read desc limit 1""",
        (reader,),
    ).fetchone()
    finished_year = 0
    for r in con.execute("select * from book where reader=? and (mode='on' or (mode='auto' and history=0))", (reader,)):
        w = desired(r)
        if w and w["status"] == "read" and w.get("finished", "").startswith(today[:4]):
            finished_year += 1
    last = con.execute("select max(last_import) from device where reader=?", (reader,)).fetchone()[0]
    return {
        "reader": reader,
        "minutes_today": minutes(today),
        "minutes_week": minutes(week_start),
        "minutes_month": minutes(today[:8] + "01"),
        "finished_this_year": finished_year,
        "current_title": cur["title"] if cur else None,
        "current_author": cur["author"] if cur else None,
        "current_percent": cur["percent"] if cur else None,
        "last_upload": last,
    }
