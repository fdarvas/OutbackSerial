"""
Created on Sat Sep 26 14:06:26 2015

@author: Felix Darvas


This is an example of how to read data from an Outback mate controller and post to a database and a unix domain socket

"""

from OutBackSerial import inverter,MX,FlexNetDC
import serial

def init_serial(): # init serial port for reading from the mate serial port
    #print "connecting serial port..."
    ser=serial.Serial(0,19200,timeout=120)
    #print ser.portstr
    ser.setDTR(1)
    ser.setRTS(0)
    ser.flushInput()
    #print "done"
    return ser

def read_serial(ser): # read the status string
    flag=0
    while flag==0:
        byte=ser.read(1)
        if byte=='\n':
            data=ser.read(48)
            #data=data
            flag = 1
    #data=ser.readline()
    return data
    
def analyze_datastring(data): # find out which device sent the current string
    res='error'
    if len(data)==48:
        item=data.split(',')
        item=item[0]
        if item.isdigit():
            res='inverter'
        if item.isupper():
            res='MX'
        if item.islower():
            res='FlexNetDC'
    return res    

# initialize objects, e.g. inverter with 48V battery voltage

my_inverter=inverter(48,None,"/tmp/inverter_socket")
my_MX=MX(None,"/tmp/MX1_socket")
my_FlexNetDC=FlexNetDC(None,"/tmp/FlexNetDC_socket")

my_serial=init_serial()
data_str=read_serial(my_serial)
current_device=analyze_datastring(data_str)

if current_device=='MX':
    erg=my_MX.parse_data_string(data_str)
    my_MX.send_data() # write data to socket
if current_device=='inverter':
    erg=my_inverter.parse_data_string(data_str)
if erg==0:
    #print my_inverter.print_values()
    my_inverter.update_energy() # accumulate energy
    #my_inverter.send_data() # send to socket
if current_device=='FlexNetDC':
    erg=my_FlexNetDC.parse_data_string(data_str)
