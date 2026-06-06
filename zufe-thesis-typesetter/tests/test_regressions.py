#!/usr/bin/env python3
"""Regression tests for DOCX fidelity issues found in real conversions."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import tempfile
import zipfile
from pathlib import Path

from docx import Document


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_tiny_png(path: Path) -> None:
    path.write_bytes(TINY_PNG)


def rewrite_docx_xml(docx_path: Path, replacements: dict[str, str], additions: dict[str, str] | None = None) -> None:
    original = docx_path.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        original_zip = Path(tmp) / "original.docx"
        rewritten_zip = Path(tmp) / "rewritten.docx"
        original_zip.write_bytes(original)
        with zipfile.ZipFile(original_zip, "r") as source, zipfile.ZipFile(rewritten_zip, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename in replacements:
                    data = replacements[info.filename].encode("utf-8")
                target.writestr(info, data)
            for filename, text in (additions or {}).items():
                target.writestr(filename, text.encode("utf-8"))
        docx_path.write_bytes(rewritten_zip.read_bytes())


def test_import_docx_preserves_superscript_runs():
    import_docx = load_module("import_docx")
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("引用")
    ref = paragraph.add_run("1")
    ref.font.superscript = True

    runs = import_docx.run_payload(paragraph)
    assert runs == [
        {
            "index": 1,
            "text": "引用",
            "bold": False,
            "italic": False,
            "superscript": False,
            "subscript": False,
            "font_size_pt": None,
        },
        {
            "index": 2,
            "text": "1",
            "bold": False,
            "italic": False,
            "superscript": True,
            "subscript": False,
            "font_size_pt": None,
        },
    ]


def test_render_chapters_preserves_superscript_and_heading_levels():
    render_chapters = load_module("render_chapters")
    assert render_chapters.block_to_latex(
        {"semantic_role": "heading", "level": 2, "text": "二级标题"}
    ) == "\\section{二级标题}"
    assert render_chapters.block_to_latex(
        {
            "source_type": "paragraph",
            "text": "引用1",
            "runs": [
                {"text": "引用", "superscript": False},
                {"text": "1", "superscript": True},
            ],
        }
    ) == "引用\\textsuperscript{1}\n"
    assert render_chapters.block_to_latex(
        {
            "source_type": "paragraph",
            "runs": [
                {"text": '"产品', "superscript": False},
                {"text": '差异化"', "superscript": False},
            ],
        }
    ) == "``产品差异化''\n"


def test_latex_escape_ascii_double_quotes_and_single_scan():
    common = load_module("common")
    assert common.latex_escape('"产品差异化"') == "``产品差异化''"
    assert common.latex_escape('A&B "test"') == r"A\&B ``test''"
    assert common.latex_escape("“中文引号”") == "“中文引号”"
    assert common.latex_escape("student's") == "student's"
    assert common.latex_escape(r"\alpha {x}") == r"\textbackslash{}alpha \{x\}"


def test_import_docx_preserves_image_anchor_order():
    import_docx = load_module("import_docx")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/input").mkdir(parents=True)
        png = root / "anchor.png"
        write_tiny_png(png)
        document = Document()
        document.add_paragraph("图片前段落")
        document.add_picture(str(png))
        document.add_paragraph("图片后段落")
        docx_path = root / "workspace/input/thesis.docx"
        document.save(docx_path)

        import_docx.extract(root, docx_path)
        thesis = json.loads((root / "workspace/intermediate/thesis.json").read_text(encoding="utf-8"))
        blocks = thesis["source_blocks"]
        before = next(block for block in blocks if block.get("text") == "图片前段落")
        after = next(block for block in blocks if block.get("text") == "图片后段落")
        image = next(block for block in blocks if block.get("source_type") == "image")

        assert before["order"] < image["order"] < after["order"]
        assert image["status"] == "needs_confirmation"
        assert image["asset_status"] == "pending_export"
        assert image["target_slot"] is None
        assert image["evidence"]["docx_media_path"].startswith("word/media/")
        assert image["evidence"]["anchor_paragraph_id"] == "p0002"


def test_export_assets_does_not_mark_image_semantic_position_mapped():
    import_docx = load_module("import_docx")
    export_assets = load_module("export_assets")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/input").mkdir(parents=True)
        png = root / "anchor.png"
        write_tiny_png(png)
        document = Document()
        document.add_paragraph("图片前段落")
        document.add_picture(str(png))
        document.add_paragraph("图片后段落")
        docx_path = root / "workspace/input/thesis.docx"
        document.save(docx_path)

        import_docx.extract(root, docx_path)
        thesis_path = root / "workspace/intermediate/thesis.json"
        export_assets.export_assets(root, docx_path, thesis_path)
        thesis = json.loads(thesis_path.read_text(encoding="utf-8"))
        image = next(block for block in thesis["source_blocks"] if block.get("source_type") == "image")

        assert image["status"] == "needs_confirmation"
        assert image["target_slot"] is None
        assert image["asset_status"] == "exported"
        assert image["asset_output"].startswith("Images/word_media/")
        assert image["render_result"]["kind"] == "asset_extracted"


def test_import_docx_reports_unsupported_features():
    import_docx = load_module("import_docx")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "workspace/input").mkdir(parents=True)
        document = Document()
        document.add_paragraph("正文段落")
        docx_path = root / "workspace/input/thesis.docx"
        document.save(docx_path)

        with zipfile.ZipFile(docx_path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        insertion = (
            '<w:p><w:hyperlink><w:r><w:t>链接文本</w:t></w:r></w:hyperlink></w:p>'
            '<w:p><w:r><m:oMath><m:r><m:t>x=1</m:t></m:r></m:oMath></w:r></w:p>'
            '<w:p><w:ins w:id="1" w:author="tester"><w:r><w:t>修订文本</w:t></w:r></w:ins></w:p>'
            '<w:p><w:r><w:pict><v:textbox><w:txbxContent><w:p><w:r><w:t>文本框</w:t></w:r></w:p></w:txbxContent></v:textbox></w:pict></w:r></w:p>'
        )
        rewrite_docx_xml(
            docx_path,
            {"word/document.xml": document_xml.replace("<w:sectPr", insertion + "<w:sectPr", 1)},
            {
                "word/footnotes.xml": (
                    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:footnote w:id="1"><w:p><w:r><w:t>脚注</w:t></w:r></w:p></w:footnote>'
                    "</w:footnotes>"
                ),
                "word/comments.xml": (
                    '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:comment w:id="1"><w:p><w:r><w:t>批注</w:t></w:r></w:p></w:comment>'
                    "</w:comments>"
                ),
                "word/header1.xml": (
                    '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:p><w:r><w:t>页眉</w:t></w:r></w:p></w:hdr>'
                ),
            },
        )

        import_docx.extract(root, docx_path)
        thesis = json.loads((root / "workspace/intermediate/thesis.json").read_text(encoding="utf-8"))
        features = {feature["type"]: feature for feature in thesis["unsupported_features"]}

        assert features["hyperlink"]["count"] == 1
        assert features["equation_omml"]["count"] == 1
        assert features["tracked_changes"]["count"] == 1
        assert features["textbox"]["count"] == 1
        assert features["footnote_or_endnote"]["count"] == 1
        assert features["comment"]["count"] == 1
        assert features["header_footer"]["count"] == 1
        for feature in features.values():
            assert feature["status"] == "needs_confirmation"
            assert feature["locations"]


def test_flow_b_gate_blocks_unconfirmed_unsupported_features():
    check_flow_b_gate = load_module("check_flow_b_gate")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/basicinfo.tex").write_text("基本信息\n", encoding="utf-8")
        (root / "chapters/mainbody.tex").write_text("\\input{chapters/1_intro}\n", encoding="utf-8")
        (root / "chapters/1_intro.tex").write_text("正文\n", encoding="utf-8")
        (root / "Reference.bib").write_text("% empty\n", encoding="utf-8")
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "counts": {"total_source_blocks": 0},
                    "source_blocks": [],
                    "unsupported_features": [
                        {
                            "type": "equation_omml",
                            "count": 1,
                            "severity": "high",
                            "status": "needs_confirmation",
                            "locations": [{"part": "word/document.xml", "count": 1}],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = check_flow_b_gate.check(root, thesis_path)
        assert result["status"] == "blocked"
        assert any(issue["check"] == "unsupported_feature_confirmation" for issue in result["issues"])


def test_check_env_reports_missing_required_latex_packages():
    check_env = load_module("check_env")
    original_command_exists = check_env.command_exists
    original_kpsewhich_exists = getattr(check_env, "kpsewhich_exists", None)
    try:
        check_env.command_exists = lambda _name: True
        check_env.kpsewhich_exists = lambda filename: filename != "gb7714-2015.bbx"
        result = check_env.check("latex")
    finally:
        check_env.command_exists = original_command_exists
        if original_kpsewhich_exists is not None:
            check_env.kpsewhich_exists = original_kpsewhich_exists

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["tex_package_ctexbook.cls"]["status"] == "passed"
    assert checks["tex_package_biblatex.sty"]["status"] == "passed"
    assert checks["tex_package_gb7714-2015.bbx"]["status"] == "blocked"
    assert result["status"] == "blocked"


def test_prescan_reads_cover_table_metadata_without_report_style_default():
    prescan_docx = load_module("prescan_docx")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        docx_path = root / "cover.docx"
        document = Document()
        document.add_paragraph("专业实践报告")
        table = document.add_table(rows=4, cols=2)
        rows = [
            ("指导教师", "张老师"),
            ("专业名称", "数字经济"),
            ("学院", "经济学院"),
            ("日期", "2026年6月"),
        ]
        for row, (label, value) in zip(table.rows, rows):
            row.cells[0].text = label
            row.cells[1].text = value
        document.save(docx_path)

        result = prescan_docx.prescan(root, docx_path)
        candidates = result["metadata_candidates"]
        assert candidates["report_style"] == "1"
        assert candidates["mentor"] == "张老师"
        assert candidates["major"] == "数字经济"
        assert candidates["college"] == "经济学院"
        assert candidates["date"] == "2026年6月"

        assert prescan_docx.metadata_candidates(["普通论文标题"])["report_style"] == ""


def test_render_basicinfo_blocks_missing_report_style():
    render_basicinfo = load_module("render_basicinfo")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        metadata = root / "metadata.yaml"
        metadata.write_text("thesis_title_cn: 测试题目\n", encoding="utf-8")

        result = render_basicinfo.render(root, metadata, thesis_path=None)
        assert result["status"] == "blocked"
        assert "report_style" in result["missing_fields"]
        assert not (root / "chapters/basicinfo.tex").exists()


def test_render_basicinfo_blocks_unapproved_generated_english():
    render_basicinfo = load_module("render_basicinfo")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        metadata = root / "metadata.yaml"
        metadata.write_text(
            "report_style: 1\n"
            "thesis_title_cn: 测试题目\n",
            encoding="utf-8",
        )
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "metadata": {
                        "abstract_en": "Generated English abstract.",
                        "keywords_en": ["generated", "keywords"],
                        "english_content_source": "generated",
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = render_basicinfo.render(root, metadata, thesis_path)
        assert result["status"] == "blocked"
        assert result["gate"] == "generated_english_requires_confirmation"
        assert not (root / "chapters/basicinfo.tex").exists()

        metadata.write_text(
            "report_style: 1\n"
            "thesis_title_cn: 测试题目\n"
            "allow_generated_english: true\n",
            encoding="utf-8",
        )
        result = render_basicinfo.render(root, metadata, thesis_path)
        assert result["status"] == "passed"


def test_qa_flags_bibtex_and_citation_lint_failures():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/1_intro.tex").write_text(
            r"正文引用 \cite{known,missing}。",
            encoding="utf-8",
        )
        (root / "Reference.bib").write_text(
            "@article{known,\n"
            "  title={A}\n"
            "}\n"
            "@book{known,\n"
            "  title={B}\n"
            "}\n"
            "@misc{broken,\n"
            "  title={Broken}\n",
            encoding="utf-8",
        )
        (root / "workspace/intermediate/thesis.json").write_text("{}", encoding="utf-8")

        checks = {check["name"]: check for check in qa.source_quality_checks(root)}
        assert checks["bibtex_duplicate_keys"]["status"] == "failed"
        assert "known" in checks["bibtex_duplicate_keys"]["detail"]
        assert checks["bibtex_braces_balanced"]["status"] == "failed"
        assert checks["citation_keys_defined"]["status"] == "failed"
        assert "missing" in checks["citation_keys_defined"]["detail"]


def test_render_chapters_blocks_prefix_path_escape():
    render_chapters = load_module("render_chapters")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        thesis_path = root / "workspace/intermediate/thesis.json"
        thesis_path.write_text(
            json.dumps(
                {
                    "source_blocks": [
                        {
                            "id": "p0001",
                            "status": "mapped",
                            "text": "越界正文",
                            "target_slot": "chapters_evil/escape.tex",
                        }
                    ],
                    "structure": {
                        "chapters": [
                            {
                                "title": "bad",
                                "file": "chapters_evil/escape.tex",
                                "block_ids": ["p0001"],
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = render_chapters.render(root, thesis_path, allow_incomplete=False)
        assert result["status"] == "blocked"
        assert not (root / "chapters_evil/escape.tex").exists()


def test_render_basicinfo_supports_thesis_title_abs():
    render_basicinfo = load_module("render_basicinfo")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        metadata = root / "metadata.yaml"
        metadata.write_text(
            "report_style: 1\n"
            "thesis_title_cn: 封面题目\n"
            "thesis_title_abs_cn: 摘要页题目\n",
            encoding="utf-8",
        )
        render_basicinfo.render(root, metadata, thesis_path=None)
        basicinfo = (root / "chapters/basicinfo.tex").read_text(encoding="utf-8")
        assert "\\newcommand{\\thesisTitle}{封面题目}" in basicinfo
        assert "\\newcommand{\\thesisTitleAbs}{摘要页题目}" in basicinfo


def test_build_xelatex_uses_noninteractive_error_flags():
    build = load_module("build")
    xelatex_steps = [command for command in build.COMPILE_CHAIN if command[0] == "xelatex"]
    assert xelatex_steps
    for command in xelatex_steps:
        assert command[:4] == [
            "xelatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
        ]
        assert command[-1] == "main.tex"


def test_render_chapters_table_uses_fixed_font_without_resizebox():
    render_chapters = load_module("render_chapters")
    latex = render_chapters.block_to_latex(
        {
            "source_type": "table",
            "table": {"rows": [["指标", "值"], ["样本", "1"]]},
        }
    )
    assert "\\zihao{5}" in latex
    assert "\\songti" in latex
    assert "\\resizebox" not in latex
    assert "\\begin{tabular}{@{}ll@{}}" in latex


def test_qa_flags_missing_superscript_rendering_and_resizebox():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/1_test.tex").write_text(
            "\\resizebox{\\textwidth}{!}{bad table}\n引用1\n",
            encoding="utf-8",
        )
        thesis = {
            "source_blocks": [
                {
                    "id": "p0001",
                    "status": "rendered",
                    "runs": [
                        {"text": "引用", "superscript": False},
                        {"text": "1", "superscript": True},
                    ],
                }
            ]
        }
        (root / "workspace/intermediate/thesis.json").write_text(
            json.dumps(thesis, ensure_ascii=False),
            encoding="utf-8",
        )
        checks = {check["name"]: check for check in qa.source_quality_checks(root)}
        assert checks["source_table_resizebox_textwidth"]["status"] == "warning"
        assert checks["source_superscript_runs_rendered"]["status"] == "warning"


def test_qa_placeholder_scan_includes_generated_chapter_files():
    qa = load_module("qa")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chapters").mkdir()
        (root / "workspace/intermediate").mkdir(parents=True)
        (root / "chapters/basicinfo.tex").write_text("基本信息\n", encoding="utf-8")
        (root / "chapters/mainbody.tex").write_text(
            "\\input{chapters/1_intro}\n",
            encoding="utf-8",
        )
        (root / "chapters/1_intro.tex").write_text(
            "正文里残留 xxxxxxxxxxxx\n",
            encoding="utf-8",
        )
        (root / "workspace/intermediate/thesis.json").write_text("{}", encoding="utf-8")
        result = qa.qa(root)
        checks = {check["name"]: check for check in result["checks"]}
        assert checks[r"placeholder_xxxxxxxxxxxx"]["status"] == "warning"


if __name__ == "__main__":
    test_import_docx_preserves_superscript_runs()
    test_import_docx_preserves_image_anchor_order()
    test_export_assets_does_not_mark_image_semantic_position_mapped()
    test_import_docx_reports_unsupported_features()
    test_flow_b_gate_blocks_unconfirmed_unsupported_features()
    test_check_env_reports_missing_required_latex_packages()
    test_prescan_reads_cover_table_metadata_without_report_style_default()
    test_render_basicinfo_blocks_missing_report_style()
    test_render_basicinfo_blocks_unapproved_generated_english()
    test_qa_flags_bibtex_and_citation_lint_failures()
    test_render_chapters_preserves_superscript_and_heading_levels()
    test_latex_escape_ascii_double_quotes_and_single_scan()
    test_render_chapters_blocks_prefix_path_escape()
    test_render_basicinfo_supports_thesis_title_abs()
    test_build_xelatex_uses_noninteractive_error_flags()
    test_render_chapters_table_uses_fixed_font_without_resizebox()
    test_qa_flags_missing_superscript_rendering_and_resizebox()
    test_qa_placeholder_scan_includes_generated_chapter_files()
    print("DOCX fidelity regression tests passed")
