#!/usr/bin/env python3
"""
Integration tests for the midware stage.

Tests the midware stage in the context of the full compilation pipeline,
ensuring it integrates correctly with frontend and prepares for backend.
"""

import pytest
from gelb.frontend.stage1_frontend import (
    get_ast,
    validate_ast_root_is_program,
    build_symbols_tables,
    add_implicit_symbols,
    resolve_all_constants,
    resolve_ranges,
    infer_types,
    promote_types,
    validate_types,
    validate_constant_assignments
)
from gelb.midware.stage2_midware import validate_midware_input, fold_constants, validate_division_by_zero
from gelb.gelb_ast.ASTNodes import Program_N
from gelb.tests.test_utils import minimal_gelb_program_1d, get_fully_validated_ast
from gelb.utils.exceptions import GeLBExTypeError


class TestMidwareIntegration:
    """Integration tests for midware in the compilation pipeline."""
    
    def test_frontend_to_midware_pipeline(self):
        """Test that midware integrates correctly with frontend output."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int N = 32;",
            initializer_content='f.out[x | 0] = 0;',
            dynamic_content='f.out[x | 0] = 1;',
            gauge_content='val = f.in[x | 0];',
            geometry_content='nodes[:] = BULK;'
        )
        
        # Complete frontend pipeline
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Process through midware
        validate_midware_input(ast)
        processed_ast = fold_constants(ast)
        
        # Verify output is suitable for backend
        assert isinstance(processed_ast, Program_N)
        assert processed_ast.global_constants is not None
        assert processed_ast.lattices is not None
        assert processed_ast.node_classes is not None
        assert processed_ast.geometry is not None
    
    def test_midware_with_ex0_example_structure(self):
        """Test midware with a structure similar to ex0_int_vec_setto_one.gelb."""
        gelb_code = '''
        simulation_description("Pretty much the hello world of GeLB");

        lattices {
          lattice f(1, 1, int, 32, false);
        }

        initializer SetDFsToZero {
          f.out[x | 0] = 0;
        }

        dynamic SetDFsToOne {
          f.out[x | 0] = 1;
        }

        gauge CurrentState -> (int state) {
          state = f.in[x | 0];
        }

        node_classes {
          node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
        }

        geometry {
          nodes[:] = BULK;
        }
        '''
        
        # Complete frontend pipeline
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Process through midware
        validate_midware_input(ast)
        processed_ast = fold_constants(ast)
        
        # Verify key structures for backend
        assert isinstance(processed_ast, Program_N)
        
        # Should have lattice definition
        assert processed_ast.lattices is not None
        assert len(processed_ast.lattices.stmts) == 1
        
        # Should have one of each block type
        assert len(processed_ast.initializers) == 1
        assert len(processed_ast.dynamics) == 1
        assert len(processed_ast.gauges) == 1
        
        # Should have node class definition
        assert processed_ast.node_classes is not None
        assert len(processed_ast.node_classes.stmts) == 1
        
        # Should have geometry setup
        assert processed_ast.geometry is not None
    
    def test_midware_preserves_type_information(self):
        """Test that midware preserves type inference information."""
        gelb_code = '''
        simulation_description("Test type preservation");
        
        global_constants {
            const int N = 16;
            const real PI = 3.14;
        }
        
        lattices {
            lattice f(1, 1, real, N, true);
        }
        
        initializer Init {
            f.out[x | 0] = PI;
        }
        
        dynamic Update {
            f.out[x | 0] = f.in[x | 0] + 1.0;
        }
        
        gauge Output -> (real value) {
            value = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(Init, Update, Output);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        '''
        
        # Complete frontend pipeline with type inference
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Verify type information exists before midware
        initializer_stmt = ast.initializers[0].stmts[0]
        assert hasattr(initializer_stmt.rhs, 'inferred_type')
        
        # Process through midware
        validate_midware_input(ast)
        processed_ast = fold_constants(ast)
        
        # Verify type information is preserved
        processed_initializer_stmt = processed_ast.initializers[0].stmts[0]
        assert hasattr(processed_initializer_stmt.rhs, 'inferred_type')
        
        # For pass-through, should be the same object
        assert processed_initializer_stmt is initializer_stmt
    
    def test_midware_error_handling(self):
        """Test that midware properly handles invalid input."""
        # Test with non-Program_N input
        from gelb.gelb_ast.ASTNodes import IntLiteral_N
        invalid_ast = IntLiteral_N(code_range=None, value=42)
        
        with pytest.raises(TypeError) as excinfo:
            validate_midware_input(invalid_ast)
        
        assert "Expected Program_N, got IntLiteral_N" in str(excinfo.value)
    
    def test_division_by_zero_detection_integration(self):
        """Test that division by zero detection works in the full pipeline."""
        
        # Test case: constant that evaluates to zero through folding
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 3 - 3;",
            initializer_content="f.out[x | 0] = 1 / ZERO;"
        )
        
        # Run through frontend
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast) 
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Process through midware stages
        validate_midware_input(ast)
        folded_ast = fold_constants(ast)  # This should fold ZERO to 0
        
        # Division by zero detection should catch the error
        with pytest.raises(GeLBExTypeError) as excinfo:
            validate_division_by_zero(folded_ast)
        
        assert "Division by zero" in str(excinfo.value.error)
        assert "divisor is" in str(excinfo.value.error)
    
    def test_division_by_zero_valid_cases_integration(self):
        """Test that valid divisions pass through the full pipeline."""
        # Test case: valid division after constant folding
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int FIVE = 2 + 3;",
            initializer_content="f.out[x | 0] = 10 / FIVE;"
        )
        
        # Run through frontend
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Process through midware stages
        validate_midware_input(ast)
        folded_ast = fold_constants(ast)  # This should fold FIVE to 5
        validated_ast = validate_division_by_zero(folded_ast)  # Should not raise error
        
        # Verify the AST is returned successfully
        assert isinstance(validated_ast, Program_N)

    def test_intrinsic_function_through_full_pipeline(self):
        """Test that intrinsic functions (sum, dot_prod) work through the full pipeline.

        TypePromotionVisitor, TypeValidationVisitor, ConstantFoldingVisitor and
        DivisionByZeroValidator each need a visitIntrinsicFunctionCall_N; a missing
        one raises GeLBExMissingASTVisitationMethod in a downstream stage.
        """
        gelb_code = '''
        simulation_description("Intrinsic function pipeline test");

        lattices {
            lattice f(1, 3, real, 8, false);
        }

        initializer Init {
            f.out[x | 0] = 0.0;
            f.out[x | 1] = 0.0;
            f.out[x | 2] = 0.0;
        }

        dynamic Dyn {
            real f0 = f.in[x | 0];
            real f1 = f.in[x | 1];
            real f2 = f.in[x | 2];
            real rho = f0 + f1 + f2;
            f.out[x | 0] = f0;
            f.out[x | 1] = f1;
            f.out[x | 2] = f2;
        }

        gauge Out -> (real val) {
            val = sum({f.in[x | 0], f.in[x | 1], f.in[x | 2]});
        }

        node_classes {
            node_class BULK(Init, Dyn, Out);
        }

        geometry {
            nodes[:] = BULK;
        }
        '''

        # Run through full frontend pipeline, including type promotion & validation
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = validate_types(ast)
        ast = validate_constant_assignments(ast)

        # Process through the full midware pipeline
        validate_midware_input(ast)
        folded_ast = fold_constants(ast)
        validated_ast = validate_division_by_zero(folded_ast)

        assert isinstance(validated_ast, Program_N)


class TestTypePromotionIntegration:
    """End-to-end tests for type promotion through the full pipeline.

    These tests verify that programs with mixed-type arithmetic,
    comparisons, and assignments compile through the full frontend +
    midware pipeline without errors.  Derived from former standalone
    example files (test_type_promotion*.gelb).
    """

    def test_arithmetic_promotion_int_real(self):
        """int + real promotes correctly through full pipeline."""
        code = minimal_gelb_program_1d(
            initializer_content="real x1; x1 = 1 + 2.5;\nf.out[x | 0] = 0;")
        ast = get_fully_validated_ast(code)
        assert isinstance(ast, Program_N)

    def test_bool_int_promotion(self):
        """bool + int promotes correctly."""
        code = minimal_gelb_program_1d(
            initializer_content="int x2; x2 = true + 5;\nf.out[x | 0] = 0;")
        ast = get_fully_validated_ast(code)
        assert isinstance(ast, Program_N)

    def test_bool_real_promotion(self):
        """bool * real promotes correctly."""
        code = minimal_gelb_program_1d(
            initializer_content="real x3; x3 = false * 3.14;\nf.out[x | 0] = 0;")
        ast = get_fully_validated_ast(code)
        assert isinstance(ast, Program_N)

    def test_comparison_with_promotion(self):
        """int < real promotes correctly."""
        code = minimal_gelb_program_1d(
            initializer_content="bool b1; b1 = 1 < 2.5;\nf.out[x | 0] = 0;")
        ast = get_fully_validated_ast(code)
        assert isinstance(ast, Program_N)

    def test_assignment_promotion(self):
        """int assigned to real promotes correctly."""
        code = minimal_gelb_program_1d(
            initializer_content="real z; z = 42;\nf.out[x | 0] = 0;")
        ast = get_fully_validated_ast(code)
        assert isinstance(ast, Program_N)

    def test_const_with_promotion(self):
        """const real = int promotes correctly."""
        code = minimal_gelb_program_1d(
            global_constants_content="const real PI = 3.14159;",
            initializer_content=(
                "const real radius = 10;\n"
                "real area; area = PI * radius * radius;\n"
                "bool big; big = area > 100;\n"
                "f.out[x | 0] = 0;"))
        ast = get_fully_validated_ast(code)
        assert isinstance(ast, Program_N)

    def test_mixed_chain(self):
        """Complex mixed-type chain through full pipeline."""
        code = minimal_gelb_program_1d(
            dynamic_content=(
                "real result; result = 2 * 3.14;\n"
                "f.out[x | 0] = f.in[x | 0];"))
        ast = get_fully_validated_ast(code)
        assert isinstance(ast, Program_N)


class TestTypeErrorIntegration:
    """End-to-end tests for type errors through the full pipeline.

    These tests verify that invalid type combinations are correctly
    rejected.  Derived from former standalone example file
    (test_type_errors.gelb).
    """

    def test_logical_and_on_int_rejects(self):
        """int && int should be rejected by type validation."""
        code = minimal_gelb_program_1d(
            initializer_content="bool b; b = 1 && 2;\nf.out[x | 0] = 0;")
        with pytest.raises(GeLBExTypeError):
            get_fully_validated_ast(code)

# Exercise executable values and both optimized and plain compilation paths.
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler, requires_gpu_cuda_cpp_compiler,
)
import numpy as np


_SLICE_CONFIGS = [
    pytest.param('cpu_fortran_serial', None, marks=requires_compiler, id='fortran'),
    *(pytest.param('cpu_highway', layout, marks=requires_cpp_highway_compiler, id=layout)
      for layout in ('soa', 'aos', 'cbt')),
    pytest.param('gpu_cuda_cpp', None, marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler], id='cuda'),
]


_ARRAY_WEIGHTS = '{1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0}'
_RUNTIME_INTS = 'array[int, 9] k = A + x; '
_LOCAL_SQUARE = 'array[real, 9] q = W * W; '
_TAIL = ',1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0}'


def _slice_program(body):
    return f'''simulation_description("Slice scalarization");
    global_constants {{
      const array[real, 9] W = {_ARRAY_WEIGHTS};
      const array[int, 9] A = {{1,2,3,4,5,6,7,8,9}};
      const array[int, 9] EX = {{0,1,0,-1,0,1,-1,-1,1}};
      const array[int, 9] EY = {{0,0,1,0,-1,1,1,-1,-1}};
    }}
    lattices {{ lattice f(2,9,real,{{8,4}},{{true,true}}); }}
    initializer I {{ f.out[x,y|:] = real(x) + W; }}
    dynamic D {{ {body} }}
    gauge G -> ({', '.join(f'real v{i}' for i in range(9))}) {{
      {' '.join(f'v{i} = f.in[x,y|{i}];' for i in range(9))}
    }}
    node_classes {{ node_class B(I,D,G); }}
    geometry {{ nodes[:,:] = B; }}
    function Cast(array[int,9] arg) -> (array[real,9] result) {{ result = real(arg); }}
    '''


# Each expected value depends on the direction; runtime casts also depend on x.
_SLICE_CASES = [
    ('cast-local', _RUNTIME_INTS + 'array[real,9] r; r = real(k); f.out[x,y|:] = r;', lambda w,x: w+x, 'all'),
    ('cast-global', 'array[real,9] r; r = real(A); f.out[x,y|:] = r;', lambda w,x: w, 'all'),
    ('cast-narrow', _RUNTIME_INTS + 'array[real32,9] r; r = real32(k); f.out[x,y|:] = r;', lambda w,x: w+x, 'all'),
    ('cast-integer', 'array[int32,9] r; r = int32(W); f.out[x,y|:] = r;', lambda w,x: w, 'all'),
    ('cast-function', _RUNTIME_INTS + 'array[real,9] r = Cast(k); f.out[x,y|:] = r;', lambda w,x: w+x, 'all'),
    ('cast-whole', _RUNTIME_INTS + 'int s = sum(k); array[real,9] r; r = real(k); f.out[x,y|:] = r + real(s);', lambda w,x: w+10*x+45, 'all'),
    ('cast-declaration', _RUNTIME_INTS + 'array[real,9] r = real(k); f.out[x,y|:] = r;', lambda w,x: w+x, 'all'),
    ('cast-slice', 'f.out[x,y|:] = real(f.in[x,y|:]) * 0.5;', lambda w,x: (w+x)*0.5, 'all'),
    ('cast-nested', 'f.out[x,y|:] = real(real32(f.in[x,y|:])) * 0.5;', lambda w,x: (w+x)*0.5, 'all'),
    ('cast-bare', 'f.out[x,y|:] = real(f.in[x,y|:]);', lambda w,x: w+x, 'all'),
    ('element-cast', 'array[int,9] q = A*A; f.out[x,y|:] = W + real(q[8]);', lambda w,x: w+81, 'all'),
    ('element-math', 'array[int,9] q = A*A; f.out[x,y|:] = W + sqrt(real(q[8]));', lambda w,x: w+9, 'all'),
    ('slice-open', _LOCAL_SQUARE + 'f.out[x,y|:] = f.in[x,y|:] + q[:];', lambda w,x: w+x+w*w, 'fortran'),
    ('slice-explicit', _LOCAL_SQUARE + 'f.out[x,y|:] = f.in[x,y|:] + q[0:8];', lambda w,x: w+x+w*w, 'fortran'),
    ('collision', 'array[real,9] a = W*W; real b_0 = 1.0; array[real,9] b = a*2.0; f.out[x,y|:] = b+b_0;', lambda w,x: 2*w*w+1, 'all'),
    ('reduction-sum', _LOCAL_SQUARE + 'f.out[x,y|:] = q + sum(q);', lambda w,x: w*w+285, 'all'),
    ('reduction-dot', _LOCAL_SQUARE + 'f.out[x,y|:] = W * dot_prod(W,q);', lambda w,x: w*2025, 'all'),
    ('literal-store', 'f.out[x,y|:] = 2.0 * {f.in[x,y|0]' + _TAIL + ';', lambda w,x: np.where(w==1,2*(x+1),2*(w-1)), 'literal'),
    ('literal-declaration', 'array[real,9] q = 2.0 * {f.in[x,y|0]' + _TAIL + '; f.out[x,y|:] = q;', lambda w,x: np.where(w==1,2*(x+1),2*(w-1)), 'literal'),
    ('literal-cast', 'f.out[x,y|:] = real({x,1,2,3,4,5,6,7,8});', lambda w,x: np.where(w==1,x,w-1), 'all'),
    ('literal-repeated', 'f.out[x,y|:] = 2.0 * {' + ','.join(['f.in[x,y|0]*3.0']*9) + '};', lambda w,x: 6*(x+1), 'literal'),
    ('singleton', _LOCAL_SQUARE + 'array[real,9] c = {q[8:8]' + _TAIL + '; f.out[x,y|:] = f.in[x,y|:] + c;', lambda w,x: w+x+np.where(w==1,81,w-1), 'all'),
    ('streaming', 'array[real,9] g = upstream_dfs(f,x,y,{EX,EY}); f.out[x,y|:] = g;', lambda w,x: (x-np.array([0,1,0,-1,0,1,-1,-1,1])[:,None,None])%8+w, 'all'),
]


@pytest.mark.parametrize('backend,layout', _SLICE_CONFIGS)
@pytest.mark.parametrize('name,body,expected,plain', _SLICE_CASES, ids=[c[0] for c in _SLICE_CASES])
def test_slice_scalarization_values(tmp_path, monkeypatch, backend, layout, name, body, expected, plain):
    from gelb.backends.highway.common import _detect_avx512_available
    from gelb.tests.integration.test_tutorial_regressions import run_source
    if layout == 'cbt' and not _detect_avx512_available():
        pytest.skip('the cbt layout needs AVX-512')
    w = np.arange(1,10,dtype=float)[:,None,None]
    x = np.arange(8,dtype=float)[None,None,:]
    target = np.broadcast_to(expected(w,x), (9,4,8))
    flags = f'--storage-layout {layout}' if layout else ''
    results = []
    modes = ['default']
    if (plain == 'all' or (plain == 'fortran' and backend == 'cpu_fortran_serial')
            or (plain == 'literal' and layout not in ('soa', 'cbt'))):
        modes.append('plain')
    for mode in modes:
        monkeypatch.setenv('GELBC_EXTRA', flags + (' --no-slice-simplify --no-scalar-cse' if mode == 'plain' else ''))
        directory = tmp_path / mode
        directory.mkdir()
        fields = run_source(directory, backend, _slice_program(body))
        actual = np.stack([fields[f'v{i}'][-1] for i in range(9)])
        np.testing.assert_array_equal(actual, target)
        results.append(actual)
    if len(results) == 2:
        assert results[0].tobytes() == results[1].tobytes()


@pytest.mark.parametrize('body,expected', [
    (_LOCAL_SQUARE + 'f.out[x,y|:] = f.in[x,y|:] + W*sum(q*2.0) + dot_prod(q*2.0,W);', lambda w,x: w+x+570*w+4050),
    ('array[real,9] a = W*W; array[real,9] b = W*2.0; real u = sum(a+b)*2.0; real v = sum(a+b)*2.0; f.out[x,y|:] = W+u+v;', lambda w,x: w+1500),
])
def test_reductions_keep_array_expression_operands(tmp_path, monkeypatch, body, expected):
    from gelb.tests.integration._toolchain import HAS_GFORTRAN
    if not HAS_GFORTRAN:
        pytest.skip('gfortran is required')
    test_slice_scalarization_values(tmp_path, monkeypatch, 'cpu_fortran_serial', None,
                                    'reduction-expression', body, expected, 'all')
