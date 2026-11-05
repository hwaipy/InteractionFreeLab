"""Rich console and nonblocking terminal commands; no device calls here."""
from collections import deque, Counter
from datetime import datetime, timezone, timedelta
import math
import queue
import select
import sys
import threading
import time

from rich.console import Console, Group
from rich.cells import cell_len
from rich.constrain import Constrain
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

TZ = timezone(timedelta(hours=8))


def clock(slot):
    return datetime.fromtimestamp(slot, TZ).strftime('%H:%M:%S') if slot is not None else '—'


def number(value, spec='.3f'):
    return '—' if value is None else format(value, spec)


class TerminalCommands:
    """Reader thread queues commands; only the controller thread operates devices."""
    def __init__(self, controller, stream=None):
        self.controller = controller
        self.stream = stream or sys.stdin
        self.commands = queue.Queue()
        self.editing = None
        self.buffer = ''
        self.active = False
        self._stop = threading.Event()
        self._thread = None
        self._original = None
        self._escape = 0

    @property
    def prompt(self):
        if self.editing is None:
            return 'o 观察  ·  e 实施  ·  a Alice目标  ·  b Bob目标  ·  t 两路目标  ·  q 退出'
        label = {'Alice':'Alice', 'Bob':'Bob', 'both':'两路（一个数共用，或 Alice Bob 两个数）'}[self.editing]
        return f'输入{label}目标衰减/dB，Enter提交、Esc取消： {self.buffer}▏'

    def handle(self, char):
        if self._escape == 2:
            if '@' <= char <= '~': self._escape = 0
            return
        if self._escape == 1:
            self._escape = 0
            if char in ('[','O'):
                self._escape = 2
                return
        # o/q also work during numeric entry. Pause is visible immediately to
        # the write guard, even while the main thread is awaiting an RPC.
        if char.lower() == 'o':
            self.controller.pause_writes.set()
            self.editing = None; self.buffer = ''
            self.commands.put(('observe', None))
        elif char.lower() == 'q' or char == '\x03':
            self.controller.pause_writes.set()
            self.controller.stop()
        elif char == '\x1b':
            self._escape = 1
            self.editing = None; self.buffer = ''
        elif self.editing is not None:
            if char in ('\r', '\n'):
                try:
                    values = [float(v) for v in self.buffer.replace(',', ' ').replace('，',' ').split()]
                    if not values or not all(math.isfinite(v) for v in values):
                        raise ValueError('请输入有限数值')
                    if self.editing == 'both' and len(values) in (1, 2):
                        targets = {'Alice':values[0], 'Bob':values[-1]}
                    elif self.editing != 'both' and len(values) == 1:
                        targets = {self.editing:values[0]}
                    else:
                        raise ValueError('单路输入一个数，两路输入一个或两个数')
                    self.commands.put(('targets', targets))
                    self.editing = None; self.buffer = ''
                except ValueError as e:
                    self.commands.put(('input_error', str(e)))
            elif char in ('\x7f', '\b'):
                self.buffer = self.buffer[:-1]
            elif char.isprintable() and len(self.buffer) < 80:
                self.buffer += char
        elif char.lower() == 'e':
            self.commands.put(('implement', None))
        elif char.lower() in ('a', 'b', 't'):
            self.editing = {'a':'Alice', 'b':'Bob', 't':'both'}[char.lower()]
            self.buffer = ''

    def start(self):
        if not self.stream.isatty():
            return self
        import termios
        import tty
        self._original = termios.tcgetattr(self.stream.fileno())
        try:
            tty.setcbreak(self.stream.fileno())
            self.active = True
            self._thread = threading.Thread(target=self._read, daemon=True)
            self._thread.start()
        except BaseException:
            self.close()
            raise
        return self

    def _read(self):
        # os.read avoids TextIO buffering swallowing pasted characters after
        # select() says the underlying descriptor has no further bytes.
        import os
        try:
            while not self._stop.is_set():
                if select.select([self.stream], [], [], .1)[0]:
                    data = os.read(self.stream.fileno(), 256)
                    if not data:
                        break
                    for char in data.decode('utf-8', errors='replace'):
                        self.handle(char)
        except (OSError, ValueError) as e:
            self.commands.put(('input_error', '键盘读取停止：'+str(e)))

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=.5)
        if self._original is not None:
            import termios
            termios.tcsetattr(self.stream.fileno(), termios.TCSADRAIN, self._original)
            self._original = None
        self.active = False


class StabilizerConsole:
    def __init__(self, controller, keys=None, *, history_seconds=900, history_rows=8, width=120, console=None):
        if not 30 <= history_seconds <= 86400 or not 1 <= history_rows <= 100:
            raise ValueError('历史窗口需为30～86400秒，显示行数需为1～100')
        if not 60 <= width <= 240:
            raise ValueError('面板宽度需为60～240列')
        self.controller, self.keys = controller, keys
        self.seconds, self.rows = history_seconds, history_rows
        self.console = console or Console()
        self.width = width
        self.started = time.monotonic()
        self.history = deque(maxlen=1000)
        self.events = deque(maxlen=6)
        self.estimates = {}
        self.arm_status = {}
        self.last_second = None
        self.last_sample = None
        self.counts = Counter()
        self._live = None
        self._last_snapshot = -math.inf

    def record(self, row):
        event = row['event']
        if event == 'second':
            self.last_second = row
            self.counts['valid' if row['valid'] else 'invalid'] += 1
        elif event == 'sample':
            self.last_sample = row
            self.counts['samples'] += 1
            self.history.append({'slot':row['slot'], 'z':row['z'], 'actions':{}})
        elif event == 'estimate':
            self.estimates[row['arm']] = row
            status = '待执行' if row['required'] and row['enabled'] else ('仅建议' if row['required'] else '死区内/预热')
            self.arm_status[row['arm']] = status
            self._action(row['slot'], row['arm'], status)
        elif event == 'target_changed':
            for arm in row['targets_db']:
                self.estimates.pop(arm,None)
                self.arm_status[arm] = '目标已更新，待新有效秒'
        elif event in ('adjusted','range_insufficient','isolated_z_jump','stale_measurement'):
            text = {'adjusted':f"已调 {row.get('applied_db',0):+.3f}dB",
                    'range_insufficient':'量程不足，未调节',
                    'isolated_z_jump':f'Z突变，确认 {row.get("confirmations",1)}/{row.get("needed",3)}',
                    'stale_measurement':'数据过期，未调节'}[event]
            self.arm_status[row['arm']] = text
            if 'slot' in row: self._action(row['slot'], row['arm'], text)
        if event not in ('second','sample','estimate'):
            labels = {'started':'程序启动', 'armed':'电源读回已核对', 'phase':'周期识别',
                      'target_captured':'目标已建立', 'target_changed':'目标已修改',
                      'mode':'模式切换', 'adjusted':'已调压', 'write_intent':'准备调压',
                      'range_insufficient':'量程不足', 'isolated_z_jump':'Z异常',
                      'fault':'故障', 'stopped':'已停止', 'input_error':'输入错误',
                      'command_error':'命令未执行', 'invalid_z':'Z数据无效'}
            labels['control_phase']='控制阶段切换'
            labels['response_checked']='调压响应已确认'
            labels['jump_reacquired']='连续有效测量已重新接纳'
            details = {k:v for k,v in row.items() if k not in ('event','logged_at','raw','config')}
            self.events.append((row['logged_at'], labels.get(event,event), str(details)))
        self._prune()

    def _prune(self):
        high = self.controller.latest
        if high is not None:
            while self.history and self.history[0]['slot'] < high-self.seconds:
                self.history.popleft()

    def _action(self, slot, arm, text):
        for item in reversed(self.history):
            if item['slot'] == slot:
                item['actions'][arm] = text
                break

    def render(self):
        self._prune()
        c = self.controller
        width = min(self.width,self.console.width)
        inner = max(1,width-4)  # border + one-cell padding on both sides
        event_rows = 6 if self.console.height>=50 else (2 if self.console.height>=34 else 1)
        display_rows = max(1,min(self.rows,self.console.height-30-event_rows))

        def grid(widths, headers=None):
            table = Table(width=inner,expand=False,box=None,padding=(0,1),show_header=headers is not None)
            for i,col_width in enumerate(widths):
                table.add_column(headers[i] if headers else '',width=col_width,min_width=col_width,
                                 max_width=col_width,no_wrap=True,overflow='ellipsis',
                                 justify='right' if headers and headers[0]=='指标' and i else 'left')
            return table

        prompt = self.keys.prompt if self.keys and self.keys.active else '键盘控制不可用：请在 VS Code 集成终端或 SSH 的交互终端运行'
        if self.keys and self.keys.editing:
            name = {'Alice':'Alice','Bob':'Bob','both':'Alice/Bob'}[self.keys.editing]
            prefix = f'目标 {name} dB > '
            suffix = '  Enter确认 · Esc取消'
            room = max(1,inner-cell_len(prefix)-cell_len(suffix)-1)
            prompt = prefix+self.keys.buffer[-room:]+'▏'+suffix
        keyboard = Panel(Text(prompt,style='bold yellow',no_wrap=True,overflow='ellipsis'),
                         title='键盘控制 · 输入目标时采数继续',width=width,height=3)
        if width<60 or self.console.height<32:
            return Group(Panel(Text('请将终端调整到至少 60 列 × 32 行，以显示完整固定面板。',no_wrap=True,overflow='ellipsis'),
                               width=width,height=4,title='终端尺寸不足'),keyboard)
        enabled = c.enabled and not c.pause_writes.is_set()
        mode = '实施模式 · 自动调压' if enabled else '观察模式 · 不调电压'
        color = 'green' if enabled else 'cyan'
        age = None if c.last_progress is None else max(0,time.monotonic()-c.last_progress)
        state = {'idle':'正在初始化', 'observing':'正在观察', 'controlling':'正在控制',
                 'waiting_for_data':'等待新数据', 'stopped':'已停止', 'fault':'故障'}.get(c.state,c.state)
        header = Text(f'{mode}    {state}    运行 {int(time.monotonic()-self.started)}s',style='bold '+color,
                      no_wrap=True,overflow='ellipsis')
        half = (inner-4)//2
        meta = grid([half,inner-4-half])
        phase = '学习中（至少3个周期）' if c.phase is None else f'已确认 offset={c.phase}，优势 {c.phase_info.get("margin",0):.4f}'
        stage = '未知'
        if c.phase is not None and c.latest is not None:
            i = (c.latest-c.phase)%15
            stage = '15/15 不补偿' if i==14 else f'{i+1}/15 ρ={7**(i/13):.3f}'
        backlog = '—' if c.cursor is None or c.latest is None else str(max(0,int(c.latest-c.cursor)))+'s'
        meta.add_row(Text(f'数据最新 {clock(c.latest)}（UTC+8） · 更新间隔 {number(age,".1f")}s'),
                     Text(f'缓存 {len(c.cache)}/{c.max_meta} · 待追赶 {backlog}'))
        meta.add_row(Text('周期 '+phase),Text('最新meta推定位置 '+stage))
        meta.add_row(Text(f'已判定 有效 {self.counts["valid"]} / 无效 {self.counts["invalid"]}'),
                     Text(f'新有效不补偿秒 {self.counts["samples"]} · 最新 {clock(self.last_sample["slot"] if self.last_sample else None)}'))
        last = self.last_second
        quality = '尚未完成判定' if last is None else f'{clock(last["slot"])} '+('有效' if last['valid'] else '无效：'+', '.join(last['reasons']))
        meta.add_row(Text('最近判定 '+quality),Text('端点 '+c.endpoint))
        frame = max(c.cache.values(),key=lambda f:f['slot']) if c.cache else {}
        counts = frame.get('counter',{}); sync = frame.get('sync_counts',{})
        meta.add_row(Text(f'最新整秒 CH2/3: {number(counts.get("2"),",.0f")} / {number(counts.get("3"),",.0f")}'),
                     Text(f'CH4/5: {number(sync.get("4"),",.0f")} / {number(sync.get("5"),",.0f")}'))

        label_width = min(44,(inner-6)*2//5)
        value_width = (inner-6-label_width)//2
        links = grid([label_width,value_width,inner-6-label_width-value_width],['指标','Alice · Z10','Bob · Z01'])
        fields = {}
        for arm in ('Alice','Bob'):
            raw = self.last_sample['z'].get(arm,{}) if self.last_sample else {}
            filt = c.filters.get(arm,{})
            smooth = -10*math.log10(filt['eta']) if filt.get('eta') else None
            target = c.targets.get(arm)
            estimate = self.estimates.get(arm,{})
            delta = estimate.get('proposed_db',0)/c.actuators[arm].slope_db_per_volt if estimate.get('required') else 0
            delta = math.trunc(max(-c.max_step_voltage,min(c.max_step_voltage,delta))*1000)*.001
            fields[arm] = [f'{raw["counts"]:,} / {raw["pulses"]:,}' if 'counts' in raw else '等待首个有效秒',
                number(raw.get('yield',0)*100 if raw else None,'.5f')+' %',
                number(raw.get('efficiency',0)*100 if raw else None,'.4f')+' %',
                number(raw.get('attenuation_db'))+' / '+number(smooth),
                number(target) if target is not None else f'采集参考 {len(filt.get("initial",[]))}/5',
                number(target-smooth if target is not None and smooth is not None else None,'+.3f'),
                f'{delta:+.3f} V' if estimate else '—',
                number(c.voltages.get(arm))+' V' if arm in c.voltages else '未读取（观察模式）',
                (('快速逼近 · ' if estimate.get('control_phase')=='fast' else '稳定维持 · ') if estimate else '')
                +self.arm_status.get(arm,'等待估计')]
        labels = ['探测数 / 发送数（最近不补偿秒）','探测概率','总有效效率（扣背景）',
                  '衰减 raw / 平滑 [dB]','目标衰减 [dB]','目标 − 平滑 [dB]（正值应增衰减）',
                  '建议单步 ΔV（实际按模式执行）','电压（最近读回设定值）','最近处理']
        for i,label in enumerate(labels): links.add_row(Text(label),Text(fields['Alice'][i]),Text(fields['Bob'][i]))

        remaining = inner-10-8
        count_width,eff_width = remaining*22//100,remaining*23//100
        history = grid([8,count_width,eff_width,eff_width,remaining-count_width-2*eff_width],
                       ['数据时间','Z10 / Z01','Alice η% / dB','Bob η% / dB','处理 A / B'])
        for item in list(self.history)[-display_rows:]:
            a,b = item['z'].get('Alice',{}),item['z'].get('Bob',{})
            history.add_row(clock(item['slot']),f'{a.get("counts",0):,} / {b.get("counts",0):,}',
                            f'{a.get("efficiency",0)*100:.4f} / {a.get("attenuation_db",0):.3f}',
                            f'{b.get("efficiency",0)*100:.4f} / {b.get("attenuation_db",0):.3f}',
                            Text(' / '.join(item['actions'].get(arm,'参考采集中') for arm in ('Alice','Bob'))))
        if not self.history: history.add_row('—','等待新有效不补偿秒','—','—','—')
        for _ in range(display_rows-max(1,min(len(self.history),display_rows))):
            history.add_row('','','','','')
        trend = []
        for arm in ('Alice','Bob'):
            values = [h['z'][arm]['attenuation_db'] for h in self.history if arm in h['z']]
            if values:
                trend.append(f'{arm} {min(values):.3f}～{max(values):.3f}dB，首尾Δ {values[-1]-values[0]:+.3f}dB')
        history_block = Group(history,Text(' · '.join(trend) or '趋势：等待历史数据',style='dim',no_wrap=True,overflow='ellipsis'))
        event_table = grid([8,14,inner-6-8-14])
        for when,label,details in list(self.events)[-event_rows:]:
            event_table.add_row(datetime.fromisoformat(when).astimezone(TZ).strftime('%H:%M:%S'),Text(label),Text(details,no_wrap=True,overflow='ellipsis'))
        for _ in range(event_rows-min(len(self.events),event_rows)): event_table.add_row('','','')
        return Constrain(Group(Panel(Group(header,meta),title='MEMS 链路效率慢漂 · 实时监控',border_style=color,width=width,height=8),
                     keyboard,
                     Panel(links,title='两路状态 · η包含模拟衰减与探测效率',border_style='blue',width=width,height=12),
                     Panel(history_block,title=f'有效不补偿秒历史 · 最近 {self.seconds}s 共 {len(self.history)} 秒，显示最近 {display_rows} 条',
                           width=width,height=display_rows+4),
                     Panel(event_table,title='最近事件（本机时间 UTC+8）',width=width,height=event_rows+2),
                     Text('完整历史：'+str(c.output/'events.jsonl'),style='dim',no_wrap=True,overflow='ellipsis')),width=width)

    def start(self):
        if self.console.is_terminal:
            self._live = Live(self.render(),console=self.console,auto_refresh=False,vertical_overflow='ellipsis')
            self._live.start(refresh=True)
        else:
            self.refresh(force=True)

    def refresh(self,force=False):
        if self._live is not None:
            self._live.update(self.render(),refresh=True)
        elif force or time.monotonic()-self._last_snapshot>=15:
            self.console.print(self.render())
            self._last_snapshot=time.monotonic()

    def close(self):
        self.refresh(force=True)
        if self._live is not None: self._live.stop()
