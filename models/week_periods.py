from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import IntEnum

from .tag import Tag

SLOT_MINUTES = 15
SLOT = timedelta(minutes=SLOT_MINUTES)
SLOTS_PER_DAY = timedelta(days=1) // SLOT  # 96
DAYS_IN_WEEK = 7


class Weekday(IntEnum):
    """Numeracja zgodna z datetime.weekday()."""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


@dataclass(frozen=True)
class Interval:
    """Ciągły przedział w jednym dniu tygodnia.
    `start` i `end` to przesunięcia od północy (end wyłącznie, maks. 24 h)."""
    day: int
    start: timedelta
    end: timedelta

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def start_time(self) -> time:
        return (datetime.min + self.start).time()

    def to_datetimes(self, week_of: date | datetime) -> tuple[datetime, datetime]:
        """Przenosi przedział na konkretny tydzień kalendarzowy (ten, w którym
        leży `week_of`) i zwraca (początek, koniec) jako datetime."""
        d = week_of.date() if isinstance(week_of, datetime) else week_of
        monday = d - timedelta(days=d.weekday())
        midnight = datetime.combine(monday + timedelta(days=self.day), time.min)
        return midnight + self.start, midnight + self.end

    @staticmethod
    def _fmt(delta: timedelta) -> str:
        minutes = delta // timedelta(minutes=1)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def __str__(self) -> str:
        return f"{Weekday(self.day).name} {self._fmt(self.start)}-{self._fmt(self.end)}"


class WeekTime:
    """
    Tygodniowa siatka 7 dni x 288 slotów (po 5 minut).
    Każdy slot przechowuje listę tagów, więc tagi mogą się nakładać.

    Struktura nic nie wie o zadaniach ani o Tag.is_interactive –
    przechowuje wyłącznie relację "slot czasowy -> tagi".
    """

    def __init__(self) -> None:
        self._slots: list[list[list[Tag]]] = [
            [[] for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_IN_WEEK)
        ]

    # ---------- pomocnicze ----------

    @staticmethod
    def _check_day(day: int) -> int:
        if not 0 <= int(day) < DAYS_IN_WEEK:
            raise ValueError(f"Dzień musi być w zakresie 0-6, otrzymano: {day}")
        return int(day)

    @staticmethod
    def _offset(t: time) -> timedelta:
        """Czas dnia jako przesunięcie od północy."""
        return timedelta(hours=t.hour, minutes=t.minute,
                         seconds=t.second, microseconds=t.microsecond)

    @classmethod
    def _slot_of(cls, t: time) -> int:
        """Indeks slotu zawierającego dany czas (zaokrąglenie w dół)."""
        return cls._offset(t) // SLOT

    @classmethod
    def _boundary(cls, t: time, *, is_end: bool) -> int:
        """Indeks granicy slotu; czas musi być wielokrotnością 5 min.
        time(0, 0) jako koniec oznacza 24:00."""
        offset = cls._offset(t)
        if offset % SLOT:
            raise ValueError(f"Czas {t} nie jest wielokrotnością {SLOT_MINUTES} minut")
        if is_end and offset == timedelta(0):
            return SLOTS_PER_DAY
        return offset // SLOT

    @classmethod
    def _range(cls, start: time, end: time) -> range:
        first = cls._boundary(start, is_end=False)
        last = cls._boundary(end, is_end=True)
        if first >= last:
            raise ValueError("Początek musi być wcześniejszy niż koniec")
        return range(first, last)

    # ---------- modyfikacja ----------

    def assign(self, days: int | Iterable[int], start: time, end: time, tag: Tag) -> None:
        """Przypisuje tag do przedziału [start, end) w podanym dniu lub dniach."""
        slots = self._range(start, end)
        for day in ([days] if isinstance(days, int) else days):
            day_slots = self._slots[self._check_day(day)]
            for i in slots:
                if tag not in day_slots[i]:
                    day_slots[i].append(tag)

    def unassign(self, days: int | Iterable[int], start: time, end: time, tag: Tag) -> None:
        """Usuwa tag z przedziału [start, end) w podanym dniu lub dniach."""
        slots = self._range(start, end)
        for day in ([days] if isinstance(days, int) else days):
            day_slots = self._slots[self._check_day(day)]
            for i in slots:
                if tag in day_slots[i]:
                    day_slots[i].remove(tag)

    # ---------- zapytania ----------

    def get_tags(self, when: datetime) -> list[Tag]:
        """Tagi dla slotu, w którym leży `when` (dzień tygodnia i godzina brane z datetime)."""
        return self.get_tags_on(when.weekday(), when.time())

    def get_tags_on(self, day: int, at: time) -> list[Tag]:
        """To samo co get_tags, ale dla dnia tygodnia (0-6) i czasu dnia."""
        return list(self._slots[self._check_day(day)][self._slot_of(at)])

    def tags(self) -> list[Tag]:
        """Wszystkie tagi użyte gdziekolwiek w tygodniu."""
        found: list[Tag] = []
        for day_slots in self._slots:
            for slot in day_slots:
                for tag in slot:
                    if tag not in found:
                        found.append(tag)
        return found

    def intervals_for(self, tag: Tag) -> list[Interval]:
        """Ciągłe przedziały (połączone sąsiednie sloty), w których występuje tag."""
        result: list[Interval] = []
        for day, day_slots in enumerate(self._slots):
            run_start: int | None = None
            for i in range(SLOTS_PER_DAY + 1):
                present = i < SLOTS_PER_DAY and tag in day_slots[i]
                if present and run_start is None:
                    run_start = i
                elif not present and run_start is not None:
                    result.append(Interval(day, run_start * SLOT, i * SLOT))
                    run_start = None
        return result

# Backward compatibility alias
WeeklySchedule = WeekTime
