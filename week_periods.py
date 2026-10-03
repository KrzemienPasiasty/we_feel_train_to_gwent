from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import time
from enum import IntEnum

from tag import Tag

SLOT_MINUTES = 15
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 96
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
    """Ciągły przedział czasu w jednym dniu (minuty od północy, koniec wyłącznie)."""
    day: int
    start: int
    end: int

    @staticmethod
    def _fmt(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def __str__(self) -> str:
        return f"{Weekday(self.day).name} {self._fmt(self.start)}-{self._fmt(self.end)}"


class WeeklySchedule:
    """
    Tygodniowa siatka 7 dni x 96 slotów (po 15 minut).
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
    def _slot_of(t: time) -> int:
        """Indeks slotu zawierającego dany czas (zaokrąglenie w dół)."""
        return (t.hour * 60 + t.minute) // SLOT_MINUTES

    @staticmethod
    def _boundary(t: time, *, is_end: bool) -> int:
        """Indeks granicy slotu; czas musi być wielokrotnością 15 min.
        time(0, 0) jako koniec oznacza 24:00."""
        minutes = t.hour * 60 + t.minute
        if t.second or t.microsecond or minutes % SLOT_MINUTES:
            raise ValueError(f"Czas {t} nie jest wielokrotnością {SLOT_MINUTES} minut")
        if is_end and minutes == 0:
            return SLOTS_PER_DAY
        return minutes // SLOT_MINUTES

    def _range(self, start: time, end: time) -> range:
        first = self._boundary(start, is_end=False)
        last = self._boundary(end, is_end=True)
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

    def get_tags(self, day: int, at: time) -> list[Tag]:
        """Tagi przypisane do slotu, w którym mieści się czas `at` (może być pusta lista)."""
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
        """Ciągłe przedziały czasu (połączone sąsiednie sloty), w których występuje tag."""
        result: list[Interval] = []
        for day, day_slots in enumerate(self._slots):
            run_start: int | None = None
            for i in range(SLOTS_PER_DAY + 1):
                present = i < SLOTS_PER_DAY and tag in day_slots[i]
                if present and run_start is None:
                    run_start = i
                elif not present and run_start is not None:
                    result.append(Interval(day, run_start * SLOT_MINUTES, i * SLOT_MINUTES))
                    run_start = None
        return result