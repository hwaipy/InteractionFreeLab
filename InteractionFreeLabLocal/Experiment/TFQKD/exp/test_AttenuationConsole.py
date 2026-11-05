"""Offline terminal/UI checks; no IFWorker or physical voltage source."""
from datetime import datetime, timezone
import io
import os
import pty
import tempfile
import termios
import time
import unittest
from unittest.mock import Mock, patch

from rich.console import Console
from rich.cells import cell_len

from AttenuationConsole import StabilizerConsole, TerminalCommands
from AttenuationStabilizer import AttenuationStabilizer


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=AttenuationStabilizer(output_dir=self.tmp.name,worker=Mock())
        self.c.log=Mock()
        self.keys=TerminalCommands(self.c)

    def type(self,text):
        for char in text:self.keys.handle(char)
        self.c._commands(self.keys)

    def test_edit_targets_and_cancel_invalid_input(self):
        self.type('t25.9 26.1\r')
        self.assertEqual(self.c.targets,{'Alice':25.9,'Bob':26.1})
        self.type('a27\x1b')
        self.assertEqual(self.c.targets['Alice'],25.9)
        self.type('bnan\r')
        self.assertEqual(self.c.targets['Bob'],26.1)
        self.c._worker.assert_not_called()
        self.assertEqual(self.c._worker.mock_calls,[])

    def test_enable_checks_voltage_observe_does_not_touch_supply(self):
        self.c.arm=Mock();self.c.latest=200;self.c.live_after=100
        self.type('e')
        self.c.arm.assert_called_once();self.assertTrue(self.c.enabled)
        self.assertEqual(self.c.live_after,200)
        self.type('o')
        self.assertFalse(self.c.enabled);self.assertTrue(self.c.pause_writes.is_set())
        self.c.arm.assert_called_once()

    def test_o_during_arm_cannot_be_overwritten_by_enable(self):
        self.c.arm=Mock(side_effect=lambda:self.keys.handle('o'))
        self.type('e')
        self.assertFalse(self.c.enabled)
        self.assertTrue(self.c.pause_writes.is_set())

    def test_pause_during_readback_blocks_not_yet_sent_write(self):
        remote=Mock()
        def read():
            self.keys.handle('o')
            return [0,0,3.09]
        remote.getVoltageSetpoints.side_effect=read
        remote.getOutputStatuses.return_value=[True]*3
        self.c._worker=Mock(TF_PowerSupply_Alice_3=remote)
        self.c.voltages={'Alice':3.09};self.c.initial_voltages={'Alice':3.09}
        self.c.latest=200
        self.assertIsNone(self.c.adjust('Alice',.02,186))
        remote.setVoltage.assert_not_called()

    def test_failed_enable_keeps_observation_running(self):
        self.c.arm=Mock(side_effect=RuntimeError('readback failed'))
        self.type('e')
        self.assertFalse(self.c.enabled)
        self.assertTrue(self.c.pause_writes.is_set())
        self.assertFalse(self.c.stop_event.is_set())

    def test_pause_after_write_intent_still_blocks_write(self):
        remote=Mock()
        remote.getVoltageSetpoints.return_value=[0,0,3.09]
        remote.getOutputStatuses.return_value=[True]*3
        self.c._worker=Mock(TF_PowerSupply_Alice_3=remote)
        self.c.voltages={'Alice':3.09};self.c.initial_voltages={'Alice':3.09}
        self.c.latest=200
        self.c.log=Mock(side_effect=lambda event,**kw:self.keys.handle('o') if event=='write_intent' else None)
        self.assertIsNone(self.c.adjust('Alice',.02,186))
        remote.setVoltage.assert_not_called()

    def test_observe_run_renders_and_stops_without_supply_calls(self):
        out=io.StringIO();console=Console(file=out,width=120,height=55,color_system=None)
        self.c.log=AttenuationStabilizer.log.__get__(self.c)
        self.c.arm=Mock()
        def tick(**kw):
            self.assertFalse(kw['enable'])
            self.c.stop()
        self.c.tick=Mock(side_effect=tick)
        with patch('AttenuationConsole.Console',return_value=console):
            self.c.run(interactive=False)
        self.c.arm.assert_not_called()
        self.assertEqual(self.c._worker.mock_calls,[])
        self.assertIn('观察模式',out.getvalue())
        self.assertIn('已停止',out.getvalue())

    def test_render_history_pruning_and_no_voltage_calls(self):
        out=io.StringIO();console=Console(file=out,width=130,height=55,color_system=None)
        ui=StabilizerConsole(self.c,self.keys,history_seconds=60,console=console)
        now=datetime.now(timezone.utc).isoformat()
        self.c.latest=200
        z={arm:{'counts':5000,'pulses':4000000,'yield':.00125,'efficiency':.0025,
                'variance':1e-10,'attenuation_db':26.021} for arm in ('Alice','Bob')}
        for slot in (100,150,180):
            ui.record({'event':'sample','logged_at':now,'slot':slot,'z':z})
        self.assertEqual([r['slot'] for r in ui.history],[150,180])
        ui.record({'event':'second','logged_at':now,'slot':198,'valid':False,
                   'reasons':['gen1_waiting_or_constant']})
        console.print(ui.render())
        text=out.getvalue()
        for value in ('观察模式','不调电压','Alice','Bob','5,000','0.2500','目标','历史','gen1_waiting_or_constant'):
            self.assertIn(value,text)
        self.assertEqual(self.c._worker.mock_calls,[])

    def test_real_pty_nonblocking_input_and_terminal_restoration(self):
        master,slave=pty.openpty()
        stream=os.fdopen(os.dup(slave),'r')
        original=termios.tcgetattr(slave)
        keys=TerminalCommands(self.c,stream)
        try:
            keys.start();self.assertTrue(keys.active)
            os.write(master,b't26 27\r')
            deadline=time.monotonic()+2
            while keys.commands.empty() and time.monotonic()<deadline:time.sleep(.01)
            self.c._commands(keys)
            self.assertEqual(self.c.targets,{'Alice':26.,'Bob':27.})
        finally:
            keys.close()
            restored=termios.tcgetattr(slave)
            stream.close();os.close(master);os.close(slave)
            # macOS may set its pending-input flag when canonical mode returns;
            # ECHO, ICANON, ISIG, timeouts and all other settings must match.
            restored[3] &= ~getattr(termios,'PENDIN',0)
            original[3] &= ~getattr(termios,'PENDIN',0)
            self.assertEqual(restored,original)

    def test_fixed_layout_does_not_move_with_history_or_long_values(self):
        for terminal_width,height in ((150,55),(80,40)):
            out=io.StringIO()
            console=Console(file=out,width=terminal_width,height=height,color_system=None)
            ui=StabilizerConsole(self.c,self.keys,console=console,width=120)
            def draw():
                out.seek(0);out.truncate(0)
                console.print(ui.render())
                lines=out.getvalue().splitlines()
                for line in lines:self.assertLessEqual(cell_len(line),min(120,terminal_width))
                return lines
            before=draw()
            now=datetime.now(timezone.utc).isoformat()
            self.c.latest=200
            z={arm:{'counts':1234567890123,'pulses':999999999999999,'yield':.001,
                    'efficiency':.0025,'attenuation_db':26.021} for arm in ('Alice','Bob')}
            for slot in range(100,200,15):ui.record({'event':'sample','logged_at':now,'slot':slot,'z':z})
            ui.record({'event':'input_error','logged_at':now,'reason':'Very long event '*100})
            self.keys.active=True;self.keys.editing='both';self.keys.buffer='1234567890 '*7
            after=draw()
            self.assertEqual(len(before),len(after))
            self.assertLessEqual(len(after),height)
            for label in ('键盘控制','两路状态','有效不补偿秒历史','最近事件'):
                self.assertEqual(next(i for i,line in enumerate(before) if label in line),
                                 next(i for i,line in enumerate(after) if label in line))


if __name__=='__main__':unittest.main()
