"""ScalarBlockCSEVisitor: identical ordered subtrees of a run of scalar
assignments are shared only while every name they read has one value
(user manual, Numerical semantics: What the optimizer promises)."""

from gelb.gelb_ast.ASTNodes import (
    ArrayDataType_N,
    DynamicBlock_N,
    Identifier_N,
    IntLiteral_N,
    IntrinsicFunctionCall_N,
    LatticeOutSelectionAssignmentStmt_N,
    List_N,
    Mul_N,
    RealLiteral_N,
    VariableAssignmentStmt_N,
    VariableDeclarationStmt_N,
)
from gelb.midware.ScalarBlockCSEVisitor import ScalarBlockCSEVisitor
from gelb.utils.CodeRange import CodeRange

_CR = CodeRange(1, 1, 1, 1)


def _scalar():
    return ArrayDataType_N(_CR, 'real64', List_N(_CR))


def _var(name):
    node = Identifier_N(_CR, name)
    node.inferred_type = _scalar()
    return node


def _square(name):
    node = Mul_N(_CR, _var(name), _var(name))
    node.inferred_type = _scalar()
    return node


def _decl(name, value):
    return VariableDeclarationStmt_N(_CR, _scalar(), _var(name), initial_value=value)


def _assign(name, value):
    return VariableAssignmentStmt_N(_CR, _var(name), value)


def _two():
    literal = RealLiteral_N(_CR, 2.0)
    literal.inferred_type = _scalar()
    return literal


def _run(stmts):
    block = DynamicBlock_N(_CR, _var('D'), List_N(_CR))
    for stmt in stmts:
        block.stmts.append(stmt)
    ScalarBlockCSEVisitor()._process_block(block)
    return block.stmts.elements


def _temps(stmts):
    return [s for s in stmts if isinstance(s, VariableDeclarationStmt_N)
            and s.name.name.startswith('_gelb_pre_cse_')]


def test_identical_subtrees_of_one_value_are_shared():
    out = _run([_decl('a', _square('v')), _decl('b', _square('v'))])
    assert len(_temps(out)) == 1
    assert [s.initial_value.name for s in out[1:]] == ['_gelb_pre_cse_0'] * 2


def test_a_write_to_a_name_the_run_read_ends_the_run():
    # `a = v*v; v = 2.0; b = v*v` reads two values of v; sharing the
    # product once gave b = a (0 instead of 3 for b - a with v = 1).
    out = _run([_decl('a', _square('v')), _assign('v', _two()), _decl('b', _square('v'))])
    assert _temps(out) == []
    assert isinstance(out[2].initial_value, Mul_N)


def test_after_the_write_the_new_value_is_shared_again():
    out = _run([_decl('a', _square('v')), _assign('v', _two()),
                _decl('b', _square('v')), _decl('c', _square('v'))])
    temps = _temps(out)
    assert len(temps) == 1
    # Declared after v's new value, before its first use.
    assert [type(s).__name__ for s in out] == [
        'VariableDeclarationStmt_N', 'VariableAssignmentStmt_N',
        'VariableDeclarationStmt_N', 'VariableDeclarationStmt_N', 'VariableDeclarationStmt_N']
    assert out[1].lhs.name == 'v' and out[2] is temps[0]
    assert isinstance(out[0].initial_value, Mul_N)


def test_a_statement_reading_its_own_target_ends_the_run():
    # `v = v*v` reads the old v; the next v*v reads the new one.
    out = _run([_assign('v', _square('v')), _decl('w', _square('v'))])
    assert _temps(out) == []


def test_a_redefinition_still_ends_the_run():
    out = _run([_decl('a', _square('v')), _assign('a', _square('v'))])
    assert _temps(out) == []


def test_a_lattice_write_ends_the_run():
    write = LatticeOutSelectionAssignmentStmt_N(_CR, _var('f'), _two())
    out = _run([_decl('a', _square('v')), write, _decl('b', _square('v'))])
    assert _temps(out) == []


def _array(q=9):
    return ArrayDataType_N(_CR, 'real64', IntLiteral_N(_CR, q))


def test_a_whole_array_assignment_is_left_to_the_slice_path():
    # `a = w * w; b = w * w` with 9-element arrays once shared the
    # array-valued product in a scalar temporary; Fortran rejected it
    # ("Incompatible ranks 0 and 1") and Highway failed to generate.
    def whole(name):
        lhs = Identifier_N(_CR, name)
        lhs.inferred_type = _array()
        rhs = Mul_N(_CR, _var('w'), _var('w'))
        rhs.inferred_type = _array()
        return VariableAssignmentStmt_N(_CR, lhs, rhs)
    out = _run([whole('a'), whole('b')])
    assert _temps(out) == []
    assert all(isinstance(s.rhs, Mul_N) for s in out)


def test_an_assignment_of_unknown_shape_is_left_alone():
    lhs, rhs = Identifier_N(_CR, 'a'), Mul_N(_CR, Identifier_N(_CR, 'w'), Identifier_N(_CR, 'w'))
    lhs2, rhs2 = Identifier_N(_CR, 'b'), Mul_N(_CR, Identifier_N(_CR, 'w'), Identifier_N(_CR, 'w'))
    out = _run([VariableAssignmentStmt_N(_CR, lhs, rhs), VariableAssignmentStmt_N(_CR, lhs2, rhs2)])
    assert _temps(out) == []


def _draw_times_two():
    call = IntrinsicFunctionCall_N(_CR, 'random', List_N(_CR))
    call.inferred_type = _scalar()
    node = Mul_N(_CR, _two(), call)
    node.inferred_type = _scalar()
    return node


def test_random_draws_are_never_shared():
    # `a = 2.0 * random(); b = 2.0 * random()` are two draws; sharing the
    # subtree once made them one.
    out = _run([_decl('a', _draw_times_two()), _decl('b', _draw_times_two())])
    assert _temps(out) == []
    # A pure subtree beside a draw is still shared.
    def mixed():
        node = Mul_N(_CR, _square('v'), _draw_times_two())
        node.inferred_type = _scalar()
        return node
    out = _run([_decl('a', mixed()), _decl('b', mixed())])
    temps = _temps(out)
    assert len(temps) == 1 and isinstance(temps[0].initial_value, Mul_N)
    assert temps[0].initial_value.left.name == 'v'
