#!/usr/bin/env python3

from abc import ABC, abstractmethod
from gelb.gelb_ast import SymbolReference


class Node_N(ABC):
    """
    Base class (for all GeLB AST Node-types)
    """
    def __init__(self, code_range):
        self.code_range = code_range

    @abstractmethod
    def __str__(self):
        pass

    def get_children_names(self):
        return [
            field for field in dir(self) if not (
                    field.startswith('_') or
                    field.startswith('code_range') or
                    field.startswith('get_children') or
                    field.startswith('iterate_over_ast_fields') or
                    field.startswith('get_referenced_symbols') or
                    field.startswith('replace_symbol_references') or
                    field.startswith('is_terminal_node') or
                    field.startswith('append') or  # from List_N
                    # exclude the symbol-table
                    field.startswith('symbol_defs')
            )
        ]

    def get_children(self):
        # special treatment for List_N
        if isinstance(self, List_N):
            return self.elements
        else:
            return [
                getattr(self, field) for field in self.get_children_names()
            ]

    def get_referenced_symbols(self):
        result = set()
        # recursive descent
        for child in self.get_children():
            if child is not None:
                result |= child.get_referenced_symbols()
        return result

    def replace_symbol_references(self, symbol_name, replacement):
        # recursive descent
        for child_name in self.get_children_names():
            child = getattr(self, child_name)
            if child is None:  # Handle None fields (e.g., in Range_N)
                continue
            if isinstance(child, Identifier_N):
                if child.name == symbol_name:
                    self.__setattr__(child_name, replacement)
            else:
                if isinstance(child, Node_N):
                    child.replace_symbol_references(
                        symbol_name, replacement
                    )

    def is_terminal_node(self):
        """
        By definition, a terminal AST node does not have any children
        which are themselves AST Nodes.
        """
        for child in self.get_children():
            if child is not None and isinstance(child, Node_N):
                return False
        return True

    # def accept(self, visitor):
    #     raise NotImplementedError()

    # @abstractmethod
    # def eval(self):
    #     pass


class List_N(Node_N):
    """
    Wrapper for Python lists, with some GeLB-related functionality.

    Used in various places throughout the GeLB AST.
    """
    def __init__(self, code_range):
        super().__init__(code_range)  # pass code_range to superclass
        self.elements = []

    def append(self, element):
        self.elements.append(element)

    def __iter__(self):
        # return an iterator over the elements list
        return iter(self.elements)

    def __getitem__(self, i):
        return self.elements[i]

    def __len__(self):
        return len(self.elements)

    def __setitem__(self, key, value):
        self.elements[key] = value

    def __str__(self):
        return f"(List {' '.join(f'{e}' for e in self.elements)})"


class Program_N(Node_N):
    """
    Represents the root AST node for a GeLB program.
    """
    def __init__(self, code_range):
        super().__init__(code_range)
        self.simulation_description = None
        self.global_constants = None
        self.lattices = None
        self.initializers = None
        self.dynamics = None
        self.gauges = None
        # self.functions = None
        self.node_classes = None
        self.geometry = None
        # symbol_defs table (built after AST construction)
        self.symbol_defs = None

    def __str__(self):
        result = (
            f"(Program"
            f" {str(self.simulation_description)}"
        )
        if self.global_constants is not None:
            result += f" {str(self.global_constants)}"
        result += f" {str(self.lattices)}"
        result += f" {str(self.initializers)}"
        result += f" {str(self.dynamics)}"
        result += f" {str(self.gauges)}"
        result += f" {str(self.node_classes)}"
        result += f" {str(self.geometry)}"
        result += ")"
        return result


class Stmt_N(Node_N):
    """Base-class for all types of GeLB statements."""
    @abstractmethod
    def __str__(self):
        pass


class Expr_N(Node_N):
    """Base-class for all types of GeLB expression-elements."""
    @abstractmethod
    def __str__(self):
        pass


class SetSimulationDescriptionStmt_N(Stmt_N):
    """
    Represents an instruction to set the simulation's description.

    Example of corresponding code:

    simulation_description(
    "This is
    a test"
    );

    NOTE: The description may be a multi-line string.
    """
    def __init__(self, code_range, description):
        super().__init__(code_range)
        self.description = description

    def __str__(self):
        return f"(SetSimulationDescriptionStmt {self.description})"


class Block_N(Node_N):
    """
    Base-class for larger AST sub-trees.

    All derived classes have a list of statements, enclosed within curly
    braces (with a preamble which depends on the specific type of block).
    """
    def __init__(self, code_range, stmts):
        super().__init__(code_range)
        self.stmts = stmts
        self.symbol_defs = None

    @abstractmethod
    def __str__(self):
        pass


class GlobalConstantsBlock_N(Block_N):
    """
    Represents the block of global constants.

    The constants defined within this block are visible in all other blocks.
    """
    def __str__(self):
        return (
            f"(GlobalConstantsBlock {' '.join(f'{e}' for e in self.stmts)})"
        )


class LatticesBlock_N(Block_N):
    """
    Represents the block (one per program) of lattice-instantiations.
    """
    def __str__(self):
        return (
            f"(LatticesBlock {' '.join(f'{e}' for e in self.stmts)})"
        )


class LatticeInstaStmt_N(Node_N):
    """
    Represents a lattice-instantiation statement.

    TODO (validation): only allow inside LatticesBlock_N
    """
    def __init__(self, code_range, name, d, q, df_type, grid_size, periodicity):
        super().__init__(code_range)
        self.name = name
        self.d = d
        self.q = q
        self.df_type = df_type
        self.grid_size = grid_size      # NEW: grid dimensions
        self.periodicity = periodicity  # NEW: periodicity

    def __str__(self):
        return (
            f"(LatticeInstaStmt {self.name} {self.d} {self.q} {self.df_type} {self.grid_size} {self.periodicity})"
        )


class NodeClassesBlock_N(Block_N):
    """
    Represents the block (one per program) of node-classes.
    """
    def __str__(self):
        return (
            f"(NodeClassesBlock {' '.join(f'{e}' for e in self.stmts)})"
        )


class NodeClassInstaStmt_N(Node_N):
    """
    Represents a node-class-instantiation statement.

    TODO (validation): only allow inside NodeClassesBlock_N
    TODO (GeLB-v1): allow multiple {initializers, dynamics, gauges}
    """
    def __init__(self, code_range, name, initializer, dynamic, gauge):
        super().__init__(code_range)
        self.name = name
        self.initializer = initializer
        self.dynamic = dynamic
        self.gauge = gauge

    def __str__(self):
        return (
            f"(NodeClassInstaStmt"
            f" {self.name}"
            f" {self.initializer}"
            f" {self.dynamic}"
            f" {self.gauge})"
        )


class InitializerBlock_N(Block_N):
    """
    Represents an initializer-block (one or more per program).
    """
    def __init__(self, code_range, name, stmts):
        super().__init__(code_range, stmts)
        self.name = name

    def __str__(self):
        return (
            f"(Initializer"
            f" {self.name}"
            f" {' '.join(f'{e}' for e in self.stmts)})"
        )


class DynamicBlock_N(Block_N):
    """
    Represents a dynamic-block (one or more per program).
    """
    def __init__(self, code_range, name, stmts):
        super().__init__(code_range, stmts)
        self.name = name

    def __str__(self):
        return (
            f"(Dynamic"
            f" {self.name}"
            f" {' '.join(f'{e}' for e in self.stmts)})"
        )


class GaugeBlock_N(Block_N):
    """
    Represents a gauge-block (one or more per program).
    """
    def __init__(self, code_range, name, outputs, stmts):
        super().__init__(code_range, stmts)
        self.name = name
        self.outputs = outputs

    def __str__(self):
        return (
            f"(Gauge"
            f" {self.name}"
            f" {' '.join(f'{e}' for e in self.outputs)}"
            f" {' '.join(f'{e}' for e in self.stmts)})"
        )


class GeometryBlock_N(Block_N):
    """
    Represents the block (one per program) of node-painting statements.
    """
    def __init__(self, code_range, stmts):
        super().__init__(code_range, stmts)

    def __str__(self):
        return (
            f"(GeometryBlock"
            f" {' '.join(f'{e}' for e in self.stmts)}"
            f")"
        )


class Identifier_N(Expr_N):
    """
    Represents an identifier.
    """
    def __init__(self, code_range, name):
        super().__init__(code_range)
        self.name = name

    def __str__(self):
        return f"(Identifier {self.name})"

    def get_referenced_symbols(self):
        result = set()
        result.add(
            SymbolReference.SymbolReference(self.name, self.code_range)
        )
        return result


class Range_N(Node_N):
    """
    Represents an index-range.
    """
    def __init__(self, code_range, low, high):
        super().__init__(code_range)
        self.low = low
        self.high = high

    def __str__(self):
        low_repres = self.low if self.low else "(RangePlaceholder Min)"
        high_repres = self.high if self.high else "(RangePlaceholder Max)"
        return f"(Range {low_repres} {high_repres})"


class RectSel_N(Expr_N):
    """
    Base-class for rectangular selections of elements.
    """
    def __init__(self, code_range, element_ranges):
        super().__init__(code_range)
        self.element_ranges = element_ranges

    def __getitem__(self, i):
        return self.element_ranges[i]

    def __len__(self):
        return len(self.element_ranges)

    @abstractmethod
    def __str__(self):
        pass


class RectSelOfLatticeDFs_N(RectSel_N):
    """
    Base-class for rectangular selection of lattice IN/OUT DFs.

    NOTE: Last element in self.element_ranges represents the DFs-range.
    """
    def __init__(self, code_range, lattice_name, element_ranges):
        super().__init__(code_range, element_ranges)
        self.lattice_name = lattice_name

    @abstractmethod
    def __str__(self):
        pass


class RectSelOfLatticeInDFs_N(RectSelOfLatticeDFs_N):
    """
    Rectangular selection of lattice IN DFs.

    NOTE: Last element in self.element_ranges represents the DFs-range.
    """
    def __str__(self):
        return (
            f"(RectSelOfLatticeInDFs"
            f" {self.lattice_name}"
            f" {' '.join(f'{e}' for e in self.element_ranges)})"
        )


class RectSelOfLatticeOutDFs_N(RectSelOfLatticeDFs_N):
    """
    Rectangular selection of lattice OUT DFs.

    NOTE: Last element in self.element_ranges represents the DFs-range.
    """
    def __str__(self):
        return (
            f"(RectSelOfLatticeOutDFs"
            f" {self.lattice_name}"
            f" {' '.join(f'{e}' for e in self.element_ranges)})"
        )


class RectSelOfArrayElems_N(RectSel_N):
    """
    Rectangular selection of array elements.
    """
    def __init__(self, code_range, array_name, element_ranges):
        super().__init__(code_range, element_ranges)
        self.array_name = array_name

    def __str__(self):
        return (
            f"(RectSelOfArrayElems"
            f" {self.array_name}"
            f" {' '.join(f'{e}' for e in self.element_ranges)})"
        )


class ArrayDataType_N(Node_N):
    """
    Represents all computational data types (scalars and arrays).
    Scalars are represented as 0-dimensional arrays with empty List_N shape.
    """
    def __init__(self, code_range, element_dtype, shape):
        super().__init__(code_range)
        self.element_dtype = element_dtype
        self.shape = shape  # might be either Array1DLiteral_N or IntLiteral_N

    def __str__(self):
        return (
            f"(ArrayDataType {self.element_dtype} {self.shape})"
        )

    def get_children(self):
        # Only return shape as child since element_dtype is a string
        # and doesn't have get_referenced_symbols method
        return {self.shape}


class StringType_N(Node_N):
    """
    AST node representing the string type for metadata contexts.
    This is separate from the computational type system (ArrayDataType_N).
    
    Used only for:
    - simulation_description("text") statements
    - Future string metadata contexts
    
    NOT used for:
    - Expressions or computations
    - Type promotion or validation
    - Array/scalar type relationships
    """
    def __init__(self, code_range):
        super().__init__(code_range)
    
    def __str__(self):
        return "(StringType)"
    
    def __repr__(self):
        return f"StringType_N({self.code_range})"
    
    def get_children(self):
        return set()


class BinaryExpr_N(Expr_N):
    """
    Base-class for all GeLB binary expressions.
    """
    def __init__(self, code_range, left, right):
        super().__init__(code_range)
        self.left = left
        self.right = right

    @abstractmethod
    def __str__(self):
        pass


class Mul_N(BinaryExpr_N):
    """
    Represents a multiplication (*) binary expression.
    """
    def __str__(self):
        return f"(Mul {self.left} {self.right})"


class Div_N(BinaryExpr_N):
    """
    Represents a division (/) binary expression.
    """
    def __str__(self):
        return f"(Div {self.left} {self.right})"


class Add_N(BinaryExpr_N):
    """
    Represents an addition (+) binary expression.
    """
    def __str__(self):
        return f"(Add {self.left} {self.right})"


class Sub_N(BinaryExpr_N):
    """
    Represents a subtraction (-) binary expression.
    """
    def __str__(self):
        return f"(Sub {self.left} {self.right})"


class Pow_N(BinaryExpr_N):
    """
    Represents a raise-to-power (^) binary expression.
    """
    def __str__(self):
        return f"(Pow {self.left} {self.right})"


# Comparison operators
class Less_N(BinaryExpr_N):
    """
    Represents a less-than (<) comparison expression.
    """
    def __str__(self):
        return f"(Less {self.left} {self.right})"


class Greater_N(BinaryExpr_N):
    """
    Represents a greater-than (>) comparison expression.
    """
    def __str__(self):
        return f"(Greater {self.left} {self.right})"


class LessEqual_N(BinaryExpr_N):
    """
    Represents a less-than-or-equal (<=) comparison expression.
    """
    def __str__(self):
        return f"(LessEqual {self.left} {self.right})"


class GreaterEqual_N(BinaryExpr_N):
    """
    Represents a greater-than-or-equal (>=) comparison expression.
    """
    def __str__(self):
        return f"(GreaterEqual {self.left} {self.right})"


class Equal_N(BinaryExpr_N):
    """
    Represents an equality (==) comparison expression.
    """
    def __str__(self):
        return f"(Equal {self.left} {self.right})"


class NotEqual_N(BinaryExpr_N):
    """
    Represents a not-equal (!=) comparison expression.
    """
    def __str__(self):
        return f"(NotEqual {self.left} {self.right})"


# Logical operators
class And_N(BinaryExpr_N):
    """
    Represents a logical AND (&&) expression.
    """
    def __str__(self):
        return f"(And {self.left} {self.right})"


class Or_N(BinaryExpr_N):
    """
    Represents a logical OR (||) expression.
    """
    def __str__(self):
        return f"(Or {self.left} {self.right})"


class UnaryExpr_N(Expr_N):
    """
    Base-class for all GeLB unary expressions.
    """
    def __init__(self, code_range, value):
        super().__init__(code_range)
        self.value = value

    @abstractmethod
    def __str__(self):
        pass


class NotExpr_N(UnaryExpr_N):
    """
    Represents a logical negation (not) unary expression.
    """
    def __str__(self):
        return f"(NotExpr {self.value})"


class UnaryMinusExpr_N(UnaryExpr_N):
    """
    Represents an arithmetic negation (-) unary expression.

    NOTE: This is how negative numbers are represented in GeLB (since the
    lexer only knows about positive numbers).
    """
    def __str__(self):
        return f"(UnaryMinusExpr {self.value})"


class TypePromotionNode_N(Expr_N):
    """
    Represents an implicit type promotion in the AST.
    
    This node wraps an expression that needs to be implicitly promoted
    to a different type. It makes type conversions explicit in the AST,
    which helps with code generation and debugging.
    
    Examples:
        int → real: TypePromotionNode_N(IntLiteral_N(5), ArrayDataType_N("real", List_N()))
        bool → int: TypePromotionNode_N(BoolLiteral_N(true), ArrayDataType_N("int", List_N()))
    """
    def __init__(self, code_range, expr, target_type):
        super().__init__(code_range)
        self.expr = expr  # Original expression to be promoted
        self.target_type = target_type  # Type to promote to
        # The inferred type of a promotion node is its target type
        self.inferred_type = target_type
    
    def get_children(self):
        children = set()
        if self.expr is not None:
            children.add(self.expr)
        if self.target_type is not None:
            children.add(self.target_type)
        return children
    
    def __str__(self):
        return f"(TypePromotion {self.expr} -> {self.target_type})"


class BroadcastNode_N(Expr_N):
    """
    Represents a scalar-to-array broadcast operation in the AST.
    
    This node wraps a scalar expression that needs to be broadcast
    to fill an array of a specific shape. It makes broadcasting explicit
    in the AST, allowing backends to generate efficient code.
    
    Examples:
        Broadcast scalar 1 to array[real, {2, 3}]:
        BroadcastNode_N(IntLiteral_N(1), ArrayDataType_N("real", shape))
        
        In backend, this could generate:
        - Fortran: a(:,:) = 1.0
        - C: memset or loop with single value
        - NumPy: np.full(shape, 1.0)
    """
    def __init__(self, code_range, scalar_expr, target_array_type):
        super().__init__(code_range)
        self.scalar_expr = scalar_expr  # Scalar expression to broadcast
        self.target_array_type = target_array_type  # Target array type with shape
        # The inferred type is the target array type
        self.inferred_type = target_array_type
    
    def get_children(self):
        children = set()
        if self.scalar_expr is not None:
            children.add(self.scalar_expr)
        if self.target_array_type is not None:
            children.add(self.target_array_type)
        return children
    
    def __str__(self):
        return f"(Broadcast {self.scalar_expr} -> {self.target_array_type})"


class IntrinsicFunctionCall_N(Expr_N):
    """
    Represents a call to an intrinsic (built-in) function.
    
    Intrinsic functions are pure functions with no side effects that provide
    essential mathematical operations like sum, dot_prod, etc.
    
    Examples:
        sum(array): IntrinsicFunctionCall_N("sum", [array_expr])
        dot_prod(a, b): IntrinsicFunctionCall_N("dot_prod", [a_expr, b_expr])
    """
    def __init__(self, code_range, function_name, arguments):
        super().__init__(code_range)
        self.function_name = function_name  # str: function name (e.g., "sum", "dot_prod")
        self.arguments = arguments          # List_N of Expr_N: function arguments
    
    def get_children(self):
        children = set()
        if self.arguments is not None:
            children.add(self.arguments)
        return children
    
    def get_referenced_symbols(self):
        result = set()
        if self.arguments is not None:
            result |= self.arguments.get_referenced_symbols()
        return result
    
    def replace_symbol_references(self, old_symbol_name, new_symbol_name):
        if self.arguments is not None:
            self.arguments.replace_symbol_references(old_symbol_name, new_symbol_name)
    
    def __str__(self):
        args_str = ", ".join(str(arg) for arg in self.arguments.elements) if self.arguments else ""
        return f"(IntrinsicCall {self.function_name}({args_str}))"


class Literal_N(Expr_N):
    """
    Base-class for all GeLB literals.
    """
    def __init__(self, code_range, value):
        super().__init__(code_range)
        self.value = value

    @abstractmethod
    def __str__(self):
        pass


class IntLiteral_N(Literal_N):
    """
    Represents an integer literal.
    """
    def __str__(self):
        return f"(IntLiteral {self.value})"

    def get_referenced_symbols(self):
        return set()


class RealLiteral_N(Literal_N):
    """
    Represents a real literal.
    """
    def __str__(self):
        return f"(RealLiteral {self.value})"

    def get_referenced_symbols(self):
        return set()


class BoolLiteral_N(Literal_N):
    """
    Represents a boolean literal.

    NOTE: In GeLB, we use lowercase ('true' & 'false'), unlike Python,
    which capitalizes the first letter ('True' & 'False').
    """
    def __str__(self):
        return f"(BoolLiteral {self.value})"

    def get_referenced_symbols(self):
        return set()


class StringLiteral_N(Literal_N):
    """
    Represents a string literal.

    NOTE: In GeLB-v1, this class is only used for setting the name and the
    description of the simulations.
    """
    def __str__(self):
        return f"(StringLiteral {self.value})"

    def get_children(self):
        return set()


class ArrayLiteral_N(Literal_N):
    """
    Base-class for Array{1,2,3,4}DLiteral_N.

    NOTE: value has a different type for each sub-class.
    """
    @abstractmethod
    def __str__(self):
        pass


class Array1DLiteral_N(ArrayLiteral_N):
    """
    Represents a 1D array literal.

    NOTE: value is a List_N with elements of type Expr_N
    """
    def __str__(self):
        return (
            f"(ArrayLiteral1D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


class Array2DLiteral_N(ArrayLiteral_N):
    """
    Represents a 2D array literal.

    NOTE: value is a List_N with elements of type Array1DLiteral_N.
    """
    def __str__(self):
        return (
            f"(ArrayLiteral2D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


class Array3DLiteral_N(ArrayLiteral_N):
    """
    Represents a 3D array literal.

    NOTE: value is a List_N with elements of type Array2DLiteral_N.
    """
    def __str__(self):
        return (
            f"(ArrayLiteral3D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


class Array4DLiteral_N(ArrayLiteral_N):
    """
    Represents a 4D array literal.

    NOTE: value is a List_N with elements of type Array3DLiteral_N.
    """
    def __str__(self):
        return (
            f"(ArrayLiteral4D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


# class FunctionCall_N(Node_N):
#     """
#     Represents a call of an intrinsic / user-defined function.
#     """
#     def __init__(self, code_range, args_list):
#         super().__init__(code_range)
#         self.args_list = args_list  # TODO: make this a =List_N= !


class ConstantDefinitionStmt_N(Stmt_N):
    """
    Represents a constant-definition statement.

    NOTE: declaration AND immediate assignment!
    """
    def __init__(self, code_range, data_type, name, value):
        super().__init__(code_range)
        self.data_type = data_type
        self.name = name
        self.value = value

    def __str__(self):
        return (
            f"(ConstantDefinitionStmt"
            f" {self.name} {self.data_type} {self.value}"
            f")"
        )


class VariableDeclarationStmt_N(Stmt_N):
    """
    Represents a variable-declaration statement.

    Supports both:
    - Simple declaration: int x;
    - Declaration with initialization: int x = 5;
    """
    def __init__(self, code_range, data_type, name, initial_value=None):
        super().__init__(code_range)
        self.data_type = data_type
        self.name = name
        self.initial_value = initial_value  # Optional initialization expression

    def __str__(self):
        if self.initial_value:
            return f"(VariableDeclarationStmt {self.name} {self.data_type} {self.initial_value})"
        else:
            return f"(VariableDeclarationStmt {self.name} {self.data_type})"


class AssignmentStmt_N(Stmt_N):
    """
    Base-class for all GeLB assignment statements.
    """
    def __init__(self, code_range, lhs, rhs):
        super().__init__(code_range)
        self.lhs = lhs
        self.rhs = rhs

    @abstractmethod
    def __str__(self):
        pass


class PaintNodesStmt_N(AssignmentStmt_N):
    """
    Represents a node-painting statement (@GeometryBlock).

    NOTE: - lhs = spatial_ranges
          - rhs = node_class
    """
    def __str__(self):
        return (
            f"(PaintNodesStmt"
            f" {self.lhs}"
            f" {self.rhs})"
        )


class VariableAssignmentStmt_N(AssignmentStmt_N):
    """
    Represents a variable-assignment statement.
    """
    def __str__(self):
        return (
            f"(VariableAssignmentStmt {self.lhs} {self.rhs})"
        )


class LatticeOutSelectionAssignmentStmt_N(AssignmentStmt_N):
    """
    Represents an assignment to a lattice-out (rectangular) selection.
    """
    def __str__(self):
        return (
            f"(LatticeOutSelectionAssignmentStmt {self.lhs} {self.rhs})"
        )


class ArraySelectionAssignmentStmt_N(AssignmentStmt_N):
    """
    Represents an assignment to an array element or slice selection.
    
    Examples:
        my_array[0] = 42;
        my_array[i:j] = some_expr;
        matrix[x, y] = value;
    """
    def __str__(self):
        return (
            f"(ArraySelectionAssignmentStmt {self.lhs} {self.rhs})"
        )
