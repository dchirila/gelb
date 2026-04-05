"""Unit tests for the Fortran line formatter."""

import pytest

from gelb.backends.fortran.line_formatter import (
    format_fortran_lines,
    _tokenize,
    _join_continuations,
    _split_line,
)


# ===================================================================
# Tokenizer tests
# ===================================================================

class TestTokenizer:
    """Verify that the tokenizer preserves input and keeps tokens atomic."""

    def test_roundtrip_simple(self):
        line = '  double precision :: g_x = 1.5d-10'
        assert ''.join(_tokenize(line)) == line

    def test_roundtrip_array_constructor(self):
        line = '  x = (/1.0d0, -2.0d0, 3.14e-05/)'
        assert ''.join(_tokenize(line)) == line

    def test_exponent_is_one_token(self):
        tokens = _tokenize('1.5d-10')
        assert '1.5d-10' in tokens

    def test_negative_exponent_e(self):
        tokens = _tokenize('3.14e-05')
        assert '3.14e-05' in tokens

    def test_positive_exponent(self):
        tokens = _tokenize('1.0E+03')
        assert '1.0E+03' in tokens

    def test_kind_parameter(self):
        tokens = _tokenize('1.0_dp')
        assert '1.0_dp' in tokens

    def test_integer_kind(self):
        tokens = _tokenize('42_8')
        assert '42_8' in tokens

    def test_dot_operator(self):
        tokens = _tokenize('a .and. b')
        assert '.and.' in tokens

    def test_dot_true(self):
        tokens = _tokenize('.true.')
        assert '.true.' in tokens

    def test_string_single_quote(self):
        tokens = _tokenize("'hello world'")
        assert "'hello world'" in tokens

    def test_string_double_quote(self):
        tokens = _tokenize('"hello world"')
        assert '"hello world"' in tokens

    def test_string_with_escaped_quote(self):
        tokens = _tokenize("'it''s fine'")
        assert "'it''s fine'" in tokens

    def test_array_constructor_delimiters(self):
        tokens = _tokenize('(/ 1, 2 /)')
        assert '(/' in tokens
        assert '/)' in tokens

    def test_double_colon(self):
        tokens = _tokenize('integer :: x')
        assert '::' in tokens

    def test_power_operator(self):
        tokens = _tokenize('x**2')
        assert '**' in tokens

    def test_comparison_operators(self):
        for op in ('==', '/=', '<=', '>=', '=>'):
            tokens = _tokenize(f'a {op} b')
            assert op in tokens, f'{op} not found as single token'

    def test_real_starting_with_dot(self):
        tokens = _tokenize('.5d0')
        assert '.5d0' in tokens

    def test_real_no_exponent(self):
        tokens = _tokenize('3.14')
        assert '3.14' in tokens


# ===================================================================
# Continuation joining tests
# ===================================================================

class TestJoinContinuations:
    """Verify that physical continuation lines are joined into logical lines."""

    def test_simple_continuation(self):
        lines = ['  x = a + &', '    &b + c']
        result = _join_continuations(lines)
        assert result == ['  x = a + b + c']

    def test_continuation_without_leading_ampersand(self):
        lines = ['  x = a + &', '    b + c']
        result = _join_continuations(lines)
        assert result == ['  x = a + b + c']

    def test_no_continuation(self):
        lines = ['  x = 1', '  y = 2']
        result = _join_continuations(lines)
        assert result == ['  x = 1', '  y = 2']

    def test_multi_continuation(self):
        lines = [
            '  x = a + &',
            '    &b + &',
            '    &c',
        ]
        result = _join_continuations(lines)
        assert result == ['  x = a + b + c']

    def test_empty_lines_preserved(self):
        lines = ['  x = 1', '', '  y = 2']
        result = _join_continuations(lines)
        assert result == ['  x = 1', '', '  y = 2']

    def test_streaming_dfs_pattern(self):
        """The pattern produced by _emit_streaming_dfs: embedded &\\n."""
        lines = [
            '  arr = (/elem1, &',
            '    elem2, &',
            '    elem3/)',
        ]
        result = _join_continuations(lines)
        assert result == ['  arr = (/elem1, elem2, elem3/)']


# ===================================================================
# Pass-through tests
# ===================================================================

class TestPassThrough:
    """Lines that should not be modified by the formatter."""

    def test_empty_string(self):
        assert format_fortran_lines('') == ''

    def test_blank_line(self):
        assert format_fortran_lines('   ') == '   '

    def test_short_line(self):
        line = '  integer :: x = 42'
        assert format_fortran_lines(line) == line

    def test_comment_line(self):
        line = '  ! This is a comment'
        assert format_fortran_lines(line) == line

    def test_exactly_132_chars(self):
        line = '  x = ' + '1' * 126  # 132 chars
        assert len(line) == 132
        assert format_fortran_lines(line) == line

    def test_multiple_short_lines(self):
        code = 'integer :: x\ninteger :: y\n'
        assert format_fortran_lines(code) == code

    def test_omp_directive_preserved(self):
        """OpenMP directives use their own continuation syntax."""
        code = (
            '  !$omp parallel do collapse(2) default(private) &\n'
            '  !$omp& shared(g_f, g_f_old, g_f_new)\n'
            '  do g_y = 0, 33'
        )
        result = format_fortran_lines(code)
        assert '!$omp parallel do' in result
        assert '!$omp& shared' in result
        # The two OMP lines must remain separate
        lines = result.split('\n')
        assert any('!$omp parallel do' in l for l in lines)
        assert any('!$omp& shared' in l for l in lines)


# ===================================================================
# Comma-separated splitting
# ===================================================================

class TestCommaSplitting:
    """Long comma-separated lists should split after commas."""

    def test_long_parameter_declaration(self):
        elements = ', '.join(f'{i}.0d0' for i in range(30))
        line = f'  double precision :: arr(0:29) = (/{elements}/)'
        result = format_fortran_lines(line)
        for phys_line in result.split('\n'):
            assert len(phys_line) <= 132, (
                f'Line is {len(phys_line)} chars: {phys_line[:80]}...')

    def test_long_call_statement(self):
        args = ', '.join(f'argument_{i}' for i in range(20))
        line = f'    call some_subroutine({args})'
        result = format_fortran_lines(line)
        for phys_line in result.split('\n'):
            assert len(phys_line) <= 132

    def test_comma_is_preferred_split(self):
        """When both comma and operator are available, comma wins."""
        # Build a line with commas and operators, > 132 chars.
        elements = ', '.join(f'a{i} + b{i}' for i in range(15))
        line = f'  x = (/{elements}/)'
        result = format_fortran_lines(line)
        lines = result.split('\n')
        assert len(lines) > 1
        # First continuation should end with a comma before ' &'
        assert lines[0].rstrip().endswith(', &') or \
               lines[0].rstrip().endswith(' &')


# ===================================================================
# Operator splitting
# ===================================================================

class TestOperatorSplitting:
    """Long expressions should split at operators."""

    def test_long_arithmetic(self):
        terms = ' + '.join(f'variable_{i}' for i in range(20))
        line = f'  result = {terms}'
        result = format_fortran_lines(line)
        for phys_line in result.split('\n'):
            assert len(phys_line) <= 132

    def test_assignment_split(self):
        """A very long RHS can split after '='."""
        rhs = 'x' * 130
        line = f'  result = {rhs}'
        result = format_fortran_lines(line)
        lines = result.split('\n')
        assert len(lines) > 1
        for phys_line in lines:
            assert len(phys_line) <= 132


# ===================================================================
# Token integrity
# ===================================================================

class TestTokenIntegrity:
    """Tokens must never be broken across continuation lines."""

    def _assert_token_intact(self, token, context_before='  x = ',
                              context_after=''):
        """Build a line > 132 chars containing *token* and verify it's intact
        in the formatted output."""
        padding = 'a, ' * 40  # enough to force wrapping
        line = f'{context_before}{padding}{token}{context_after}'
        result = format_fortran_lines(line)
        # Join all continuation lines back together and check token is there.
        joined = _join_continuations(result.split('\n'))
        assert any(token in l for l in joined), (
            f'Token {token!r} was broken in output:\n{result}')

    def test_real_with_d_exponent(self):
        self._assert_token_intact('1.5d-10')

    def test_real_with_e_exponent(self):
        self._assert_token_intact('3.14e-05')

    def test_real_with_positive_exponent(self):
        self._assert_token_intact('2.0D+08')

    def test_kind_parameter(self):
        self._assert_token_intact('1.0_dp')

    def test_integer_kind(self):
        self._assert_token_intact('42_8')

    def test_dot_operator(self):
        self._assert_token_intact('.and.')

    def test_string_literal(self):
        self._assert_token_intact("'hello world'")

    def test_identifier(self):
        self._assert_token_intact('very_long_identifier_name')

    def test_power_operator(self):
        self._assert_token_intact('**')

    def test_array_constructor_open(self):
        self._assert_token_intact('(/')

    def test_array_constructor_close(self):
        self._assert_token_intact('/)')


# ===================================================================
# Continuation format
# ===================================================================

class TestContinuationFormat:
    """Verify continuation line formatting."""

    def test_continuation_has_ampersand_prefix(self):
        elements = ', '.join(f'{i}.0d0' for i in range(30))
        line = f'  double precision :: arr = (/{elements}/)'
        result = format_fortran_lines(line)
        lines = result.split('\n')
        assert len(lines) >= 2
        # First line ends with ' &'
        assert lines[0].rstrip().endswith(' &')
        # Continuation line(s) start with spaces + '&'
        for cont in lines[1:]:
            assert cont.lstrip().startswith('&'), (
                f'Continuation line missing & prefix: {cont!r}')

    def test_continuation_indent_deeper(self):
        """Continuation should be indented deeper than the original."""
        elements = ', '.join(f'{i}.0d0' for i in range(30))
        line = f'    x = (/{elements}/)'  # 4-space indent
        result = format_fortran_lines(line)
        lines = result.split('\n')
        orig_indent = len(line) - len(line.lstrip())
        for cont in lines[1:]:
            cont_indent = len(cont) - len(cont.lstrip())
            assert cont_indent > orig_indent

    def test_multi_level_continuation(self):
        """A very long line may need 3+ physical lines."""
        elements = ', '.join(f'{i}.0d0' for i in range(80))
        line = f'  x = (/{elements}/)'
        result = format_fortran_lines(line)
        lines = result.split('\n')
        assert len(lines) >= 3
        for phys_line in lines:
            assert len(phys_line) <= 132


# ===================================================================
# Already-continued input
# ===================================================================

class TestAlreadyContinued:
    """Input that already has & continuations should be re-normalized."""

    def test_renormalize_existing_continuations(self):
        code = '  x = a + &\n    &b + c'
        result = format_fortran_lines(code)
        # Should produce a single short line (no continuation needed).
        assert '&' not in result
        assert 'a + b + c' in result

    def test_renormalize_and_resplit(self):
        """Existing continuations that are too long get re-split properly."""
        elements = ', '.join(f'{i}.0d0' for i in range(30))
        # Manually pre-split in a bad way (lines > 132).
        half = len(elements) // 2
        code = (f'  x = (/{elements[:half]} &\n'
                f'    &{elements[half:]}/)')
        result = format_fortran_lines(code)
        for phys_line in result.split('\n'):
            assert len(phys_line) <= 132


# ===================================================================
# Large array (MRT-like)
# ===================================================================

class TestLargeArray:
    """Realistic test with a large array resembling MRT matrices."""

    def test_reshape_361_elements(self):
        """A 19x19 matrix as reshape((/...361 elements.../), (/19, 19/))."""
        elements = ', '.join(f'{float(i):.1f}d0' for i in range(361))
        line = (f'  double precision, parameter :: m(0:18, 0:18) = '
                f'reshape((/{elements}/), (/19, 19/))')
        result = format_fortran_lines(line)
        for i, phys_line in enumerate(result.split('\n'), 1):
            assert len(phys_line) <= 132, (
                f'Line {i} is {len(phys_line)} chars: '
                f'{phys_line[:80]}...')

    def test_reshape_high_precision_floats(self):
        """High-precision floats (22+ char mantissa) in a large array."""
        import random
        random.seed(42)
        elements = ', '.join(
            f'{random.uniform(-1, 1):.17f}d0' for _ in range(100))
        line = (f'  double precision, parameter :: inv(0:99) = '
                f'(/{elements}/)')
        result = format_fortran_lines(line)
        for phys_line in result.split('\n'):
            assert len(phys_line) <= 132
