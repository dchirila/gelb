"""C++ real literals, including explicit IEEE special values."""

import math


def cpp_real(value, cpp_type='double'):
    number = float(value)
    if not math.isfinite(number):
        limits = f'std::numeric_limits<{cpp_type}>'
        if math.isnan(number):
            return f'{limits}::quiet_NaN()'
        return f'{limits}::infinity()' if number > 0 else f'(-{limits}::infinity())'
    text = value if isinstance(value, str) else repr(value)
    return text + 'f' if cpp_type == 'float' and not isinstance(value, str) else text
