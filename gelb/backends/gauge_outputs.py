"""NetCDF output layout shared by the native backends."""

from dataclasses import dataclass

from gelb.gelb_ast.ASTNodes import VariableDeclarationStmt_N


@dataclass
class GaugeOutputLayout:
    outputs: list[VariableDeclarationStmt_N]
    partial: bool


def collect_gauge_outputs(gauges):
    """Union the active gauges' outputs, retaining their declaration order.

    A name shared by gauges is one field. A field absent from any active
    class needs initialization before the class-specific gauge sweep.
    """
    outputs = {}
    names_by_class = []
    for gauge in gauges:
        names = set()
        if gauge is not None:
            for decl in gauge.outputs:
                if isinstance(decl, VariableDeclarationStmt_N):
                    name = decl.name.name
                    outputs.setdefault(name, decl)
                    names.add(name)
        names_by_class.append(names)
    if not outputs:
        return None
    return GaugeOutputLayout(
        list(outputs.values()), any(names != outputs.keys() for names in names_by_class))
