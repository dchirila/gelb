"""A slice of a lattice's DFs is an array of its length.

``f.in[x, y | lo:hi]`` with literal bounds is ``array[T, hi-lo+1]``, and
so is ``f.out[x, y | lo:hi]`` on the left of an assignment; element ``i``
of the slice is DF ``lo+i``. An open end means the first or the last DF.
A single DF (``| i``) is a scalar and ``| :`` the whole set (user manual,
chapter 3, the ``|`` notation). Before, a partial slice was typed as a
scalar, and an open end with a lower bound (``| 2:``) as the full set.
"""
import pytest

from gelb.tests.test_utils import get_typed_ast, get_fully_validated_ast, minimal_gelb_program_2d
from gelb.utils.exceptions import GeLBExTypeError

# The minimal 2-D program's lattice has q = 9.


@pytest.mark.parametrize(('df_range', 'length'), [
    ('2:5', 4), ('2:', 7), (':5', 6), ('0:7', 8), ('1:8', 8), ('0:', 9), (':', 9), ('0:8', 9),
    ('LO:HI', 4), ('1+1:HI', 4), ('LO:', 7)])
def test_a_df_slice_is_an_array_of_its_length(df_range, length):
    source = minimal_gelb_program_2d(
        global_constants_content='const int N = 8; const int LO = 2; const int HI = 5;',
        gauge_content=f'array[int, {length}] v = f.in[x, y | {df_range}]; val = v[0];')
    get_fully_validated_ast(source)   # the declared length matches; a wrong one is rejected below


@pytest.mark.parametrize('df_range', ['2:5', '2:', ':5'])
def test_a_slice_of_the_wrong_length_is_rejected(df_range):
    source = minimal_gelb_program_2d(
        gauge_content=f'array[int, 3] v = f.in[x, y | {df_range}]; val = v[0];')
    with pytest.raises(GeLBExTypeError, match=r'declared with shape \[3\] but initialized with shape \[\d\]'):
        get_fully_validated_ast(source)


def test_a_single_df_read_is_a_scalar():
    get_typed_ast(minimal_gelb_program_2d(gauge_content='val = f.in[x, y | 2];'))


def test_a_slice_in_arithmetic_and_sum():
    get_typed_ast(minimal_gelb_program_2d(
        gauge_content='array[int, 4] v = f.in[x, y | 2:5] * 2; val = sum(f.in[x, y | 2:5]) + v[1];'))


def test_a_slice_write_takes_an_array_of_its_length():
    get_typed_ast(minimal_gelb_program_2d(
        dynamic_content='array[int, 4] a = {1, 2, 3, 4};'
                        ' f.out[x, y | 0:4] = f.in[x, y | 0:4]; f.out[x, y | 5:8] = a + f.in[x, y | 1:4];'))
    with pytest.raises(GeLBExTypeError):
        get_fully_validated_ast(minimal_gelb_program_2d(
            dynamic_content='f.out[x, y | 0:4] = f.in[x, y | 0:3]; f.out[x, y | 5:8] = f.in[x, y | 5:8];'))


@pytest.mark.parametrize(('df_range', 'message'), [
    ('5:3', 'DF range 5:3 is reversed'), ('3:12', 'DF index 3:12 is outside'),
    ('12', 'DF index 12 is outside'), ('0:9', 'DF index 0:9 is outside')])
@pytest.mark.parametrize('side', ['in', 'out'])
def test_a_df_index_outside_the_lattice_is_rejected(df_range, message, side):
    if side == 'in':
        content = dict(gauge_content=f'val = sum(f.in[x, y | {df_range}]);'
                       if ':' in df_range else f'val = f.in[x, y | {df_range}];')
    else:
        content = dict(dynamic_content=f'f.out[x, y | {df_range}] = f.in[x, y | 0];')
    with pytest.raises(GeLBExTypeError, match=message):
        get_typed_ast(minimal_gelb_program_2d(**content))


def test_dot_prod_takes_a_slice_directly():
    get_fully_validated_ast(minimal_gelb_program_2d(
        gauge_content='array[int, 4] c = {1, 2, 3, 4}; val = dot_prod(c, f.in[x, y | 2:5]);'))


def test_a_single_run_time_df_index_is_a_scalar_read():
    get_fully_validated_ast(minimal_gelb_program_2d(gauge_content='val = f.in[x, y | mod(x, 9)];'))


@pytest.mark.parametrize('df_range', ['x:x+1', 'mod(x, 3):5', '2:mod(x, 3)+4'])
def test_a_range_with_run_time_bounds_is_rejected(df_range):
    with pytest.raises(GeLBExTypeError, match='bounds of a DF range must be compile-time constants'):
        get_typed_ast(minimal_gelb_program_2d(
            gauge_content=f'array[int, 4] v = f.in[x, y | {df_range}]; val = v[0];'))
