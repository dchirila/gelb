#!/usr/bin/env python3
"""
Integration tests for the Fortran backend (CPU, serial).

Tests verify that generated Fortran code is structurally correct for both
NetCDF and stdout output modes.
"""

import re

import pytest
from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran
from gelb.frontend.constant_overrides import parse_overrides, apply_constant_overrides
from gelb.tests.test_utils import get_fully_validated_ast, minimal_gelb_program_1d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate(gelb_code, output_mode='netcdf', num_timesteps=1,
              output_filename='test_output.nc'):
    """Run full pipeline and generate Fortran code."""
    ast = get_fully_validated_ast(gelb_code)
    return generate_fortran(ast, num_timesteps=num_timesteps,
                            output_mode=output_mode,
                            output_filename=output_filename)


def _default_program():
    """Return a minimal valid 1D GeLB program source string."""
    return minimal_gelb_program_1d()


def _program_with_real_gauge():
    """Return a 1D GeLB program with real-valued gauge output."""
    return """
    simulation_description("Real gauge test");
    lattices {
        lattice f(1, 1, real, 16, false);
    }
    initializer Init {
        f.out[x | 0] = 1.0;
    }
    dynamic Dyn {
        f.out[x | 0] = f.in[x | 0];
    }
    gauge Out -> (real val) {
        val = f.in[x | 0];
    }
    node_classes {
        node_class BULK(Init, Dyn, Out);
    }
    geometry {
        nodes[:] = BULK;
    }
    """


def _program_with_multiple_gauge_outputs():
    """Return a 1D GeLB program with multiple gauge output variables."""
    return """
    simulation_description("Multi-output gauge test");
    lattices {
        lattice f(1, 3, int, 8, false);
    }
    initializer Init {
        f.out[x | 0] = 10;
        f.out[x | 1] = 20;
        f.out[x | 2] = 30;
    }
    dynamic Dyn {
        f.out[x | 0] = f.in[x | 0];
        f.out[x | 1] = f.in[x | 1];
        f.out[x | 2] = f.in[x | 2];
    }
    gauge Out -> (int a, int b, int c) {
        a = f.in[x | 0];
        b = f.in[x | 1];
        c = f.in[x | 2];
    }
    node_classes {
        node_class BULK(Init, Dyn, Out);
    }
    geometry {
        nodes[:] = BULK;
    }
    """


# ===================================================================
# NetCDF output mode
# ===================================================================

class TestNetCDFCodeGeneration:
    """Tests for NetCDF output mode in generated Fortran code."""

    def test_use_netcdf_present(self):
        """Generated code must include 'use netcdf'."""
        code = _generate(_default_program())
        assert 'use netcdf' in code

    def test_implicit_none_after_use_netcdf(self):
        """'implicit none' must follow 'use netcdf'."""
        code = _generate(_default_program())
        use_pos = code.index('use netcdf')
        none_pos = code.index('implicit none')
        assert none_pos > use_pos

    def test_ncid_declared(self):
        """NetCDF file ID variable must be declared."""
        code = _generate(_default_program())
        assert 'integer :: gelb_ncid' in code

    def test_dim_ids_declared(self):
        """Spatial and time dimension IDs must be declared."""
        code = _generate(_default_program())
        assert 'gelb_dim_x_id' in code
        assert 'gelb_dim_time_id' in code

    def test_coord_var_ids_declared(self):
        """Coordinate variable IDs must be declared."""
        code = _generate(_default_program())
        assert 'gelb_coord_x_id' in code
        assert 'gelb_coord_time_id' in code

    def test_gauge_var_id_declared(self):
        """Gauge output variable ID must be declared."""
        code = _generate(_default_program())
        assert 'integer :: gelb_varid_g_val' in code

    def test_buffer_array_declared(self):
        """Buffer array for gauge output must be declared."""
        code = _generate(_default_program())
        assert 'gelb_buf_g_val' in code
        assert '0:g__nx-1' in code

    def test_output_filename_embedded(self):
        """Output filename must be embedded as a Fortran parameter."""
        code = _generate(_default_program(), output_filename='my_output.nc')
        assert "gelb_nc_file = 'my_output.nc'" in code

    def test_nf90_create_present(self):
        """File creation call must be present."""
        code = _generate(_default_program())
        assert 'nf90_create' in code
        assert 'NF90_CLOBBER' in code

    def test_nf90_def_dim_spatial(self):
        """Spatial dimension definition must be present."""
        code = _generate(_default_program())
        assert "nf90_def_dim(gelb_ncid, 'x'" in code

    def test_nf90_def_dim_time_unlimited(self):
        """Time dimension must be defined as unlimited."""
        code = _generate(_default_program())
        assert 'NF90_UNLIMITED' in code

    def test_nf90_def_var_gauge_output(self):
        """Gauge output variable must be defined in NetCDF."""
        code = _generate(_default_program())
        assert "nf90_def_var(gelb_ncid, 'val'" in code

    def test_nf90_enddef_present(self):
        """End-define call must be present."""
        code = _generate(_default_program())
        assert 'nf90_enddef' in code

    def test_buffer_fill_in_spatial_loop(self):
        """Buffer fill statement must be inside spatial loop."""
        code = _generate(_default_program())
        assert 'gelb_buf_g_val(g_x) = gelb_b2_g_val' in code

    def test_nf90_put_var_present(self):
        """Data write calls must be present."""
        code = _generate(_default_program())
        assert 'nf90_put_var' in code

    def test_nf90_sync_present(self):
        """Sync call must be present for live monitoring."""
        code = _generate(_default_program())
        assert 'nf90_sync' in code

    def test_nf90_close_present(self):
        """File close call must be present after time loop."""
        code = _generate(_default_program())
        assert 'nf90_close(gelb_ncid)' in code

    def test_nccheck_subroutine_present(self):
        """Error-checking subroutine must be in 'contains' section."""
        code = _generate(_default_program())
        assert 'subroutine gelb_nc_check(status)' in code
        assert 'nf90_strerror' in code

    def test_no_write_stdout_in_netcdf_mode(self):
        """In NetCDF mode, gauge output must not use write(*)."""
        code = _generate(_default_program())
        # write(*, should only appear inside gelb_nc_check, not for gauge output
        lines = code.split('\n')
        gauge_writes = [l for l in lines
                        if 'write(*' in l and 'NetCDF error' not in l
                        and 'MLUPS' not in l and 'Wall time' not in l
                        and 'Compute' not in l and 'GPU' not in l]
        assert len(gauge_writes) == 0


class TestNetCDFTypeMapping:
    """Tests that GeLB types map to correct NetCDF types."""

    def test_int_gauge_uses_nf90_int(self):
        """Integer gauge output should use NF90_INT."""
        code = _generate(_default_program())
        assert 'NF90_INT' in code

    def test_real_gauge_uses_nf90_double(self):
        """Real gauge output should use NF90_DOUBLE."""
        code = _generate(_program_with_real_gauge())
        assert 'NF90_DOUBLE' in code

    def test_real_buffer_type(self):
        """Real gauge buffer should be declared as double precision."""
        code = _generate(_program_with_real_gauge())
        assert 'double precision :: gelb_buf_g_val' in code

    def test_int_buffer_type(self):
        """Integer gauge buffer should be declared as integer(8) (int == int64)."""
        code = _generate(_default_program())
        assert 'integer(8) :: gelb_buf_g_val' in code


class TestNetCDFMultipleOutputs:
    """Tests for programs with multiple gauge output variables."""

    def test_multiple_var_ids_declared(self):
        """Each gauge output variable must have its own NetCDF var ID."""
        code = _generate(_program_with_multiple_gauge_outputs())
        assert 'gelb_varid_g_a' in code
        assert 'gelb_varid_g_b' in code
        assert 'gelb_varid_g_c' in code

    def test_multiple_buffers_declared(self):
        """Each gauge output variable must have its own buffer array."""
        code = _generate(_program_with_multiple_gauge_outputs())
        assert 'gelb_buf_g_a' in code
        assert 'gelb_buf_g_b' in code
        assert 'gelb_buf_g_c' in code

    def test_multiple_buffer_fills(self):
        """Each buffer must be filled in the spatial loop."""
        code = _generate(_program_with_multiple_gauge_outputs())
        assert 'gelb_buf_g_a(g_x) = gelb_b2_g_a' in code
        assert 'gelb_buf_g_b(g_x) = gelb_b2_g_b' in code
        assert 'gelb_buf_g_c(g_x) = gelb_b2_g_c' in code

    def test_multiple_nf90_def_var(self):
        """Each gauge output variable must be defined in NetCDF."""
        code = _generate(_program_with_multiple_gauge_outputs())
        assert "nf90_def_var(gelb_ncid, 'a'" in code
        assert "nf90_def_var(gelb_ncid, 'b'" in code
        assert "nf90_def_var(gelb_ncid, 'c'" in code

    def test_multiple_nf90_put_var(self):
        """Each gauge output variable must be written to NetCDF."""
        code = _generate(_program_with_multiple_gauge_outputs())
        assert 'gelb_varid_g_a, gelb_buf_g_a' in code
        assert 'gelb_varid_g_b, gelb_buf_g_b' in code
        assert 'gelb_varid_g_c, gelb_buf_g_c' in code


# ===================================================================
# Stdout output mode (backward compatibility)
# ===================================================================

class TestStdoutCodeGeneration:
    """Tests for stdout output mode (backward-compatible)."""

    def test_no_use_netcdf(self):
        """Stdout mode must not include 'use netcdf'."""
        code = _generate(_default_program(), output_mode='stdout')
        assert 'use netcdf' not in code

    def test_no_netcdf_declarations(self):
        """Stdout mode must not declare NetCDF variables."""
        code = _generate(_default_program(), output_mode='stdout')
        assert 'gelb_ncid' not in code
        assert 'gelb_dim_x_id' not in code
        assert 'gelb_buf_g_val' not in code

    def test_write_stdout_present(self):
        """Stdout mode must use write(*) for gauge output."""
        code = _generate(_default_program(), output_mode='stdout')
        assert 'write(*' in code

    def test_no_nccheck_subroutine(self):
        """Stdout mode must not include the ncCheck subroutine."""
        code = _generate(_default_program(), output_mode='stdout')
        assert 'gelb_nc_check' not in code

    def test_no_nf90_calls(self):
        """Stdout mode must not contain any nf90_ calls."""
        code = _generate(_default_program(), output_mode='stdout')
        assert 'nf90_' not in code


# ===================================================================
# General code structure (both modes)
# ===================================================================

class TestGeneralCodeStructure:
    """Tests for Fortran code structure common to all output modes."""

    def test_program_header(self):
        """Generated code must start with 'program gelb_simulation'."""
        code = _generate(_default_program())
        assert 'program gelb_simulation' in code

    def test_program_footer(self):
        """Generated code must end with 'end program gelb_simulation'."""
        code = _generate(_default_program())
        assert 'end program gelb_simulation' in code

    def test_contains_section(self):
        """Generated code must have a 'contains' section."""
        code = _generate(_default_program())
        assert 'contains' in code

    def test_swap_subroutine_present(self):
        """Swap subroutine must always be present."""
        code = _generate(_default_program())
        assert 'subroutine gelb_swap' in code

    def test_time_loop_present(self):
        """Time loop must be present."""
        code = _generate(_default_program(), num_timesteps=10)
        assert 'do gelb_timestep = 1, 10' in code

    def test_spatial_loop_present(self):
        """Spatial loop must be present."""
        code = _generate(_default_program())
        assert 'do g_x = 0, g__nx - 1' in code

    def test_pingpong_init(self):
        """Ping-pong buffer initialization must be present."""
        code = _generate(_default_program())
        assert 'g_f_old = 0' in code
        assert 'g_f_new = 1' in code

    def test_swap_call(self):
        """Buffer swap must be called inside time loop."""
        code = _generate(_default_program())
        assert 'call gelb_swap(g_f_old, g_f_new)' in code

    @pytest.mark.parametrize("mode", ['netcdf', 'stdout'])
    def test_grid_parameter_declared(self, mode):
        """Grid size parameter must be declared in both modes."""
        code = _generate(_default_program(), output_mode=mode)
        assert 'integer, parameter :: g__nx = 32' in code

    @pytest.mark.parametrize("mode", ['netcdf', 'stdout'])
    def test_lattice_array_declared(self, mode):
        """Lattice array must be declared in both modes.  Hidden-halo
        storage: each spatial dim is sized -1:N (one ghost cell per
        axis-end), filled by gelb_halo_update_<lname>() each timestep."""
        code = _generate(_default_program(), output_mode=mode)
        assert 'g_f(0:0, -1:g__nx, 0:1)' in code


class TestHiddenHaloStorage:
    """Codegen-shape regression tests for the hidden-halo refactor.

    The cpu_fortran backend stores each lattice with a 1-cell halo on
    every spatial axis (`-1:N` per axis), filled by a per-lattice
    ``gelb_halo_update_<lname>(buf)`` subroutine called once per
    timestep at the top of the time loop.  This lets the inner
    streaming reads use plain offset arithmetic -- no ``modulo()`` --
    and matches the storage convention used by ``cpu_highway`` so
    cross-backend bit-equivalence (``compare_backends.py``) doesn't
    have to special-case storage shape.

    These tests assert the codegen patterns; numerical correctness is
    covered by the existing 104 backend tests + the 78-example smoke
    matrix + ``compare_backends.py`` cross-backend ULP checks.
    """

    def test_storage_uses_halo_range(self):
        """Storage declarations widen each spatial dim from
        ``0:N-1`` to ``-1:N`` -- the +2 hidden-halo extent."""
        code = _generate(_default_program())
        # 1D periodic example: g_f(0:Q-1, -1:Nx, 0:1)
        assert '-1:g__nx' in code, \
            ('expected -1:g__nx halo bound in lattice declaration; '
             'this is the per-axis +2 hidden-halo storage shape')

    @staticmethod
    def _periodic_1d_program():
        """A minimal 1D periodic program -- the simplest case that
        exercises the halo-update emit and the no-modulo streaming."""
        return """
        simulation_description("Hidden-halo regression");
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        initializer Init {
            f.out[x | 0] = 0.6666666666666666;
            f.out[x | 1] = 0.16666666666666666;
            f.out[x | 2] = 0.16666666666666666;
        }
        dynamic Dyn {
            f.out[x | 0] = f.in[x | 0];
            f.out[x | 1] = f.in[x - 1 | 1];
            f.out[x | 2] = f.in[x + 1 | 2];
        }
        gauge Out -> (real rho) {
            rho = f.in[x | 0] + f.in[x | 1] + f.in[x | 2];
        }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """

    def test_halo_update_subroutine_emitted(self):
        """For lattices with at least one periodic axis, a
        ``gelb_halo_update_<lname>(buf)`` subroutine must be emitted
        in the program's ``contains`` block, and called once per
        timestep on the input buffer (``_old``)."""
        code = _generate(self._periodic_1d_program())
        assert 'subroutine gelb_halo_update_g_f(buf)' in code, \
            'expected gelb_halo_update_g_f subroutine in contains block'
        assert 'call gelb_halo_update_g_f(g_f_old)' in code, \
            ('expected call gelb_halo_update_g_f(g_f_old) in time '
             'loop (refresh halo before dynamic reads)')

    def test_no_modulo_in_streaming_reads(self):
        """With the hidden halo, periodic-axis offset reads in the
        dynamic body emit as plain ``({coord} + {offset})`` -- no
        ``modulo()`` call.  Walls keep their ``max(0,...)`` /
        ``min(N-1,...)`` clamps, but that's separate.

        Tested on a fully-periodic 1-D program: the generated body
        must contain zero ``modulo(`` calls outside comments."""
        code = _generate(self._periodic_1d_program())
        non_comment = '\n'.join(
            line for line in code.splitlines()
            if not line.lstrip().startswith('!'))
        assert 'modulo(' not in non_comment, (
            'expected zero modulo() calls in non-comment generated '
            'Fortran for a fully-periodic program after the hidden-'
            'halo refactor')

    def test_no_halo_update_for_non_periodic(self):
        """A program with no periodic axes (all walls) must NOT emit
        a halo-update subroutine -- there's nothing to wrap."""
        code = _generate(_default_program())  # 1D periodic=false
        assert 'subroutine gelb_halo_update_' not in code, \
            ('non-periodic-only program should not emit halo-update '
             'subroutines (storage halo cells are still allocated for '
             'shape parity, but they stay zero)')


class TestNetCDFSimulationDescription:
    """Tests for simulation description in NetCDF global attributes."""

    def test_description_in_global_attributes(self):
        """Simulation description must be written as a global attribute."""
        code = _generate(_default_program())
        assert "nf90_put_att(gelb_ncid, NF90_GLOBAL, 'description'" in code


# ===================================================================
# 2D multi-region geometry (node-class map with IF guards)
# ===================================================================

def _2d_multi_region_program():
    """A minimal 2D program with two node classes and multi-region geometry."""
    return """
    simulation_description("2D multi-region test");
    global_constants {
        const int N = 16;
    }
    lattices {
        lattice f(2, 1, int, {N, N}, {false, false});
    }
    initializer Init {
        f.out[x, y | 0] = 0;
    }
    dynamic Dyn {
        f.out[x, y | 0] = f.in[x, y | 0];
    }
    gauge Out -> (int val) {
        val = f.in[x, y | 0];
    }
    node_classes {
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }
    geometry {
        nodes[:, :] = BULK;
        nodes[:, 0] = WALL;
        nodes[:, N - 1] = WALL;
    }
    """


def _2d_single_region_program():
    """A minimal 2D program with a single node class."""
    return """
    simulation_description("2D single-region test");
    global_constants {
        const int N = 16;
    }
    lattices {
        lattice f(2, 1, int, {N, N}, {false, false});
    }
    initializer Init {
        f.out[x, y | 0] = 0;
    }
    dynamic Dyn {
        f.out[x, y | 0] = f.in[x, y | 0];
    }
    gauge Out -> (int val) {
        val = f.in[x, y | 0];
    }
    node_classes {
        node_class BULK(Init, Dyn, Out);
    }
    geometry {
        nodes[:, :] = BULK;
    }
    """


def _1d_multi_region_program():
    """A minimal 1D program with two node classes and bounded regions."""
    return """
    simulation_description("1D multi-region test");
    lattices {
        lattice f(1, 1, int, 16, false);
    }
    initializer InitA {
        f.out[x | 0] = 0;
    }
    initializer InitB {
        f.out[x | 0] = 1;
    }
    dynamic DynA {
        f.out[x | 0] = f.in[x | 0];
    }
    dynamic DynB {
        f.out[x | 0] = f.in[x | 0];
    }
    gauge Out -> (int val) {
        val = f.in[x | 0];
    }
    node_classes {
        node_class BULK(InitA, DynA, Out);
        node_class WALL(InitB, DynB, Out);
    }
    geometry {
        nodes[0:7] = BULK;
        nodes[8:15] = WALL;
    }
    """


def _3d_multi_region_program():
    """A minimal 3D program with two node classes and multi-region geometry."""
    return """
    simulation_description("3D multi-region test");
    global_constants {
        const int N = 8;
    }
    lattices {
        lattice f(3, 1, int, {N, N, N}, {false, false, false});
    }
    initializer Init {
        f.out[x, y, z | 0] = 0;
    }
    dynamic Dyn {
        f.out[x, y, z | 0] = f.in[x, y, z | 0];
    }
    gauge Out -> (int val) {
        val = f.in[x, y, z | 0];
    }
    node_classes {
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }
    geometry {
        nodes[:, :, :] = BULK;
        nodes[:, 0, :] = WALL;
        nodes[:, N - 1, :] = WALL;
    }
    """


class TestMultiRegion2D:
    """Tests for 2D multi-region geometry using node-class map with IF guards."""

    def test_nc_map_declared(self):
        """Node-class map array must be declared for multi-region 2D."""
        code = _generate(_2d_multi_region_program())
        assert 'integer :: gelb_nc_map(0:g__nx-1, 0:g__ny-1)' in code

    def test_nc_map_initialized(self):
        """Paint statements must be emitted as gelb_nc_map assignments."""
        code = _generate(_2d_multi_region_program())
        # First paint: all BULK (id=1)
        assert 'gelb_nc_map(:, :) = 1' in code
        # Second paint: bottom wall (id=2)
        assert 'gelb_nc_map(:, 0) = 2' in code
        # Third paint: top wall (id=2)
        assert 'gelb_nc_map(:, 15) = 2' in code

    def test_if_guard_emitted(self):
        """IF guard on gelb_nc_map must appear inside spatial loops."""
        code = _generate(_2d_multi_region_program())
        assert 'if (gelb_nc_map(g_x, g_y) ==' in code

    def test_multiple_dynamics_are_correctly_scoped(self):
        """Each node class's dynamic block must be correctly scoped to
        its own cells -- either via a tight bbox loop (for dense NCs)
        or via an IF guard on ``gelb_nc_map`` (for non-dense NCs).
        """
        code = _generate(_2d_multi_region_program())
        # BULK's bbox is [(0, 15), (1, 14)] -- dense (all interior rows
        # belong to BULK), so its dynamic uses tight y-loops bounded
        # to 1..14 and emits NO IF guard.
        assert 'do g_y = 1, 14' in code, (
            "Expected tight y-loops for the dense BULK interior")
        # WALL's bbox is the full grid [(0, 15), (0, 15)] because it
        # occupies both the top and bottom rows; it is non-dense
        # (32/256 cells) and therefore retains the runtime IF guard.
        assert 'gelb_nc_map(g_x, g_y) == 2' in code, (
            "Expected the non-dense WALL dynamic to retain its "
            "runtime IF guard on gelb_nc_map")

    def test_end_if_before_end_do(self):
        """The IF guard must be closed before the DO loop ends."""
        code = _generate(_2d_multi_region_program())
        lines = code.split('\n')
        # Find lines with 'end if' and 'end do' in the dynamic section
        for i, line in enumerate(lines):
            if 'end if' in line.strip().lower():
                # Next non-blank line should be 'end do'
                for j in range(i + 1, len(lines)):
                    stripped = lines[j].strip().lower()
                    if stripped:
                        assert stripped == 'end do', \
                            f"Expected 'end do' after 'end if', got: {lines[j]}"
                        break
                break

    def test_single_region_no_mask(self):
        """Single-node-class 2D programs must NOT use gelb_nc_map."""
        code = _generate(_2d_single_region_program())
        assert 'gelb_nc_map' not in code

    def test_1d_multi_region_uses_bounded_loops(self):
        """1D multi-region must use bounded DO loops, not IF guards."""
        code = _generate(_1d_multi_region_program())
        # Should have bounded loops for each region
        assert 'do g_x = 0, 7' in code
        assert 'do g_x = 8, 15' in code
        # Should NOT use a node-class map
        assert 'gelb_nc_map' not in code


class TestMultiRegion3D:
    """Tests for 3D multi-region geometry using node-class map with IF guards."""

    def test_nc_map_declared(self):
        """Node-class map array must be declared for multi-region 3D."""
        code = _generate(_3d_multi_region_program())
        assert 'integer :: gelb_nc_map(0:g__nx-1, 0:g__ny-1, 0:g__nz-1)' in code

    def test_nc_map_initialized(self):
        """Paint statements must be emitted as gelb_nc_map assignments."""
        code = _generate(_3d_multi_region_program())
        assert 'gelb_nc_map(:, :, :) = 1' in code
        assert 'gelb_nc_map(:, 0, :) = 2' in code
        assert 'gelb_nc_map(:, 7, :) = 2' in code

    def test_if_guard_emitted(self):
        """IF guard on gelb_nc_map must appear inside spatial loops."""
        code = _generate(_3d_multi_region_program())
        assert 'if (gelb_nc_map(g_x, g_y, g_z) ==' in code

    def test_multiple_dynamics_are_correctly_scoped(self):
        """Each node class's dynamic block must be correctly scoped --
        tight loops for dense NCs, IF guard for non-dense.
        """
        code = _generate(_3d_multi_region_program())
        # BULK's bbox is [(0, 7), (1, 6), (0, 7)] -- dense (interior
        # rows), so its dynamic uses a tight y-loop bounded to 1..6.
        assert 'do g_y = 1, 6' in code, (
            "Expected tight y-loops for the dense BULK interior")
        # WALL's bbox is the full grid because it occupies both y=0
        # and y=N-1; it's non-dense (128/512 cells) and retains its
        # runtime IF guard.
        assert 'gelb_nc_map(g_x, g_y, g_z) == 2' in code, (
            "Expected the non-dense WALL dynamic to retain its "
            "runtime IF guard on gelb_nc_map")

    def test_end_if_before_end_do(self):
        """The IF guard must be closed before the DO loop ends."""
        code = _generate(_3d_multi_region_program())
        lines = code.split('\n')
        for i, line in enumerate(lines):
            if 'end if' in line.strip().lower():
                for j in range(i + 1, len(lines)):
                    stripped = lines[j].strip().lower()
                    if stripped:
                        assert stripped == 'end do', \
                            f"Expected 'end do' after 'end if', got: {lines[j]}"
                        break
                break


class TestRandomIntrinsicCodeGeneration:
    """Test that random() intrinsic generates correct Fortran code."""

    def test_random_emits_seed_init(self):
        """Programs using random() should include PRNG seed initialization."""
        gelb_code = minimal_gelb_program_1d(
            dynamic_content='real r = random();'
        )
        code = _generate(gelb_code)
        assert 'call random_seed(size=gelb_seed_n)' in code
        assert 'call system_clock(count=gelb_clock_count)' in code
        assert 'call random_seed(put=gelb_seed)' in code

    def test_random_emits_wrapper_function(self):
        """Programs using random() should include gelb_random() wrapper."""
        gelb_code = minimal_gelb_program_1d(
            dynamic_content='real r = random();'
        )
        code = _generate(gelb_code)
        assert 'function gelb_random()' in code
        assert 'call random_number(r)' in code

    def test_random_call_in_expression(self):
        """random() should be emitted as gelb_random() in expressions."""
        gelb_code = minimal_gelb_program_1d(
            dynamic_content='real r = random();'
        )
        code = _generate(gelb_code)
        assert 'gelb_random()' in code

    def test_no_random_no_seed(self):
        """Programs without random() should NOT include seed code."""
        gelb_code = minimal_gelb_program_1d()
        code = _generate(gelb_code)
        assert 'gelb_random' not in code
        assert 'random_seed' not in code


# ===================================================================
# Masked node classes
# ===================================================================

def _1d_masked_program():
    """A 1D program with a masked SOLID node class (0 args)."""
    return """
    simulation_description("1D masked test");
    lattices {
        lattice f(1, 1, int, 16, false);
    }
    initializer Init {
        f.out[x | 0] = 0;
    }
    dynamic Dyn {
        f.out[x | 0] = f.in[x | 0];
    }
    gauge Out -> (int val) {
        val = f.in[x | 0];
    }
    node_classes {
        node_class BULK(Init, Dyn, Out);
        node_class SOLID() masked;
    }
    geometry {
        nodes[0:12] = BULK;
        nodes[13:15] = SOLID;
    }
    """


def _2d_masked_program():
    """A 2D program with a masked SOLID node class (0 args)."""
    return """
    simulation_description("2D masked test");
    global_constants {
        const int N = 16;
    }
    lattices {
        lattice f(2, 1, int, {N, N}, {false, false});
    }
    initializer Init {
        f.out[x, y | 0] = 0;
    }
    dynamic Dyn {
        f.out[x, y | 0] = f.in[x, y | 0];
    }
    gauge Out -> (int val) {
        val = f.in[x, y | 0];
    }
    node_classes {
        node_class BULK(Init, Dyn, Out);
        node_class SOLID() masked;
    }
    geometry {
        nodes[:, :] = BULK;
        nodes[5:10, 5:10] = SOLID;
    }
    """


class TestMaskedNodeClasses:
    """Tests for masked node classes in generated Fortran code."""

    def test_masked_emits_ieee_arithmetic(self):
        """Programs with masked nodes must include 'use ieee_arithmetic'."""
        code = _generate(_1d_masked_program())
        assert 'use ieee_arithmetic' in code

    def test_no_ieee_without_masked(self):
        """Programs without masked nodes must NOT include 'use ieee_arithmetic'."""
        code = _generate(_default_program())
        assert 'use ieee_arithmetic' not in code

    @pytest.mark.parametrize("dtype", ["int", "real"])
    def test_masked_emits_nan_init(self, dtype):
        """Missing real outputs use NaN; integer outputs use zero."""
        code = _generate(_1d_masked_program().replace("int val", f"{dtype} val"))
        value = 'ieee_value(0.0d0, ieee_quiet_nan)' if dtype == 'real' else '0'
        assert f'gelb_buf_g_val = {value}' in code
        assert 'gelb_buf_g_val' in code

    def test_masked_no_initializer_loop(self):
        """Masked nodes with no initializer must not emit an initializer loop."""
        code = _generate(_1d_masked_program())
        # The SOLID node class has no initializer, so no "Initializer: ..." comment for it
        assert 'SOLID' not in code.split('Initializer')[0] or \
               'Initializer' not in code or \
               code.count('Initializer:') == 1  # only BULK's initializer

    def test_masked_no_gauge_loop(self):
        """Masked nodes must not emit gauge loops."""
        code = _generate(_1d_masked_program())
        # Only one gauge block should appear (BULK's Out), not SOLID's
        gauge_sections = [l for l in code.split('\n')
                          if 'Gauge:' in l and 'SOLID' not in l]
        solid_gauge = [l for l in code.split('\n')
                       if 'Gauge:' in l and 'SOLID' in l]
        assert len(solid_gauge) == 0

    def test_2d_masked_emits_ieee(self):
        """2D programs with masked nodes must include ieee_arithmetic."""
        code = _generate(_2d_masked_program())
        assert 'use ieee_arithmetic' in code

    @pytest.mark.parametrize("dtype", ["int", "real"])
    def test_2d_masked_emits_nan_init(self, dtype):
        """2D missing outputs follow the same typed initialization."""
        code = _generate(_2d_masked_program().replace("int val", f"{dtype} val"))
        value = 'ieee_value(0.0d0, ieee_quiet_nan)' if dtype == 'real' else '0'
        assert f'gelb_buf_g_val = {value}' in code


# ---------------------------------------------------------------------------
# Explicit-precision real types (real32 / real64)
# ---------------------------------------------------------------------------

def _real32_2d_program():
    """A 2D program using explicit real32 types throughout."""
    return """
    simulation_description("FP32 test");
    global_constants { const int N = 16; const real32 TAU = 0.6; }
    lattices { lattice f(2, 1, real32, {N, N}, {true, true}); }
    initializer Init { f.out[x, y | 0] = 1.0; }
    dynamic Dyn { f.out[x, y | 0] = (f.in[x, y | 0] * TAU); }
    gauge Out -> (real32 val) { val = f.in[x, y | 0]; }
    node_classes { node_class BULK(Init, Dyn, Out); }
    geometry { nodes[:, :] = BULK; }
    """


def _real64_2d_program():
    """A 2D program using explicit real64 types throughout."""
    return """
    simulation_description("FP64 test");
    global_constants { const int N = 16; const real64 TAU = 0.6; }
    lattices { lattice f(2, 1, real64, {N, N}, {true, true}); }
    initializer Init { f.out[x, y | 0] = 1.0; }
    dynamic Dyn { f.out[x, y | 0] = (f.in[x, y | 0] * TAU); }
    gauge Out -> (real64 val) { val = f.in[x, y | 0]; }
    node_classes { node_class BULK(Init, Dyn, Out); }
    geometry { nodes[:, :] = BULK; }
    """


class TestExplicitPrecisionReal32:

    def test_real32_lattice_declaration(self):
        code = _generate(_real32_2d_program())
        assert 'real(4) :: g_f(' in code

    def test_real32_constant_is_a_real_literal_narrowed_at_the_store(self):
        # `const real32 TAU = 0.6`: the literal is `real`, double precision
        # (the manual's alias for real64), spelled d0; the parameter's
        # real(4) type narrows it, so the literal's own kind survives.
        code = _generate(_real32_2d_program())
        assert 'real(4), parameter :: g__t_a_u = real(0.6d0)' in code

    def test_real_literal_stays_double_precision_in_a_real32_program(self):
        # The backend used to pick a "dominant" real kind per program and
        # spell every literal in it, making `real` single precision here.
        code = _generate(_real32_2d_program())
        assert '1.0d0' in code
        assert '1.0e0' not in code and '0.6e0' not in code

    def test_real32_gauge_nan_fill_follows_the_output_type(self):
        # With masked cells the gauge buffers are NaN-filled; the zero the
        # NaN is built from has the output's declared width.
        program = _real32_2d_program().replace(
            "node_class BULK(Init, Dyn, Out); }",
            "node_class BULK(Init, Dyn, Out); node_class WALL() masked; }",
        ).replace("nodes[:, :] = BULK; }", "nodes[:, :] = BULK; nodes[8, :] = WALL; }")
        code = _generate(program)
        assert 'ieee_value(0.0e0, ieee_quiet_nan)' in code

    def test_real32_gauge_buffer_type(self):
        code = _generate(_real32_2d_program())
        assert 'real(4) :: gelb_buf_g_val(' in code

    def test_real32_netcdf_uses_float(self):
        code = _generate(_real32_2d_program())
        assert 'NF90_FLOAT' in code


def _int64_literal_program():
    """A 1D program with an int64 value outside the default integer kind,
    as a constant and in an expression: a native literal must express its
    GeLB value and type, so one outside the default kind carries _8."""
    return """
    simulation_description("int64 literal");
    global_constants { const int BIG = 9007199254740993; }
    lattices { lattice f(1, 1, real, 4, false); }
    initializer Init { f.out[x | 0] = 0.0; }
    dynamic Dyn { f.out[x | 0] = f.in[x | 0] + real(x + 9007199254740993) - real(x + BIG); }
    gauge Out -> (real val) { val = f.in[x | 0]; }
    node_classes { node_class BULK(Init, Dyn, Out); }
    geometry { nodes[:] = BULK; }
    """


class TestIntegerLiteralKind:

    def test_a_literal_outside_the_default_kind_carries_its_kind(self):
        # gfortran rejects a bare 9007199254740993: it does not fit the
        # default integer kind.  Both the parameter and the expression
        # spell it as an integer(8) literal.
        code = _generate(_int64_literal_program())
        assert 'integer(8), parameter :: g__b_i_g = 9007199254740993_8' in code
        assert 'dble((g_x + 9007199254740993_8))' in code
        assert re.search(r'(?<![\w.])9007199254740993(?![\w.])', code) is None

    def test_a_literal_inside_the_default_kind_stays_bare(self):
        code = _generate(_int64_literal_program())
        assert '_8)' not in code.replace('9007199254740993_8)', '')
        assert 'dble((g_x + 9007199254740993_8))' in code

    def test_the_minimum_int64_literal_is_the_negative_maximum_minus_one(self, tmp_path):
        # Its magnitude is not an integer(8) literal, so no native literal
        # spells the value directly.
        # The midware folds `-9223372036854775807 - 1` into one literal,
        # so this goes through gelbc rather than the frontend-only helper.
        from click.testing import CliRunner
        from gelb.gelbc import cli as gelbc_cli
        source = tmp_path / "minimum.gelb"
        source.write_text(_int64_literal_program().replace(
            "real(x + BIG)", "real(x * (-9223372036854775807 - 1))"))
        out = tmp_path / "minimum.f90"
        result = CliRunner().invoke(
            gelbc_cli, [str(source), "--backend", "cpu_fortran_serial", "--output", str(out)])
        assert result.exit_code == 0, result.output
        code = out.read_text()
        assert '(-9223372036854775807_8 - 1_8)' in code
        assert '9223372036854775808' not in code


def _implicit_integers_program():
    """A coordinate, `t` and `Nx` in user expressions are int64 throughout."""
    return """
    simulation_description("implicit integers");
    lattices { lattice f(1, 1, real, 4, false); }
    initializer Init { f.out[x | 0] = 0.0; }
    dynamic Dyn { f.out[x | 0] = f.in[x | 0] + (Nx + t) * 1073741824 + x; }
    gauge Out -> (real val) { val = f.in[x | 0]; }
    node_classes { node_class BULK(Init, Dyn, Out); }
    geometry { nodes[:] = BULK; }
    """


class TestImplicitIntegerWidths:

    def test_coordinates_are_integer_8(self):
        code = _generate(_implicit_integers_program())
        assert 'integer(8) :: g_x' in code
        assert 'integer :: g_x' not in code

    def test_a_collapsed_axis_substitutes_an_int64_literal(self):
        # A one-cell axis has no loop; the coordinate's literal
        # is an int64, so `(x + 2147483647) + 1` does not overflow.
        program = _implicit_integers_program().replace(
            "lattice f(1, 1, real, 4, false)", "lattice f(1, 1, real, 1, false)").replace(
            "(Nx + t) * 1073741824 + x", "((x + 2147483647) + 1)")
        code = _generate(program)
        assert 'dble(((int(0, 8) + 2147483647) + 1))' in code
        assert 'g_f(0, 0, g_f_new)' in code      # in a subscript the literal stays bare

    def test_timestep_and_grid_size_are_widened_where_read(self):
        code = _generate(_implicit_integers_program())
        assert 'dble(((int(g__nx, 8) + int(gelb_timestep, 8)) * 1073741824))' in code
        # Their carriers stay default integers.
        assert 'integer :: gelb_timestep' in code
        assert 'integer, parameter :: g__nx = 4' in code


class TestExplicitPrecisionReal64:

    def test_real64_lattice_declaration(self):
        code = _generate(_real64_2d_program())
        assert 'real(8) :: g_f(' in code

    def test_real64_constant_uses_d0_suffix(self):
        code = _generate(_real64_2d_program())
        assert '0.6d0' in code

    def test_real64_literal_uses_d0_suffix(self):
        code = _generate(_real64_2d_program())
        assert '1.0d0' in code

    def test_real64_netcdf_uses_double(self):
        code = _generate(_real64_2d_program())
        assert 'NF90_DOUBLE' in code


# ---------------------------------------------------------------------------
# Constant overrides (-D NAME=VALUE)
# ---------------------------------------------------------------------------

def _2d_program_with_derived():
    """A 2D program with a constant that depends on another."""
    return """
    simulation_description("Override test");
    global_constants {
        const int N = 16;
        const real TAU = 0.6;
        const real K = (6.28 / N);
    }
    lattices { lattice f(2, 1, real, {N, N}, {true, true}); }
    initializer Init { f.out[x, y | 0] = 1.0; }
    dynamic Dyn { f.out[x, y | 0] = f.in[x, y | 0]; }
    gauge Out -> (real val) { val = f.in[x, y | 0]; }
    node_classes { node_class BULK(Init, Dyn, Out); }
    geometry { nodes[:, :] = BULK; }
    """


def _generate_with_overrides(gelb_code, overrides_dict, **kwargs):
    """Run the pipeline with constant overrides applied."""
    from gelb.frontend.stage1_frontend import (
        get_ast, build_symbols_tables, add_implicit_symbols,
        resolve_all_constants, resolve_ranges, infer_types,
        promote_types, validate_types,
    )
    from gelb.midware.inline_functions import inline_functions
    import gelb.utils.config as config
    config.GELB_SRC_RAW = gelb_code
    ast = get_ast("gelb_program", gelb_code)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    ast = apply_constant_overrides(ast, overrides_dict)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    ast = infer_types(ast)
    ast = promote_types(ast)
    validate_types(ast)
    ast = inline_functions(ast)
    return generate_fortran(ast, **kwargs)


class TestConstantOverrides:

    def test_override_int_constant(self):
        code = _generate_with_overrides(
            _2d_program_with_derived(), {'N': '128'})
        assert 'g__n = 128' in code

    def test_override_real_constant(self):
        code = _generate_with_overrides(
            _2d_program_with_derived(), {'TAU': '0.8'})
        assert '0.8d0' in code

    def test_derived_constant_recomputed(self):
        """Overriding N should propagate to K = 6.28 / N."""
        code = _generate_with_overrides(
            _2d_program_with_derived(), {'N': '256'})
        # K should be recomputed: 6.28 / 256
        assert 'g__n = 256' in code
        # The K value should differ from the default (6.28/16 = 0.3925)
        assert '0.3925' not in code

    def test_grid_size_propagated(self):
        """Overriding N should change Nx/Ny (via g__nx = g__n)."""
        code = _generate_with_overrides(
            _2d_program_with_derived(), {'N': '64'})
        # N is overridden; Nx/Ny reference g__n
        assert 'g__n = 64' in code
        assert 'g__nx = int(g__n)' in code

    def test_multiple_overrides(self):
        code = _generate_with_overrides(
            _2d_program_with_derived(), {'N': '32', 'TAU': '0.9'})
        assert 'g__n = 32' in code
        assert '0.9d0' in code

    def test_override_nonexistent_raises(self):
        from gelb.utils.exceptions import GeLBException
        with pytest.raises(GeLBException) as exc_info:
            _generate_with_overrides(
                _2d_program_with_derived(), {'BOGUS': '5'})
        assert "not declared" in exc_info.value.error

    def test_override_type_mismatch_raises(self):
        from gelb.utils.exceptions import GeLBException
        with pytest.raises(GeLBException) as exc_info:
            _generate_with_overrides(
                _2d_program_with_derived(), {'N': 'hello'})
        assert "Cannot parse" in exc_info.value.error

    def test_parse_overrides_bad_format(self):
        from gelb.utils.exceptions import GeLBException
        with pytest.raises(GeLBException) as exc_info:
            parse_overrides(('NTAU',))
        assert "Invalid override" in exc_info.value.error

    def test_int_to_real_auto_promotion(self):
        """Passing an int value to a real constant should work."""
        code = _generate_with_overrides(
            _2d_program_with_derived(), {'TAU': '1'})
        assert '1.0d0' in code


# ---------------------------------------------------------------------------
# Line-length guard (Fortran 132-char limit)
# ---------------------------------------------------------------------------

def test_no_line_exceeds_132_chars_mrt():
    """D3Q19 MRT with 19x19 constant matrices must wrap correctly."""
    import os
    from gelb.midware.stage2_midware import fold_constants
    from gelb.midware.inline_functions import inline_functions
    mrt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        'examples', 'lbm', '3d', 'poiseuille_flow_3d_mrt.gelb')
    with open(mrt_path) as f:
        gelb_code = f.read()
    ast = get_fully_validated_ast(gelb_code)
    ast = fold_constants(ast)
    ast = inline_functions(ast)
    code = generate_fortran(ast, num_timesteps=10,
                            output_mode='netcdf',
                            output_filename='test.nc')
    for i, line in enumerate(code.split('\n'), 1):
        assert len(line) <= 132, (
            f'Line {i} is {len(line)} chars (max 132):\n  {line[:140]}...')


# ===================================================================
# Regression guards for geometry paint out-of-bounds errors
# ===================================================================

class TestGeometryPaintOutOfBounds:
    """Regression guards for the backend out-of-bounds paint-range
    check.  Before the fix, a paint statement whose upper bound equals
    the grid size (e.g. ``nodes[:, NY-K:NY]`` instead of the correct
    ``nodes[:, NY-K:NY-1]``) produced an opaque Python
    ``IndexError: list assignment index out of range`` with no source
    location.  The backend must now raise a ``GeLBExStencilError``
    whose message clearly identifies the offending range and cites the
    source line.
    """

    _OOB_PROGRAM = """
    simulation_description("OOB paint test");
    global_constants {
        const int NX = 20;
        const int NY = 20;
        const int K = 3;
    }
    lattices { lattice f(2, 1, int, {NX, NY}, {false, false}); }
    initializer Init { f.out[x, y | 0] = 0; }
    dynamic Dyn { f.out[x, y | 0] = f.in[x, y | 0]; }
    gauge G -> (int v) { v = f.in[x, y | 0]; }
    node_classes {
        node_class A(Init, Dyn, G);
        node_class B(Init, Dyn, G);
    }
    geometry {
        nodes[:, :]         = A;
        nodes[:, NY - K:NY] = B;
    }
    """

    _VALID_PROGRAM = """
    simulation_description("valid inclusive paint");
    global_constants {
        const int NX = 20;
        const int NY = 20;
        const int K = 3;
    }
    lattices { lattice f(2, 1, int, {NX, NY}, {false, false}); }
    initializer Init { f.out[x, y | 0] = 0; }
    dynamic Dyn { f.out[x, y | 0] = f.in[x, y | 0]; }
    gauge G -> (int v) { v = f.in[x, y | 0]; }
    node_classes {
        node_class A(Init, Dyn, G);
        node_class B(Init, Dyn, G);
    }
    geometry {
        nodes[:, :]             = A;
        nodes[:, 0:K]           = B;
        nodes[:, NY - K:NY - 1] = B;
    }
    """

    def test_out_of_bounds_raises_stencil_error(self):
        """An out-of-bounds paint range must raise GeLBExStencilError,
        not an opaque IndexError."""
        from gelb.utils.exceptions import GeLBExStencilError
        with pytest.raises(GeLBExStencilError) as exc_info:
            _generate(self._OOB_PROGRAM)
        # The error message must mention the offending dimension
        # and cite the valid range.
        msg = str(exc_info.value)
        assert 'out of bounds' in msg
        assert 'y-range' in msg
        assert '[0, 19]' in msg   # valid range for NY=20

    def test_inclusive_upper_bound_compiles(self):
        """The corrected form using inclusive upper bound (NY - 1)
        must compile cleanly."""
        code = _generate(self._VALID_PROGRAM)
        # Should emit a node-class map with two classes
        assert 'gelb_nc_map' in code

    def test_inclusive_semantics_paint_count(self):
        """``nodes[:, 0:2]`` must paint exactly 3 rows (inclusive)."""
        src = """
        simulation_description("inclusive semantics");
        global_constants { const int N = 10; }
        lattices { lattice f(2, 1, int, {N, N}, {false, false}); }
        initializer Init { f.out[x, y | 0] = 0; }
        dynamic Dyn { f.out[x, y | 0] = f.in[x, y | 0]; }
        gauge G -> (int v) { v = f.in[x, y | 0]; }
        node_classes {
            node_class A(Init, Dyn, G);
            node_class B(Init, Dyn, G);
        }
        geometry {
            nodes[:, :]    = A;
            nodes[:, 0:2]  = B;
        }
        """
        code = _generate(src)
        # GeLB paint ranges are inclusive -- rows 0, 1, and 2 should
        # all be painted as B (Fortran nc_map id 2)
        assert 'gelb_nc_map(:, 0:2) = 2' in code


# ===================================================================
# Regression guards for boundary-aware upstream_dfs clamping
# ===================================================================

class TestUpstreamDfsBoundaryClamping:
    """Regression guards for the boundary-aware clamping of
    ``upstream_dfs`` reads.

    Before the fix, a 1D Neumann BC at the left wall would emit

        g_f_in = (/g_f(0, g_x, ...), g_f(1, (g_x - 1), ...), ...) /)

    inside a ``do g_x = 0, 0`` loop, and gfortran's static bounds
    check would flag ``(g_x - 1) = -1`` as out of bounds.  The read
    was dead in practice (the user immediately overwrote f_1 via the
    BC formula) but it was undefined behaviour and cluttered gfortran
    output with warnings.

    The backend now records which dimension sides each node class is
    painted at (``_nc_boundary_dims``) and wraps the non-periodic
    upstream-read indices in ``max(0, ...)`` / ``min(N - 1, ...)`` on
    the sides where the current node class touches the boundary.
    Interior node classes keep the fast, unclamped path.
    """

    _NEUMANN_1D = """
    simulation_description("1D Neumann boundary");
    global_constants {
        const int GRID = 32;
        const real TAU = 1.25;
        const real OMEGA = 1.0 / TAU;
        const array[real, 3] EX = {0.0, 1.0, -1.0};
        const array[real, 3] W  = {4.0/6.0, 1.0/6.0, 1.0/6.0};
    }
    lattices { lattice f(1, 3, real, GRID, false); }
    initializer Init { f.out[x | :] = W; }
    dynamic CollideAndStream {
        array[real, 3] fIn = upstream_dfs(f, x, EX);
        real T = sum(fIn);
        f.out[x | :] = (1.0 - OMEGA) * fIn + OMEGA * (W * T);
    }
    dynamic LeftNeumann {
        array[real, 3] fIn = upstream_dfs(f, x, EX);
        f.out[x | 0] = fIn[0];
        f.out[x | 2] = fIn[2];
        f.out[x | 1] = fIn[2] + 0.1;
    }
    gauge G -> (real T) { T = sum(f.in[x | :]); }
    node_classes {
        node_class BULK(Init, CollideAndStream, G);
        node_class LEFT(Init, LeftNeumann, G);
        node_class RIGHT(Init, G);
    }
    geometry {
        nodes[:]        = BULK;
        nodes[0]        = LEFT;
        nodes[GRID - 1] = RIGHT;
    }
    """

    def test_boundary_nc_gets_clamped_upstream_read(self):
        """Left-wall upstream read must be wrapped in ``max(0, ...)``."""
        code = _generate(self._NEUMANN_1D)
        # The boundary node class LeftNeumann is a single-point region
        # at x=0, so the backend elides its do-loop entirely and
        # substitutes `g_x` with the literal `0` at every reference
        # site.  The clamp is still emitted -- it becomes
        # `max(0, 0 - 1)`, which gfortran constant-folds to `0`.  The
        # source-level check here is on the unfolded form.
        assert 'max(0, 0 - 1)' in code, (
            "Expected a max(0, 0 - 1) clamp on the elided left-wall "
            "upstream read; got none.  The clamping is still required "
            "for boundary NCs so that gfortran's static bounds check "
            "is satisfied.")

    def test_interior_nc_uses_unclamped_fast_path(self):
        """The bulk (interior) node class must NOT be clamped."""
        code = _generate(self._NEUMANN_1D)
        # The bulk loop spans `do g_x = 1, <GRID-2>` and reads
        # f(1, g_x - 1).  That read should be raw `(g_x - 1)`, not
        # `max(0, g_x - 1)` -- otherwise the fast path pays an extra
        # branch per cell per step.  Check the exact unclamped
        # pattern is present in the generated Fortran.
        assert 'g_f(1, (g_x - 1), g_f_old)' in code, (
            "Expected the interior BULK node class to keep the raw "
            "unclamped upstream read `(g_x - 1)` for the fast path.")

    _NEUMANN_2D = """
    simulation_description("2D diffusion with boundary NCs");
    global_constants {
        const int N = 16;
        const real TAU = 1.25;
        const real OMEGA = 1.0 / TAU;
        const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0,  0.0, 1.0, -1.0, -1.0,  1.0};
        const array[real, 9] EY = {0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};
        const array[real, 9] W  = {4.0/9.0,
            1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
            1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0};
    }
    lattices { lattice f(2, 9, real, {N, N}, {false, false}); }
    initializer Init { f.out[x, y | :] = W; }
    dynamic Bulk {
        array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
        real T = sum(fIn);
        f.out[x, y | :] = (1.0 - OMEGA) * fIn + OMEGA * (W * T);
    }
    dynamic WallDyn {
        array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
        f.out[x, y | :] = fIn;
    }
    gauge G -> (real T) { T = sum(f.in[x, y | :]); }
    node_classes {
        node_class BULK(Init, Bulk, G);
        node_class WALL(Init, WallDyn, G);
    }
    geometry {
        nodes[:, :]     = BULK;
        nodes[0, :]     = WALL;
        nodes[N - 1, :] = WALL;
        nodes[:, 0]     = WALL;
        nodes[:, N - 1] = WALL;
    }
    """

    def test_nd_boundary_nc_has_clamped_reads(self):
        """In 2D, the WALL node class touches all four non-periodic
        boundaries, so its upstream reads must be clamped on both x
        and y axes."""
        code = _generate(self._NEUMANN_2D)
        # WALL touches the low and high boundary on both x and y.
        # Therefore negative-direction reads in WALL get clamped
        # with max(0, ...) and positive-direction reads with
        # min(g__nx - 1, ...) / min(g__ny - 1, ...).
        assert 'max(0, g_x - 1)' in code
        assert 'max(0, g_y - 1)' in code
        assert 'min(g__nx - 1, g_x + 1)' in code
        assert 'min(g__ny - 1, g_y + 1)' in code


# ===================================================================
# Spatial loop elision (coordinate-literal substitution)
# ===================================================================

def _extract_block(code, marker):
    """Return the text from ``marker`` to the next block delimiter.

    Block delimiters are either a ``! ---`` (dynamic/gauge sub-section)
    or ``! ====`` (top-level section) line.  Used by the loop-elision
    tests below so their assertions only see the target block and
    not bleed into adjacent blocks.
    """
    idx = code.index(marker)
    # Start after the marker's own line
    next_line_start = code.index('\n', idx) + 1
    # Find the next delimiter
    rest = code[next_line_start:]
    delims = []
    for d in ('! ---', '! ===='):
        j = rest.find(d)
        if j != -1:
            delims.append(j)
    if not delims:
        return code[idx:]
    end = next_line_start + min(delims)
    return code[idx:end]


class TestSpatialLoopElision:
    """The backend elides do-loops whose bbox collapses to a single
    point along a dimension: every reference to that coordinate is
    rewritten as a literal, no ``do``/``end do`` pair is emitted for
    that dim, and the surrounding ``!$omp parallel do`` directive is
    dropped when zero dims remain active.  For dense bboxes (every
    cell inside the bbox belongs to the node class), the runtime
    ``if (gelb_nc_map == nc_id)`` guard is also dropped since the
    tight loops already cover exactly the right cells.
    """

    _1D_LEFT_WALL = """
    simulation_description("1D left wall single-point region");
    global_constants {
        const int N = 32;
        const array[real, 3] W = {4.0/6.0, 1.0/6.0, 1.0/6.0};
    }
    lattices { lattice f(1, 3, real, N, false); }
    initializer Init { f.out[x | :] = W; }
    dynamic Bulk { f.out[x | :] = f.in[x | :]; }
    dynamic Left { f.out[x | 1] = 0.5; }
    gauge G -> (real T) { T = sum(f.in[x | :]); }
    node_classes {
        node_class BULK(Init, Bulk, G);
        node_class LEFT(Init, Left, G);
    }
    geometry {
        nodes[:] = BULK;
        nodes[0] = LEFT;
    }
    """

    def test_1d_single_point_region_has_no_do_loop(self):
        """A ``nodes[0] = LEFT`` single-point region must emit the
        block body without any surrounding ``do g_x = ...``.
        """
        code = _generate(self._1D_LEFT_WALL)
        # The LEFT dynamic block writes f.out[x | 1] = 0.5 -- check
        # that the emitted form uses literal 0 for x (not g_x).
        assert 'g_f(1, 0, g_f_new) = 0.5' in code, (
            "Expected LEFT block to emit a literal-coordinate write "
            "g_f(1, 0, g_f_new) = 0.5 without a surrounding do-loop.")

    def test_1d_bulk_uses_tight_loop(self):
        """The BULK region after LEFT was painted at x=0 must use a
        tight loop starting at x=1, not at x=0.
        """
        code = _generate(self._1D_LEFT_WALL)
        assert 'do g_x = 1, 31' in code, (
            "Expected BULK bulk loop to be tightly bounded to x=1..31 "
            "after LEFT claimed x=0.")

    _2D_BOTTOM_WALL = """
    simulation_description("2D bottom-wall line region");
    global_constants {
        const int NX = 32;
        const int NY = 16;
    }
    lattices { lattice f(2, 1, int, {NX, NY}, {false, false}); }
    initializer Init { f.out[x, y | 0] = x + y; }
    dynamic Bulk { f.out[x, y | 0] = f.in[x, y | 0] + 1; }
    dynamic Bot  { f.out[x, y | 0] = 42; }
    gauge G -> (int val) { val = f.in[x, y | 0]; }
    node_classes {
        node_class BULK(Init, Bulk, G);
        node_class BOT(Init, Bot, G);
    }
    geometry {
        nodes[:, :] = BULK;
        nodes[:, 0] = BOT;
    }
    """

    def test_2d_line_region_partial_elision(self):
        """A ``nodes[:, 0] = BOT`` line region must elide the g_y loop
        (y=0 literal substituted) but keep the g_x loop.  The bbox is
        dense (all 32 cells at y=0 belong to BOT), so no IF guard.
        """
        code = _generate(self._2D_BOTTOM_WALL)
        excerpt = _extract_block(code, '! --- Dynamic: Bot')
        # g_x loop must still be there (full width)
        assert 'do g_x = 0, 31' in excerpt, (
            "Expected BOT to keep its full-width g_x loop")
        # g_y loop MUST be absent (elided to y=0)
        assert 'do g_y' not in excerpt, (
            "Expected BOT's g_y loop to be elided (single-point dim)")
        # The assignment should use literal 0 for y
        assert 'g_f(0, g_x, 0, g_f_new) = 42' in excerpt, (
            "Expected BOT's write to use literal y=0")
        # No IF guard (dense bbox)
        assert 'if (gelb_nc_map' not in excerpt, (
            "Expected BOT (dense bbox) to have no IF guard")

    def test_2d_line_region_initializer_also_elided(self):
        """Initializer loops also benefit from elision -- a line-region
        NC must have its y-dim elided when painted at y=0.
        """
        code = _generate(self._2D_BOTTOM_WALL)
        # Both BULK and BOT use the same Init block; the second
        # Initializer emission with label "(BOT" is the one we want.
        first = code.index('Initializer: Init')
        second_marker_pos = code.index('Initializer: Init', first + 1)
        # Extract from the second occurrence to the next delimiter
        excerpt = _extract_block(
            code, code[second_marker_pos - 10:second_marker_pos + 30])
        # Elided y: no `do g_y`, literal 0 in the index
        assert 'do g_y' not in excerpt, (
            "Expected BOT's initializer y-loop to be elided")
        # The init body `f.out[x, y | 0] = x + y` should emit with
        # g_y -> 0, an int64 where a user expression reads it, on a
        # collapsed axis too: `(g_x + int(0, 8))`
        assert '(g_x + int(0, 8))' in excerpt, (
            "Expected the init body to use g_y → 0 substitution: "
            "(g_x + int(0, 8))")

    _2D_CORNER = """
    simulation_description("2D corner single-point region");
    global_constants {
        const int N = 8;
    }
    lattices { lattice f(2, 1, int, {N, N}, {false, false}); }
    initializer Init { f.out[x, y | 0] = 0; }
    dynamic Bulk { f.out[x, y | 0] = f.in[x, y | 0] + 1; }
    dynamic Corner { f.out[x, y | 0] = 99; }
    gauge G -> (int val) { val = f.in[x, y | 0]; }
    node_classes {
        node_class BULK(Init, Bulk, G);
        node_class CORNER(Init, Corner, G);
    }
    geometry {
        nodes[:, :] = BULK;
        nodes[0, 0] = CORNER;
    }
    """

    def test_2d_corner_region_has_no_loops_at_all(self):
        """A ``nodes[0, 0] = CORNER`` single-point 2D region must emit
        the block body with zero do-loops -- both dims elided to
        literal 0.
        """
        code = _generate(self._2D_CORNER)
        excerpt = _extract_block(code, '! --- Dynamic: Corner')
        assert 'do g_x' not in excerpt
        assert 'do g_y' not in excerpt
        # The assignment should be a single line with literal (0, 0)
        assert 'g_f(0, 0, 0, g_f_new) = 99' in excerpt, (
            "Expected the corner write to use literal (0, 0) coords")

    def test_2d_non_dense_retains_if_guard(self):
        """A WALL that is painted at both y=0 and y=N-1 has a
        non-dense bbox (full grid) and therefore MUST retain its
        runtime IF guard.
        """
        code = _generate(_2d_multi_region_program())
        # WALL is nc_id=2 in the test program
        assert 'gelb_nc_map(g_x, g_y) == 2' in code

    def test_2d_dense_bulk_drops_if_guard(self):
        """The BULK interior of a 2D channel (non-wall cells) has a
        dense bbox and drops its IF guard entirely.
        """
        code = _generate(_2d_multi_region_program())
        excerpt = _extract_block(code, '! --- Dynamic: Dyn (BULK')
        # BULK dynamic uses tight y-loops (1..14) and no IF guard
        assert 'do g_y = 1, 14' in excerpt
        assert 'if (gelb_nc_map' not in excerpt

    def test_1d_single_point_gauge_buffer_uses_literal_index(self):
        """A single-point region's gauge buffer fill must use the
        literal coordinate (0) instead of the loop variable (g_x),
        since the do-loop is elided.
        """
        code = _generate(self._1D_LEFT_WALL)
        excerpt = _extract_block(code, '! --- Gauge: G (nodes 0..0)')
        assert 'gelb_buf_g__t(0)' in excerpt, (
            "Expected gauge buffer fill to use literal 0 for the "
            "elided x coordinate, not g_x.  Got:\n" + excerpt)

    def test_2d_corner_gauge_buffer_uses_literal_indices(self):
        """A 2D single-point region's gauge buffer fill must use
        literal coordinates (0, 0) instead of (g_x, g_y).
        """
        code = _generate(self._2D_CORNER)
        excerpt = _extract_block(code, '! --- Gauge: G (CORNER')
        assert 'gelb_buf_g_val(0, 0)' in excerpt, (
            "Expected gauge buffer fill to use literal (0, 0) for the "
            "elided x,y coordinates.  Got:\n" + excerpt)
