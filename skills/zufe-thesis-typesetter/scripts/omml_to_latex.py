#!/usr/bin/env python3
"""把 Word 原生 OMML 公式转换为可审计的 LaTeX 数学表达式。"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MATH_VAL = f"{{{MATH_NS}}}val"

SYMBOLS = {
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ϵ": r"\varepsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ϑ": r"\vartheta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ϖ": r"\varpi",
    "ρ": r"\rho",
    "ϱ": r"\varrho",
    "σ": r"\sigma",
    "ς": r"\varsigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\phi",
    "ϕ": r"\varphi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
    "∞": r"\infty",
    "∂": r"\partial",
    "∇": r"\nabla",
    "±": r"\pm",
    "∓": r"\mp",
    "×": r"\times",
    "÷": r"\div",
    "⋅": r"\cdot",
    "·": r"\cdot",
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "≡": r"\equiv",
    "∝": r"\propto",
    "∈": r"\in",
    "∉": r"\notin",
    "⊂": r"\subset",
    "⊆": r"\subseteq",
    "⊃": r"\supset",
    "⊇": r"\supseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "∧": r"\land",
    "∨": r"\lor",
    "¬": r"\neg",
    "∀": r"\forall",
    "∃": r"\exists",
    "→": r"\to",
    "←": r"\leftarrow",
    "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow",
    "⇔": r"\Leftrightarrow",
    "∅": r"\varnothing",
    "∴": r"\therefore",
    "∵": r"\because",
    "ℝ": r"\mathbb{R}",
    "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}",
    "ℚ": r"\mathbb{Q}",
    "ℂ": r"\mathbb{C}",
    "−": "-",
    "–": "-",
}

NARY_OPERATORS = {
    "∑": r"\sum",
    "∏": r"\prod",
    "∐": r"\coprod",
    "∫": r"\int",
    "∬": r"\iint",
    "∭": r"\iiint",
    "∮": r"\oint",
    "⋃": r"\bigcup",
    "⋂": r"\bigcap",
    "⋁": r"\bigvee",
    "⋀": r"\bigwedge",
}

FUNCTIONS = {
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "sinh",
    "cosh",
    "tanh",
    "log",
    "ln",
    "exp",
    "lim",
    "max",
    "min",
    "sup",
    "inf",
    "det",
    "dim",
    "gcd",
    "ker",
    "arg",
}

PROPERTY_TAGS = {
    "accPr",
    "argPr",
    "barPr",
    "borderBoxPr",
    "boxPr",
    "ctrlPr",
    "dPr",
    "eqArrPr",
    "fPr",
    "funcPr",
    "groupChrPr",
    "limLowPr",
    "limUppPr",
    "mPr",
    "mrPr",
    "naryPr",
    "oMathParaPr",
    "phantPr",
    "radPr",
    "rPr",
    "sPrePr",
    "sSubPr",
    "sSubSupPr",
    "sSupPr",
}


@dataclass(frozen=True)
class OmmlConversion:
    """一次 OMML 转换的结果和完整性证据。"""

    latex: str
    unsupported_tags: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """未知结构为空且转换结果非空时，转换才算完整。"""
        return bool(self.latex.strip()) and not self.unsupported_tags


def local_name(tag: str) -> str:
    """返回不含 XML 命名空间的标签名。"""
    return tag.rsplit("}", 1)[-1]


def property_value(parent: ET.Element | None, property_tag: str, value_tag: str) -> str:
    """读取 OMML 属性节点的 ``m:val``。"""
    if parent is None:
        return ""
    properties = parent.find(f"{{{MATH_NS}}}{property_tag}")
    if properties is None:
        return ""
    value = properties.find(f"{{{MATH_NS}}}{value_tag}")
    return "" if value is None else str(value.get(MATH_VAL, ""))


def property_is_true(parent: ET.Element | None, property_tag: str, value_tag: str) -> bool:
    """读取 OMML on/off 属性。"""
    value = property_value(parent, property_tag, value_tag).strip().lower()
    return value in {"1", "on", "true"}


def math_text(text: str) -> str:
    """把 OMML 数学文本中的 Unicode 符号转换为 LaTeX。"""
    converted = []
    for char in text:
        if char in SYMBOLS:
            replacement = SYMBOLS[char]
            if replacement.startswith("\\") and replacement[1:].isalpha():
                replacement += "{}"
            converted.append(replacement)
        elif char == "\\":
            converted.append(r"\backslash{}")
        elif char in {"%", "#", "&", "$", "_"}:
            converted.append("\\" + char)
        elif char == "{":
            converted.append(r"\{")
        elif char == "}":
            converted.append(r"\}")
        elif char == "~":
            converted.append(r"\sim{}")
        elif char == "^":
            converted.append(r"\hat{}")
        elif char.isspace():
            converted.append(r"\ ")
        else:
            converted.append(char)
    return "".join(converted)


class OmmlConverter:
    """递归转换 OMML，并收集无法证明正确的节点类型。"""

    def __init__(self) -> None:
        self.unsupported_tags: set[str] = set()

    def convert(self, element: ET.Element | None) -> str:
        """转换单个 OMML 节点。"""
        if element is None:
            return ""
        tag = local_name(element.tag)
        dispatch = {
            "r": self._run,
            "f": self._fraction,
            "rad": self._radical,
            "sSub": self._subscript,
            "sSup": self._superscript,
            "sSubSup": self._subsup,
            "sPre": self._prescript,
            "nary": self._nary,
            "d": self._delimiter,
            "func": self._function,
            "eqArr": self._equation_array,
            "m": self._matrix,
            "limLow": self._lower_limit,
            "limUpp": self._upper_limit,
            "acc": self._accent,
            "bar": self._bar,
            "groupChr": self._group_character,
            "borderBox": self._border_box,
            "phant": self._phantom,
        }
        if tag in dispatch:
            return dispatch[tag](element)
        if tag == "t":
            return math_text(element.text or "")
        if tag in PROPERTY_TAGS:
            return ""
        if tag in {
            "oMath",
            "oMathPara",
            "e",
            "num",
            "den",
            "deg",
            "sub",
            "sup",
            "fName",
            "lim",
            "box",
        }:
            return self._children(element)

        nested = self._children(element)
        if element.tag.startswith(f"{{{MATH_NS}}}"):
            self.unsupported_tags.add(tag)
        return nested

    def _children(self, element: ET.Element) -> str:
        return "".join(self.convert(child) for child in element)

    def _argument(self, element: ET.Element, tag: str) -> str:
        return self.convert(element.find(f"{{{MATH_NS}}}{tag}"))

    def _run(self, element: ET.Element) -> str:
        text = "".join(math_text(node.text or "") for node in element.findall(f".//{{{MATH_NS}}}t"))
        style = property_value(element, "rPr", "sty")
        script = property_value(element, "rPr", "scr")
        if not text:
            return ""
        script_command = {
            "roman": r"\mathrm",
            "script": r"\mathcal",
            "fraktur": r"\mathfrak",
            "double-struck": r"\mathbb",
            "doubleStruck": r"\mathbb",
            "sans-serif": r"\mathsf",
            "sansSerif": r"\mathsf",
            "monospace": r"\mathtt",
        }.get(script)
        if script and script_command is None:
            self.unsupported_tags.add(f"runScript:{script}")
        elif script_command is not None:
            text = f"{script_command}{{{text}}}"

        if style in {"b", "bold"}:
            text = rf"\mathbf{{{text}}}"
        elif style in {"bi", "boldItalic"}:
            text = rf"\boldsymbol{{{text}}}"
        elif not script and (style in {"p", "plain"} or property_is_true(element, "rPr", "nor")):
            text = rf"\mathrm{{{text}}}"
        return text

    def _fraction(self, element: ET.Element) -> str:
        numerator = self._argument(element, "num")
        denominator = self._argument(element, "den")
        fraction_type = property_value(element, "fPr", "type") or "bar"
        if fraction_type == "noBar":
            return rf"\genfrac{{}}{{}}{{0pt}}{{}}{{{numerator}}}{{{denominator}}}"
        if fraction_type in {"skw", "lin"}:
            return rf"{{{numerator}}}/{{{denominator}}}"
        return rf"\frac{{{numerator}}}{{{denominator}}}"

    def _radical(self, element: ET.Element) -> str:
        degree = self._argument(element, "deg")
        body = self._argument(element, "e")
        if property_is_true(element, "radPr", "degHide") or not degree:
            return rf"\sqrt{{{body}}}"
        return rf"\sqrt[{degree}]{{{body}}}"

    def _subscript(self, element: ET.Element) -> str:
        return f"{self._argument(element, 'e')}_{{{self._argument(element, 'sub')}}}"

    def _superscript(self, element: ET.Element) -> str:
        return f"{self._argument(element, 'e')}^{{{self._argument(element, 'sup')}}}"

    def _subsup(self, element: ET.Element) -> str:
        return (
            f"{self._argument(element, 'e')}_{{{self._argument(element, 'sub')}}}"
            f"^{{{self._argument(element, 'sup')}}}"
        )

    def _prescript(self, element: ET.Element) -> str:
        return (
            f"{{}}_{{{self._argument(element, 'sub')}}}"
            f"^{{{self._argument(element, 'sup')}}}{self._argument(element, 'e')}"
        )

    def _nary(self, element: ET.Element) -> str:
        character = property_value(element, "naryPr", "chr") or "∫"
        operator = NARY_OPERATORS.get(character)
        if operator is None:
            self.unsupported_tags.add(f"nary:{character}")
            operator = math_text(character)
        result = operator
        subscript = self._argument(element, "sub")
        superscript = self._argument(element, "sup")
        if subscript and not property_is_true(element, "naryPr", "subHide"):
            result += f"_{{{subscript}}}"
        if superscript and not property_is_true(element, "naryPr", "supHide"):
            result += f"^{{{superscript}}}"
        body = self._argument(element, "e")
        return f"{result} {body}".rstrip()

    def _delimiter(self, element: ET.Element) -> str:
        start = property_value(element, "dPr", "begChr") or "("
        end = property_value(element, "dPr", "endChr") or ")"
        separator = property_value(element, "dPr", "sepChr") or ","
        arguments = [self.convert(child) for child in element.findall(f"{{{MATH_NS}}}e")]
        if len(arguments) == 1:
            matrix = element.find(f"{{{MATH_NS}}}e/{{{MATH_NS}}}m")
            if matrix is not None:
                environment = {
                    ("(", ")"): "pmatrix",
                    ("[", "]"): "bmatrix",
                    ("{", "}"): "Bmatrix",
                    ("|", "|"): "vmatrix",
                    ("‖", "‖"): "Vmatrix",
                }.get((start, end))
                if environment:
                    return (
                        rf"\begin{{{environment}}}{self._matrix_rows(matrix)}\end{{{environment}}}"
                    )
        left = {
            "(": r"\left(",
            "[": r"\left[",
            "{": r"\left\{",
            "|": r"\left|",
            "‖": r"\left\|",
            "⟨": r"\left\langle",
            "": r"\left.",
        }.get(start, rf"\left{math_text(start)}")
        right = {
            ")": r"\right)",
            "]": r"\right]",
            "}": r"\right\}",
            "|": r"\right|",
            "‖": r"\right\|",
            "⟩": r"\right\rangle",
            "": r"\right.",
        }.get(end, rf"\right{math_text(end)}")
        return f"{left}{f' {math_text(separator)} '.join(arguments)}{right}"

    def _function(self, element: ET.Element) -> str:
        name = self._argument(element, "fName").strip()
        argument = self._argument(element, "e")
        command = rf"\{name}" if name in FUNCTIONS else name
        return f"{command} {argument}".rstrip()

    def _equation_array(self, element: ET.Element) -> str:
        rows = [self.convert(child) for child in element.findall(f"{{{MATH_NS}}}e")]
        return r"\begin{aligned}" + r" \\ ".join(rows) + r"\end{aligned}"

    def _matrix_rows(self, element: ET.Element) -> str:
        rows = []
        for row in element.findall(f"{{{MATH_NS}}}mr"):
            cells = [self.convert(cell) for cell in row.findall(f"{{{MATH_NS}}}e")]
            rows.append(" & ".join(cells))
        return r" \\ ".join(rows)

    def _matrix(self, element: ET.Element) -> str:
        return rf"\begin{{matrix}}{self._matrix_rows(element)}\end{{matrix}}"

    def _lower_limit(self, element: ET.Element) -> str:
        return f"{self._argument(element, 'e')}_{{{self._argument(element, 'lim')}}}"

    def _upper_limit(self, element: ET.Element) -> str:
        return f"{self._argument(element, 'e')}^{{{self._argument(element, 'lim')}}}"

    def _accent(self, element: ET.Element) -> str:
        character = property_value(element, "accPr", "chr") or "^"
        command = {
            "̂": r"\hat",
            "^": r"\hat",
            "̃": r"\tilde",
            "~": r"\tilde",
            "̄": r"\bar",
            "¯": r"\bar",
            "́": r"\acute",
            "̀": r"\grave",
            "̇": r"\dot",
            "̈": r"\ddot",
            "̆": r"\breve",
            "̌": r"\check",
            "⃗": r"\vec",
            "→": r"\vec",
        }.get(character)
        if command is None:
            self.unsupported_tags.add(f"accent:{character}")
            command = r"\hat"
        return f"{command}{{{self._argument(element, 'e')}}}"

    def _bar(self, element: ET.Element) -> str:
        position = property_value(element, "barPr", "pos") or "top"
        command = r"\underline" if position == "bot" else r"\overline"
        return f"{command}{{{self._argument(element, 'e')}}}"

    def _group_character(self, element: ET.Element) -> str:
        character = property_value(element, "groupChrPr", "chr")
        body = self._argument(element, "e")
        if character == "⏟":
            return rf"\underbrace{{{body}}}"
        if character == "⏞":
            return rf"\overbrace{{{body}}}"
        self.unsupported_tags.add(f"groupChr:{character or 'unknown'}")
        return body

    def _border_box(self, element: ET.Element) -> str:
        return rf"\boxed{{{self._argument(element, 'e')}}}"

    def _phantom(self, element: ET.Element) -> str:
        return rf"\phantom{{{self._argument(element, 'e')}}}"


def convert_omml(element: ET.Element) -> OmmlConversion:
    """转换一个 ``m:oMath`` 或 ``m:oMathPara`` 元素。"""
    converter = OmmlConverter()
    latex = converter.convert(element).strip()
    return OmmlConversion(latex=latex, unsupported_tags=tuple(sorted(converter.unsupported_tags)))
