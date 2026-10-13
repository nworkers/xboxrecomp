"""Translated functions read the guest memory base once, into a local.

XBOX_PTR used to add the global g_xbox_mem_offset at every guest access. Guest
stores go through volatile pointers, and a compiler has to assume those may
alias any global, so the global was reloaded after every store. A translated
chunk now defines RECOMP_LOCAL_MEM_BASE, each translated function declares
its copy first (RECOMP_MEM_BASE_DECL), and the switch sits after every helper
in recomp_types.h so that the helpers, compiled without such a local, keep
the global."""
import os
import re

from tools.recomp import config, translator

HEADER = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "runtime", "recomp_types.h")


def _translate(image):
    base = 0x10000
    config._install([config.Section('.text', base, len(image), 0, len(image), True)],
                    entry_point=base, kernel_thunk_addr=base, origin='mem-base-test')
    db = {base: {'end': base + len(image), 'size': len(image)}}
    return translator.FunctionTranslator(image, db).translate_function(base, db[base])


def test_function_declares_the_base_before_any_access():
    # mov [ecx], eax; mov eax, [ecx+4]; ret
    code = _translate(bytes.fromhex('89 01 8b 41 04 c3'))
    assert code.count('RECOMP_MEM_BASE_DECL') == 1
    first_access = min(code.index(m) for m in ('MEM32(', 'MEM8(', 'MEM16(') if m in code)
    assert code.index('RECOMP_MEM_BASE_DECL') < first_access
    assert code.index('{') < code.index('RECOMP_MEM_BASE_DECL')


def test_header_switches_after_every_helper():
    text = open(HEADER, encoding='utf-8').read()
    switch = text.index('#define RECOMP_MEM_BASE _recomp_mem_base')
    # Every inline function body in the header comes before the switch.
    helpers = [m.start() for m in re.finditer(r'\bstatic\s+(?:__inline|inline|__forceinline)\b', text)]
    assert helpers and max(helpers) < switch
    # Outside a translated chunk the base stays the global.
    assert '#define RECOMP_MEM_BASE g_xbox_mem_offset' in text
    assert 'defined(RECOMP_LOCAL_MEM_BASE)' in text[:switch]
