# from Instrument.WaveformGenerator.USTCDAC.da_board import *
# import filecmp
# from Instrument.WaveformGenerator.USTCDAC.data_waves import *
# import matplotlib.pyplot as plt
#
# new_ip = '172.16.60.199'
# da1 = DABoard(id=new_ip, ip=new_ip, port=40230, batch_mode=False)
# da2 = DABoard(id=new_ip, ip=new_ip, port=40231, batch_mode=False)
# board_status1 = da1.connect()
# board_status2 = da2.connect()
# da1.set_loop(1, 1, 1, 1)
# da2.set_loop(1, 1, 1, 1)
# da_ctrl = waveform()
# freq = 1e6
# step = int(2e9 / freq)
# print(step)
# da_ctrl.generate_sin(repeat=40, cycle_count=step)
# da_ctrl.generate_trig_seq(0, length=len(da_ctrl.wave))
# print(len(da_ctrl.wave))
#
# da1.set_multi_board(0)
# da2.set_multi_board(0)
# for i in range(1, 5):
#     da1.stop_output_wave(i)
#     da2.stop_output_wave(i)
# for i in range(1, 5):
#     da1.write_seq_fast(i, seq=da_ctrl.seq)
#     da1.write_wave_fast(i, wave=da_ctrl.wave)
#     da2.write_seq_fast(i, seq=da_ctrl.seq)
#     da2.write_wave_fast(i, wave=da_ctrl.wave)
# for i in range(1, 5):
#     da1.start_output_wave(i)
#     da2.start_output_wave(i)
# da1.set_trig_count_l1(100000)
# da1.set_trig_interval_l1(200e-6)
# da1.set_trig_select(0)
# da2.set_trig_select(0)
# da1.send_int_trig()
# time.sleep(2)
#
# # da.StartStop(240)
# da1.disconnect()
# da2.disconnect()
# if board_status1 < 0:
#     print('Failed to find board 1')
# if board_status2 < 0:
#     print('Failed to find board 2')
