"""A branch into another function's interior, on final bodies, becomes an alias.

_pass_tail_jump_targets aliases a jmp into another function, but runs before
passes that can still split a body, and never takes a jcc; the gap pass takes
only jcc targets in gaps. A branch that ended up pointing into a neighbour's
interior was lowered to an unresolved-target stub that pops only a return
address. The shape: a function whose shared `pop esi; ret` tail falls inside a
block _pass_gap_prologues made into its own function (Jet Set Radio Future,
0x0007E180 -> 0x0007E255 inside sub_0007E242); every branch to the tail came
back with esp 4 low and esi unrestored.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.disasm.functions import FunctionDetector, Function  # noqa: E402


class _Insn:
    def __init__(self, addr, ret=False, jcc=None, jmp=None):
        self.address = addr
        self.end_address = addr + 4
        self.is_ret = ret
        self.is_jump = jmp is not None
        self.is_cond_jump = jcc is not None
        self.is_branch = jcc is not None or jmp is not None
        self.jump_target = jcc if jcc is not None else jmp
        self.jump_table = None


class _Engine:
    def __init__(self, insns):
        self.instructions = {i.address: i for i in insns}


def _run(insns, functions, aliases=()):
    det = FunctionDetector.__new__(FunctionDetector)
    det.engine = _Engine(insns)
    det.functions = {s: Function(start=s, end=e, name=f"sub_{s:08X}") for s, e in functions}
    det._alias_entries = dict(aliases)
    det._candidates = {}
    added = det._pass_branches_into_bodies()
    return added, det._alias_entries


# sub_1000 (0x1000..0x1020) and sub_1020 (0x1020..0x1040), whose tail at
# 0x1030 is the `pop esi; ret` sub_1000's branches share; 0x1050.. is a gap.
FUNCTIONS = [(0x1000, 0x1020), (0x1020, 0x1040)]


def _body(**branch):
    return [_Insn(0x1000), _Insn(0x1004, **branch), _Insn(0x1008, jcc=0x1010),
            _Insn(0x100C, ret=True), _Insn(0x1010), _Insn(0x101C, ret=True),
            _Insn(0x1020), _Insn(0x102C), _Insn(0x1030), _Insn(0x1034, ret=True),
            _Insn(0x1050), _Insn(0x1054, ret=True)]


class BranchesIntoBodies(unittest.TestCase):
    def test_jcc_into_a_neighbour_interior_becomes_an_alias(self):
        added, aliases = _run(_body(jcc=0x1030), FUNCTIONS)
        self.assertTrue(added)
        self.assertEqual(aliases, {0x1030: 0x1040})

    def test_jmp_into_a_neighbour_interior_becomes_an_alias(self):
        added, aliases = _run(_body(jmp=0x1030), FUNCTIONS)
        self.assertTrue(added)
        self.assertEqual(aliases, {0x1030: 0x1040})

    def test_a_known_alias_is_kept(self):
        added, aliases = _run(_body(jcc=0x1030), FUNCTIONS, aliases={0x1030: 0x1038})
        self.assertFalse(added)
        self.assertEqual(aliases, {0x1030: 0x1038})

    def test_branch_to_a_function_start_adds_nothing(self):
        self.assertEqual(_run(_body(jcc=0x1020), FUNCTIONS), (False, {}))

    def test_branch_into_the_middle_of_an_instruction_adds_nothing(self):
        self.assertEqual(_run(_body(jcc=0x1032), FUNCTIONS), (False, {}))

    def test_intra_function_branch_adds_nothing(self):
        self.assertEqual(_run(_body(jcc=0x100C), FUNCTIONS), (False, {}))

    def test_branch_from_an_alias_in_a_gap_becomes_an_alias(self):
        # sub_1000 is not a function here: an alias reached only from data,
        # in the gap before sub_1020 (the JSRF 0x0007E180 shape).
        added, aliases = _run(_body(jcc=0x1030), [(0x1020, 0x1040)], aliases={0x1000: 0x1020})
        self.assertTrue(added)
        self.assertEqual(aliases, {0x1000: 0x1020, 0x1030: 0x1040})

    def test_a_new_alias_is_examined_too(self):
        # 0x1030 branches on into sub_1060's interior once it is an alias.
        insns = _body(jcc=0x1030)
        insns[8] = _Insn(0x1030, jcc=0x1068)
        insns += [_Insn(0x1060), _Insn(0x1068), _Insn(0x106C, ret=True)]
        added, aliases = _run(insns, FUNCTIONS + [(0x1060, 0x1070)])
        self.assertTrue(added)
        self.assertEqual(aliases, {0x1030: 0x1040, 0x1068: 0x1070})

    def test_branch_into_a_gap_is_left_to_the_gap_passes(self):
        self.assertEqual(_run(_body(jcc=0x1050), FUNCTIONS), (False, {}))


if __name__ == "__main__":
    unittest.main()
