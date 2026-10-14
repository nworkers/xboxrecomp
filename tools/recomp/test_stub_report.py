"""An unresolved-target stub reports that it ran, when the project asks.

A stub stands in for code the disassembler never found, so a stub that runs
means the original executed something the recompiled build skipped. Each stub
calls RECOMP_UNRESOLVED_STUB(va): with RECOMP_STUB_REPORT defined that is
recomp_unresolved_stub_log(va), and without it nothing, so a project that does
not implement the report links as before.

The behavioural half compiles the macro taken from the runtime header, both
ways; it skips itself if no C compiler is on PATH.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.recomp.translator import _stub_definition  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HEADER = os.path.join(ROOT, "templates", "runtime", "recomp_types.h")


def _cc():
    return shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")


def _stub_block():
    """The RECOMP_STUB_REPORT #ifdef block of the runtime header."""
    text = open(HEADER, encoding="utf-8").read()
    m = re.search(r"#ifdef RECOMP_STUB_REPORT\n.*?#endif\n", text, re.S)
    assert m, "RECOMP_STUB_REPORT block missing from recomp_types.h"
    return m.group(0)


class StubDefinition(unittest.TestCase):
    def test_reports_then_pops_the_return_address(self):
        line = _stub_definition("sub_00054750", 0x00054750, 0)
        self.assertIn("RECOMP_UNRESOLVED_STUB(0x00054750u);", line)
        self.assertIn("g_esp += 4;", line)
        self.assertLess(line.index("RECOMP_UNRESOLVED_STUB"), line.index("g_esp"))
        self.assertIn("not detected", line)

    def test_stdcall_bytes_are_still_popped(self):
        line = _stub_definition("sub_00011000", 0x00011000, 8)
        self.assertIn("g_esp += 12;", line)
        self.assertIn("ret 8", line)


class StubReportMacro(unittest.TestCase):
    PROGRAM = r"""
#include <stdint.h>
#include <stdio.h>
static uint32_t reported;
static int calls;
void recomp_unresolved_stub_log(uint32_t va) { reported = va; ++calls; }
uint32_t g_esp = 0x1000;
%s
void sub_00054750(void) { RECOMP_UNRESOLVED_STUB(0x00054750u); g_esp += 4; }
int main(void) {
    sub_00054750();
    printf("%%u %%08X %%08X\n", (unsigned)calls, (unsigned)reported, (unsigned)g_esp);
    return 0;
}
"""

    def _run(self, report):
        cc = _cc()
        if cc is None:
            self.skipTest("no C compiler on PATH")
        source = ("#define RECOMP_STUB_REPORT\n" if report else "") + _stub_block()
        with tempfile.TemporaryDirectory() as tmp:
            c = os.path.join(tmp, "stub.c")
            exe = os.path.join(tmp, "stub.exe")
            with open(c, "w", encoding="utf-8") as f:
                f.write(self.PROGRAM % source)
            subprocess.run([cc, c, "-o", exe], check=True, capture_output=True)
            return subprocess.run([exe], check=True, capture_output=True, text=True).stdout.split()

    def test_reports_when_enabled(self):
        self.assertEqual(self._run(True), ["1", "00054750", "00001004"])

    def test_silent_when_disabled(self):
        self.assertEqual(self._run(False), ["0", "00000000", "00001004"])


if __name__ == "__main__":
    unittest.main()
