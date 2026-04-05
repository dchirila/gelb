"""The wall intrinsic's values, guards, wrapping and full-way timing."""

import itertools

import numpy as np
import pytest

from gelb.tests.integration.test_tutorial_regressions import BACKENDS, run_source
from gelb.tests.integration._toolchain import requires_cpp_highway_compiler


def probe_source(d, periodic, speed=1):
    # A wide x axis exercises Highway vector bodies, scalar heads and tails.
    sizes = [21, 4, 3][:d]
    velocities = list(itertools.product([0, speed, -speed], repeat=d))
    q = len(velocities)
    coords = ", ".join("xyz"[:d])
    axes = ["EX", "EY", "EZ"][:d]
    arrays = "\n".join(
        f"const array[real, {q}] {name} = {{" +
        ", ".join(str(v[a]) + ".0" for v in velocities) + "};"
        for a, name in enumerate(axes))
    shape = str(sizes[0]) if d == 1 else "{" + ", ".join(map(str, sizes)) + "}"
    per = [str(p).lower() for p in periodic]
    per = per[0] if d == 1 else "{" + ", ".join(per) + "}"
    vel = axes[0] if d == 1 else "{" + ", ".join(axes) + "}"
    fields = ", ".join(f"real p{i}" for i in range(q))
    writes = "\n".join(f"p{i} = f.in[{coords} | {i}];" for i in range(q))
    cell = " + ".join(f"{10**a}.0 * real({c})" for a, c in enumerate("xyz"[:d]))
    initial = "\n".join(f"f.out[{coords} | {i}] = {1000*i}.0 + ({cell});"
                         for i in range(q))
    source = f'''
simulation_description("guarded bounce back");
global_constants {{ {arrays} }}
lattices {{ lattice f({d}, {q}, real, {shape}, {per}); }}
initializer I {{ {initial} }}
dynamic D {{
    array[real, {q}] reflected = bounce_back_dfs(f, {coords}, {vel});
    f.out[{coords} | :] = reflected;
}}
gauge G -> ({fields}) {{ {writes} }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[{", ".join(":" for _ in sizes)}] = B; }}
'''
    return source, sizes, velocities


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("d,periodic,speed", [
    (1, [False], 1), (1, [True], 2),
    (1, [False], 30), (1, [True], 30),
    (2, [False, False], 1), (2, [True, False], 2),
    (3, [False, False, False], 1), (3, [False, True, True], 1),
])
def test_guarded_values(tmp_path, backend, d, periodic, speed):
    source, sizes, velocities = probe_source(d, periodic, speed)
    data = run_source(tmp_path, backend, source, timesteps=3)
    values = np.stack([data[f"p{i}"][0] for i in range(len(velocities))], axis=-1)
    for step in range(1, 4):
        expected = np.empty_like(values)
        for cell in itertools.product(*(range(n) for n in sizes)):
            for i, v in enumerate(velocities):
                target = tuple(c + off for c, off in zip(cell, v))
                if any(not per and not 0 <= c < n
                       for c, n, per in zip(target, sizes, periodic)):
                    target = cell
                else:
                    target = tuple(c % n for c, n in zip(target, sizes))
                opposite = velocities.index(tuple(-off for off in v))
                expected[(*reversed(cell), i)] = values[(*reversed(target), opposite)]
        for i in range(len(velocities)):
            np.testing.assert_array_equal(data[f"p{i}"][step], expected[..., i])
        values = expected


@pytest.mark.parametrize("backend", BACKENDS)
def test_obstacle_returns_a_population_after_two_steps(tmp_path, backend):
    data = run_source(tmp_path, backend, """
simulation_description("full-way reflection at an interior obstacle");
global_constants { const array[real, 3] EX = {0.0, 1.0, -1.0}; }
lattices { lattice f(1, 3, real, 25, false); }
initializer I {
    f.out[x | 0] = 0.0;
    f.out[x | 1] = real(x == 10);
    f.out[x | 2] = 0.0;
}
dynamic Fluid {
    array[real, 3] pulled = upstream_dfs(f, x, EX);
    f.out[x | :] = pulled;
}
dynamic Wall { f.out[x | :] = bounce_back_dfs(f, x, EX); }
gauge G -> (real rightward, real leftward) {
    rightward = f.in[x | 1]; leftward = f.in[x | 2];
}
node_classes { node_class F(I, Fluid, G); node_class W(I, Wall, G); }
geometry { nodes[:] = F; nodes[0] = W; nodes[11] = W; nodes[24] = W; }
""", timesteps=3)
    expected_right = np.zeros((4, 25))
    expected_left = np.zeros((4, 25))
    expected_right[0, 10] = 1
    expected_left[1, 11] = 1
    expected_left[2, 10] = 1
    expected_left[3, 9] = 1
    np.testing.assert_array_equal(data["rightward"], expected_right)
    np.testing.assert_array_equal(data["leftward"], expected_left)


@pytest.mark.parametrize("backend", BACKENDS)
def test_bounce_back_in_a_gauge(tmp_path, backend):
    source, sizes, velocities = probe_source(2, [True, False])
    source = source.replace(
        "array[real, 9] reflected = bounce_back_dfs(f, x, y, {EX, EY});",
        "array[real, 9] reflected = f.in[x, y | :];")
    source = source.replace("p0 = f.in[x, y | 0];",
        "array[real, 9] bb = bounce_back_dfs(f, x, y, {EX, EY}); p0 = bb[0];")
    for i in range(1, 9):
        source = source.replace(f"p{i} = f.in[x, y | {i}];", f"p{i} = bb[{i}];")
    data = run_source(tmp_path, backend, source)
    for i, (dx, dy) in enumerate(velocities):
        opposite = velocities.index((-dx, -dy))
        expected = np.empty(tuple(reversed(sizes)))
        for y, x in np.ndindex(expected.shape):
            target = ((x + dx) % sizes[0], y + dy) if 0 <= y + dy < sizes[1] else (x, y)
            expected[y, x] = 1000*opposite + target[0] + 10*target[1]
        np.testing.assert_array_equal(data[f"p{i}"][0], expected)
        np.testing.assert_array_equal(data[f"p{i}"][1], expected)


@requires_cpp_highway_compiler
@pytest.mark.parametrize("layout", ["soa", "cbt"])
def test_highway_vector_paths(tmp_path, layout):
    from gelb.backends.highway.common import _detect_avx512_available
    from gelb.tests.integration.test_real_width_contract import _run, _generated
    if layout == "cbt" and not _detect_avx512_available():
        pytest.skip("CBT requires AVX-512")
    source, sizes, velocities = probe_source(2, [True, False])
    # Exercise the direct slice assignment, including periodic x-edge
    # tiles; the other value tests initialize an array from the call.
    source = source.replace(
        "array[real, 9] reflected = bounce_back_dfs(f, x, y, {EX, EY});\n"
        "    f.out[x, y | :] = reflected;",
        "f.out[x, y | :] = bounce_back_dfs(f, x, y, {EX, EY});")
    with _run(tmp_path, source, "cpu_highway", extra=f"--storage-layout {layout}") as data:
        for i, (dx, dy) in enumerate(velocities):
            opposite = velocities.index((-dx, -dy))
            for y, x in np.ndindex(tuple(reversed(sizes))):
                target = ((x + dx) % sizes[0], y + dy) if 0 <= y + dy < sizes[1] else (x, y)
                assert data[f"p{i}"][1, y, x] == 1000*opposite + target[0] + 10*target[1]
    code = _generated(tmp_path, "cpu_highway")
    assert "// x = SIMD body" in code
    if layout == "cbt":
        assert "hn::TwoTablesLookupLanes" in code
