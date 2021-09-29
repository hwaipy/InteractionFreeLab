# # -*- coding: utf-8 -*-
# import struct
# from math import floor
#
#
# # DA板序列控制定义，控制波形输出的核心
# # seq[4 * k] = 0    # start_addr
# # seq[4 * k + 1] = 5 # length
# # seq[4 * k + 2] = 2000 # repeat_trig or count
# # seq[4 * k + 3] = 16384  # 触发
#
# def generate_trig_seq(loop_cnt, trig_delay, trig_interval, length, channel_output_delay):
#     if channel_output_delay > 2.5e-4:  # 通道延时必须小于等于250us
#         ret = 0
#         logger.error(f'generate trig seq error,channel_output_delay:{channel_output_delay} out of range')
#         return ret
#     ch_delay = round(channel_output_delay / 4e-9)
#
#     length = 40 if length < 40 else length
#     length = (length + 7) >> 3
#     idle_wave_len = 5
#     idle_wave_addr = length
#     ## 输出波形的最小长度为20ns 即 5个时钟计数, 空波形数据是AWG驱动写入时会在每个通道波形数据后面自动加入20ns的空波形数据
#     ## 波形长度小于20ns时，波形会补齐成20ns
#
#     # 1 1级循环开始
#     func = 0x1 << 11
#     loop_level = 0
#     ctrl = func | (loop_level << 8)
#     seq_L1 = [idle_wave_addr, idle_wave_len, loop_cnt, ctrl]
#
#     # 2 触发输出波形
#     seq_T = [0, length, ch_delay, 16384]
#
#     # 3 1级循环结束
#     func = 0x2 << 11
#     loop_level = 0
#     jump_addr = 0
#     ctrl = func | (loop_level << 8)
#     seq_J1 = [idle_wave_addr, idle_wave_len, jump_addr, ctrl]
#
#     # 4 停止输出
#     func = 0x4 << 11
#     stop = 1 << 15
#     ctrl = func | stop
#     seq_S = [idle_wave_addr, idle_wave_len, 4, ctrl]
#
#     seq = seq_L1 + seq_T + seq_J1 + seq_S
#     seq = seq + [32768] * (32 - (len(seq) & 31))
#     # 32768停止输出波形操作
#     return seq
#
#
# def generate_continuous_seq(count):
#     count_temp = (count + 7) >> 3
#     return [0, count_temp, 0, 0] * 4096
