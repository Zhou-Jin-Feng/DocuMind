import unittest

from app.core.citations import (
    CITATION_PARSER_VERSION,
    analyze_answer_citations,
    parse_answer_citations,
)


class CitationTests(unittest.TestCase):
    def test_parser_accepts_only_exact_bracketed_markers_and_deduplicates(self):
        text = "[文档2] 文档1 [文档2] [文档10] [文档0] [文档 3]"

        self.assertEqual(parse_answer_citations(text), (2, 10))
        self.assertEqual(CITATION_PARSER_VERSION, "bracketed-document-v1")

    def test_analysis_reports_invalid_and_out_of_range_markers(self):
        analysis = analyze_answer_citations(
            "事实 [文档1]，补充 [文档9]，以及文档2和[文档 3]。",
            document_count=2,
        )

        self.assertEqual(analysis.citations, (1, 9))
        self.assertEqual(
            analysis.invalid_citations,
            ("[文档9]", "文档2", "[文档 3]"),
        )
        self.assertTrue(analysis.has_citations)

    def test_analysis_rejects_non_string_and_negative_document_count(self):
        with self.assertRaises(TypeError):
            parse_answer_citations(None)
        with self.assertRaises(ValueError):
            analyze_answer_citations("[文档1]", -1)


if __name__ == "__main__":
    unittest.main()
