import ast
import sympy as sp


class InvalidMathAnswer(ValueError):
    pass


class MathValidator:
    """Parse only small arithmetic/polynomial expressions; never eval/sympify user text."""
    def expression(self, text: str) -> sp.Expr:
        if not isinstance(text, str) or not text.strip() or len(text) > 200:
            raise InvalidMathAnswer("답은 200자 이내의 수식이어야 합니다.")
        try:
            tree = ast.parse(text.replace("^", "**"), mode="eval")
        except (SyntaxError, RecursionError) as exc:
            raise InvalidMathAnswer("수식 형식을 확인해주세요. 곱셈은 *로 입력해주세요.") from exc
        if sum(1 for _ in ast.walk(tree)) > 80:
            raise InvalidMathAnswer("수식이 너무 복잡합니다.")

        def bounded(value):
            polynomial = sp.Poly(value, sp.Symbol("x"))
            if polynomial.degree() > 4 or any(abs(int(c)).bit_length() > 256 for c in polynomial.all_coeffs()):
                raise InvalidMathAnswer("수식의 차수나 숫자가 너무 큽니다.")
            return value

        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) <= 10000:
                return sp.Integer(node.value)
            if isinstance(node, ast.Name) and node.id == "x":
                return sp.Symbol("x")
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = visit(node.operand)
                return value if isinstance(node.op, ast.UAdd) else -value
            if isinstance(node, ast.BinOp):
                left, right = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Add):
                    return bounded(left + right)
                if isinstance(node.op, ast.Sub):
                    return bounded(left - right)
                if isinstance(node.op, ast.Mult):
                    return bounded(left * right)
                if isinstance(node.op, ast.Pow) and right.is_Integer and 0 <= right <= 4:
                    return bounded(left ** right)
            raise InvalidMathAnswer("정수, x, +, -, *, 0~4의 정수 지수만 사용할 수 있습니다.")

        try:
            return sp.expand(visit(tree.body))
        except (RecursionError, TypeError) as exc:
            raise InvalidMathAnswer("수식 형식을 확인해주세요.") from exc

    def equivalent(self, answer: str, expected: str) -> bool:
        return sp.expand(self.expression(answer) - self.expression(expected)) == 0

    def matches_task(self, answer: str, expected: str, answer_form: str = "integer") -> bool:
        if not self.equivalent(answer, expected):
            return False
        tree = ast.parse(answer.replace("^", "**"), mode="eval").body
        def monomial(node):
            if isinstance(node, (ast.Constant, ast.Name)):
                return True
            if isinstance(node, ast.UnaryOp):
                return monomial(node.operand)
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Pow)):
                return monomial(node.left) and monomial(node.right)
            return False
        def expanded(node):
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
                return expanded(node.left) and expanded(node.right)
            if isinstance(node, ast.UnaryOp):
                return expanded(node.operand)
            return monomial(node)
        if answer_form == "expanded":
            return expanded(tree)
        if answer_form == "factored":
            if not isinstance(tree, ast.BinOp) or not isinstance(tree.op, ast.Mult):
                return False
            x = sp.Symbol("x")
            return all(sp.Poly(self.expression(ast.unparse(factor)), x).degree() >= 1
                       for factor in (tree.left, tree.right))
        return (isinstance(tree, ast.Constant) and type(tree.value) is int) or (
            isinstance(tree, ast.UnaryOp) and isinstance(tree.operand, ast.Constant)
            and type(tree.operand.value) is int)

    def validate_problem(self, template: str, a: int, b: int, answer: str) -> bool:
        if template == "signed_multiplication":
            expected = str(a * b)
        elif template == "binomial_expansion":
            x = sp.Symbol("x")
            expected = str(sp.expand((x + a) * (x + b)))
        else:
            return False
        try:
            return self.equivalent(answer, expected)
        except InvalidMathAnswer:
            return False
