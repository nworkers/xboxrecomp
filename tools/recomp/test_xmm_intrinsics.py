"""The SSE2-intrinsic XMM helpers give the same bits as the plain C ones.

recomp_types.h implements the packed helpers with intrinsics when the
compiler targets SSE2 and in plain C otherwise (or with
RECOMP_XMM_PORTABLE). One driver is built both ways and every helper is run
on the same inputs -- signed zeros, infinities, NaNs, denormals and ordinary
values -- and the two outputs must match exactly. Needs a C compiler that
targets SSE2: clang, gcc, or cl when it is on PATH."""
import os
import shutil
import subprocess
import tempfile

import pytest

RUNTIME = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "runtime")

DRIVER = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "recomp_types.h"

ptrdiff_t g_xbox_mem_offset;
static uint8_t memory[256];

static const uint32_t inputs[] = {
    0x00000000u, 0x80000000u, 0x3F800000u, 0xBF800000u, 0x7F800000u, 0xFF800000u,
    0x7FC00000u, 0xFFC00001u, 0x00000001u, 0x807FFFFFu, 0x3FC00000u, 0x40490FDBu,
    0xC2F6E979u, 0x7F7FFFFFu, 0x00800000u, 0x3EAAAAABu,
};
#define N (sizeof(inputs) / sizeof(inputs[0]))

static RecompXmm vec(unsigned k) {
    RecompXmm r; unsigned i;
    for (i = 0; i < 4; ++i) r.u[i] = inputs[(k + i * 5) % N];
    return r;
}
static void show(const char *name, RecompXmm v) {
    printf("%s %08X %08X %08X %08X\n", name, v.u[0], v.u[1], v.u[2], v.u[3]);
}

int main(void) {
    unsigned k, j;
    float f;
    g_xbox_mem_offset = (ptrdiff_t)(uintptr_t)memory;
    printf("sse %d\n",
#ifdef RECOMP_XMM_SSE
           1
#else
           0
#endif
    );
    for (k = 0; k < N; ++k) {
        RecompXmm a = vec(k), b = vec(k + 3), d;
        memcpy(&f, &inputs[k], 4);
        show("zero", XMM_ZERO());
        show("scalar", XMM_SCALAR(f));
        show("scalar_bits", XMM_SCALAR_BITS(inputs[k]));
        show("scalar_double", XMM_SCALAR_DOUBLE((double)f));
        show("add", XMM_ADD(a, b)); show("sub", XMM_SUB(a, b));
        show("mul", XMM_MUL(a, b)); show("div", XMM_DIV(a, b));
        show("min", XMM_MIN(a, b)); show("max", XMM_MAX(a, b));
        show("and", XMM_AND(a, b)); show("or", XMM_OR(a, b));
        show("xor", XMM_XOR(a, b)); show("andn", XMM_ANDN(a, b));
        show("eq", XMM_CMP_EQ(a, b)); show("lt", XMM_CMP_LT(a, b));
        show("le", XMM_CMP_LE(a, b)); show("neq", XMM_CMP_NEQ(a, b));
        show("sqrt", XMM_SQRT(a, b));
        show("unpacklo", XMM_UNPACK_LOW(a, b)); show("unpackhi", XMM_UNPACK_HIGH(a, b));
        show("movlh", XMM_MOVE_LOW_TO_HIGH(a, b)); show("movhl", XMM_MOVE_HIGH_TO_LOW(a, b));
        printf("movemask %u\n", XMM_MOVEMASK(a));
        show("shuf00", XMM_SHUFFLE(a, b, 0x00)); show("shuf1B", XMM_SHUFFLE(a, b, 0x1B));
        show("shuf4E", XMM_SHUFFLE(a, b, 0x4E)); show("shufE4", XMM_SHUFFLE(a, b, 0xE4));
        /* Guest memory at unaligned guest addresses. */
        for (j = 0; j < sizeof(memory); ++j) memory[j] = (uint8_t)(j * 37 + k);
        show("mem", XMM_MEM(k + 1));
        XMM_STORE(k + 3, a); show("store", XMM_MEM(k + 3));
        d = b; XMM_LOAD_LOW(d, k + 5); show("loadlo", d);
        d = b; XMM_LOAD_HIGH(d, k + 7); show("loadhi", d);
        XMM_STORE_LOW(k + 40, a); XMM_STORE_HIGH(k + 60, a);
        show("storelo", XMM_MEM(k + 40)); show("storehi", XMM_MEM(k + 60));
    }
    return 0;
}
'''


def _compilers():
    for cc in ("clang", "gcc"):
        path = shutil.which(cc)
        if path:
            yield [path, "-O2", "-msse2", "-I", RUNTIME], "-o", "-D"
    if shutil.which("cl"):
        yield ["cl", "/nologo", "/O2", "/I", RUNTIME], "/Fe", "/D"


def _run(cmd, out_flag, define_flag, src, exe, portable):
    args = list(cmd) + [src]
    if portable:
        args.append(define_flag + "RECOMP_XMM_PORTABLE")
    if out_flag == "/Fe":
        args.append("/Fe" + exe)
    else:
        args += [out_flag, exe, "-lm"]
    built = subprocess.run(args, capture_output=True, text=True, cwd=os.path.dirname(src))
    assert built.returncode == 0, built.stdout + built.stderr
    return subprocess.run([exe], capture_output=True, text=True, check=True).stdout


def test_intrinsics_match_plain_c():
    compilers = list(_compilers())
    if not compilers:
        pytest.skip("no C compiler targeting SSE2")
    cmd, out_flag, define_flag = compilers[0]
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "xmm_driver.c")
    with open(src, "w", encoding="utf-8") as f:
        f.write(DRIVER)
    sse = _run(cmd, out_flag, define_flag, src, os.path.join(tmp, "sse.exe"), portable=False)
    plain = _run(cmd, out_flag, define_flag, src, os.path.join(tmp, "plain.exe"), portable=True)
    assert sse.splitlines()[0] == "sse 1"
    assert plain.splitlines()[0] == "sse 0"
    assert sse.splitlines()[1:] == plain.splitlines()[1:]
