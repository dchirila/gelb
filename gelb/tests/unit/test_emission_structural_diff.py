"""Alpha-renaming accepts real emitted names and rejects arithmetic mutations."""

import importlib.util
from pathlib import Path
import re

from click.testing import CliRunner
import pytest

from gelb.gelbc import cli

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("structural_diff", ROOT / "scripts/emission_structural_diff.py")
diff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diff)
NAMES = (
    "g___CascadedCollide_1_cs2", "gelb_b0_g______ceq_a_d__1___c",
    "g__gelb_draw_0", "g__gelb_call_0", "g__gelb_dpa_0", "g__gelb_pre_cse_0",
    "gelb_b0_g___gelb__pre__cse__0", "gelb_b0_g___gelb__cse__0",
    "g__gelb_cse_0", "g_gelb_matmul_in_0", "g_gelb_tmp_a", "gelb_tmp_a",
)


@pytest.mark.parametrize("suffix", (".cpp", ".cu", ".f90"))
@pytest.mark.parametrize("name", NAMES)
def test_emitted_temporary_families(name, suffix):
    renamed = name + "_new"
    body = (f"subroutine step()\nreal(8) :: {name}\n{name} = (g_u + 1.0d0)\ng_out = {name}\nend subroutine step"
            if suffix == ".f90" else f"void step() {{ double {name} = (g_u + 1.0); g_out = {name}; }}")
    assert diff.TEMP_RE.fullmatch(name) and diff.TEMP_RE.fullmatch(renamed)
    assert diff.equivalent(body, body.replace(name, renamed), suffix)


CPP = "void step() { float g__gelb_cse_0 = (g_u[0] + 1.0f); g_v = static_cast<float>(g__gelb_cse_0); g_w = g_v; }"
@pytest.mark.parametrize("before,after,suffix", [
    (CPP, CPP.replace("(g_u[0] + 1.0f)", "g_u[0] + 1.0f"), ".cpp"),
    (CPP, CPP.replace(" + ", " - "), ".cu"),
    (CPP, CPP.replace("static_cast<float>", "static_cast<double>"), ".cpp"),
    (CPP, CPP.replace("1.0f", "1.0"), ".cu"),
    ("g_x = 0.0d0", "g_x = 0.0e0", ".f90"),
    (CPP, CPP.replace("[0]", "[1]"), ".cpp"),
    (CPP, CPP.replace("g_u", "g_z"), ".cpp"),
    ("void f() { g_x = 1; g_y = 2; }", "void f() { g_y = 2; g_x = 1; }", ".cpp"),
    (CPP, CPP.replace("float g_", "double g_"), ".cu"),
    ('void f() { puts("g__gelb_cse_0"); }', 'void f() { puts("g__gelb_cse_1"); }', ".cpp"),
])
def test_semantic_mutations(before, after, suffix):
    assert not diff.equivalent(before, after, suffix)


def test_bijection_and_function_scope():
    before = "void f() { g__gelb_cse_0 = g__gelb_cse_1; } void g() { g__gelb_cse_0 = g__gelb_cse_0; }"
    after = "void f() { g__gelb_cse_7 = g__gelb_cse_8; } void g() { g__gelb_cse_2 = g__gelb_cse_2; }"
    assert diff.equivalent(before, after, ".cpp")
    assert not diff.equivalent(before, after.replace("g__gelb_cse_8", "g__gelb_cse_7"), ".cpp")
    assert not diff.equivalent(before, after.replace("g__gelb_cse_2;", "g__gelb_cse_3;"), ".cpp")


@pytest.mark.parametrize("suffix", (".cpp", ".cu"))
def test_sibling_scope_reset_and_enclosing_uses(suffix):
    before = """void step() {
      { double g___Mix_0_a = g_u;
        for (int i = 0; i < 2; ++i) { g_out[i] = g___Mix_0_a; } }
      { double g___Mix_1_a = g_v;
        for (int i = 0; i < 2; ++i) { g_out[i] = g___Mix_1_a; } }
    }"""
    after = before.replace("g___Mix_1_a", "g___Mix_0_a")
    assert diff.equivalent(before, after, suffix)
    assert not diff.equivalent(before, after.replace("g_out[i] = g___Mix_0_a", "g_out[i] = g___Mix_2_a", 1), suffix)


@pytest.mark.parametrize("suffix", (".cpp", ".cu"))
@pytest.mark.parametrize("mutation", ("collision", "capture", "enclosing_use"))
def test_nested_scope_binding_mutations(suffix, mutation):
    before = """void step() {
      double g__gelb_cse_0 = g_u;
      { double g__gelb_cse_1 = g_v;
        g_out = g__gelb_cse_0 + g__gelb_cse_1; }
      g_out = g__gelb_cse_0;
    }"""
    after = before.replace("cse_0", "cse_7").replace("cse_1", "cse_8")
    assert diff.equivalent(before, after, suffix)
    if mutation == "collision":
        after = after.replace("cse_8", "cse_7")
    elif mutation == "capture":
        after = after.replace("g_out = g__gelb_cse_7 +", "g_out = g__gelb_cse_8 +")
    else:
        after = after.replace("g_out = g__gelb_cse_7;", "g_out = g__gelb_cse_8;")
    assert not diff.equivalent(before, after, suffix)


@pytest.mark.parametrize("before,after", [
    ("g_out = (g_u + 1.0d0) + 2.0d0", "g_out = (g_u + &\n &1.0d0) + 2.0d0"),
    ("g_out = g_u + 1.0d0", "g_out = g_u & ! comment\n ! between\n\n &+ 1.0d0"),
    ("g_out = g_u + 1.0d0", "g_out = g_u + &\n   1.0d0"),
    ("g_out = not x", "g_out = not &\n &x"),
    ("g_out = notx", "g_out = not&\n&x"),
    ("g_out = 'can''t ! & change'", "g_out = 'can''t ! &&\n& change'"),
    ('g_out = "a!&b"', 'g_out = "a!&b" ! trailing comment'),
    ("g_out = 'ab'", "g_out = 'a&\n! between\n&b'"),
])
def test_fortran_continuations(before, after):
    assert diff.equivalent(before, after, ".f90")


@pytest.mark.parametrize("before,after", [
    ("g_out = not &\n&x", "g_out = not&\n&x"),
    ("g_out = 'a&b'", "g_out = 'ab'"),
    ("g_out = 'a &\n&b'", "g_out = 'a&\n&b'"),
    ("g_out = (g_u &\n &+ 1.0d0)", "g_out = (g_u &\n &- 1.0d0)"),
    ("g_out = (g_u &\n &+ 1.0d0)", "g_out = (g_u) &\n &+ 1.0d0"),
])
def test_fortran_continuation_mutations(before, after):
    assert not diff.equivalent(before, after, ".f90")


@pytest.mark.parametrize("suffix", (".cpp", ".cu", ".f90"))
def test_whitespace_comments_and_quoted_text(suffix):
    if suffix == ".f90":
        before, after = "g_x = 'can''t !'", "g_x  =  'can''t !' ! comment"
    else:
        before = 'void f() { puts("first""second //"); }'
        after = 'void f() { /* comment */ puts("first" "second //"); }'
    assert diff.equivalent(before, after, suffix)
    assert not diff.equivalent(before, after.replace("'can''t !'", "'can !'").replace("first", "changed"), suffix)


@pytest.mark.parametrize("backend,suffix", [("cpu_highway", ".cpp"), ("gpu_cuda_cpp", ".cu"), ("cpu_fortran_serial", ".f90")])
def test_real_block_reorder_emission(tmp_path, backend, suffix):
    prefix = '''simulation_description("block reorder");
global_constants { const array[real, 2] W = {0.25, 0.75}; }
lattices { lattice f(2, 2, real, {67, 4}, {true, true}); }
function Mix(real a, real b) -> (real r) { real t = a * W[0]; r = t + b * W[1]; }
initializer Init { f.out[x, y | 0] = real(x); f.out[x, y | 1] = real(y); }
'''
    blocks = ["dynamic StepA { f.out[x, y | 0] = Mix(f.in[x, y | 0], f.in[x, y | 1]); f.out[x, y | 1] = f.in[x, y | 1]; }\n",
              "dynamic StepB { f.out[x, y | 0] = f.in[x, y | 0]; f.out[x, y | 1] = Mix(f.in[x, y | 1], f.in[x, y | 0]); }\n"]
    tail = '''gauge G -> (real s) { s = f.in[x, y | 0]; }
node_classes { node_class A(Init, StepA, G); node_class B(Init, StepB, G); }
geometry { nodes[:, :] = A; nodes[10:19, :] = B; }
'''
    emissions = []
    for order, extra in ((blocks, ""), (blocks[::-1], ""),
                         (blocks, "function __Mix_0_t(real a) -> (real r) { r = a; }")):
        path = tmp_path / "reorder.gelb"
        out = path.with_suffix(suffix)
        path.write_text(prefix + "".join(order) + tail + extra)
        args = [str(path), "-b", backend, "-o", str(out), "--nc-output", "out.nc"]
        if backend == "cpu_highway":
            args += ["--storage-layout", "aos"]
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, result.output
        emissions.append(out.read_text())
    assert emissions[0] == emissions[1]
    pushed = emissions[2]
    assert pushed != emissions[0]
    assert diff.equivalent(emissions[0], pushed, suffix)
    name = next(t for t in diff.tokens(pushed, suffix == ".f90")
                if diff.TEMP_RE.fullmatch(t))
    corrupted = pushed.replace(name, name + "_broken", 1)
    assert not diff.equivalent(emissions[0], corrupted, suffix)
    if suffix != ".f90":
        head, sep, tail = emissions[0].rpartition("double g___Mix_0_a =")
        assert sep
        asymmetric = head + (sep + tail).replace("g___Mix_0_", "g___Mix_1_")
        assert asymmetric != emissions[0]
        assert diff.equivalent(emissions[0], asymmetric, suffix)


@pytest.mark.parametrize("n_calls", (1, 10))
def test_fortran_reorder_wrap_shift(tmp_path, n_calls):
    prefix = '''simulation_description("wrap");
lattices { lattice f(2, 2, real, {67, 4}, {true, true}); }
function Id(real a) -> (real p) { p = (a * 0.5) + (a * 0.25) + (a * 0.125) + 1.0; }
initializer Init { f.out[x, y | 0] = real(x); f.out[x, y | 1] = real(y); }
'''
    calls = "\n".join(f"real v{i} = Id(f.in[x, y | 0] + {i}.0);" for i in range(n_calls))
    total = " + ".join(f"v{i}" for i in range(n_calls))
    blocks = [f"dynamic StepA {{ {calls}\nf.out[x, y | 0] = {total}; f.out[x, y | 1] = f.in[x, y | 1]; }}\n",
              "dynamic StepB { f.out[x, y | 0] = Id(f.in[x, y | 1]); f.out[x, y | 1] = f.in[x, y | 1]; }\n"]
    tail = '''gauge G -> (real s) { s = f.in[x, y | 0]; }
node_classes { node_class A(Init, StepA, G); node_class B(Init, StepB, G); }
geometry { nodes[:, :] = A; nodes[10:19, :] = B; }
'''
    emissions = []
    occupied = "\n".join(f"function __Id_{i}_p(real a) -> (real p) {{ p = a; }}"
                         for i in range(n_calls))
    for order, extra in ((blocks, ""), (blocks[::-1], ""), (blocks, occupied)):
        path, out = tmp_path / "wrap.gelb", tmp_path / "wrap.f90"
        path.write_text(prefix + "".join(order) + tail + extra)
        result = CliRunner().invoke(cli, [str(path), "-b", "cpu_fortran_serial", "-o", str(out), "--nc-output", "out.nc"])
        assert result.exit_code == 0, result.output
        emissions.append(out.read_text())
    assert emissions[0] == emissions[1]
    pushed = emissions[2]
    assert pushed != emissions[0]
    assert diff.equivalent(emissions[0], pushed, ".f90")
    if n_calls == 10:
        def wrap_tokens(text):
            return [["temp" if diff.TEMP_RE.fullmatch(t) else t
                     for t in diff.tokens(line, True)]
                    for line in text.splitlines() if "&" in line]
        assert "&" in pushed
        assert wrap_tokens(emissions[0]) != wrap_tokens(pushed)
    name = next(t for t in diff.tokens(pushed, True) if diff.TEMP_RE.fullmatch(t))
    corrupted = pushed.replace(name, name + "_broken", 1)
    assert not diff.equivalent(emissions[0], corrupted, ".f90")
