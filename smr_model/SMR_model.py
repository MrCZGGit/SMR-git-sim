#Copyright (c) 2016 Northeastern University
############## How to run ###################
# $pypy ./SMR_model.py "input_trace"	    #
# the output can be found at output.log     #
#############################################
# cProfile 性能分析工具
import collections
import random
import cProfile
import sys
# import pysnooper

class Logger(object):
    def __init__(self, logFile ="Default.log"):
        self.terminal = sys.stdout
        self.log = open(logFile,'a+',encoding='utf-8')
 
    def write(self,message):
        self.terminal.write(message)
        self.log.write(message)
 
    def flush(self):
        pass
 

# round function has been used throughout the code to resolve the floating point issue
# initializes zones, bands and track size as well as zone boundaries
# consecutive zones have 4KB of size difference (zone_sz_diff)
# and every band consists of 20 consecutive tracks
# round 函数作为浮点数运算问题的解决 
# 初始化扇区域（zone）、band 和磁道（trace）大小 以及 区域边界； 
# 相邻连续 区域有 4KB 大小差异 (zone_sz_diff)                       diff差别
# 每个band 由 20 个连续磁道组成
def initialize_zones_bands_and_tracks (): 
        print("执行初始化initialize_zones_bands_and_tracks函数");
        global nr_of_tracks_per_band  # 定义全局变量每个带上的磁道数 20 
        global nr_of_zones            # 定义扇区数
        global nr_of_tracks_per_zone  # 定义一个扇区的磁道数
        z_sum = 0

        prev_zones_ub=0;
        nr_of_tracks_per_band = int(od_band_sz/od_track_sz)+1;
        nr_of_zones=(od_track_sz-id_track_sz)/zone_sz_diff
        nr_of_zones = int(nr_of_zones)
        zero_to_od=(od_track_sz/zone_sz_diff)*((od_track_sz/zone_sz_diff)+1)/2;
        zero_to_id=((id_track_sz/zone_sz_diff)-1)*(id_track_sz/zone_sz_diff)/2;
        total_sz_of_single_track_zones=(zero_to_od-zero_to_id)*zone_sz_diff;
        nr_of_tracks_per_zone=int(int(device_sz/total_sz_of_single_track_zones)/20)*20;

        global track_sz_in_zone
        global band_sz_in_zone
        track_sz_in_zone = []
        band_sz_in_zone = []
        track_sz_in_zone.append(0)    # 初始化
        band_sz_in_zone.append(0)    # 初始化
        # zone[i][0]: zone i's lower boundary && zone[i][1]: zone i's upper boundary 
        # 第一列参数为上边界 一个参数为下边界
        global zone
        # print("nr_of_zones大小为：" + nr_of_zones)
        # zone 初始化为一个二维数组 [[0,0],[0,0],[0,0]......]
        zone = [[0 for i in range (2)] for j in range(int(nr_of_zones+1))]
        # print("zone:" + zone)

        for i in range(1,nr_of_zones+1):
                if(i != nr_of_zones):
                        track_sz_in_zone.append(((od_track_sz/zone_sz_diff)-(i-1))*zone_sz_diff)
                        band_sz_in_zone.append(track_sz_in_zone[i]*nr_of_tracks_per_band)
                        z_sum+=nr_of_tracks_per_zone*track_sz_in_zone[i]
                        zone[i][0] = prev_zones_ub
                        zone[i][1] =  z_sum
                else:
                        track_sz_in_zone.append(((od_track_sz/zone_sz_diff)-(i-1))*zone_sz_diff);
                        band_sz_in_zone.append(track_sz_in_zone[i]*nr_of_tracks_per_band);
                        z_sum=device_sz;
                        zone[i][0] = prev_zones_ub
                        zone[i][1] =  z_sum
                prev_zones_ub=z_sum;

# finding the correponding track for a given address
# 搜索对应地址的 磁道
def calc_track_number(address):
        print("执行了 calc_track_number 函数 搜索对应的磁道")
        global zone_info
        global track_info
        track_info = [-1,-1,-1]

        for i in range(1,nr_of_zones+1):
                if ((address-int(zone[i][0])>=0) and (address-int(zone[i][1])<0)):
                        des_z=i;
                        des_z_lb=zone[i][0];
                        des_z_ub=zone[i][1];
                        break;
        # track_info[0]: global track number for a given address && track_info[1]  and track_info[2]: lower and upper bound in the calculated track
        # 第一位 是全局磁道号对给定地址  后续为计算的 边界的上限 和 下限
        track_info[0]= ((des_z-1)*nr_of_tracks_per_zone)+int((address-des_z_lb)/track_sz_in_zone[des_z])+1 ;
        track_info[1]= des_z_lb+int((address-des_z_lb)/track_sz_in_zone[des_z])*track_sz_in_zone[des_z] ;
        track_info[2]= des_z_lb+(int((address-des_z_lb)/track_sz_in_zone[des_z])+1)*track_sz_in_zone[des_z];
        # zone_info: zone number  扇区号
        zone_info=des_z;

# finding the correponding band for a given address
# 搜索对应地址的 磁道带
def find_band_number(address):
        print("执行了 find_band_number 函数 搜索对应的band带")
        global band_info
        band_info = [-1,-1,-1]
        # initilalize to -1, Every time the function is called, it will be changed, so there is no worries about the initial value
        # finding out which zone this address belongs to
        # 元素初始化为-1  每一次调用就会改变值 所以不需要担心初始值的问题
        # 根据 给定地址 找出属于哪个 zone带
        for i in range(1,nr_of_zones+1):
                if((address-int(zone[i][0])>=0) and (address-int(zone[i][1])<0)):
                        des_z = i
                        des_z_lb = zone[i][0]   # lower bound
                        des_z_ub = zone[i][1]   # uper  bound
                        break
        # band_info[0]: global band number for a given address && 
        # band_info[1] and band_info[2]: lower and upper bound in the calculated band
        band_info[0]= ((des_z-1)*(nr_of_tracks_per_zone/nr_of_tracks_per_band))+int((address-des_z_lb)/band_sz_in_zone[des_z])+1;
        band_info[1]= des_z_lb+int((address-des_z_lb)/band_sz_in_zone[des_z])*band_sz_in_zone[des_z];
        band_info[2]= des_z_lb+(int((address-des_z_lb)/band_sz_in_zone[des_z])+1)*band_sz_in_zone[des_z];

# returns a packet id from persistent cache's log head
# 从持久缓存中 的日志头 中返回一个数据包ID
def get_new_PID(trks_req,data):
        print("执行了 get_new_PID 函数 从持久缓存中的日志头返回一个数据包ID ")
        global PID   # array of packet ids  数据包ID列表
        global pc_wb_log_head   # log head for write backs（wb） in persistent cache 在持久缓存中回写的 日志头
        global avail_space_in_cur_pc_wb_band
        global cache_under_pressur # is set if all 23000 map entries are in use -- gets reset when gets back to less than 22986 
        global pc_log_head
        global pc_log_tail
        pc_log_head = round(pc_log_head,1)
        pc_log_tail = round(pc_log_tail,1)

	# data: flag bit to determine if or not a write is for new data or just a write back from cleaning
        if(data==1):
                plh=pc_log_head;
                if (pc_log_head > pc_log_tail):
                        if(round(pc_log_head+trks_req,1)>(pc_map_sz1*1.5*0.4)-0.4):
                                if(round(pc_log_tail-(pc_log_head+trks_req-pc_map_sz1*1.5*0.4+0.4),1) < pc_map_sz1*0.4*0.5  and in_the_middle_of_cleaning==0):
                                        clean_pc()
                        elif(round(pc_log_head-pc_log_tail+trks_req,1) > pc_map_sz1*0.4 and  in_the_middle_of_cleaning==0):
                                clean_pc()
                elif (pc_log_head < pc_log_tail):
                        if(round(pc_log_tail-pc_log_head-trks_req,1) < pc_map_sz1*0.4*0.5 and  in_the_middle_of_cleaning==0):
                                clean_pc();
                PID[int(round((pc_log_head*2.5),1))]=trks_req 
                if(round(pc_log_head+trks_req,1)> pc_map_sz1*1.5*0.4-0.4):
                        pc_log_head=round((pc_log_head+trks_req-pc_map_sz1*1.5*0.4+0.4),1);
                else:
                        pc_log_head=round((pc_log_head+trks_req),1);
        else:
                plh=pc_wb_log_head;
                pc_wb_log_head=(pc_wb_log_head+trks_req)%(40);
                avail_space_in_cur_pc_wb_band=(20-(pc_wb_log_head%20))*pc_track_sz;

        if(find_array_length(PID)==pc_map_sz2):
                cache_under_pressure=1;
        return plh

# 计算长度
def find_array_length(input_array):
        print("执行了 find_array_length 函数 ")
        array_length = 0
        for item in input_array:
                if item > 0:
                        array_length += 1
        return array_length

# makes a reference table for seeks from outer diameter to inner diameter (seek_time_OI) and vice versa (seek_time_IO)
# seek time references are read from "OI-analyzed-sorted.db" and "IO-analyzed-sorted.db"
# 制作一个从外径到内径（seek_time_OI）和反之（seek_time_IO）的寻道参考表
# 查找时间参考从这两个文件这种读取
def  initialize_seek_time_map():
        print("执行初始化：给一个寻道参考映射表initialize_seek_time_map")
        global seek_time_OI
        global seek_time_IO
        seek_time_OI = {}
        seek_time_IO = {}
        db_file = open ("OI-analyzed-sorted.db", "r")
        for line1 in db_file:
                line2 = line1.split(" ")
                # print("OI_line:");print(line2)
                value = line2[5].split("\n")    # 分离最后一个参数 和 换行 然后使用列表在输出valu[0]即可
                seek_time_OI.update({line2[4]:value[0]})        # seek_time_OI 作为Set 集合 不断更新数据
                # print("seek_time_OI:");print(seek_time_OI)    # 存放的 值对()
        db_file.close();

        db_file = open ("IO-analyzed-sorted.db", "r")
        for line1 in db_file:
                line2 = line1.split(" ")
                # print("IO_line:");print(line2)
                value = line2[5].split("\n")
                seek_time_IO.update({line2[4]:value[0]})
                # print("seek_time_IO:");print(seek_time_IO)
        db_file.close();

# finds the closest cases in either seek_time_OI or seek_time_IO and 
# then estimates the seek time using inter(extra)polations
# 在 seek_time_OI 或 seek_time_IO 中找到最接近的情况，然后使用 内/外差值 估计寻道时间
def estimate_seek_time(p_track,c_track):
        print("执行了 estimate_seek_time 函数 ")
        min_diff=device_sz+1
        abs_diff=abs(c_track-p_track)
        if (c_track>p_track):
                for trk_dis in seek_time_OI:
                        diff=abs(int(trk_dis)-abs_diff);
                        if diff<min_diff:
                                min_diff=diff;
                                desired_dis=trk_dis;
                return (float(seek_time_OI[desired_dis])/float(desired_dis))*abs_diff;
        else:
                for trk_dis in seek_time_IO:
                        diff=abs(int(trk_dis)-abs_diff);
                        if diff<min_diff:
                                min_diff=diff;
                                desired_dis=trk_dis;
                return (float(seek_time_IO[desired_dis])/float(desired_dis))*abs_diff;

# estimates rotational latency based on the location of previous and current tracks
# 根据先前和当前 磁道的位置 来计算估计旋转延迟
def estimate_rot_lat(p_track,c_track,p_add,c_add,p_off):
        print("执行了 estimate_rot_lat 函数  计算估计旋转延迟")
        if (p_track == c_track):
                if(p_track == 1): # both tracks on the persistent cache
                        if (abs(prev_r_pid - r_pid) < 0.2):
                                if(prev_r_chunck == r_chunck):
                                        return 0
                                else:
                                        return(full_rot_lat)
                        else:
                                if(abs((prev_r_pid%1) - (r_pid%1)) < 0.2):
                                        return(full_rot_lat)
                                elif((prev_r_pid%1) < (r_pid%1)):
                                        return((r_pid%1 - prev_r_pid%1) * full_rot_lat)
                                else:
                                        return((1+((r_pid%1) - (prev_r_pid%1))) * full_rot_lat)
                else:
                        if (prev_r_chunck == r_chunck):
                                return 0
                        c_t_p_a = p_add
        else:
                if (c_track == 1 or p_track==1): # if either of current or precious trackes is on the persistents cache
                        return (random.random() * full_rot_lat)
                c_t_p_a = track_info[1] + int((p_off*(track_info[2]-track_info[1]))/4096)*4096
        if (c_add - c_t_p_a >= 147456):
                return ((float((c_add-c_t_p_a))/(track_info[2]-track_info[1]))*full_rot_lat)
        else:
            return (full_rot_lat)

# finds the next valid packet id
# 寻找下一个有效的数据包ID
def set_tail_to_next_valid_pid():
        print("执行了set_tail_to_next_valid_pid函数 寻找下一个有效的数据包ID")
        # Moving the pc_log_tail to the first next valid pid
        # 将 pc_log_tail 移动到下一个有效的PID位置
        global pc_log_tail
        found_flag = 0

        print("pc_log_tail:");print(pc_log_tail)
        print("round(pc_log_tail*2.5):");print(round(pc_log_tail*2.5))
        print("int(round(pc_log_tail*2.5)+1):");print(int(round(pc_log_tail*2.5)+1))

        for i in range (int(round((pc_log_tail*2.5))+1), pc_sz):
                if ((PID[i] % 0.4 == 0) and PID[i] > 0):
                        found_index = i
                        found_flag = 1
                        break
        if found_flag == 0:
                for i in range (0,int(round(pc_log_tail*2.5))):
                        if ((PID[i] % 0.4 == 0) and PID[i] > 0):
                                found_index = i
                                found_flag = 1
                                break
        if found_flag == 1:
                # Should be divided by 2.5, as in the first place we multiplied that by 2.5
                # 应该 除以2.5 因为刚才我们乘以了 2.5
                pc_log_tail = round((found_index / 2.5),1) 
        else:
                pc_log_tail = round(pc_log_head,1)

# adds new writes to persistent cache
# 向持久缓存中添加新的写请求
def add_io_to_pc(address,lengths):
        print("执行了 add_io_to_pc 函数 向持久缓存中添加新的写请求 ")
        global band_pid_blck
        global pid_add
        global pc_log_tail
        pid_couner = 0;
        item_to_del_found_flag = 0
        nr_d_p=1; # number of data packets 数据包数
        nr_t=1; # extent map 映射范围？
        trks_req=(nr_d_p*0.4)
        new_pid=get_new_PID(trks_req,1)
        # breaking down write extents into 4K blocks
        # 将写入的数据 分解为 4K 块的大小
        # +1 数组的范围到变量本身结束
        for add in range (address,address+lengths+1,4096):   
                find_band_number(add)
                bnd = band_info[0]
                bnd = int(bnd)
                # print("band_info[0]:");print(band_info[0])
                # print("band:");print(bnd)
                if len(band_pid_blck[bnd]) > 0:
                        if(add < first_add_written_in_band[bnd]):
                                first_add_written_in_band[bnd]=add
                        # check band_pid_blck[bnd] to see if it has the address or not?
                        # 检查 band_pid_blck[bnd] 中 是否存在地址？
                        found_item_index = -1
                        index_counter = -1
                        pid_counter = 0
                        for item in band_pid_blck[bnd]:
                                index_counter += 1
                                if (item[1] == add):
                                        found_item_index = index_counter
                                        # the pid associated with the target address 
                                        # 和目标地址 向关联的PID
                                        pid = item[0] 
                                        pid_add[int(round(pid*2.5))].remove(add)
                                        del band_pid_blck[bnd][found_item_index]
                                        pid_counter = 1
                                        break
                        # check if pid only occures once or not in case the address was found
                        # 检查 PID 是否只 出现过一次，来防止地址被找到过
                        if found_item_index > -1:
                                for item in band_pid_blck[bnd]:
                                        if (item[0] == pid ):
                                                pid_counter += 1
                                                if pid_counter > 1:
                                                        break
                        # if there is no more address associated with the target pid, we need to remove the pid 
                        # 如果没有更多地址 与 目标 pid 相关联，我们需要删除 pid
                        if pid_counter == 1:
                                # remove PID[pid] by setting the content to -1
                                # 通过将内容 设置为-1 来清除 PID
                                PID[int(round(pid*2.5,1))]=-1 
                                if(round(pid,1)==round(pc_log_tail,1)):
                                        # 寻找下一个有效的数据包 PID
                                        set_tail_to_next_valid_pid()
                else:
                        first_add_written_in_band[bnd] = add
                if add not in blks_in_pc[bnd]:
                        blks_in_pc[bnd].append(add)
                pid_add[int(round(new_pid*2.5))].append(add)
                band_pid_blck[bnd].append([round(new_pid,1),add])

# adds 300 ms extra latency after every 240 write operations
# 每 240 次写入操作后增加 300 毫秒的额外延迟
def  journal_update():
        print("执行了 journal_update 函数 每 240 次写入操作后增加 300 毫秒的额外延迟 ")
        global journal_delay
        global writes_since_prev_journaling
        journal_delay = 300
        writes_since_prev_journaling=0;

def reset_latencies():
        print("执行了 reset_latencies 函数")
        global seek_time_w, rot_lat_w, transfer_lat_w, total_lat_w, seek_time_r, rot_lat_r, transfer_lat_r, total_lat_r
        seek_time_w=0;
        rot_lat_w=0;
        transfer_lat_w=0;
        total_lat_w=0;
        seek_time_r=0;
        rot_lat_r=0;
        transfer_lat_r=0;
        total_lat_r=0;

# cleans 2 bands
def clean_pc():
        print("执行了 clean_pc 函数")
        global cleaned_band_in_recent_cleaning  # 全局变量 清理最近的一次band带 、set集合参数
        global band_read_delay                  # 带读取延迟
        global packets_collected                # 收集数据包
        global w_into_pc_delay                  # 向PC写的延迟
        global wb_to_band_delay                 # 写回磁道带 的延迟 wb  write back
        global cleaning_delay                   # 清理延迟
        global pck_coll_delay                   # delay of reading updates(writes) of the band currently being cleaned 清理过程时的 读写延迟 
        global in_the_middle_of_cleaning        # flag to check if the cleaning process is in run 一个用于检测是都处于清理过程中的 标志位
        global pc_log_head                      # PC日志头
        global pc_log_tail                      # PC日志尾

        sz_of_involved_tracks = [-1 for i in range (0,300000)] # 8TiB / 30MiB = 279621 = 300000, Drivesz/Bandsz
        s_p = [-1 for i in range(3)]
        f_p = [-1 for i in range(3)]
        global cache_under_pressure
        # one band is cleaned per iteration 迭代清理每一个磁道带
        for i in range (1, 3):
                if len(pid_add[int(round(pc_log_tail*2.5))]) == 0:
                        sys.exit("nothing to clean")
                else:
                        # in case a sinmgle packet's consecutive blocks belonged to different consequent bands 
                        # 如果单个数据包的连续块 属于不同的后续磁道带
                        min_add = min(pid_add[int(round(pc_log_tail*2.5))]) 
                        find_band_number(min_add)
                        bnd=band_info[0]

                cleaned_band_in_recent_cleaning[i]=bnd;

                calc_track_number(first_add_written_in_band[bnd]);
                first_written_track=track_info[0];
                bnd_pc_seek_time=estimate_seek_time(first_written_track,0);

                calc_track_number(band_info[2]);
                track_num_of_last_track_in_band=track_info[0];
                # drive reads from the first written track to the end of band
                # 从第一个写入的磁道读取到带的末尾
                nr_of_tracks_to_be_read_from_band = track_num_of_last_track_in_band-first_written_track;
                sz_of_involved_tracks[bnd]=track_sz_in_zone[zone_info];
                # the volume of data being read from band 
                # 从一个 band 读取的数据量
                data_to_be_read_from_band=nr_of_tracks_to_be_read_from_band*sz_of_involved_tracks[bnd]; 
                # the ratio of track size in persistent cache to the one in target band
                # 持久缓存中磁道的大小 与 目标带中磁道大小 的 比率
                pc_to_bnd_track_sz_ratio=float(sz_of_involved_tracks[bnd])/pc_track_sz
                # calculating the number of phases and specifying the tracks to be cleaned in each phase based on a number criteria 
                # including the size of cache dedicate in DRAM for this purpose
                # 计算每个阶段的数量，并根据标准指定每个阶段要清理的磁道 包括在这个设计过程中所用的DRAM缓存大小
                if(data_to_be_read_from_band > merge_cache_sz): 
                        if(data_to_be_read_from_band <= 2*merge_cache_sz):
                                nr_of_phases_for_this_band=2;
                                tracks_for_first_phase=int(merge_cache_sz/sz_of_involved_tracks[bnd]);
                                tracks_for_second_phase=nr_of_tracks_to_be_read_from_band-tracks_for_first_phase;
                                tracks_for_third_phase=0;
                                if(avail_space_in_cur_pc_wb_band < tracks_for_first_phase*sz_of_involved_tracks[bnd]):
                                        avail_space_for_first_phase=avail_space_in_cur_pc_wb_band;
                                        avail_space_for_second_phase=tracks_for_second_phase*sz_of_involved_tracks[bnd];
                                elif(avail_space_in_cur_pc_wb_band < nr_of_tracks_to_be_read_from_band*sz_of_involved_tracks[bnd]):
                                        avail_space_for_first_phase=tracks_for_first_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_second_phase=avail_space_in_cur_pc_wb_band-avail_space_for_first_phase;
                                else:
                                        avail_space_for_first_phase=tracks_for_first_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_second_phase=tracks_for_second_phase*sz_of_involved_tracks[bnd];
                                avail_space_for_third_phase=0
                        else:
                                nr_of_phases_for_this_band=3;
                                tracks_for_first_phase=int(merge_cache_sz/sz_of_involved_tracks[bnd]);
                                tracks_for_second_phase=int(merge_cache_sz/sz_of_involved_tracks[bnd]);
                                tracks_for_third_phase=nr_of_tracks_to_be_read_from_band-tracks_for_first_phase-tracks_for_second_phase;
                                if(avail_space_in_cur_pc_wb_band < tracks_for_first_phase*sz_of_involved_tracks[bnd]):
                                        avail_space_for_first_phase=avail_space_in_cur_pc_wb_band;
                                        avail_space_for_second_phase=tracks_for_second_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_third_phase=tracks_for_third_phase*sz_of_involved_tracks[bnd];
                                elif(avail_space_in_cur_pc_wb_band < (tracks_for_first_phase+tracks_for_second_phase)*sz_of_involved_tracks[bnd]):
                                        avail_space_for_first_phase=tracks_for_first_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_second_phase=avail_space_in_cur_pc_wb_band-avail_space_for_first_phase;
                                        avail_space_for_third_phase=tracks_for_third_phase*sz_of_involved_tracks[bnd];
                                elif(avail_space_in_cur_pc_wb_band < nr_of_tracks_to_be_read_from_band*sz_of_involved_tracks[bnd]):
                                        avail_space_for_first_phase=tracks_for_first_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_second_phase=tracks_for_second_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_third_phase=avail_space_in_cur_pc_wb_band-avail_space_for_first_phase-avail_space_for_second_phase;
                                else:
                                        avail_space_for_first_phase=tracks_for_first_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_second_phase=tracks_for_second_phase*sz_of_involved_tracks[bnd];
                                        avail_space_for_third_phase=tracks_for_third_phase*sz_of_involved_tracks[bnd];
                else:
                        nr_of_phases_for_this_band=1;
                        tracks_for_first_phase=nr_of_tracks_to_be_read_from_band;
                        tracks_for_second_phase=0;
                        tracks_for_third_phase=0;
                        if(avail_space_in_cur_pc_wb_band < tracks_for_first_phase*sz_of_involved_tracks[bnd]):
                                 avail_space_for_first_phase=avail_space_in_cur_pc_wb_band
                                 avail_space_for_second_phase=0
                                 avail_space_for_third_phase=0
                        else:
                                 avail_space_for_first_phase=tracks_for_first_phase*sz_of_involved_tracks[bnd]
                                 avail_space_for_second_phase = 0
                                 avail_space_for_third_phase = 0
                get_new_PID(int((tracks_for_first_phase+tracks_for_second_phase+tracks_for_third_phase)*pc_to_bnd_track_sz_ratio),0);
                # calculating the latency for reading band in each phase
                # 计算每个阶段读取带的延迟
                band_read_delay[bnd,1]=tracks_for_first_phase*full_rot_lat+(2*bnd_pc_seek_time);
                if(nr_of_phases_for_this_band>=2):
                        band_read_delay[bnd,2]=tracks_for_second_phase*full_rot_lat+(2*bnd_pc_seek_time);
                        if(nr_of_phases_for_this_band==3):
                                band_read_delay[bnd,3]=tracks_for_third_phase*full_rot_lat+(2*bnd_pc_seek_time);

                pc_log_head = round(pc_log_head,1)
                pc_log_tail = round(pc_log_tail,1)
                # s_p, f_p: start point and finish point
                # calculating the number of rounds(rnd) used in the next for loop 计算下一个for 循环中使用的轮数
                if(pc_log_tail < pc_log_head):
                        s_p[1]=pc_log_tail
                        f_p[1]=pc_log_head
                        rnd=1
                else:
                        s_p[1]=pc_log_tail
                        f_p[1]=round(pc_map_sz1*1.5*0.4-0.4,1)
                        s_p[2]=0
                        f_p[2]=pc_log_head
                        rnd=2
                for r in range(1,rnd+1):
                        pid = s_p[r]
                        while (pid <= f_p[r]):
                                item_to_del = []
                                index_counter = -1
                                item_to_del_found_flag = 0
                                pck_coll_delay_set=0
                                pc_block_to_del = []    # stores elemetns that need to be removed from pc_block 存放需要从pc_block中删除的元素
                                pid_add_to_del = []     # stores elements that need to be removed from pid_add 存放需要从pid_add中移除的元素
                                if len(band_pid_blck[bnd]) == 0:
                                        break
                                pid_rounded = round(pid,1)
                                mx_add = 0
                                for element in band_pid_blck[bnd]:
                                        if (element[0] == pid_rounded):
                                                if element[1] > mx_add:
                                                        mx_add = element[1]

                                # sets packet collection delays for different phases
                                # 设置不同阶段的数据包 接收延迟
                                for item in band_pid_blck[bnd]:
                                        index_counter += 1
                                        if (item[0] == pid_rounded):
                                                pid_add[int(round(pid*2.5))].remove(item[1])
                                                blks_in_pc[bnd].remove(item[1])
                                                item_to_del_found_flag += 1; # c
                                                item_to_del.append(index_counter)
                                                if(pck_coll_delay_set==0):
                                                        calc_track_number(mx_add)
                                                        if((track_info[0]-first_written_track)*sz_of_involved_tracks[bnd]<=avail_space_for_first_phase):
                                                                if (bnd,1,1) not in pck_coll_delay:
                                                                        pck_coll_delay[bnd,1,1]=0
                                                                pck_coll_delay[bnd,1,1]+=(0.2*full_rot_lat)
                                                                invovled_in_phase=1
                                                        elif (track_info[0]-first_written_track<=tracks_for_first_phase):
                                                                if (bnd,1,2) not in pck_coll_delay:
                                                                        pck_coll_delay[bnd,1,2]=0
                                                                pck_coll_delay[bnd,1,2]+=(0.2*full_rot_lat)
                                                                invovled_in_phase=1
                                                        elif ((track_info[0]-first_written_track-tracks_for_first_phase)*sz_of_involved_tracks[bnd]<=avail_space_for_second_phase):
                                                                if (bnd,2,1) not in pck_coll_delay:
                                                                        pck_coll_delay[bnd,2,1]=0
                                                                pck_coll_delay[bnd,2,1]+=(0.2*full_rot_lat)
                                                                invovled_in_phase=2
                                                        elif (track_info[0]-first_written_track<=tracks_for_first_phase+tracks_for_second_phase):
                                                                if (bnd,2,2) not in pck_coll_delay:
                                                                        pck_coll_delay[bnd,2,2]=0
                                                                pck_coll_delay[bnd,2,2]+=(0.2*full_rot_lat)
                                                                invovled_in_phase=2
                                                        elif ((track_info[0]-first_written_track-tracks_for_first_phase-tracks_for_second_phase)*sz_of_involved_tracks[bnd]<=avail_space_for_third_phase):
                                                                if (bnd,3,1) not in pck_coll_delay:
                                                                          pck_coll_delay[bnd,3,1]=0
                                                                pck_coll_delay[bnd,3,1]+=(0.2*full_rot_lat)
                                                                invovled_in_phase=3
                                                        else:
                                                                if (bnd,3,2) not in pck_coll_delay:
                                                                        pck_coll_delay[bnd,3,2]=0
                                                                pck_coll_delay[bnd,3,2]+=(0.2*full_rot_lat)
                                                                invovled_in_phase=3
                                                        pck_coll_delay_set=1
                                                        # The value does not matter as we just care about the key
                                                        # 值不是所关心的 只关注key
                                                packets_collected[bnd,invovled_in_phase,item[1]]= 1 
                                # removing the pc_blocks[bnd][add]
                                # removing band_pid_blck[bnd][pid][add] and pid_add[pid][add]
                                for i in range (len(item_to_del)-1,-1,-1):
                                        del band_pid_blck[bnd][item_to_del[i]]
                                        if i == 0: # We are working on the last item 正在处理最后一项
                                                if(round(pid,1)==round(pc_log_tail,1)):
                                                        set_tail_to_next_valid_pid()
                                                PID[int(round((pid*2.5),1))] = -1 #remove PID[pid[ by settin the content to -1                        
                                                if (find_array_length(PID) < pc_map_sz1):
                                                        cache_under_pressure=0
                                if len(band_pid_blck[bnd]) == 0:
                                        del first_add_written_in_band[bnd]
                                pid += 0.4
                if (bnd,1,1) not in pck_coll_delay:
                        pck_coll_delay[bnd,1,1]=0
                if (bnd,1,2) not in pck_coll_delay:
                        pck_coll_delay[bnd,1,2]=0
                if (bnd,2,1) not in pck_coll_delay:
                        pck_coll_delay[bnd,2,1]=0
                if (bnd,2,2) not in pck_coll_delay:
                        pck_coll_delay[bnd,2,2]=0
                if (bnd,3,1) not in pck_coll_delay:
                        pck_coll_delay[bnd,3,1]=0
                if (bnd,3,2) not in pck_coll_delay:
                        pck_coll_delay[bnd,3,2]=0
                if (bnd,1,1) not in w_into_pc_delay:
                        w_into_pc_delay[bnd,1,1]=0
                if (bnd,1,2) not in w_into_pc_delay:
                        w_into_pc_delay[bnd,1,2]=0
                if (bnd,2,1) not in w_into_pc_delay:
                        w_into_pc_delay[bnd,2,1]=0
                if (bnd,2,2) not in w_into_pc_delay:
                        w_into_pc_delay[bnd,2,2]=0
                if (bnd,3,1) not in w_into_pc_delay:
                        w_into_pc_delay[bnd,3,1]=0
                if (bnd,3,2) not in w_into_pc_delay:
                        w_into_pc_delay[bnd,3,2]=0
                # setting the latency for writing merged data into persistent cache before writing it back to data bands
                # checking if available space in write back log is enough for this pupose in each phase -- the operation is split into two sub-phases otherwise
                # 设置 在将合并的数据写回数据带之前 将合并的数据写入持久缓存 的延迟
                # 在每个阶段 检查 回写日志中的可用空间是否 满足此目的，否则将操作分为两个子阶段
                if(avail_space_for_first_phase != tracks_for_first_phase*sz_of_involved_tracks[bnd]):
                        w_into_pc_delay[bnd,1,1]=(avail_space_for_first_phase/float(pc_track_sz))*full_rot_lat;
                        w_into_pc_delay[bnd,1,2]=((tracks_for_first_phase*sz_of_involved_tracks[bnd]-avail_space_for_first_phase)/float(pc_track_sz))*full_rot_lat;
                else:
                        w_into_pc_delay[bnd,1,1]=(avail_space_for_first_phase/float(pc_track_sz))*full_rot_lat;
                        w_into_pc_delay[bnd,1,2]=0;
                wb_to_band_delay[bnd,1]=(tracks_for_first_phase-int(nr_of_phases_for_this_band/2))*full_rot_lat+(2*bnd_pc_seek_time);
                cleaning_delay[bnd,1]=band_read_delay[bnd,1]+pck_coll_delay[bnd,1,1]+pck_coll_delay[bnd,1,2]+w_into_pc_delay[bnd,1,1]+w_into_pc_delay[bnd,1,2]+wb_to_band_delay[bnd,1];
                if(nr_of_phases_for_this_band>=2):
                        if(avail_space_for_second_phase != tracks_for_second_phase*sz_of_involved_tracks[bnd]):
                                w_into_pc_delay[bnd,2,1]=(avail_space_for_second_phase/float(pc_track_sz))*full_rot_lat;
                                w_into_pc_delay[bnd,2,2]=((tracks_for_second_phase*sz_of_involved_tracks[bnd]-avail_space_for_second_phase)/float(pc_track_sz))*full_rot_lat;
                        else:
                                w_into_pc_delay[bnd,2,1]=(tracks_for_second_phase/pc_to_bnd_track_sz_ratio)*full_rot_lat;
                                w_into_pc_delay[bnd,2,2]=0;
                        wb_to_band_delay[bnd,2]=(tracks_for_second_phase-int(nr_of_phases_for_this_band/3))*full_rot_lat+(2*bnd_pc_seek_time);
                        cleaning_delay[bnd,2]=band_read_delay[bnd,2]+pck_coll_delay[bnd,2,1]+pck_coll_delay[bnd,2,2]+w_into_pc_delay[bnd,2,1]+w_into_pc_delay[bnd,2,2]+wb_to_band_delay[bnd,2];
                        if(nr_of_phases_for_this_band==3):
                                if(avail_space_for_third_phase != tracks_for_third_phase*sz_of_involved_tracks[bnd]):
                                        w_into_pc_delay[bnd,3,1] = (avail_space_for_third_phase/float(pc_track_sz))*full_rot_lat;
                                        w_into_pc_delay[bnd,3,2] = ((tracks_for_third_phase*sz_of_involved_tracks[bnd]-avail_space_for_third_phase)/float(pc_track_sz))*full_rot_lat;
                                else:
                                        w_into_pc_delay[bnd,3,1]=(tracks_for_third_phase/pc_to_bnd_track_sz_ratio)*full_rot_lat;
                                        w_into_pc_delay[bnd,3,2]=0;
                                wb_to_band_delay[bnd,3]=tracks_for_third_phase*full_rot_lat+(2*bnd_pc_seek_time);
                                cleaning_delay[bnd,3]=band_read_delay[bnd,3]+pck_coll_delay[bnd,3,1]+pck_coll_delay[bnd,3,2]+w_into_pc_delay[bnd,3,1]+w_into_pc_delay[bnd,3,2]+wb_to_band_delay[bnd,3];
        in_the_middle_of_cleaning=1;

# distibutes cleaning latencies among IOs being served in the middle of cleaning
# 在清理过程中 对被服务的IO请求  进行分配清理延迟
def get_cleaning_delays(rw,rw_addr):
        print("执行了 get_cleaning_delays 函数 ")
        global reads_served_from_pc
        global additional_cleaning_delay # 额外的清理延迟
        global max_reads_from_pc        # 从PC的最大读取数
        global in_the_meddle_of_cleaning   
        delay_set=0;
        rw_trk=calc_track_number(rw_addr);
        # assigns the band's entire cleaning delay to additional_cleaning_delay i.e.
        # IOs need to wait for a band's clenaing to get done before getting served if cache is under pressure. 
        # 将 band区 的整个清理延迟分配给 additional_cleaning_delay
        # 即如果缓存空间压力较大，IO 需要等待带区的清理完成 才能获得服务
        if(cache_under_pressure==1):
                for key in cleaning_delay:
                        additional_cleaning_delay+=cleaning_delay[key];
                        band_read_delay[key]=0
                        for key2 in w_into_pc_delay:
                                if key2[0]== key[0] and key2[1] == key[1]:
                                        pck_coll_delay[key2]=0
                                        w_into_pc_delay[key2]=0
                        wb_to_band_delay[key]=0;

                cleaning_delay.clear();
                cleaned_band_in_recent_cleaning.clear();
                packets_collected.clear();
                in_the_middle_of_cleaning=0;
                delay_set=1;
        else: # otherwise, each IO gets affected by only the portion of cleaning process in which it gets served
              # 否则，每个 IO 只会受到它所服务的清理过程部分 的影响
                for b in range (1,3):
                        if (b in cleaned_band_in_recent_cleaning):
                                bnds=cleaned_band_in_recent_cleaning[b];
                                cleaning_of_band=b;
                                break;

                nr_of_cleaning_phases = 0
                for key in cleaning_delay:
                        if key[0] == bnds:
                                nr_of_cleaning_phases += 1

                for j in range (1, nr_of_cleaning_phases+1):
                        if(cleaning_delay[bnds,j] >0):
                                rw_addr_found_flag = 0
                                for key in packets_collected:
                                        if key[0] == bnds and key[1] == j and key[2] == rw_addr:
                                                rw_addr_found_flag = 1
                                                break
                                if (band_read_delay[bnds,j] != 0):
                                        additional_cleaning_delay=band_read_delay[bnds,j];
                                        if(pck_coll_delay[bnds,j,1]!=0 or pck_coll_delay[bnds,j,2]!=0):
                                                max_reads_from_pc[1]=int(band_read_delay[bnds,j]*(pck_coll_delay[bnds,j,1]/(pck_coll_delay[bnds,j,1]+pck_coll_delay[bnds,j,2])));
                                                max_reads_from_pc[2]= int(band_read_delay[bnds,j]-max_reads_from_pc[1]);
                                        cleaning_delay[bnds,j]-=band_read_delay[bnds,j];
                                        band_read_delay[bnds,j]=0;
                                        delay_set=1;
                                        break;
                                # reads in the middle of packet collection phase see no additional delays if they are for the same blocks being cleaned 
                                # 如果 数据包收集阶段中间的读取是 针对正在清理的相同块 则不会计算额外的延迟
                                elif (pck_coll_delay[bnds,j,1] != 0):
                                        if(rw==0 and  rw_addr_found_flag == 1 and max_reads_from_pc[1] >0):
                                                additional_cleaning_delay=0;
                                                reads_served_from_pc += 1;
                                                if(reads_served_from_pc==max_reads_from_pc[1]):
                                                        pck_coll_delay[bnds,j,1]=0;
                                                        cleaning_delay[bnds,j]-=pck_coll_delay[bnds,j,1];
                                                        reads_served_from_pc=0;
                                                delay_set=1;
                                                break;
                                        else:
                                                if(max_reads_from_pc[1]>0):
                                                        additional_cleaning_delay=(1-(reads_served_from_pc/max_reads_from_pc[1]))*pck_coll_delay[bnds,j,1];
                                                cleaning_delay[bnds,j]-=pck_coll_delay[bnds,j,1];
                                                pck_coll_delay[bnds,j,1]=0;
                                                reads_served_from_pc=0;
                                                delay_set=1;
                                                break;
                                elif (w_into_pc_delay[bnds,j,1] != 0):
                                        additional_cleaning_delay=w_into_pc_delay[bnds,j,1];
                                        cleaning_delay[bnds,j]-=w_into_pc_delay[bnds,j,1];
                                        w_into_pc_delay[bnds,j,1]=0;
                                        delay_set=1;
                                        break;
                                elif (pck_coll_delay[bnds,j,2] != 0):
                                        if(rw==0 and rw_addr_found_flag == 1 and max_reads_from_pc[2]>0 ):
                                                additional_cleaning_delay=0;
                                                reads_served_from_pc += 1
                                                if(reads_served_from_pc==max_reads_from_pc[2]):
                                                        pck_coll_delay[bnds,j,2]=0;
                                                        cleaning_delay[bnds,j] -= pck_coll_delay[bnds,j,2];
                                                        reads_served_from_pc=0;
                                                delay_set=1;
                                                break;
                                        else:
                                                if(max_reads_from_pc[2] > 0):
                                                        additional_cleaning_delay=(1-(reads_served_from_pc/max_reads_from_pc[2]))*pck_coll_delay[bnds,j,2];
                                                cleaning_delay[bnds,j]-=pck_coll_delay[bnds,j,2];
                                                pck_coll_delay[bnds,j,2]=0;
                                                reads_served_from_pc=0;
                                                delay_set=1;
                                                break;
                                elif (w_into_pc_delay[bnds,j,2] !=0):
                                        additional_cleaning_delay=w_into_pc_delay[bnds,j,2];

                                        cleaning_delay[bnds,j]-=w_into_pc_delay[bnds,j,2];
                                        w_into_pc_delay[bnds,j,2]=0;
                                        delay_set=1;
                                        break;
                                elif (wb_to_band_delay[bnds,j] !=0):
                                        additional_cleaning_delay=wb_to_band_delay[bnds,j];
                                        cleaning_delay[bnds,j]=0;
                                        wb_to_band_delay[bnds,j]=0;
                                        to_del_cleaning_delay = []
                                        to_del_packets_collected = []
                                        if(j==nr_of_cleaning_phases):
                                                for key in cleaning_delay: # delete cleaning_delay[bnds];
                                                        if key[0] == bnds:
                                                                to_del_cleaning_delay.append(key)
                                                for element in to_del_cleaning_delay:
                                                        del cleaning_delay[element]
                                                for key in packets_collected:
                                                        if key[0] == bnds:
                                                                # delete packets_collected[bnds];
                                                                del packets_collected[key] 
                                                        break
                                                if(len(cleaned_band_in_recent_cleaning)==1):
                                                        in_the_middle_of_cleaning=0;
                                                del cleaned_band_in_recent_cleaning[cleaning_of_band];
                                        delay_set=1;
                                        break;
                                else:
                                        sys.exit("Cleaning Delay Inconsistency");

if __name__ == '__main__':
        sys.stdout = Logger("Defalust.log")
        print("-------------------开 始 执 行 MAIN 函 数-------------------")
        device_sz = 5000980856832;  # 5TB
        rpm = 5980;                 # 转速
        max_io_sz = 524288;         # 一次最大为512KB == 0.5MB
        merge_cache_sz = 14680064;  # DRAM space dedicated for data reading during cleaning 在数据清理过程中 专用缓存空间

        cur_time = 0;              # 当前时间
        journal_update_period = 240;   # 日志更新的时间间隔 某个阈值
        seek_time_w=0; rot_lat_w = 0; transfer_lat_w=0; total_lat_w=0; # 写寻道时间、旋转延迟时间、写传输时间、写入总延迟时间
        seek_time_r=0; rot_lat_r = 0; transfer_lat_r=0; total_lat_r=0; # 读寻道时间、旋转延迟时间、读传输时间、读总的延迟时间
        writes_since_prev_journaling = 0;   # 自上一次日志写（每次更新重新计数）
        total_writes=0;       # 总写入

        od_track_sz = 1900544; # track size at outer diameter 1.8125 MiB 外径单个磁道大小 
        id_track_sz = 987136;  # track size at inner diameter 0.941 MiB 内径磁道大小
        od_band_sz = 36*(2**20);   # band size at outer diameter 外径 band 的尺寸大小 36MB
        id_band_sz = 18*(2**20);   # band size at inner diameter 18MB

        pc_track_sz = od_track_sz # 持久缓存 一个磁道大小（persistent cache == PC）
        pc_band_sz = od_band_sz   # 持久缓存的 band大小

        zone_sz_diff=4096   # the track size diff 区域之间的大小差异 4 KB

        pc_log_tail = 0     # 持久缓存的日志尾
        pc_log_head = 0     # PC的日志头
        pc_wb_log_head = 0  # log head for write backs in persistent cache 在持久缓存中回写的 日志头
        journal_delay = 0     # adds journaling delay of ~300ms after every 240 writes 每240次写入后 增加 300ms 的日志延迟
        in_the_middle_of_cleaning = 0; # flag to check if the cleaning process is in run 一个用于检查清理过程中是否存在运行的 标志位

        pc_map_sz1 = 22986 # mapping table size "number of entries that triggers cleaning" # 映射表的大小 触发清理的条目数
        pc_map_sz2 = 23000 # real mapping table size # 真实映射表大小
        pc_sz = int(pc_map_sz1 * 1.5) # persistent cache size with 50% of OP based on our observations 持久缓存设置为OP的50% 

        PID  = [-1 for j in range (0,pc_sz)] # persistent cache log 持久缓存的日志表 大小根据 pc_sz 大小进行初始化 为 一维数据表
        first_add_written_in_band = {}   # 向band中的首次写

        # a list of lists. each row is dedicated to a band. each column of a row stores an address belongs to that band
        # 二位列表 每一行对应一个带 每一行的列中存储band 的地址
        blks_in_pc= [[0 for i in range (0)] for j in range(300000)] 
        # a list of lists. each row is dedicated to a pid. each column of a row stores an address belongs to that pid
        # 每一行 对应PID列表  每一行上的列 存储对应PID的地址
        pid_add = [[0 for i in range (0)] for j in range(pc_sz)] 
        # a list of lists. each row is dedicated to a fixed band number. each column of a row stores a pair of (pid, address) belongs to that band.
        # 每一行 band号  每一行的列 存储键值对（PID，Address）
        band_pid_blck = [[0 for i in range (0)] for j in range(300000)] 

        cleaning_delay = collections.OrderedDict() # total delay per band cleaning 每个带清理的总延迟
        band_read_delay = {} # delay of reading a band's data  读取每个带 的延迟
        pck_coll_delay = {} # delay of reading updates(writes) of the band currently being cleaned 清理过程时的 读写延迟 
        w_into_pc_delay = {} # delaly of writing the merged data from band and pc into pc  从pc 向pc中 合并写数据时的延迟
        wb_to_band_delay = {} # delay of writing back band's updated data to its original place 更新band数据 写回原始位置的延迟

        cleaned_band_in_recent_cleaning = {}  # 最近的一次清理磁道带
        packets_collected = {}  

        # reads served from pc while the same band is being cleaned and the cleaning is in packet collection phase
        # 在清理同一条数据带 且清理处于数据包收集阶段时 的PC读取服务
        reads_served_from_pc = 0; 
        max_reads_from_pc = [-1 for i in range (0,3)] # max servable reads from persistent cache 来自持久缓存的最大读取服务

        cur_track=1  
        cur_time=0
        half_rot_lat=60000/float(rpm)/2;
        full_rot_lat=60000/float(rpm)

        # used in rotational latency estimations
        # 用于旋转延迟估计
        r_pid, prev_r_pid, prev_r_chunck, cur_off, cur_add=0, 0, 0, 0, 0


        initialize_seek_time_map();     # 初始化映射 寻找时间
        initialize_zones_bands_and_tracks(); # 初始换 bands  tracks

        # the space avialble in pc's current band dedicated to writing of merged data before write back to band
        # 当前band中 专用于在 写回band之前写入合并数据的空间  od_band_sz
        avail_space_in_cur_pc_wb_band = od_band_sz; # od_band_sz=36*(2**20);   # band size at outer diameter 外径band的尺寸大小 36MB

        Address = set()  # 设置一个地址 的集合

        in_file = open(sys.argv[1], "r")
        print(in_file)
        out_file = open ("output.log", "w")
        in_file_content = in_file.readlines()
        print("in_file_content输入文件内容:")
        print(in_file_content)
        
        #################### Main loop ######################
        for line in in_file_content:
                line_splitted = line.split(",");print(line_splitted)
                if (writes_since_prev_journaling%journal_update_period==0):  # 需要日志更新的临界值
                        print("开始调用journal_update！");
                        journal_update()
                if (line_splitted[1]=="Read"):
                        print("执行Read部分")
                        print("line_splitted[2、3]:");print(line_splitted[2],line_splitted[3])
                        # breaks down the io extent in case of being greater than 512K
                        # 大于 512K 的情况下 来分解IO的的范围
                        if (int(line_splitted[3])>max_io_sz):
                                for i in range(int(line_splitted[2]), int(line_splitted[2])+int(line_splitted[3])+1-max_io_sz, max_io_sz):
                                        Address.add((i, max_io_sz))
                                        if (i+max_io_sz+max_io_sz+0 > int(line_splitted[2])+int(line_splitted[3])):
                                                Address.add(i+max_io_sz,int(line_splitted[2])+int(line_splitted[3])-(i+max_io_sz))         
                                                break;
                        else:
                                Address.add((int(line_splitted[2]),int(line_splitted[3])))
                        add_list = []
                        for add_item in Address:
                                a = add_item[0]
                                additional_cleaning_delay=0
                                additional_journal_delay=0
                                if add_item[0] not in add_list:
                                        add_list.append(add_item[0])
                                        for add_item2 in Address:
                                                l = add_item2[1]
                                                if add_item2[0] == a:
                                                        r_chunck=-1
                                                        prev_r_chunck=-1;
                                                        for addr in range(a+0, a+l+0+1, 4096):
                                                                r_chunck=a;
                                                                find_band_number(addr)
                                                                # print("band_info[0]:");print(band_info)
                                                                bnd=int(band_info[0])
                                                                # print("bnd:");print(bnd)
                                                                found_band_addr_flag2=0
                                                                if addr in blks_in_pc[bnd]:
                                                                        calc_track_number(0)
                                                                        track_to_seek_r=track_info[0]
                                                                        for pid_add_pair in band_pid_blck[bnd]:
                                                                                if pid_add_pair[1] == addr:
                                                                                        r_pid=pid_add_pair[0]+0;
                                                                                        break;
                                                                        cur_add=0;
                                                                        cur_off=r_pid%1;
                                                                        found_band_addr_flag2 = 1
                                                                if found_band_addr_flag2==0:
                                                                        calc_track_number(addr);
                                                                        track_to_seek_r=track_info[0];
                                                                        cur_add=addr;
                                                                        cur_off=int((addr-track_info[1])/4096)/float(track_info[2]-track_info[1]);      
                                                                if (abs(cur_track-track_to_seek_r)>0):
                                                                        seek_time_r+=estimate_seek_time(cur_track,track_to_seek_r);
                                                                else:
                                                                        seek_time_r=0;
                                                                rot_lat_r+=estimate_rot_lat(cur_track,track_to_seek_r,cur_add,addr,cur_off);
                                                                prev_r_pid=r_pid;
                                                                prev_r_chunck=r_chunck;
                                                                cur_track=track_to_seek_r;
                                                                transfer_lat_r+=60000/float(rpm)*(4096/float(track_info[2]-track_info[1]));
                                                        if(in_the_middle_of_cleaning==1):
                                                                get_cleaning_delays(0,a);
                        del add_list
                        total_lat_r=seek_time_r+transfer_lat_r+rot_lat_r+additional_cleaning_delay;
                        cur_time+=total_lat_r;
                        pid_add_cnt = 0

                        out_file.write(str(cur_time)+"\t"+str(total_lat_r)+"\n")
                        Address.clear();
                        reset_latencies();
                        if(in_the_middle_of_cleaning==0):
                                if (round(pc_log_head,1) > round(pc_log_tail,1)):
                                        if(round(pc_log_head-pc_log_tail,1) > (pc_map_sz1-1)*0.4): 
                                                clean_pc();
                                elif (round(pc_log_head,1) < round(pc_log_tail,1)):
                                        if(round(pc_log_tail-pc_log_head,1) < (pc_map_sz1-1)*0.4*0.5): 
                                                clean_pc();
                elif (line_splitted[1]=="Write"):
                        print("执行Write部分")
                        additional_cleaning_delay=0;
                        additional_journal_delay=0;
                        if(int(line_splitted[3]) % max_io_sz == 0):
                                # number of packets being written in the persistent cache in this write
                                # 在此次写入 写入持久缓存的数据包 数目
                                pkts_to_write=(int(line_splitted[3])/max_io_sz);
                        else:
                                pkts_to_write=int(int(line_splitted[3])/max_io_sz)+1;
                        last_i=0
                        if(int(line_splitted[3])>max_io_sz):
                                for i in range(int(line_splitted[2]), int(line_splitted[2])+int(line_splitted[3])+1, max_io_sz):
                                        add_io_to_pc(i,max_io_sz);
                                        if(in_the_middle_of_cleaning==1):
                                                get_cleaning_delays(1,i)
                                        if(journal_delay>0):
                                                additional_journal_delay+=journal_delay;
                                                journal_delay=0;
                                        last_i=i;
                                        transfer_lat_w+=2.4*full_rot_lat*pkts_to_write;
                                if(int(line_splitted[3])%max_io_sz!=0):
                                        add_io_to_pc(last_i+max_io_sz,l-(last_i+max_io_sz));
                                        if(in_the_middle_of_cleaning==1):
                                                get_cleaning_delays(1,last_i+max_io_sz);
                                        if(journal_delay>0):
                                                additional_journal_delay+=journal_delay;
                                                journal_delay=0;
                                        transfer_lat_w+=2.4*full_rot_lat*pkts_to_write;
                        else:
                                add_io_to_pc(int(line_splitted[2]),int(line_splitted[3]));
                                if(in_the_middle_of_cleaning==1):
                                        get_cleaning_delays(1,int(line_splitted[2]));
                                if(journal_delay>0):
                                        additional_journal_delay+=journal_delay;
                                        journal_delay=0;
                                transfer_lat_w=2.4*full_rot_lat*pkts_to_write;
                        calc_track_number(0);
                        track_to_seek_w=track_info[0];
                        if (abs(cur_track-track_to_seek_w)>0):
                                seek_time_w=estimate_seek_time(cur_track,track_to_seek_w);
                                rot_lat_w=estimate_rot_lat(cur_track,1,cur_add,0,1);
                        else:
                                seek_time_w=0;
                                rot_lat_w=0.7;
                        total_lat_w=seek_time_w+rot_lat_w+transfer_lat_w+additional_cleaning_delay+additional_journal_delay;
                        cur_time+=total_lat_w;
                        cur_add=0;
                        cur_off=0;
                        pid_add_cnt = 0
                        out_file.write(str(cur_time)+"\t"+str(total_lat_w)+"\n")
                        reset_latencies();
                        total_writes=total_writes+pkts_to_write;
                        writes_since_prev_journaling=writes_since_prev_journaling+pkts_to_write;
                        cur_track=track_to_seek_w;
#         log_print = open('Defalust.log', 'w+',encoding='utf-8')
#         sys.stdout = log_print
#         sys.stderr = log_print