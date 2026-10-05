"""
Segment maths, pinned against the gateway's own test cases.

The gateway, this SDK, the PHP SDK and the Laravel SDK must all agree. When they
do not, estimate_cost() quotes a price the invoice will not match.
"""

from django.test import SimpleTestCase

from signalbridge import segments


class SegmentCountTests(SimpleTestCase):
    def test_an_empty_message_is_one_segment(self):
        self.assertEqual(segments.count(''), 1)

    def test_gsm_messages_split_at_160_and_then_153(self):
        self.assertEqual(segments.count('a' * 160), 1)
        self.assertEqual(segments.count('a' * 161), 2)
        self.assertEqual(segments.count('a' * 306), 2)
        self.assertEqual(segments.count('a' * 307), 3)

    def test_unicode_messages_split_at_70_and_then_67(self):
        self.assertEqual(segments.count('ж' * 70), 1)
        self.assertEqual(segments.count('ж' * 71), 2)
        self.assertEqual(segments.count('ж' * 134), 2)
        self.assertEqual(segments.count('ж' * 135), 3)

    def test_a_newline_does_not_turn_a_plain_message_into_unicode(self):
        self.assertEqual(segments.count('line one\nline two'), 1)
        self.assertEqual(segments.count('a' * 150 + '\n' + 'b' * 9), 1)

    def test_a_carriage_return_is_also_plain_text(self):
        self.assertEqual(segments.count('line one\r\nline two'), 1)

    def test_template_placeholders_stay_gsm(self):
        self.assertEqual(segments.count('Hello {name}, your code is [1234]'), 1)
        self.assertEqual(segments.count('{' * 160), 1)

    def test_emoji_count_as_two_units_because_they_sit_outside_the_bmp(self):
        # 35 emoji are 70 UTF-16 code units: exactly one segment.
        self.assertEqual(segments.count('😀' * 35), 1)
        self.assertEqual(segments.count('😀' * 36), 2)

    def test_characters_inside_the_bmp_count_as_one_unit(self):
        self.assertEqual(segments.count('ä' * 70), 1)

    def test_the_gsm_alphabet_matches_the_gateway(self):
        # The gateway's BalanceService::GSM_7BIT_CHARSET, written out here so a
        # change on either side fails this test rather than a client's invoice.
        gateway = (
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ^{}\\[]~€|ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )

        self.assertEqual(segments.GSM_7BIT_CHARSET, gateway)

    def test_a_real_newline_is_in_the_alphabet(self):
        # The old implementation had the two-character sequence \\n instead, so
        # every multi-line message was billed as Unicode.
        self.assertIn('\n', segments.GSM_7BIT_CHARSET)
        self.assertIn('\r', segments.GSM_7BIT_CHARSET)
        self.assertTrue(segments.is_gsm_7bit('a\nb\rc'))

    def test_the_escape_table_characters_are_in_the_alphabet(self):
        for char in '^{}\\[]~|€':
            self.assertTrue(segments.is_gsm_7bit(char), char)


class CostEstimateTests(SimpleTestCase):
    def test_the_estimate_multiplies_segments_by_the_rate(self):
        self.assertEqual(segments.estimate_cost('Hello', 75.0), 75.0)
        self.assertEqual(segments.estimate_cost('a' * 161, 75.0), 150.0)
