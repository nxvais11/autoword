import sys
import unittest

@unittest.skipUnless(sys.platform=='win32','Integração de datas do Windows')
class WindowsTimezone(unittest.TestCase):
    def test_win32_timestamp_conversion_loads_timezone_dependency(self):
        import win32timezone
        import win32file
        self.assertTrue(win32timezone.TimeZoneInfo)
        stamp=win32file.GetFileAttributesEx(sys.executable)[1]
        self.assertGreaterEqual(stamp.year,1969)
        self.assertIsNotNone(stamp.tzinfo)
