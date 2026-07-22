import unittest

from output_naming import mastered_output_stem


class MasteredOutputNamingTests(unittest.TestCase):
    def test_artist_is_prefixed_to_song_name(self):
        self.assertEqual(mastered_output_stem("Mi canción", "O-M-A"), "O-M-A - Mi canción")

    def test_artist_prefix_is_not_duplicated(self):
        self.assertEqual(
            mastered_output_stem("O-M-A - Mi canción", "O-M-A"),
            "O-M-A - Mi canción - Master",
        )

    def test_legacy_processing_suffix_is_removed(self):
        self.assertEqual(mastered_output_stem("Mi canción_processed", "O-M-A"), "O-M-A - Mi canción")

    def test_invalid_filename_characters_are_sanitized(self):
        self.assertEqual(mastered_output_stem("Tema: versión/uno", "O/M/A"), "O-M-A - Tema- versión-uno")

    def test_empty_artist_uses_default(self):
        self.assertEqual(mastered_output_stem("Tema", ""), "O-M-A - Tema")


if __name__ == "__main__":
    unittest.main()
