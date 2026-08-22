# utils/grading_engine.py
"""Grading Engine

Provides a reusable function to calculate percentage, grade, grade point, and result label
based on obtained marks and maximum marks. Supports various max‑mark scales.
"""

from typing import List, Tuple

# Primary grade mapping (grade -> grade point)
GRADE_POINT_MAP = {
    "A+": 5,
    "A": 4,
    "B+": 3,
    "B": 2,
    "C": 1,
}

# Grade ranges for 100‑mark scale (percentage based)
GRADE_RANGES_100: List[Tuple[float, float, str]] = [
    (90.0, 100.0, "A+"),
    (70.0, 89.9, "A"),
    (50.0, 69.9, "B+"),
    (30.0, 49.9, "B"),
    (0.0, 29.9, "C"),
]

# Grade ranges for 600‑mark scale (absolute marks)
GRADE_RANGES_600: List[Tuple[int, int, str]] = [
    (540, 600, "A+"),
    (420, 539, "A"),
    (300, 419, "B+"),
    (180, 299, "B"),
    (0, 179, "C"),
]

def _select_ranges(max_marks: int):
    """Select the appropriate grade range list based on the max marks.
    For 100‑mark scales we use percentage ranges, otherwise we fall back to the
    600‑mark absolute ranges and scale them proportionally.
    """
    if max_marks == 100:
        return GRADE_RANGES_100, True  # use percentage
    if max_marks == 600:
        return GRADE_RANGES_600, False  # use absolute marks
    # For any other max_marks we treat it like the 100‑scale by converting
    # the obtained marks to a percentage and then applying the 100‑scale.
    return GRADE_RANGES_100, True

def calculate_grade(max_marks: int, obtained: float):
    """Calculate overall grading details.

    Args:
        max_marks: The total maximum marks for the exam (e.g., 5, 10, 100, 600).
        obtained: The total marks obtained by the student.

    Returns:
        dict with percentage, grade, grade_point, and result_label.
    """
    if max_marks <= 0:
        raise ValueError("max_marks must be positive")

    pct = (obtained / max_marks) * 100 if max_marks else 0.0
    pct = round(pct, 2)

    # Determine grade using the selected range list
    grade_ranges, use_percentage = _select_ranges(max_marks)
    grade = "C"  # fallback default
    if use_percentage:
        for low, high, g in grade_ranges:
            if low <= pct <= high:
                grade = g
                break
    else:
        for low, high, g in grade_ranges:
            if low <= obtained <= high:
                grade = g
                break

    grade_point = GRADE_POINT_MAP.get(grade, 1)

    # Result label based on percentage (common across scales)
    if pct >= 75:
        result_label = "Distinction"
    elif pct >= 60:
        result_label = "First Class"
    elif pct >= 35:
        result_label = "Pass"
    else:
        result_label = "Fail"

    return {
        "percentage": pct,
        "grade": grade,
        "grade_point": grade_point,
        "result_label": result_label,
    }
