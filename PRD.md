# PRD — Time-Slot Enforced Attendance Marking

**Feature:** Restrict timetable "Mark Attendance" to the valid time window of each slot.
**Status:** In Progress
**Grace Window:** ±10 minutes around each slot

---

## Tasks

- [x] T1: Server-side time-window check in timetable_mark_attendance() — routes/campus.py
- [x] T2: Pass now_time from timetable route to template — routes/campus.py
- [x] T3: Conditional button state (active/disabled) in today's schedule — templates/campus/timetable.html
- [x] T4: Hide Mark Attendance button for non-today weekly grid slots — templates/campus/timetable.html
- [x] T5: Add live clock display to Today's Schedule header — templates/campus/timetable.html

---

## Future Tasks (v2)

- [ ] F1: Make grace window configurable per-organization in settings
- [ ] F2: Add audit log entry when attendance is blocked by time window
- [ ] F3: Show countdown timer on future slots in today's schedule
- [ ] F4: Email/notification alert when a slot's attendance window opens

---

## Acceptance Criteria

- [x] Clicking "Mark Attendance" 30 min before slot → blocked with flash warning
- [x] Clicking during slot (or within 10 min grace) → allowed
- [x] Clicking 30 min after slot ends → blocked
- [x] Button visually disabled for future/past slots
- [x] Weekly grid does NOT show Mark Attendance for non-today days
- [x] Live clock visible on timetable page
