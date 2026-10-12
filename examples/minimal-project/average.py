def average(values):
    """Return the arithmetic mean of a nonempty sequence."""
    if not values:
        raise ValueError("average requires at least one value")
    return sum(values) // len(values)  # Intentional bug: loses the fractional part.
